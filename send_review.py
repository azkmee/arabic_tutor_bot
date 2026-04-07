import os
import asyncio
from datetime import datetime, timezone
from pymongo import MongoClient
import urllib.request
import json
import random

# ── Config from environment ──────────────────────────────────────────────────
MONGO_URI        = os.environ["MONGO_URI"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── SRS helpers ───────────────────────────────────────────────────────────────
SRS_INTERVALS = {0:0, 1:1, 2:3, 3:7, 4:14, 5:30, 6:60, 7:90, 8:180}

TEST_TYPE_LABELS = {
    "meaning"    : "💬 What does this mean?",
    "plural"     : "📚 What is the plural (جمع)?",
    "fill_blank" : "✏️ Fill in the blank",
    "root_derive": "🌱 Derive from the root",
    "grammar"    : "📐 Apply the grammar rule",
}

# ── Telegram sender ───────────────────────────────────────────────────────────
def tg_send(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id"   : TELEGRAM_CHAT_ID,
        "text"      : text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# ── Build flash card message ──────────────────────────────────────────────────
def build_card(item: dict, progress: dict) -> str:
    arabic = item.get("arabic", "")
    trans  = item.get("transliteration", "")
    eng    = item.get("translation", "")
    root   = item.get("root", "")
    plural = item.get("plural", "")
    itype  = item.get("type", "word")
    level  = progress.get("srs_level", 0)
    streak = progress.get("streak", 0)

    # Pick a test type (avoid repeating last one)
    last_test = progress.get("last_test_type", "")
    weak      = progress.get("weak_test_types", [])

    if itype == "grammar_rule":
        test_type = "grammar"
    else:
        options = ["meaning", "meaning"]   # weight meaning higher
        if plural: options.append("plural")
        if root:   options.append("root_derive")
        options.append("fill_blank")
        # prefer weak types
        candidates = [t for t in weak if t in options] or options
        candidates = [t for t in candidates if t != last_test] or candidates
        test_type  = random.choice(candidates)

    label = TEST_TYPE_LABELS.get(test_type, "💬 Review")

    # ── Format the card ───────────────────────────────────────────────────────
    stars  = "⭐" * min(level, 8)
    streak_str = f"🔥 {streak} day streak" if streak >= 2 else ""

    lines = [
        f"<b>مراجعة يومية</b> — Daily Review",
        f"{'─'*28}",
        f"{label}",
        f"",
    ]

    if test_type == "meaning":
        lines += [
            f"<b>{arabic}</b>",
            f"<i>({trans})</i>" if trans else "",
        ]
        lines += ["", f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
                  "<i>Tap the spoiler to reveal the answer</i>"]

    elif test_type == "plural":
        lines += [
            f"<b>{arabic}</b>  —  {eng}",
            "",
            f"What is the plural (جمع)?",
        ]
        if plural:
            lines += ["", f"<tg-spoiler>➡️  {plural}</tg-spoiler>",
                      "<i>Tap to reveal</i>"]

    elif test_type == "root_derive":
        lines += [
            f"Root: <b>{root}</b>",
            "",
            f"Derive the word that means: <b>{eng}</b>",
        ]
        lines += ["", f"<tg-spoiler>➡️  {arabic}  ({trans})</tg-spoiler>",
                  "<i>Tap to reveal</i>"]

    elif test_type == "fill_blank":
        # Simple fill-blank using the word
        sentence = item.get("example_sentence", "")
        if sentence:
            blank = sentence.replace(arabic, "________")
            lines += [f"{blank}", "", f"<tg-spoiler>➡️  {arabic}  ({eng})</tg-spoiler>",
                      "<i>Tap to reveal</i>"]
        else:
            # Fallback to meaning
            lines += [f"<b>{arabic}</b>  ({trans})", "",
                      f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
                      "<i>Tap to reveal</i>"]

    elif test_type == "grammar":
        rule_desc = item.get("translation", "")
        example   = item.get("example_sentence", "")
        lines += [
            f"📐 Grammar rule:",
            f"<b>{arabic}</b>",
            f"<i>{rule_desc}</i>",
        ]
        if example:
            lines += ["", f"Example: <tg-spoiler>{example}</tg-spoiler>",
                      "<i>Tap to reveal</i>"]

    # Footer
    lines += [
        "",
        f"{'─'*28}",
        f"SRS level {level}/8  {stars}  {streak_str}",
        f"Open Claude to do your full session 👉 claude.ai",
    ]

    return "\n".join(l for l in lines if l is not None)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client = MongoClient(MONGO_URI)
    db     = client["arabic_tutor"]          # change if your db name differs

    now = datetime.now(timezone.utc)

    # Fetch due items
    due_progress = list(db.item_progress.find({
        "next_review_at": {"$lte": now}
    }))

    total_due = len(due_progress)

    if total_due == 0:
        tg_send(
            "✅ <b>لا توجد مراجعات اليوم!</b>\n\n"
            "No reviews due today — you're all caught up!\n"
            "Come back tomorrow, or open Claude to add new words."
        )
        return

    # Pick up to 3 cards to send (don't overwhelm)
    sample = due_progress[:3]

    # Header message
    header = (
        f"🌙 <b>وقت المراجعة</b> — Review Time!\n"
        f"{'─'*28}\n"
        f"You have <b>{total_due} item{'s' if total_due>1 else ''}</b> due today.\n"
        f"Here {'are' if len(sample)>1 else 'is'} your first "
        f"{'few' if len(sample)>1 else 'one'}:\n\n"
        f"Open Claude for your full graded session 👉 claude.ai"
    )
    tg_send(header)

    # Send each card
    for prog in sample:
        item_id = prog.get("item_id") or prog.get("vocabulary_item_id")
        item    = db.vocabulary_items.find_one({"_id": item_id}) or \
                  db.vocabulary_items.find_one({"item_id": str(item_id)})
        if not item:
            continue
        card_text = build_card(item, prog)
        tg_send(card_text)

    # If many items piled up, send a nudge
    if total_due >= 10:
        tg_send(
            f"⚠️ <b>تنبيه:</b> You have {total_due} items waiting.\n"
            "Don't let them pile up — even 10 minutes helps! 💪"
        )

    client.close()

if __name__ == "__main__":
    main()
