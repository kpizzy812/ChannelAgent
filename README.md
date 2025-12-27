# ChannelAgent

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=for-the-badge&logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge)

**[README in Russian](README_RU.md)**

AI-powered Telegram channel content aggregator and restyler. Automatically monitors multiple Telegram channels, analyzes content relevance using GPT-4 Vision, and reposts curated content in your unique style.

## Features

- **Multi-Channel Monitoring** - Track unlimited Telegram channels via UserBot (Telethon)
- **AI Content Analysis** - GPT-4 Vision analyzes text and images for relevance scoring
- **Smart Content Filtering** - Configurable relevance threshold (1-10 scale)
- **Style Transformation** - AI restyling based on your writing samples
- **Moderation Interface** - Telegram bot with inline keyboard for content approval
- **Scheduled Publishing** - Queue posts for optimal timing (UTC+3 timezone)
- **Daily Crypto Digest** - Automated cryptocurrency price updates via CoinGecko
- **Telegram Formatting** - Full support for bold, italic, spoilers, quotes, and more

## Architecture

```
                    +------------------+
                    |   Source         |
                    |   Channels       |
                    +--------+---------+
                             |
                    +--------v---------+
                    |    UserBot       |
                    |   (Telethon)     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   AI Processor   |
                    |   (OpenAI GPT-4) |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
     +--------v---------+         +--------v---------+
     |   SQLite DB      |         |   Moderation     |
     |   (aiosqlite)    |         |   Bot (aiogram)  |
     +------------------+         +--------+---------+
                                           |
                                  +--------v---------+
                                  |   Target         |
                                  |   Channel        |
                                  +------------------+
```

### Core Modules

| Module | Technology | Purpose |
|--------|------------|---------|
| `userbot/` | Telethon | Monitor source channels, fetch new posts |
| `bot/` | aiogram 3.x | Admin interface, moderation, commands |
| `ai/` | OpenAI API | Content analysis, relevance scoring, restyling |
| `database/` | aiosqlite | Persistent storage, post history, settings |
| `scheduler/` | APScheduler | Scheduled tasks, daily digests, delayed posts |

## Tech Stack

- **Python 3.9+** - Async/await throughout
- **aiogram 3.x** - Modern Telegram Bot framework
- **Telethon** - Telegram MTProto UserBot client
- **OpenAI API** - GPT-4 Turbo + Vision for content analysis
- **aiosqlite** - Async SQLite database
- **APScheduler** - Background task scheduling
- **loguru** - Advanced logging with rotation
- **Pydantic** - Configuration validation

## Installation

### Prerequisites

- Python 3.9 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram API credentials (from [my.telegram.org](https://my.telegram.org))
- OpenAI API Key

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/ChannelAgent.git
   cd ChannelAgent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the application**
   ```bash
   python main.py
   ```

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Telegram Bot
BOT_TOKEN=your_bot_token_here
OWNER_ID=your_telegram_user_id

# Telegram UserBot (for channel monitoring)
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+1234567890

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4-turbo

# Content Settings
MONITORING_INTERVAL=300        # Check interval in seconds
RELEVANCE_THRESHOLD=6          # Minimum relevance score (1-10)

# Target Channel
TARGET_CHANNEL_ID=-100xxxxxxxxx

# Scheduling
DAILY_POST_TIME=09:00
TIMEZONE=Europe/Moscow
```

## Project Structure

```
src/
├── bot/                    # Telegram Bot (aiogram 3.x)
│   ├── handlers/           # Command & callback handlers
│   │   ├── commands.py     # /start, /help, /status
│   │   ├── moderation.py   # Post approval workflow
│   │   ├── channels.py     # Channel management
│   │   └── daily_posts.py  # Daily digest configuration
│   ├── keyboards/          # Inline & reply keyboards
│   └── states/             # FSM states
├── userbot/                # Channel Monitor (Telethon)
│   ├── client.py           # Telethon client setup
│   └── handlers/           # New message handlers
├── ai/                     # AI Processing (OpenAI)
│   ├── client.py           # OpenAI API wrapper
│   ├── analyzer/           # Content analysis
│   │   ├── relevance.py    # Relevance scoring
│   │   └── vision.py       # Image analysis
│   └── styler/             # Content restyling
│       └── formatter.py    # Telegram formatting
├── database/               # Data Layer (SQLite)
│   ├── models/             # Data models
│   └── crud/               # CRUD operations
├── scheduler/              # Task Scheduler (APScheduler)
│   └── tasks/              # Scheduled jobs
└── utils/                  # Utilities
    ├── config.py           # Configuration management
    └── logging_config.py   # Loguru setup
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize bot, show main menu |
| `/help` | Display help information |
| `/status` | Show monitoring status |
| `/channels` | Manage monitored channels |
| `/settings` | Configure bot settings |
| `/daily` | Configure daily digest |

## Moderation Workflow

1. **New Post Detected** - UserBot finds a new post in monitored channel
2. **AI Analysis** - GPT-4 Vision analyzes content and images
3. **Relevance Check** - Posts below threshold are auto-rejected
4. **Moderation Queue** - Relevant posts sent to owner with inline buttons:
   - Post Now
   - Schedule for Later
   - Edit Content
   - Reject

## License

This project is proprietary software. See [LICENSE](LICENSE) for details.

## Author

Developed with focus on clean architecture and async best practices.

---

*Built with aiogram 3.x, Telethon, and OpenAI GPT-4*
