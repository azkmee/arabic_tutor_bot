import os
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
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "")

# ── SRS ──────────────────────────────────────────────────────────────────────
SRS_INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 14, 5: 30, 6: 60, 7: 90, 8: 180}

TEST_TYPE_LABELS = {
    "meaning": "💬 What does this mean?",
    "plural": "📚 What is the plural (جمع)?",
    "fill_blank": "✏️ Fill in the blank",
    "root_derive": "🌱 Derive from the root",
    "grammar": "📐 Apply the grammar rule",
}

# ── Review session mix ───────────────────────────────────────────────────────
REVIEW_SESSION = {"vocab": 5, "grammar": 2, "sentence": 1}
