import os
import time
import json
import random
from datetime import datetime, timezone, timedelta, date
from pymongo import MongoClient
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI        = os.environ["MONGO_URI"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── SRS helpers ───────────────────────────────────────────────────────────────
SRS_INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 14, 5: 30, 6: 60, 7: 90, 8: 180}

TEST_TYPE_LABELS = {
    "meaning"    : "💬 What does this mean?",
    "plural"     : "📚 What is the plural (جمع)?",
    "fill_blank" : "✏️ Fill in the blank",
    "root_derive": "🌱 Derive from the root",
    "grammar"    : "📐 Apply the grammar rule",
}

# ── Telegram helpers ──────────────────────────────────────────────────────────
def tg_request(method, data):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req     = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def tg_send(text, reply_markup=None):
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return tg_request("sendMessage", data)

def tg_remove_keyboard(message_id):
    try:
        tg_request("editMessageReplyMarkup", {
            "chat_id"     : TELEGRAM_CHAT_ID,
            "message_id"  : message_id,
            "reply_markup": {"inline_keyboard": []},
        })
    except Exception:
        pass

def tg_answer_callback(cq_id, text=""):
    try:
        tg_request("answerCallbackQuery", {"callback_query_id": cq_id, "text": text})
    except Exception:
        pass

def get_updates(offset=None):
    data = {"timeout": 1, "allowed_updates": ["callback_query"]}
    if offset is not None:
        data["offset"] = offset
    return tg_request("getUpdates", data)

def drain_updates():
    """Consume all pending updates and return the next offset to use."""
    result  = get_updates()
    updates = result.get("result", [])
    if updates:
        return updates[-1]["update_id"] + 1
    return None

