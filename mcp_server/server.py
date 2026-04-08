import os
import json
from datetime import date, datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from mcp.server.fastmcp import FastMCP

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client["arabic_learning"]
    return _db


mcp = FastMCP("arabic-tutor")


@mcp.tool()
def get_pending_words() -> str:
    """Get all pending raw words from the staging collection.

    These are words added via Telegram /add command that need
    to be formatted and enriched before adding to vocabulary.
    """
    db = get_db()
    pending = list(db.raw_words.find({"status": "pending"}))
    result = []
    for doc in pending:
        result.append({
            "id": str(doc["_id"]),
            "text": doc["text"],
            "source": doc.get("source", "unknown"),
            "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def add_words(words: list[dict]) -> str:
    """Add formatted vocabulary words to the database.

    Each word dict should have:
      - arabic (required): The Arabic word
      - transliteration: Romanized pronunciation
      - translation: English meaning
      - type: "word", "grammar_rule", or "phrase"
      - root: 3-letter Arabic root (optional)
      - plural: Arabic plural form (optional)
      - example_sentence: Arabic sentence using the word (optional)

    Words are deduplicated against existing vocabulary.
    Corresponding item_progress entries are created automatically.
    Any matching pending raw_words are marked as processed.
    """
    db = get_db()

    # Validate required field
    for w in words:
        if "arabic" not in w:
            return json.dumps({"error": "Each word must have an 'arabic' field"})

    # Check for existing words
    arabic_list = [w["arabic"] for w in words]
    existing = set()
    for doc in db.vocabulary_items.find({"arabic": {"$in": arabic_list}}, {"arabic": 1}):
        existing.add(doc["arabic"])

    new_words = [w for w in words if w["arabic"] not in existing]
    skipped = [w["arabic"] for w in words if w["arabic"] in existing]

    if new_words:
        today = date.today().isoformat()
        now = datetime.now(timezone.utc)

        for word in new_words:
            word.setdefault("type", "word")
            word.setdefault("created_at", now)

        db.vocabulary_items.insert_many(new_words)

        progress_docs = [
            {
                "arabic": w["arabic"],
                "srs_level": 0,
                "next_review_at": today,
                "streak": 0,
                "last_test_type": "",
                "weak_test_types": [],
            }
            for w in new_words
        ]
        db.item_progress.insert_many(progress_docs)

    # Mark matching raw_words as processed
    db.raw_words.update_many(
        {"text": {"$regex": "|".join(arabic_list)}, "status": "pending"},
        {"$set": {"status": "processed"}},
    )

    return json.dumps({
        "added": [w["arabic"] for w in new_words],
        "skipped_duplicates": skipped,
        "added_count": len(new_words),
        "skipped_count": len(skipped),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def add_paragraphs(paragraphs: list[dict]) -> str:
    """Add reading passages to the paragraphs collection.

    Each paragraph dict should have:
      - text_arabic: The Arabic paragraph text
      - text_english: English translation
      - words_used: List of Arabic words used in the paragraph
      - difficulty: "short" or "long"
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    for p in paragraphs:
        p.setdefault("created_at", now)
        p.setdefault("difficulty", "short")

    db.paragraphs.insert_many(paragraphs)

    return json.dumps({
        "added_count": len(paragraphs),
        "difficulties": [p.get("difficulty") for p in paragraphs],
    })


@mcp.tool()
def list_recent_words(limit: int = 20) -> str:
    """List the most recently added vocabulary words."""
    db = get_db()
    words = list(
        db.vocabulary_items.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    for w in words:
        if "created_at" in w and isinstance(w["created_at"], datetime):
            w["created_at"] = w["created_at"].isoformat()
    return json.dumps(words, ensure_ascii=False, indent=2)


@mcp.tool()
def search_words(query: str) -> str:
    """Search existing vocabulary by Arabic text, translation, or root."""
    db = get_db()
    results = list(db.vocabulary_items.find(
        {"$or": [
            {"arabic": {"$regex": query, "$options": "i"}},
            {"translation": {"$regex": query, "$options": "i"}},
            {"root": {"$regex": query, "$options": "i"}},
        ]},
        {"_id": 0},
    ).limit(20))
    for w in results:
        if "created_at" in w and isinstance(w["created_at"], datetime):
            w["created_at"] = w["created_at"].isoformat()
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def get_words_without_sentences() -> str:
    """Find vocabulary words that don't have example sentences yet."""
    db = get_db()
    words = list(db.vocabulary_items.find(
        {"$or": [
            {"example_sentence": {"$exists": False}},
            {"example_sentence": ""},
            {"example_sentence": None},
        ]},
        {"_id": 0, "arabic": 1, "translation": 1, "transliteration": 1, "type": 1},
    ))
    return json.dumps(words, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
