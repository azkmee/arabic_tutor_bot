"""JSON API for the Telegram Mini App (Web App) frontend.

Endpoints under /api/* are consumed by the React frontend hosted on GitHub
Pages. Auth is via Telegram's `initData` query string, which the frontend
forwards in the `X-Telegram-Init-Data` header. We validate the HMAC
signature against the bot token (per Telegram WebApp spec) and check that
the embedded user id matches TELEGRAM_CHAT_ID — this is a single-user bot.
"""
import hashlib
import hmac
import json
import logging
import random
import uuid
from urllib.parse import parse_qsl

from bson import ObjectId
from starlette.responses import JSONResponse

from bot import db
from bot.config import (
    REVIEW_SESSION,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)
from bot.services.cards import _pick_test_type

logger = logging.getLogger(__name__)


# ── Auth ────────────────────────────────────────────────────────────────────


def _validate_init_data(init_data: str) -> dict | None:
    """Verify Telegram WebApp initData HMAC and return the parsed user dict.

    Returns None if the signature is invalid or the user doesn't match the
    expected single-user chat id.
    """
    if not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs.keys())
    )
    secret_key = hmac.new(
        b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        return None

    if str(user.get("id", "")) != str(TELEGRAM_CHAT_ID):
        return None

    return user


def _json(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code)


def _authed(request):
    """Return (user_dict, error_response). Exactly one is None."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = _validate_init_data(init_data)
    if not user:
        return None, _json({"error": "unauthorized"}, status_code=401)
    return user, None


# ── Endpoints ───────────────────────────────────────────────────────────────


async def get_session(request):
    """Build a review session and return cards + passage as JSON.

    Mirrors the assembly done in `handlers/review.send_review_session` but
    returns the data instead of pushing messages.
    """
    user, err = _authed(request)
    if err:
        return err

    session_type = request.query_params.get("session_type", "on_demand")

    vocab_due = db.get_due_items(item_type="word", limit=REVIEW_SESSION["vocab"])
    grammar_due = db.get_due_items(
        item_type="grammar_rule", limit=REVIEW_SESSION["grammar"]
    )
    progresses = vocab_due + grammar_due
    if not progresses:
        # Fallback: ignore type filter (matches existing behavior)
        progresses = db.get_due_items(
            limit=REVIEW_SESSION["vocab"] + REVIEW_SESSION["grammar"]
        )
    random.shuffle(progresses)

    cards = []
    for prog in progresses:
        item = db.get_vocab_item(prog["arabic"])
        if not item:
            continue
        test_type = _pick_test_type(item, prog)
        cards.append({
            "item_progress_id": str(prog["_id"]),
            "arabic": item.get("arabic", ""),
            "transliteration": item.get("transliteration", ""),
            "translation": item.get("translation", ""),
            "type": item.get("type", "noun"),
            "root": item.get("root", ""),
            "plural": item.get("plural", ""),
            "example_sentence": item.get("example_sentence", ""),
            "example_translation": item.get("example_translation", ""),
            "test_type": test_type,
            "srs_level": prog.get("srs_level", 0),
            "streak": prog.get("streak", 0),
            "lapse_count": prog.get("lapse_count", 0),
        })

    passages = db.get_passages(limit=1)
    passage_payload = None
    if passages:
        p = passages[0]
        passage_payload = {
            "id": str(p["_id"]),
            "title": p.get("title", ""),
            "text_arabic": p.get("text_arabic") or p.get("arabic_text", ""),
            "text_english": p.get("text_english", ""),
            "words_used": p.get("words_used", []),
            "comprehension_questions": p.get("comprehension_questions", []),
            "difficulty": p.get("difficulty", "short"),
        }

    total_due = len(db.get_due_items())

    return _json({
        "session_id": uuid.uuid4().hex[:8],
        "session_type": session_type,
        "total_due_today": total_due,
        "cards": cards,
        "passage": passage_payload,
    })


async def post_result(request):
    """Record one card answer. Body: {item_progress_id, correct, test_type,
    session_type}. Returns the new SRS state for the card."""
    user, err = _authed(request)
    if err:
        return err

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _json({"error": "invalid json"}, status_code=400)

    item_id_str = body.get("item_progress_id")
    correct = bool(body.get("correct"))
    test_type = body.get("test_type", "meaning")
    session_type = body.get("session_type", "on_demand")

    if not item_id_str:
        return _json({"error": "missing item_progress_id"}, status_code=400)

    try:
        oid = ObjectId(item_id_str)
    except Exception:
        return _json({"error": "invalid item_progress_id"}, status_code=400)

    prog = db.get_db().item_progress.find_one({"_id": oid})
    if not prog:
        return _json({"error": "not found"}, status_code=404)

    db.update_progress(prog, correct, test_type, session_type=session_type)
    updated = db.get_db().item_progress.find_one({"_id": oid})

    return _json({
        "ok": True,
        "srs_level": updated.get("srs_level", 0),
        "next_review_at": updated.get("next_review_at", ""),
        "streak": updated.get("streak", 0),
    })


async def lookup_word(request):
    """Look up a single Arabic word in the vocabulary collection.

    Used by the passage reader's tap-to-translate. Returns 404 if the word
    isn't in the user's vocab — the frontend then offers an "Add to recall"
    button that POSTs to /api/raw_words.
    """
    user, err = _authed(request)
    if err:
        return err

    arabic = request.query_params.get("arabic", "").strip()
    if not arabic:
        return _json({"error": "missing arabic"}, status_code=400)

    item = db.get_vocab_item(arabic)
    if not item:
        return _json({"found": False, "arabic": arabic}, status_code=404)

    return _json({
        "found": True,
        "arabic": item.get("arabic", ""),
        "transliteration": item.get("transliteration", ""),
        "translation": item.get("translation", ""),
        "type": item.get("type", ""),
        "root": item.get("root", ""),
        "plural": item.get("plural", ""),
    })


async def post_raw_word(request):
    """Queue a word into raw_words. Mirrors the /add Telegram command so a
    user reading a passage can save unknown words for processing."""
    user, err = _authed(request)
    if err:
        return err

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _json({"error": "invalid json"}, status_code=400)

    text = (body.get("text") or "").strip()
    if not text:
        return _json({"error": "missing text"}, status_code=400)

    db.add_raw_words([text], source="webapp")
    return _json({"ok": True})


async def post_passage_shown(request):
    """Mark a passage as displayed so the least-recently-shown picker
    rotates."""
    user, err = _authed(request)
    if err:
        return err

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _json({"error": "invalid json"}, status_code=400)

    pid = body.get("passage_id")
    if not pid:
        return _json({"error": "missing passage_id"}, status_code=400)

    try:
        oid = ObjectId(pid)
    except Exception:
        return _json({"error": "invalid passage_id"}, status_code=400)

    db.mark_passage_shown(oid)
    return _json({"ok": True})


async def get_stats(request):
    """Stats for the session summary screen."""
    user, err = _authed(request)
    if err:
        return err
    return _json(db.get_stats())
