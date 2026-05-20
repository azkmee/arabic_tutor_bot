from datetime import date, datetime, timezone, timedelta
from pymongo import MongoClient
from bot.config import (
    MONGO_URI, SRS_INTERVALS, VOCAB_TYPES, GRAMMAR_TYPES,
    EASE_FACTOR_DEFAULT, EASE_FACTOR_MIN, EASE_FACTOR_MAX,
    EASE_FACTOR_CORRECT, EASE_FACTOR_WRONG, LEECH_THRESHOLD,
)

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client["arabic_learning"]
    return _db


# ── Vocabulary Items ─────────────────────────────────────────────────────────

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

    return len(new_words), len(existing)


# ── Item Progress / SRS ──────────────────────────────────────────────────────

def get_due_items(item_type=None, limit=None):
    """Get items due for review today, optionally filtered by type.

    item_type can be:
      - "word" — matches all vocab types (noun, verb, adjective, etc.)
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


def _bump_test_type_stats(stats, test_type, card_format, correct):
    """Increment per-test-type, per-format accuracy counters.

    Migrates legacy flat shape {correct, wrong} → {reveal: {correct, wrong}}
    on first touch so old records keep their history.
    """
    entry = stats.get(test_type)
    if entry is None:
        entry = {}
    elif "correct" in entry or "wrong" in entry:
        legacy_correct = entry.get("correct", 0)
        legacy_wrong = entry.get("wrong", 0)
        entry = {"reveal": {"correct": legacy_correct, "wrong": legacy_wrong}}
    fmt = entry.setdefault(card_format, {"correct": 0, "wrong": 0})
    fmt["correct" if correct else "wrong"] += 1
    stats[test_type] = entry
    return entry


def _stats_totals(entry):
    """Sum counters across formats for backward-compat weighting in picker."""
    if not entry:
        return 0, 0
    if "reveal" in entry or "mcq" in entry:
        c = sum(v.get("correct", 0) for v in entry.values() if isinstance(v, dict))
        w = sum(v.get("wrong", 0) for v in entry.values() if isinstance(v, dict))
        return c, w
    return entry.get("correct", 0), entry.get("wrong", 0)


def update_progress(prog, correct, test_type, session_type="on_demand",
                    card_format="reveal"):
    """Update SRS progress after a review answer."""
    db = get_db()
    now = datetime.now(timezone.utc)
    today = date.today()
    cur_level = prog.get("srs_level", 0)
    ease = prog.get("ease_factor", EASE_FACTOR_DEFAULT)

    # Update per-test-type, per-format accuracy stats
    stats = prog.get("test_type_stats", {})
    entry = _bump_test_type_stats(stats, test_type, card_format, correct)
    fmt_counters = entry[card_format]

    if correct:
        new_level = min(cur_level + 1, 8)
        # Apply ease factor to interval
        base_interval = SRS_INTERVALS[new_level]
        adjusted_interval = max(1, round(base_interval * ease / EASE_FACTOR_DEFAULT))
        next_rev = (today + timedelta(days=adjusted_interval)).isoformat()
        new_streak = prog.get("streak", 0) + 1
        new_ease = min(ease + EASE_FACTOR_CORRECT, EASE_FACTOR_MAX)

        # Prune from weak_test_types after 2 consecutive correct
        weak = prog.get("weak_test_types", [])
        if test_type in weak and fmt_counters["correct"] >= 2:
            # Remove if recent accuracy on this format is good
            if fmt_counters["correct"] > fmt_counters["wrong"]:
                weak = [t for t in weak if t != test_type]

        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level": new_level,
                "next_review_at": next_rev,
                "ease_factor": new_ease,
                "streak": new_streak,
                "last_test_type": test_type,
                "weak_test_types": weak,
                "test_type_stats": stats,
                "last_reviewed_at": now,
            }},
        )
    else:
        next_rev = (today + timedelta(days=1)).isoformat()
        new_ease = max(ease + EASE_FACTOR_WRONG, EASE_FACTOR_MIN)
        lapse_count = prog.get("lapse_count", 0) + 1

        weak = prog.get("weak_test_types", [])
        if test_type not in weak:
            weak.append(test_type)

        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level": 0,
                "next_review_at": next_rev,
                "ease_factor": new_ease,
                "streak": 0,
                "lapse_count": lapse_count,
                "last_test_type": test_type,
                "weak_test_types": weak,
                "test_type_stats": stats,
                "last_reviewed_at": now,
            }},
        )

    log_recall(
        item_progress_id=str(prog["_id"]),
        arabic=prog.get("arabic", ""),
        test_type=test_type,
        correct=correct,
        session_type=session_type,
        srs_level_before=cur_level,
        card_format=card_format,
    )


def log_recall(item_progress_id, arabic, test_type, correct,
               session_type="on_demand", srs_level_before=0,
               card_format="reveal"):
    db = get_db()
    db.recall_log.insert_one({
        "item_progress_id": item_progress_id,
        "arabic": arabic,
        "test_type": test_type,
        "card_format": card_format,
        "correct": correct,
        "quality": 4 if correct else 1,
        "session_type": session_type,
        "srs_level_before": srs_level_before,
        "reviewed_at": datetime.now(timezone.utc),
    })


# ── Raw Words (staging) ─────────────────────────────────────────────────────

def add_raw_words(texts, source="telegram"):
    """Add raw word entries to staging collection."""
    db = get_db()
    now = datetime.now(timezone.utc)
    docs = [
        {
            "text": t,
            "source": source,
            "status": "pending",
            "created_at": now,
            "processed_at": None,
            "vocabulary_item_arabic": None,
        }
        for t in texts
    ]
    db.raw_words.insert_many(docs)
    return len(docs)


def get_pending_raw_words():
    db = get_db()
    return list(db.raw_words.find({"status": "pending"}))


def mark_raw_words_processed(ids, vocabulary_arabic=None):
    db = get_db()
    update = {"$set": {
        "status": "processed",
        "processed_at": datetime.now(timezone.utc),
    }}
    if vocabulary_arabic:
        update["$set"]["vocabulary_item_arabic"] = vocabulary_arabic
    db.raw_words.update_many({"_id": {"$in": ids}}, update)


# ── Raw Passages (staging) ──────────────────────────────────────────────────

def add_raw_passages(texts, source="telegram"):
    """Add raw passage entries to staging collection."""
    db = get_db()
    now = datetime.now(timezone.utc)
    docs = [
        {
            "text": t,
            "source": source,
            "status": "pending",
            "created_at": now,
            "processed_at": None,
            "processed_passage_id": None,
        }
        for t in texts
        if t and t.strip()
    ]
    if not docs:
        return 0
    db.raw_passages.insert_many(docs)
    return len(docs)


def get_pending_raw_passages():
    db = get_db()
    return list(db.raw_passages.find({"status": "pending"}))


def mark_raw_passage_processed(raw_id, passage_id):
    db = get_db()
    db.raw_passages.update_one(
        {"_id": raw_id},
        {"$set": {
            "status": "processed",
            "processed_at": datetime.now(timezone.utc),
            "processed_passage_id": passage_id,
        }},
    )


# ── Passages ─────────────────────────────────────────────────────────────────

def add_passages(passages):
    """Insert passage documents for reading exercises.

    A passage may carry either the legacy `text_arabic` blob, the new
    sentence array `lines: [{arabic, english, words: [{arabic, translation}]}]`,
    or both. When `lines` is present and `words_used` is missing, derive it
    from the per-token gloss. When `raw_passage_id` is present, flip the
    matching `raw_passages` doc to `status="processed"` after insert.
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
        if raw_id is not None:
            raw_links.append(raw_id)
        else:
            raw_links.append(None)
    result = db.passages.insert_many(passages)
    for raw_id, passage_id in zip(raw_links, result.inserted_ids):
        if raw_id is not None:
            mark_raw_passage_processed(raw_id, passage_id)
    return len(passages)


