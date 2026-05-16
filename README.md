# Arabic Tutor — Telegram SRS Bot

A spaced repetition Telegram bot for learning Arabic vocabulary, grammar, and reading comprehension. Three daily scheduled reviews; each one pings you in Telegram with a button that opens a Mini App for swipe-to-rate flashcards and tap-to-translate passages.

## Architecture

```
┌────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ Claude Desktop │    │  Render web service  │    │  GitHub Pages       │
│ + MCP Server   │───▶│  Telegram bot +      │◀──▶│  React Mini App     │
│ (add words +   │    │  /api/* JSON API     │    │  (cards + passages) │
│  gen passages) │    │  + cron triggers     │    └────────────────────┘
└────────────────┘    └──────────┬───────────┘             ▲
                                 │                          │
                        ┌────────▼────────┐    Telegram WebApp button
                        │  MongoDB Atlas   │    opens this URL
                        └─────────────────┘
```

## Files

```
bot/
  main.py              # Entry point (Telegram + Starlette routes)
  api.py               # /api/* JSON endpoints for the Mini App
  config.py            # Environment config, constants, schedules
  db.py                # All MongoDB operations
  handlers/
    review.py          # send_webapp_notification + /review fallback
    add_words.py       # /add command (queues to raw_words)
    commands.py        # /status, /help
  services/
    cards.py           # Card message builder (Telegram text fallback)
    srs.py             # SRS update logic
  jobs/
    scheduled_reviews.py  # 3x daily scheduled jobs
webapp/                # React + Vite Mini App (hosted on GitHub Pages)
  src/
    App.tsx              # Session loader + stage routing
    screens/
      CardScreen.tsx     # Tap to flip, swipe to rate
      PassageScreen.tsx  # Tap-to-translate, add-to-recall
      SummaryScreen.tsx  # Session stats
    lib/
      api.ts             # Auth + JSON client for /api/*
      telegram.ts        # Telegram WebApp helpers
mcp_server/
  server.py            # MCP server for Claude Desktop
arabic-tutor.service   # systemd unit file
```

## Telegram Commands

| Command | Description |
|---|---|
| `/review` | Text-mode review fallback — one message per card |
| `/add كلمة [meaning]` | Queue a word for processing |
| `/status` | View learning stats |
| `/help` | Show available commands |

The primary review path is the **Mini App**: scheduled notifications include a "Start Review" button that opens the React app inline in Telegram. The `/review` text command is kept as a fallback for when the WebApp isn't available.

## Scheduled Reviews

| Time (SGT) | Session | Content |
|---|---|---|
| 9:00 AM | 🌅 Morning | 5 vocab + 2 grammar + 1 short sentence |
| 1:00 PM | 🌞 Lunch | 5 vocab + 2 grammar + 1 short sentence |
| 8:00 PM | 🌙 Dinner | 5 vocab + 2 grammar + 1 long passage |

## Adding Words

### Via Telegram
```
/add كتاب book
```
Words go to a staging collection (`raw_words`). Open Claude Desktop to format and add them to vocabulary.

### Via Claude Desktop
1. Drop an image of Arabic text into Claude Desktop
2. Claude extracts words, generates sentences + paragraphs
3. Claude calls MCP tools to add them to the database

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `MONGO_URI` | MongoDB Atlas connection string |
| `TELEGRAM_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |

### 2. Deploy to Render.com (Recommended)

1. Push this repo to GitHub
2. Go to [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**
3. Connect your GitHub repo and select it
4. Render reads `render.yaml` and creates:
   - A **web service** (webhook handler for Telegram)
   - **3 cron jobs** (morning/lunch/dinner review triggers)
5. Set environment variables in the Render dashboard:
   - `MONGO_URI` — your MongoDB Atlas connection string
   - `TELEGRAM_TOKEN` — from @BotFather
   - `TELEGRAM_CHAT_ID` — your chat ID
   - `WEB_APP_URL` — your GitHub Pages URL, e.g. `https://<user>.github.io/arabic_tutor_bot/` (leave blank to fall back to the message-per-card flow)
   - `WEB_APP_ORIGIN` — `https://<user>.github.io` (origin only, no path) for CORS
   - `WEBHOOK_SECRET` and `TRIGGER_SECRET` are auto-generated

The bot uses **webhooks** (not polling) — Telegram sends messages to your Render URL. The service wakes up on each message and handles it instantly. Cron jobs trigger scheduled reviews by hitting `/trigger/morning`, `/trigger/lunch`, `/trigger/dinner` endpoints.

#### Running locally

For local development, the bot falls back to **polling mode** when `RENDER_EXTERNAL_URL` is not set:

```bash
cp .env.example .env
nano .env  # fill in MONGO_URI, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
pip install -r requirements.txt
python -m bot.main
```

### 3. Alternative: Oracle Cloud VM

```bash
ssh opc@<your-vm-ip>
git clone <repo-url> arabic_tutor_bot && cd arabic_tutor_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env

sudo cp arabic-tutor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arabic-tutor
sudo journalctl -u arabic-tutor -f
```

Uses polling mode (no `RENDER_EXTERNAL_URL`). Scheduled reviews run via APScheduler in-process.

### 4. Mini App on GitHub Pages

The frontend (`webapp/`) deploys to GitHub Pages via `.github/workflows/deploy-webapp.yml`:

1. In the repo's **Settings → Pages**, set Source to "GitHub Actions".
2. In **Settings → Secrets and variables → Actions**, add:
   - `VITE_API_BASE` — your Render service URL (e.g. `https://arabic-tutor-bot.onrender.com`)
