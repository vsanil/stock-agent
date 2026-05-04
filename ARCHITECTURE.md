# Architecture & Local Setup Guide

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│  Cron: 8:00 AM · 10:30 AM · 3:30 PM (Mon–Fri)             │
│         + 8:00 AM Sat/Sun (crypto only)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │ run agent.py
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      agent.py                               │
│  detect_run_mode()                                          │
│  ┌──────────────┬────────────────┬──────────────────┐       │
│  │  morning     │  confirmation  │  close_check     │       │
│  │  weekly      │                │                  │       │
│  └──────┬───────┴───────┬────────┴───────┬──────────┘       │
└─────────┼───────────────┼────────────────┼──────────────────┘
          │               │                │
     ┌────┤               │                │
     ▼    ▼               ▼                ▼
┌─────────────┐  ┌───────────────┐  ┌───────────────┐
│ screener.py │  │ price_checker │  │ price_checker │
│ +600 tickers│  │    .py        │  │    .py        │
│ yfinance+ta │  └──────┬────────┘  └──────┬────────┘
│ +Finnhub    │         │                  │
└──────┬──────┘         ▼                  ▼
       │         ┌───────────────┐  ┌───────────────┐
       │         │ trade_logger  │  │ trade_logger  │
       │         │ check_close() │  │ check_close() │
       │         └──────┬────────┘  └───────────────┘
       │                │
┌──────┴──────┐         │ (target/stop alerts)
│ crypto_     │         │
│ screener.py │         ▼
│ CoinGecko   │  ┌─────────────────────────────────────────────┐
│ free API    │  │  telegram_notifier.py                       │
└──────┬──────┘  │  format_confirmation_message()              │
       │         │  format_weekly_recap_message()              │
       ▼         └─────────────────────────────────────────────┘
┌──────────────┐
│ ai_analyzer  │
│ .py          │
│              │
│ Claude Sonnet│  ← pick ranking, targets, stops, thesis
│ (retry Haiku)│
└──────┬───────┘
       ▼
┌──────────────────────┐
│ telegram_notifier.py │
│ format_daily_message │
│ send_message()       │
└──────────────────────┘
       │
       ▼ (user replies → Telegram → Render webhook)
┌──────────────────────────────────────────────────────────────┐
│                  webhook.py  (Render, free)                  │
│  POST /webhook → handle_incoming_command()                   │
│                  handle_callback_query()                     │
│  GET  /health  → returns config                              │
│  GET  /register → set_webhook(url)                           │
└──────────────────────────────────────────────────────────────┘
       │ all commands → telegram_notifier._parse_and_execute()
       │                → NL fallback: Claude Haiku
       ▼
┌──────────────────────────────────────────────────────────────┐
│               Persistence  (GitHub Gist)                     │
│  config.json       — budgets, risk, watchlist, exclusions    │
│  picks.json        — today's morning picks (same day TTL)    │
│  weekly_picks.json — Mon–Fri picks, auto-cleared weekly      │
│  trade_log.json    — open + closed trades, P&L history       │
│  pending_state.json — multi-step command context (60s TTL)   │
└──────────────────────────────────────────────────────────────┘
```

---

## How To Run Locally

### 1 — Clone and install dependencies
```bash
git clone https://github.com/vsanil/stock-agent.git
cd stock-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — Create a GitHub Gist (config store)
Go to [gist.github.com](https://gist.github.com), create a **secret** gist named `config.json` with:
```json
{
  "short_term_budget": 25,
  "long_term_budget": 50,
  "max_short_picks": 2,
  "max_long_picks": 3,
  "stop_loss_pct": 5,
  "target_gain_pct": 8,
  "enabled": true,
  "timezone": "America/New_York"
}
```
Copy the Gist ID from the URL.

### 3 — Create a GitHub Personal Access Token
Settings → Developer settings → Fine-grained tokens → scope: **Gist (read/write)**.

### 4 — Create a Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Get your chat ID: message [@userinfobot](https://t.me/userinfobot), copy the `Id` number.

### 5 — Get a Finnhub API key
Sign up free at [finnhub.io](https://finnhub.io), copy the key from the dashboard.

### 6 — Set environment variables
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export FINNHUB_API_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export GH_GIST_TOKEN="github_pat_..."
export GIST_ID="your_gist_id"
```

### 7 — Test with a dry run (no messages sent, no live screeners)
```bash
DRY_RUN=true MOCK_DATA=true python agent.py
```

### 8 — Run a real morning pick (sends Telegram message)
```bash
RUN_MODE=morning python agent.py
```

### 9 — Run the webhook locally (to test bot commands)
```bash
python webhook.py          # starts Flask on port 5000
```
Expose to Telegram with [ngrok](https://ngrok.com):
```bash
ngrok http 5000
# then register the tunnel URL once:
python webhook.py --set-webhook https://<ngrok-id>.ngrok.io/webhook
```

### 10 — Run individual modules for testing
```bash
python screener.py          # prints top short/long-term stock candidates
python crypto_screener.py   # prints top crypto candidates
```

---

## Run Modes

| Mode | Trigger Time | What it does |
|---|---|---|
| `morning` | 8:00 AM ET (Mon–Fri) | Full screener → Claude → send picks, open trades |
| `confirmation` | 10:30 AM ET (Mon–Fri) | Live prices vs morning picks, close checks, earnings warnings |
| `close_check` | 3:30 PM ET (Mon–Fri) | Silent trade close check — alerts only if target/stop hit |
| `weekly` | 8:00 AM ET (Sat) | Crypto morning picks + weekly P&L recap |

Override auto-detection with:
```bash
RUN_MODE=morning python agent.py       # force morning mode
RUN_MODE=confirmation python agent.py  # force confirmation mode
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `FINNHUB_API_KEY` | Yes | Finnhub free tier key |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID |
| `GH_GIST_TOKEN` | Yes | GitHub token with Gist read/write scope |
| `GIST_ID` | Yes | ID of your config Gist |
| `DRY_RUN` | No | `true` to print message instead of sending |
| `MOCK_DATA` | No | `true` to skip live screeners (fast test) |
| `RUN_MODE` | No | Force a specific run mode |
