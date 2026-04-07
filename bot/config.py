import os
from datetime import time
from dotenv import load_dotenv

load_dotenv()

# ── Secrets ──────────────────────────────────────────────────────────────────
MONGO_URI = os.environ["MONGO_URI"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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

# ── Schedules (UTC times — SGT is UTC+8) ─────────────────────────────────────
MORNING_TIME = time(1, 0)   # 9:00 AM SGT
LUNCH_TIME = time(5, 0)     # 1:00 PM SGT
DINNER_TIME = time(12, 0)   # 8:00 PM SGT
