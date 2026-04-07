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

### 2. Oracle Cloud VM Deployment

```bash
# SSH into your Oracle Cloud Always Free ARM instance
ssh opc@<your-vm-ip>

# Clone and set up
git clone <repo-url> arabic_tutor_bot
cd arabic_tutor_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # fill in secrets

# Install systemd service
sudo cp arabic-tutor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arabic-tutor

# Verify
sudo journalctl -u arabic-tutor -f
```

### 3. Claude Desktop MCP Server

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

## MongoDB Collections

Database: `arabic_learning`

### `vocabulary_items` — Master word/grammar data

| Field | Type | Description |
|---|---|---|
| `arabic` | string | Arabic word/phrase (unique key) |
| `transliteration` | string | Romanized pronunciation |
| `translation` | string | English meaning |
| `type` | string | `"word"` / `"grammar_rule"` / `"phrase"` |
| `root` | string | 3-letter Arabic root (optional) |
| `plural` | string | Arabic plural form (optional) |
| `example_sentence` | string | Arabic sentence using the word (optional) |
| `created_at` | datetime | When the word was added |

### `item_progress` — SRS state per word

| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Auto-generated |
| `arabic` | string | Reference to vocabulary_items |
| `srs_level` | int | Current SRS level (0–8) |
| `next_review_at` | string | ISO date `"YYYY-MM-DD"` for next review |
| `streak` | int | Consecutive correct answers |
| `last_test_type` | string | Last question type asked |
| `weak_test_types` | array | Question types user struggles with |

### `recall_log` — Historical review log

| Field | Type | Description |
|---|---|---|
| `item_id` | string | Reference to `item_progress._id` |
| `arabic` | string | The Arabic word reviewed |
| `test_type` | string | Question type used |
| `correct` | boolean | Whether answer was correct |
| `reviewed_at` | datetime | UTC timestamp |

### `raw_words` — Staging for Telegram input

| Field | Type | Description |
|---|---|---|
| `text` | string | Raw user input (e.g., `"كتاب book"`) |
| `source` | string | `"telegram"` or `"claude_desktop"` |
| `status` | string | `"pending"` or `"processed"` |
| `created_at` | datetime | When queued |

### `paragraphs` — AI-generated reading passages

| Field | Type | Description |
|---|---|---|
| `text_arabic` | string | Arabic paragraph |
| `text_english` | string | English translation |
| `words_used` | array | List of Arabic words used |
| `difficulty` | string | `"short"` or `"long"` |
| `created_at` | datetime | When generated |

## SRS Algorithm

Spaced repetition intervals (in days):

| Level | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| Days | 0 | 1 | 3 | 7 | 14 | 30 | 60 | 90 | 180 |

- **Correct**: Level up, extend interval, increment streak
- **Wrong**: Reset to level 0, review tomorrow, track weak test type
