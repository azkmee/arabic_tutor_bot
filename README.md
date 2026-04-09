# Arabic Tutor — Telegram SRS Bot

A spaced repetition Telegram bot for learning Arabic vocabulary, grammar, and reading comprehension. Runs as a long-running process on Oracle Cloud Free Tier VM with 3x daily scheduled reviews.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐
│  Claude Desktop  │     │  Oracle Cloud VM      │
│  + MCP Server    │────▶│  Telegram Bot (24/7)  │
│  (add words +    │     │  + 3x Daily Reviews   │
│   gen sentences) │     │  + /add command        │
└─────────────────┘     └──────────┬───────────┘
                                   │
                          ┌────────▼────────┐
                          │  MongoDB Atlas   │
                          └─────────────────┘
```

## Files

```
bot/
  main.py              # Entry point
  config.py            # Environment config, constants, schedules
  db.py                # All MongoDB operations
  handlers/
    review.py          # Review cards + callback buttons
    add_words.py       # /add command (queues to raw_words)
    commands.py        # /status, /help
  services/
    cards.py           # Card message builder
    srs.py             # SRS update logic
  jobs/
    scheduled_reviews.py  # 3x daily scheduled jobs
mcp_server/
  server.py            # MCP server for Claude Desktop
arabic-tutor.service   # systemd unit file
```

## Telegram Commands

| Command | Description |
|---|---|
| `/review` | Start an on-demand review session |
| `/add كلمة [meaning]` | Queue a word for processing |
| `/status` | View learning stats |
| `/help` | Show available commands |

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

### 4. Claude Desktop MCP Server

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