def poll_callback(message_id, item_id_str, offset, timeout=5):
    """
    Poll for a callback query on `message_id` for up to `timeout` seconds.
    Returns (answer, new_offset) where answer is 'correct', 'wrong', or None.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            result = get_updates(offset)
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                if "callback_query" not in update:
                    continue
                cq  = update["callback_query"]
                msg = cq.get("message", {})
                if (str(msg.get("chat", {}).get("id")) == str(TELEGRAM_CHAT_ID) and
                        msg.get("message_id") == message_id):
                    data = cq.get("data", "")
                    if data.startswith(f"{item_id_str}:"):
                        answer = data.split(":", 1)[1]   # 'correct' or 'wrong'
                        tg_answer_callback(cq["id"])
                        tg_remove_keyboard(message_id)
                        return answer, offset
        except Exception:
            pass
        time.sleep(1)

    tg_remove_keyboard(message_id)
    return None, offset

# ── Card builder ──────────────────────────────────────────────────────────────
def build_card(item, prog):
    arabic = item.get("arabic", "")
    trans  = item.get("transliteration", "")
    eng    = item.get("translation", "")
    root   = item.get("root", "")
    plural = item.get("plural", "")
    itype  = item.get("type", "word")
    level  = prog.get("srs_level", 0)
    streak = prog.get("streak", 0)

    last_test = prog.get("last_test_type", "")
    weak      = prog.get("weak_test_types", [])

    if itype == "grammar_rule":
        test_type = "grammar"
    else:
        options    = ["meaning", "meaning"]
        if plural: options.append("plural")
        if root:   options.append("root_derive")
        options.append("fill_blank")
        candidates = [t for t in weak if t in options] or options
        candidates = [t for t in candidates if t != last_test] or candidates
        test_type  = random.choice(candidates)

    label      = TEST_TYPE_LABELS.get(test_type, "💬 Review")
    stars      = "⭐" * min(level, 8)
    streak_str = f"🔥 {streak} day streak" if streak >= 2 else ""

    lines = ["<b>مراجعة يومية</b> — Daily Review", "─" * 28, label, ""]

    if test_type == "meaning":
        lines += [f"<b>{arabic}</b>", f"<i>({trans})</i>" if trans else ""]
        lines += ["", f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
                  "<i>Tap to reveal, then rate yourself below:</i>"]

    elif test_type == "plural":
        lines += [f"<b>{arabic}</b>  —  {eng}", "", "What is the plural (جمع)?"]
        if plural:
            lines += ["", f"<tg-spoiler>➡️  {plural}</tg-spoiler>",
                      "<i>Tap to reveal, then rate:</i>"]

    elif test_type == "root_derive":
        lines += [f"Root: <b>{root}</b>", "", f"Derive the word that means: <b>{eng}</b>"]
        lines += ["", f"<tg-spoiler>➡️  {arabic}  ({trans})</tg-spoiler>",
                  "<i>Tap to reveal, then rate:</i>"]

    elif test_type == "fill_blank":
        sentence = item.get("example_sentence", "")
        if sentence:
            blank = sentence.replace(arabic, "________")
            lines += [blank, "", f"<tg-spoiler>➡️  {arabic}  ({eng})</tg-spoiler>",
                      "<i>Tap to reveal, then rate:</i>"]
        else:
            lines += [f"<b>{arabic}</b>  ({trans})", "",
                      f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
                      "<i>Tap to reveal, then rate:</i>"]

    elif test_type == "grammar":
        rule_desc = item.get("translation", "")
        example   = item.get("example_sentence", "")
        lines += ["📐 Grammar rule:", f"<b>{arabic}</b>", f"<i>{rule_desc}</i>"]
        if example:
            lines += ["", f"Example: <tg-spoiler>{example}</tg-spoiler>",
                      "<i>Tap to reveal, then rate:</i>"]

    lines += ["", "─" * 28, f"SRS level {level}/8  {stars}  {streak_str}"]

    return "\n".join(l for l in lines if l is not None), test_type

# ── SRS update ────────────────────────────────────────────────────────────────
def update_progress(db, prog, correct, test_type):
    now       = datetime.now(timezone.utc)
    today     = date.today()
    cur_level = prog.get("srs_level", 0)

    if correct:
        new_level  = min(cur_level + 1, 8)
        next_rev   = (today + timedelta(days=SRS_INTERVALS[new_level])).isoformat()
        new_streak = prog.get("streak", 0) + 1
        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level"     : new_level,
                "next_review_at": next_rev,
                "streak"        : new_streak,
                "last_test_type": test_type,
            }}
        )
    else:
        next_rev = (today + timedelta(days=1)).isoformat()
        weak     = prog.get("weak_test_types", [])
        if test_type not in weak:
            weak.append(test_type)
        db.item_progress.update_one(
            {"_id": prog["_id"]},
            {"$set": {
                "srs_level"      : 0,
                "next_review_at" : next_rev,
                "streak"         : 0,
                "last_test_type" : test_type,
                "weak_test_types": weak,
            }}
        )

    db.recall_log.insert_one({
        "item_id"    : str(prog["_id"]),
        "arabic"     : prog.get("arabic", ""),
        "test_type"  : test_type,
        "correct"    : correct,
        "reviewed_at": now,
    })

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client = MongoClient(MONGO_URI)
    db     = client["arabic_learning"]
    today  = date.today().isoformat()

    due_progress = list(db.item_progress.find({"next_review_at": {"$lte": today}}))
    total_due    = len(due_progress)

    if total_due == 0:
        tg_send(
            "✅ <b>لا توجد مراجعات اليوم!</b>\n\n"
            "No reviews due today — you're all caught up!\n"
            "Come back tomorrow, or open Claude to add new words."
        )
        client.close()
        return

    sample = due_progress[:3]

    tg_send(
        f"🌙 <b>وقت المراجعة</b> — Review Time!\n"
        f"{'─'*28}\n"
        f"You have <b>{total_due} item{'s' if total_due > 1 else ''}</b> due today.\n"
        f"Here {'are' if len(sample) > 1 else 'is'} your first "
        f"{'few' if len(sample) > 1 else 'one'}:\n\n"
        f"Open Claude for your full graded session 👉 claude.ai"
    )

    # Drain any stale callbacks before we start sending cards
    offset  = drain_updates()
    results = {"correct": 0, "wrong": 0, "skipped": 0}

    for prog in sample:
        item = db.vocabulary_items.find_one({"arabic": prog["arabic"]})
        if not item:
            continue

        item_id_str = str(prog["_id"])
        card_text, test_type = build_card(item, prog)

        keyboard = {"inline_keyboard": [[
            {"text": "✅ Got it",    "callback_data": f"{item_id_str}:correct"},
            {"text": "❌ Missed it", "callback_data": f"{item_id_str}:wrong"},
        ]]}

        resp       = tg_send(card_text, reply_markup=keyboard)
        message_id = resp["result"]["message_id"]

        answer, offset = poll_callback(message_id, item_id_str, offset, timeout=5)

        if answer == "correct":
            update_progress(db, prog, correct=True,  test_type=test_type)
            results["correct"] += 1
        elif answer == "wrong":
            update_progress(db, prog, correct=False, test_type=test_type)
            results["wrong"] += 1
        else:
            results["skipped"] += 1

    answered = results["correct"] + results["wrong"]
    if answered > 0:
        tg_send(
            f"📊 <b>نتيجة</b> — Mini Results\n"
            f"{'─'*28}\n"
            f"✅ Correct: {results['correct']}\n"
            f"❌ Missed:  {results['wrong']}\n"
            f"⏭ Skipped: {results['skipped']}\n\n"
            f"Open Claude for your full session 👉 claude.ai"
        )

    if total_due >= 10:
        tg_send(
            f"⚠️ <b>تنبيه:</b> You still have {total_due} items waiting.\n"
            "Don't let them pile up — even 10 minutes helps! 💪"
        )

    client.close()

if __name__ == "__main__":
    main()