3. Push to `main` (or run the workflow manually). The Mini App publishes to `https://<user>.github.io/<repo>/`.
4. Set `WEB_APP_URL` in Render to that URL, and `WEB_APP_ORIGIN` to `https://<user>.github.io` for CORS.

Local dev for the Mini App:

```bash
cd webapp
cp .env.example .env
# set VITE_API_BASE to the running bot's URL (or a tunnel like ngrok)
npm install
npm run dev
```

Telegram only allows `https://` URLs in WebApp buttons, so to test locally you need a tunnel (ngrok, cloudflared, etc.) and a development bot.

### 5. Claude Desktop MCP Server

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "arabic-tutor": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/arabic_tutor_bot",
      "env": {
        "MONGO_URI": "your-mongo-uri"
      }
    }
  }
}
```

## MongoDB Collections (Canonical Schema)

Database: `arabic_learning`

### `vocabulary_items` — Master word/grammar data

| Field | Type | Required | Description |
|---|---|---|---|
| `arabic` | string | yes | Arabic word/phrase with tashkeel (unique key) |
| `transliteration` | string | yes | Romanized pronunciation |
| `translation` | string | yes | English meaning |
| `type` | string | yes | `noun`, `verb`, `adjective`, `adverb`, `preposition`, `particle`, `phrase`, `grammar_rule` |
| `root` | string | | Arabic root (e.g. `"ك ت ب"`). Enables root_derive test |
| `plural` | string | | Arabic plural form. Enables plural test |
| `gender` | string | | `"masculine"` or `"feminine"` |
| `verb_form` | int | | Arabic verb form (1–10), verbs only |
| `example_sentence` | string | | Arabic sentence using the word. Enables fill_blank test |
| `example_translation` | string | | English translation of example sentence |
| `tags` | array | | Freeform tags: `["MSA", "beginner", "school"]` |
| `source` | string | | How it was added: `"image"`, `"telegram"`, `"bulk_import"` |
| `created_at` | datetime | | When the word was added |

### `item_progress` — SRS state per word

| Field | Type | Default | Description |
|---|---|---|---|
| `arabic` | string | | Reference to `vocabulary_items.arabic` (unique) |
| `srs_level` | int | 0 | Current SRS level (0–8) |
| `next_review_at` | string | today | ISO date `"YYYY-MM-DD"` for next review |
| `ease_factor` | float | 2.5 | SM-2 style per-word difficulty multiplier (1.3–3.0) |
| `streak` | int | 0 | Consecutive correct answers |
| `lapse_count` | int | 0 | Times reset to level 0. Word is a "leech" after 4 lapses |
| `last_test_type` | string | `""` | Last question type (avoids consecutive repeats) |
| `weak_test_types` | array | `[]` | Test types user struggles with (auto-pruned on improvement) |
| `test_type_stats` | object | `{}` | Per-type accuracy: `{"meaning": {"correct": 12, "wrong": 1}}` |
| `last_reviewed_at` | datetime | null | When user last reviewed this word |
| `created_at` | datetime | | When this progress record was created |

### `recall_log` — Review history (append-only)

| Field | Type | Description |
|---|---|---|
| `item_progress_id` | string | Reference to `item_progress._id` |
| `arabic` | string | The Arabic word reviewed |
| `test_type` | string | Question type used |
| `correct` | boolean | Whether answer was correct |
| `quality` | int | 0–5 (SM-2 scale). Default: 4 if correct, 1 if wrong |
| `session_type` | string | `"morning"`, `"lunch"`, `"dinner"`, `"on_demand"` |
| `srs_level_before` | int | SRS level before this review (for analytics) |
| `reviewed_at` | datetime | UTC timestamp |

### `raw_words` — Staging for unprocessed input

| Field | Type | Description |
|---|---|---|
| `text` | string | Raw user input (e.g., `"كتاب book"`) |
| `source` | string | `"telegram"` or `"image"` |
| `status` | string | `"pending"`, `"processed"`, or `"rejected"` |
| `processed_at` | datetime | When status changed from pending |
| `vocabulary_item_arabic` | string | Which vocabulary_item was created (traceability) |
| `created_at` | datetime | When queued |

### `passages` — Reading comprehension passages

| Field | Type | Description |
|---|---|---|
| `title` | string | Short title for display |
| `text_arabic` | string | Arabic passage text (canonical field name) |
| `text_english` | string | English translation |
| `words_used` | array | Arabic words from vocabulary used in passage |
| `comprehension_questions` | array | Arabic comprehension questions |
| `difficulty` | string | `"short"` or `"long"` |
| `last_shown_at` | datetime | When last displayed (for least-recently-shown selection) |
| `times_shown` | int | Total display count |
| `created_at` | datetime | When generated |

## SRS Algorithm

Base intervals (in days):

| Level | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| Days | 0 | 1 | 3 | 7 | 14 | 30 | 60 | 90 | 180 |

Actual interval = `base_interval × (ease_factor / 2.5)`, rounded to nearest day.

- **Correct**: Level up, ease_factor +0.1 (max 3.0), increment streak
- **Wrong**: Reset to level 0, ease_factor -0.2 (min 1.3), review tomorrow, lapse_count +1
- **Leech**: After 4 lapses, word is flagged in /status
- **Test selection**: Weighted by per-type accuracy — weaker types appear more often
- **Weak type pruning**: Removed from weak list after 2+ consecutive correct answers
