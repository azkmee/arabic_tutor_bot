# Arabic Tutor — Telegram Daily Review Bot

Sends a daily Telegram message with SRS flash cards due for review.

## Files
- `send_review.py` — main script
- `.github/workflows/daily_arabic.yml` — GitHub Actions cron schedule

## Setup

### 1. GitHub Secrets
In your repo → Settings → Secrets → Actions, add:

| Secret name | Value |
|---|---|
| `MONGO_URI` | Your MongoDB connection string |
| `TELEGRAM_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |

### 2. Schedule
Default: 9:00 AM Singapore time (01:00 UTC) every day.
Edit the cron line in `.github/workflows/daily_arabic.yml` to change the time.

### 3. Manual trigger
Go to Actions tab in GitHub → "Daily Arabic Review" → "Run workflow"

## Flash card format
- Picks due items from `item_progress` where `next_review_at <= now`
- Sends up to 3 preview cards with spoiler-hidden answers
- Rotates test types: meaning, plural, root derivation, fill-blank, grammar
- Links back to Claude for the full graded session
