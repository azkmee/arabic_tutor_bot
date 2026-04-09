import random
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot import db
from bot.config import TELEGRAM_CHAT_ID, REVIEW_SESSION
from bot.services.cards import build_card, build_paragraph_card

# Abbreviations for test types in callback data (to fit 64-byte limit)
_TT_SHORT = {"meaning": "m", "plural": "p", "fill_blank": "f", "root_derive": "r", "grammar": "g"}
_TT_LONG = {v: k for k, v in _TT_SHORT.items()}


async def send_review_session(context, session_type="morning"):
    """Send a mixed review session: 5 vocab + 2 grammar + 1 sentence."""
    chat_id = TELEGRAM_CHAT_ID

    vocab_due = db.get_due_items(item_type="word", limit=REVIEW_SESSION["vocab"])
    grammar_due = db.get_due_items(item_type="grammar_rule", limit=REVIEW_SESSION["grammar"])

    all_items = vocab_due + grammar_due

    # Fallback: if type-filtered queries return nothing, try without type filter
    if not all_items:
        all_items = db.get_due_items(limit=REVIEW_SESSION["vocab"] + REVIEW_SESSION["grammar"])

    total_due_count = len(db.get_due_items())

    if not all_items:
        # Try to send a paragraph even if no vocab/grammar due
        difficulty = "long" if session_type == "dinner" else "short"
        paragraphs = db.get_paragraphs(difficulty=difficulty, limit=1)
        if paragraphs:
            card_text = build_paragraph_card(paragraphs[0])
            await context.bot.send_message(
                chat_id=chat_id, text=card_text, parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>لا توجد مراجعات اليوم!</b>\n\n"
                    "No reviews due — you're all caught up!"
                ),
                parse_mode="HTML",
            )
        return

    session_label = {"morning": "🌅 Morning", "lunch": "🌞 Lunch", "dinner": "🌙 Dinner"}.get(
        session_type, "📚"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"{session_label} <b>وقت المراجعة</b> — Review Time!\n"
            f"{'─' * 28}\n"
            f"<b>{total_due_count}</b> items due today.\n"
            f"This session: {len(vocab_due)} vocab + {len(grammar_due)} grammar"
        ),
        parse_mode="HTML",
    )

    # Initialize session tracking (short ID to fit 64-byte callback_data limit)
    session_id = uuid.uuid4().hex[:8]
    context.bot_data[session_id] = {
        "correct": 0,
        "wrong": 0,
        "total": len(all_items),
        "answered": 0,
    }

    random.shuffle(all_items)

    for prog in all_items:
        item = db.get_vocab_item(prog["arabic"])
        if not item:
            context.bot_data[session_id]["total"] -= 1
            continue

        item_id_str = str(prog["_id"])
        card_text, test_type = build_card(item, prog)

        tt = _TT_SHORT.get(test_type, test_type[0])
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Got it", callback_data=f"{item_id_str}:c:{tt}:{session_id}"),
                InlineKeyboardButton("❌ Missed it", callback_data=f"{item_id_str}:w:{tt}:{session_id}"),
            ]
        ])

        await context.bot.send_message(
            chat_id=chat_id, text=card_text, parse_mode="HTML", reply_markup=keyboard
        )

    # Send paragraph card at the end
    difficulty = "long" if session_type == "dinner" else "short"
    paragraphs = db.get_paragraphs(difficulty=difficulty, limit=1)
    if paragraphs:
        card_text = build_paragraph_card(paragraphs[0])
        await context.bot.send_message(
            chat_id=chat_id, text=card_text, parse_mode="HTML"
        )


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /review command — trigger an on-demand review session."""
    await send_review_session(context, session_type="morning")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Got it / Missed it button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(":")
    if len(parts) < 3:
        return

    item_id_str = parts[0]
    answer = parts[1]
    test_type_short = parts[2]
    session_id = parts[3] if len(parts) > 3 else None

    test_type = _TT_LONG.get(test_type_short, test_type_short)

    # Find the progress document
    from bson import ObjectId
    prog = db.get_db().item_progress.find_one({"_id": ObjectId(item_id_str)})
    if not prog:
        return

    correct = answer == "c"
    db.update_progress(prog, correct, test_type)

    # Update the message to show result
    result_emoji = "✅" if correct else "❌"
    await query.edit_message_reply_markup(reply_markup=None)

    # Track session results
    if session_id and session_id in context.bot_data:
        session = context.bot_data[session_id]
        if correct:
            session["correct"] += 1
        else:
            session["wrong"] += 1
        session["answered"] += 1

        # Send summary when all cards answered
        if session["answered"] >= session["total"]:
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=(
                    f"📊 <b>نتيجة</b> — Session Results\n"
                    f"{'─' * 28}\n"
                    f"✅ Correct: {session['correct']}\n"
                    f"❌ Missed:  {session['wrong']}\n"
                ),
                parse_mode="HTML",
            )
            del context.bot_data[session_id]
