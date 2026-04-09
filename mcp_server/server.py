import os
import json
from datetime import date, datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from mcp.server.fastmcp import FastMCP

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]

VALID_TYPES = {"noun", "verb", "adjective", "adverb", "preposition", "particle", "phrase", "grammar_rule"}
EASE_FACTOR_DEFAULT = 2.5

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client["arabic_learning"]
    return _db


def _serialize_dt(doc):
    """Convert datetime fields to ISO strings for JSON serialization."""
    for key in ("created_at", "last_reviewed_at", "processed_at", "last_shown_at"):
        if key in doc and isinstance(doc[key], datetime):
            doc[key] = doc[key].isoformat()
    return doc


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

    Each word dict must have:
      - arabic (required): The Arabic word (with tashkeel if possible)
      - transliteration: Romanized pronunciation
      - translation: English meaning
      - type: one of: noun, verb, adjective, adverb, preposition, particle, phrase, grammar_rule
      - root: Arabic root (e.g. "ك ت ب"), optional
      - plural: Arabic plural form, optional
      - gender: "masculine" or "feminine", optional
      - example_sentence: Arabic sentence using the word, optional
      - example_translation: English translation of example, optional
      - tags: list of tags (e.g. ["MSA", "beginner"]), optional

    Words are deduplicated against existing vocabulary.
    Corresponding item_progress entries are created automatically.
    Any matching pending raw_words are marked as processed.
    """
    db = get_db()

    # Validate
    errors = []
    for i, w in enumerate(words):
        if "arabic" not in w:
            errors.append(f"Word {i}: missing 'arabic' field")
        wtype = w.get("type", "noun")
        if wtype not in VALID_TYPES:
            errors.append(f"Word {i} ({w.get('arabic', '?')}): invalid type '{wtype}'. Must be one of: {', '.join(sorted(VALID_TYPES))}")
    if errors:
        return json.dumps({"errors": errors}, ensure_ascii=False, indent=2)

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
            word.setdefault("type", "noun")
            word.setdefault("created_at", now)

        db.vocabulary_items.insert_many(new_words)

        progress_docs = [
            {
                "arabic": w["arabic"],
                "srs_level": 0,
                "next_review_at": today,
                "ease_factor": EASE_FACTOR_DEFAULT,
                "streak": 0,
                "lapse_count": 0,
                "last_test_type": "",
                "weak_test_types": [],
                "test_type_stats": {},
                "last_reviewed_at": None,
                "created_at": now,
            }
            for w in new_words
        ]
        db.item_progress.insert_many(progress_docs)

    # Mark matching raw_words as processed
    if arabic_list:
        now = datetime.now(timezone.utc)
        for arabic in arabic_list:
            db.raw_words.update_many(
                {"text": {"$regex": arabic}, "status": "pending"},
                {"$set": {"status": "processed", "processed_at": now, "vocabulary_item_arabic": arabic}},
            )

    return json.dumps({
        "added": [w["arabic"] for w in new_words],
        "skipped_duplicates": skipped,
        "added_count": len(new_words),
        "skipped_count": len(skipped),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def add_passages(passages: list[dict]) -> str:
    """Add reading passages to the passages collection.

    Each passage dict should have:
      - text_arabic (required): The Arabic passage text
      - title: Short title for display, optional
      - text_english: English translation, optional
      - words_used: List of Arabic words from vocabulary, optional
      - comprehension_questions: List of Arabic questions, optional
      - difficulty: "short" or "long" (default: "short")
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    for p in passages:
        p.setdefault("created_at", now)
        p.setdefault("difficulty", "short")
        p.setdefault("last_shown_at", None)
        p.setdefault("times_shown", 0)

    db.passages.insert_many(passages)

    return json.dumps({
        "added_count": len(passages),
    }, ensure_ascii=False)


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
        _serialize_dt(w)
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
        _serialize_dt(w)
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
