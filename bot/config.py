import os
import re
from datetime import time
from dotenv import load_dotenv

load_dotenv()

# ── Secrets ──────────────────────────────────────────────────────────────────
MONGO_URI = os.environ["MONGO_URI"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── Render / Webhook ─────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 10000))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
# Telegram only allows alphanumeric, underscore, hyphen (1-256 chars)
_raw_webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
WEBHOOK_SECRET = re.sub(r"[^A-Za-z0-9_\-]", "", _raw_webhook_secret)[:256]
TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "")

# ── SRS ──────────────────────────────────────────────────────────────────────
SRS_INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 14, 5: 30, 6: 60, 7: 90, 8: 180}

# Ease factor bounds (SM-2 style per-word difficulty)
EASE_FACTOR_DEFAULT = 2.5
EASE_FACTOR_MIN = 1.3
EASE_FACTOR_MAX = 3.0
EASE_FACTOR_CORRECT = 0.1   # added on correct
EASE_FACTOR_WRONG = -0.2    # added on wrong

# Leech threshold: word is flagged after this many lapses (resets to level 0)
LEECH_THRESHOLD = 4

# ── Valid vocabulary types ───────────────────────────────────────────────────
VOCAB_TYPES = {"noun", "verb", "adjective", "adverb", "preposition", "particle", "phrase"}
GRAMMAR_TYPES = {"grammar_rule"}
ALL_WORD_TYPES = VOCAB_TYPES | GRAMMAR_TYPES

TEST_TYPE_LABELS = {
    "meaning": "💬 What does this mean?",
    "plural": "📚 What is the plural (جمع)?",
    "fill_blank": "✏️ Fill in the blank",
    "root_derive": "🌱 Derive from the root",
    "grammar": "📐 Apply the grammar rule",
}

# ── Review session mix ───────────────────────────────────────────────────────
REVIEW_SESSION = {"vocab": 5, "grammar": 2, "sentence": 1}