def get_vocab_for_passage(limit=20):
    """Source vocabulary for passage generation: due + weak + recent.

    Returned items are full `vocabulary_items` docs joined with their
    `item_progress` (when present), so cowork can pick words that need
    practice. Sorted: due-soonest first, then weak, then most-recently-added.
    """
    db = get_db()
    today = date.today().isoformat()
    due = list(
        db.item_progress.find({"next_review_at": {"$lte": today}})
        .sort("next_review_at", 1)
        .limit(limit)
    )
    seen = {p["arabic"] for p in due}
    remaining = max(0, limit - len(due))
    weak = []
    if remaining:
        weak = list(
            db.item_progress.find({
                "weak_test_types.0": {"$exists": True},
                "arabic": {"$nin": list(seen)},
            }).limit(remaining)
        )
        seen.update(p["arabic"] for p in weak)
    remaining = max(0, limit - len(due) - len(weak))
    recent_vocab = []
    if remaining:
        recent_vocab = list(
            db.vocabulary_items.find({"arabic": {"$nin": list(seen)}})
            .sort("created_at", -1)
            .limit(remaining)
        )
    progresses = due + weak
    arabic_to_prog = {p["arabic"]: p for p in progresses}
    items = list(db.vocabulary_items.find(
        {"arabic": {"$in": list(arabic_to_prog.keys())}}
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
    for v in recent_vocab:
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
    return out[:limit]


def get_passages(difficulty=None, limit=1, exclude_id=None):
    """Get least-recently-shown passages, optionally excluding one by id."""
    db = get_db()
    query = {}
    if difficulty:
        query["difficulty"] = difficulty
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    # Prefer passages not yet shown, then least recently shown
    return list(db.passages.find(query).sort("last_shown_at", 1).limit(limit))


def normalize_comprehension_questions(raw):
    """Coerce the questions array into the canonical [{question, answer, english}] shape.

    Older passages stored each question as a plain Arabic string; newer ones
    are dicts that also carry the answer (and optionally an English gloss),
    so the Mini App can reveal the answer without a second round trip.
    """
    out = []
    for entry in raw or []:
        if isinstance(entry, str):
            out.append({"question": entry, "answer": "", "english": ""})
        elif isinstance(entry, dict):
            out.append({
                "question": entry.get("question") or entry.get("arabic", ""),
                "answer": entry.get("answer", ""),
                "english": entry.get("english", ""),
            })
    return out


def mark_passage_shown(passage_id):
    db = get_db()
    db.passages.update_one(
        {"_id": passage_id},
        {"$set": {"last_shown_at": datetime.now(timezone.utc)}, "$inc": {"times_shown": 1}},
    )


# ── Stats ────────────────────────────────────────────────────────────────────

def get_stats():
    """Get learning stats for /status command."""
    db = get_db()
    today = date.today().isoformat()
    total_words = db.vocabulary_items.count_documents({})
    total_due = db.item_progress.count_documents({"next_review_at": {"$lte": today}})
    mastered = db.item_progress.count_documents({"srs_level": {"$gte": 7}})
    leeches = db.item_progress.count_documents({"lapse_count": {"$gte": LEECH_THRESHOLD}})
    pending_raw = db.raw_words.count_documents({"status": "pending"})
    pending_raw_passages = db.raw_passages.count_documents({"status": "pending"})
    return {
        "total_words": total_words,
        "due_today": total_due,
        "mastered": mastered,
        "leeches": leeches,
        "pending_raw": pending_raw,
        "pending_raw_passages": pending_raw_passages,
    }
