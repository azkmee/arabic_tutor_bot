import os
import json
from datetime import date, datetime, timezone
from bson import ObjectId
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
      - mcq_options: dict keyed by test_type, each value a list of 3
        plausible distractor strings (never duplicating the correct answer).
        Supported keys: "meaning", "plural", "root_derive", "fill_blank",
        "grammar". Optional — when absent for a given test_type, that card
        renders as tap-to-reveal.

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
      - title: Short title for display, optional (use fully diacritized Arabic)
      - lines (preferred): list of sentence objects, each
          {
            "arabic": "<fully diacritized sentence>",
            "english": "<sentence translation>",
            "words": [
              {"arabic": "<token with tashkeel>", "translation": "<gloss>"},
              ...   # every Arabic token in the sentence, particles included
            ]
          }
      - text_arabic: legacy single-blob Arabic text; only use when `lines`
        is not available. Webapp falls back to this when `lines` is absent.
      - text_english: full English translation, optional
      - words_used: list of Arabic words; auto-derived from lines[].words
        when omitted
      - comprehension_questions: list of fully-diacritized Arabic questions
      - difficulty: "short" or "long" (default: "short")
      - raw_passage_id (optional): id of a `raw_passages` doc this enriches;
        when present, that staging doc is flipped to status="processed".

    All Arabic in `lines`, `title`, and `comprehension_questions` must
    carry full tashkeel. Vocab gloss strings should match the source word
    in the corresponding vocabulary_items entry when one exists.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    raw_links = []

    for p in passages:
        p.setdefault("created_at", now)
        p.setdefault("difficulty", "short")
        p.setdefault("last_shown_at", None)
        p.setdefault("times_shown", 0)

        if p.get("lines") and not p.get("words_used"):
            seen = []
            for line in p["lines"]:
                for w in line.get("words", []):
                    ar = (w or {}).get("arabic")
                    if ar and ar not in seen:
                        seen.append(ar)
            p["words_used"] = seen

        raw_id = p.pop("raw_passage_id", None)
        if isinstance(raw_id, str):
            try:
                raw_id = ObjectId(raw_id)
            except Exception:
                return json.dumps({"error": f"invalid raw_passage_id {raw_id!r}"}, ensure_ascii=False)
        raw_links.append(raw_id)

    result = db.passages.insert_many(passages)

    for raw_id, passage_id in zip(raw_links, result.inserted_ids):
        if raw_id is not None:
            db.raw_passages.update_one(
                {"_id": raw_id},
                {"$set": {
                    "status": "processed",
                    "processed_at": now,
                    "processed_passage_id": passage_id,
                }},
            )

    return json.dumps({
        "added_count": len(passages),
        "linked_raw_passages": sum(1 for r in raw_links if r is not None),
    }, ensure_ascii=False)


@mcp.tool()
def get_pending_passages() -> str:
    """Get raw passages awaiting cowork enrichment.

    These come from the Telegram /add_passage command or the webapp
    /api/raw-passages endpoint. For each, produce fully diacritized
    Arabic, sentence-split lines, per-word gloss, and submit via
    add_passages([{..., "raw_passage_id": id}]).
    """
    db = get_db()
    pending = list(db.raw_passages.find({"status": "pending"}))
    out = []
    for doc in pending:
        out.append({
            "id": str(doc["_id"]),
            "text": doc.get("text", ""),
            "source": doc.get("source", ""),
            "created_at": doc["created_at"].isoformat()
            if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at")),
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool()
def add_raw_passages(items: list[dict]) -> str:
    """Stage passages for later cowork enrichment.

    Each item: {"text": "<paragraph>", "source": "<optional note>"}.
    Use this when pasting passages directly from a Claude Desktop
    conversation rather than enriching them inline.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    docs = []
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        docs.append({
            "text": text,
            "source": it.get("source", "mcp"),
            "status": "pending",
            "created_at": now,
            "processed_at": None,
            "processed_passage_id": None,
        })
    if docs:
        db.raw_passages.insert_many(docs)
    return json.dumps({"queued": len(docs)}, ensure_ascii=False)


@mcp.tool()
def get_vocab_for_passage(limit: int = 20) -> str:
    """Source vocab for drafting a passage: due + weak + recent words.

    Returned items carry srs_level, weak_test_types, and a `reason`
    ("due" / "weak" / "recent") so cowork can prioritize coverage.
    Aim to weave ≥6 of these into each generated passage.
    """
    db = get_db()
    today = date.today().isoformat()

    due = list(
        db.item_progress.find({"next_review_at": {"$lte": today}})
        .sort("next_review_at", 1)
        .limit(limit)
    )
    seen = {p["arabic"] for p in due}

    weak = []
    remaining = max(0, limit - len(due))
    if remaining:
        weak = list(
            db.item_progress.find({
                "weak_test_types.0": {"$exists": True},
                "arabic": {"$nin": list(seen)},
            }).limit(remaining)
        )
        seen.update(p["arabic"] for p in weak)

    progresses = due + weak
    arabic_to_prog = {p["arabic"]: p for p in progresses}
    items = list(db.vocabulary_items.find(
        {"arabic": {"$in": list(arabic_to_prog.keys())}},
        {"_id": 0},
    ))

    out = []
    for v in items:
        prog = arabic_to_prog.get(v["arabic"], {})
        out.append({
            "arabic": v.get("arabic", ""),
            "transliteration": v.get("transliteration", ""),
            "translation": v.get("translation", ""),
            "type": v.get("type", ""),
            "root": v.get("root", ""),
            "plural": v.get("plural", ""),
            "srs_level": prog.get("srs_level", 0),
            "weak_test_types": prog.get("weak_test_types", []),
            "reason": "due" if prog.get("next_review_at", "9999") <= today else "weak",
        })

    remaining = max(0, limit - len(out))
    if remaining:
        recent = list(
            db.vocabulary_items.find(
                {"arabic": {"$nin": [w["arabic"] for w in out]}},
                {"_id": 0},
            ).sort("created_at", -1).limit(remaining)
        )
        for v in recent:
            out.append({
                "arabic": v.get("arabic", ""),
                "transliteration": v.get("transliteration", ""),
                "translation": v.get("translation", ""),
                "type": v.get("type", ""),
                "root": v.get("root", ""),
                "plural": v.get("plural", ""),
                "srs_level": 0,
                "weak_test_types": [],
                "reason": "recent",
            })

    return json.dumps(out[:limit], ensure_ascii=False, indent=2)


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
