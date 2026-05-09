# restaurant-bot-factory

Telegram bot **constructor** for HoReCa: restaurants, bars, cafes and banquet halls.

A single "factory" bot lets a venue owner spin up their **own** customer-facing
Telegram bot in a few minutes — no code, no servers, no deploys.

```
                        ┌──────────────────────────┐
   /start ▶  ┌──────────│   FACTORY BOT (you)      │  ← owner talks here
             │          │   (constructor / admin)  │
             │          └──────────┬───────────────┘
             │                     │  spawns + manages
             │                     ▼
             │           ┌─────────┴─────────┐
             │           │   CHILD BOTS      │
             │           │   one per venue   │  ← guests talk here
             │           └─────────┬─────────┘
             │  reservations       │
             ▼  notifications      ▼
        Telegram chat with owner   Reservation stored in DB
```

## What the owner gets

A standalone Telegram bot for their venue with:

- **Меню** — categorized menu with prices (and optional photos)
- **Бронирование стола / банкета** — multi-step booking flow (date, time, party
  size, name, phone) with instant notification to the owner
- **Контакты** — address, phone, working hours, map link
- **О нас** — short description set by the owner
- **🤖 Поддержка** — optional live AI chat (Claude / Anthropic) that knows the
  venue's name, description, address, phone and working hours and can answer
  guest questions when `CLAUDE_API_KEYS` is configured

The owner manages everything from inside the factory bot:

- create / pause / delete venues
- edit business info (name, type, description, address, phone, hours)
- add / remove menu items
- read incoming reservations

## What's *not* in MVP (on purpose)

- Online payments — only "leave a request, owner calls back"
- Multi-staff accounts per venue
- Custom UI translations (everything is Russian by default)
- Webhook mode / Telegram **Guest Bots** — see "Roadmap" below

## Requirements

- Python **3.11+**
- A Telegram bot token for the **factory bot** from
  [@BotFather](https://t.me/BotFather) — this is the bot owners log in to
- One Telegram bot token **per venue** (each owner gets their own from BotFather)

## Quick start

```bash
git clone https://github.com/ixumix/restaurant-bot-factory.git
cd restaurant-bot-factory

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env and set FACTORY_BOT_TOKEN

restaurant-bot-factory
# or: python -m bot_factory
```

Open the factory bot in Telegram, send `/start`, and follow the wizard.

## Configuration

All configuration is read from environment variables (a local `.env` file is
loaded automatically). See [`.env.example`](./.env.example) for the full list.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `FACTORY_BOT_TOKEN` | yes | – | Constructor bot's token from [@BotFather](https://t.me/BotFather). |
| `DATABASE_URL` | no | `sqlite+aiosqlite:///./data/factory.db` | Any SQLAlchemy async URL. |
| `ALLOWED_OWNER_IDS` | no | empty (everyone) | Comma-separated Telegram user IDs allowed to register as venue owners. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `TELEGRAM_PROXY_URL` | no | empty | Proxy URL for Telegram API requests, e.g. `http://user:pass@host:port` or `socks5://user:pass@host:port`. |
| `CLAUDE_API_KEYS` | no | empty | Comma-separated Anthropic API keys. Empty disables the support-chat button. With multiple keys, the bot rotates to the next on rate-limit / quota errors. |
| `CLAUDE_MODEL` | no | `claude-opus-4-5` | Anthropic model name. |
| `CLAUDE_BASE_URL` | no | `https://api.anthropic.com` | Override only when proxying Anthropic through your own gateway. |
| `CLAUDE_ANTHROPIC_VERSION` | no | `2023-06-01` | Value of the `anthropic-version` header. |
| `CLAUDE_MAX_TOKENS` | no | `1024` | Max tokens per single Claude reply. |
| `CLAUDE_HISTORY_LIMIT` | no | `10` | Max recent (user, assistant) pairs kept in the chat context. |
| `CLAUDE_TIMEOUT_SECONDS` | no | `60` | HTTP timeout for one Claude call. |
| `CLAUDE_SYSTEM_PROMPT` | no | empty | Override the built-in restaurant-support system prompt. |

If `api.telegram.org` is unavailable from your network, set `TELEGRAM_PROXY_URL`
in `.env`. System-wide VPN usually needs no extra configuration.

### Support chat (Claude)

Setting `CLAUDE_API_KEYS=key1,key2,key3` enables a `🤖 Поддержка` button in
every child bot's main menu. Tapping it opens a live Telegram chat where the
guest talks to Claude — the model is given the venue's name, description,
address, phone and working hours so answers stay grounded in real data.

When the API responds with a key-specific failure (HTTP `429` rate limit,
`402` insufficient credit, `401` / `403` invalid or revoked key), the bot
silently rotates to the next key in the list and retries. Each failing key
is parked on a short cooldown so it isn't immediately retried. Only when
every configured key is exhausted does the user see «Чат с ассистентом
сейчас недоступен».

## Docker

```bash
cp .env.example .env
# edit FACTORY_BOT_TOKEN

docker compose up --build
```

The SQLite database is mounted on a volume so your venues / menus / reservations
survive container restarts.

## Architecture

- **aiogram 3** for both factory and child bots, single Python process
- **SQLAlchemy 2.x async** + **aiosqlite** for storage (Postgres works too — set
  `DATABASE_URL`)
- **`BotManager`** holds the factory `Dispatcher` and one `Dispatcher`/`Bot`
  per active venue and runs them all concurrently with `asyncio.gather`
- New venues get spawned at runtime — no restart required
- Long-polling only (no public webhook needed in MVP)

```
src/bot_factory/
├── config.py          # pydantic-settings
├── db/                # SQLAlchemy models + repository helpers
├── factory/           # constructor bot (handlers, FSM, keyboards, texts)
├── child/             # child-bot template (handlers, FSM, keyboards, texts)
├── notifications.py   # owner notifications via the factory bot
├── manager.py         # spawns / stops child bots at runtime
└── __main__.py        # entry point
```

## Roadmap

Things the architecture is ready for but that aren't in the MVP yet:

- **Telegram Guest Bots** (May 2026 update). Switching child bots to webhook
  mode + setting `allow_guest_chats=true` lets a venue's bot answer when its
  `@username` is mentioned in any chat — handy for "куда сходить?" style
  group conversations.
- Online payments via Telegram Payments / YooKassa.
- Per-venue staff accounts (waiters / hosts) with limited permissions.
- Reservation calendar / table map.

## Development

```bash
pip install -e ".[dev]"

ruff check .
mypy src
pytest -q
```

CI runs the same three checks on every push and pull request.

## License

[MIT](./LICENSE)
