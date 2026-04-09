from datetime import date, datetime, timezone, timedelta
from pymongo import MongoClient
from bot.config import MONGO_URI, SRS_INTERVALS

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client["arabic_learning"]
    return _db


GRAMMAR_TYPES = {"grammar_rule", "grammar"}
VOCAB_TYPES = {"noun", "verb", "adjective", "adverb", "word", "phrase", "preposition", "particle"}


def get_due_items(item_type=None, limit=None):
    """Get items due for review today, optionally filtered by type.

    item_type can be:
      - "word" — matches noun, verb, adjective, etc. (any non-grammar type)
      - "grammar_rule" — matches grammar types
      - None — no type filter
    """
    db = get_db()
    today = date.today().isoformat()
    query = {"next_review_at": {"$lte": today}}

    if item_type:
        if item_type == "word":
            type_set = VOCAB_TYPES
        elif item_type == "grammar_rule":
            type_set = GRAMMAR_TYPES
        else:
            type_set = {item_type}

        arabic_words = [
            v["arabic"]
            for v in db.vocabulary_items.find({"type": {"$in": list(type_set)}}, {"arabic": 1})
        ]
        query["arabic"] = {"$in": arabic_words}

    cursor = db.item_progress.find(query)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def get_vocab_item(arabic):
    db = get_db()
    return db.vocabulary_items.find_one({"arabic": arabic})


def find_existing_words(arabic_list):
    """Return set of arabic strings that already exist in vocabulary_items."""
    db = get_db()
    existing = db.vocabulary_items.find(
        {"arabic": {"$in": arabic_list}}, {"arabic": 1}
    )
    return {doc["arabic"] for doc in existing}


def insert_new_words(words):
    """Insert new words into vocabulary_items and create item_progress entries.
    Returns (added_count, skipped_count).
    """
    db = get_db()
    existing = find_existing_words([w["arabic"] for w in words])

    new_words = [w for w in words if w["arabic"] not in existing]
    if not new_words:
        return 0, len(words)

    today = date.today().isoformat()
    now = datetime.now(timezone.utc)

    for word in new_words:
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

    return len(new_words), len(existing)


def update_progress(prog, correct, test_type):
    """Update SRS progress after a review answer."""
    db = get_db()
    now = datetime.now(timezone.utc)
    today = date.today()
    cur_level = prog.get("srs_level", 0)

    if correct:
        new_level = min(cur_level + 1, 8)
        next_rev = (today + timedelta(days=SRS_INTERVALS[new_level])).isoformat()
        new_streak = prog.get("streak", 0) + 1
        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level": new_level,
                "next_review_at": next_rev,
                "streak": new_streak,
                "last_test_type": test_type,
            }},
        )
    else:
        next_rev = (today + timedelta(days=1)).isoformat()
        weak = prog.get("weak_test_types", [])
        if test_type not in weak:
            weak.append(test_type)
        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level": 0,
                "next_review_at": next_rev,
                "streak": 0,
                "last_test_type": test_type,
                "weak_test_types": weak,
            }},
        )

    log_recall(str(prog["_id"]), prog.get("arabic", ""), test_type, correct)


def log_recall(item_id, arabic, test_type, correct):
    db = get_db()
    db.recall_log.insert_one({
        "item_id": item_id,
        "arabic": arabic,
        "test_type": test_type,
        "correct": correct,
        "reviewed_at": datetime.now(timezone.utc),
    })


def add_raw_words(texts, source="telegram"):
    """Add raw word entries to staging collection."""
    db = get_db()
    now = datetime.now(timezone.utc)
    docs = [
        {"text": t, "source": source, "status": "pending", "created_at": now}
        for t in texts
    ]
    db.raw_words.insert_many(docs)
    return len(docs)


def get_pending_raw_words():
    db = get_db()
    return list(db.raw_words.find({"status": "pending"}))


def mark_raw_words_processed(ids):
    db = get_db()
    db.raw_words.update_many(
        {"_id": {"$in": ids}},
        {"$set": {"status": "processed"}},
    )


def add_paragraphs(paragraphs):
    """Insert paragraph documents for reading exercises."""
    db = get_db()
    now = datetime.now(timezone.utc)
    for p in paragraphs:
        p.setdefault("created_at", now)
    db.passages.insert_many(paragraphs)
    return len(paragraphs)


def get_paragraphs(difficulty=None, limit=1):
    db = get_db()
    query = {}
    if difficulty:
        query["difficulty"] = difficulty
    return list(db.passages.find(query).limit(limit))


def get_stats():
    """Get learning stats for /status command."""
    db = get_db()
    today = date.today().isoformat()
    total_words = db.vocabulary_items.count_documents({})
    total_due = db.item_progress.count_documents({"next_review_at": {"$lte": today}})
    mastered = db.item_progress.count_documents({"srs_level": {"$gte": 7}})
    pending_raw = db.raw_words.count_documents({"status": "pending"})
    return {
        "total_words": total_words,
        "due_today": total_due,
        "mastered": mastered,
        "pending_raw": pending_raw,
    }
