"""
telegram_notifier.py — Telegram Bot send/receive helpers + command parser.
Replaces whatsapp.py. Uses Telegram Bot API via plain requests (no heavy SDK).
"""

import os
import time
import requests
from datetime import date

from config_manager import get_config, update_config, update_config_multi, reset_config

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LENGTH = 4096   # Telegram limit (much larger than WhatsApp)
MAX_RETRIES = 3
RETRY_DELAY = 5


# ── Core send ─────────────────────────────────────────────────────────────────

def _bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN environment variable is not set.")
    return token

def _chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise EnvironmentError("TELEGRAM_CHAT_ID environment variable is not set.")
    return chat_id


def send_message(text: str, chat_id: str | None = None) -> bool:
    """
    Send a Telegram message. Splits messages > 4096 chars automatically.
    Retries up to 3 times on failure. Returns True on success.
    """
    token   = _bot_token()
    chat_id = chat_id or _chat_id()
    url     = TELEGRAM_API.format(token=token, method="sendMessage")

    # Split long messages
    chunks = [text[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",   # supports <b>, <i>, <code> tags
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                if resp.status_code == 200:
                    print(f"[telegram] Message chunk sent (attempt {attempt}).")
                    break
                else:
                    print(f"[telegram] Attempt {attempt} failed: HTTP {resp.status_code} — {resp.text}")
            except Exception as exc:
                print(f"[telegram] Attempt {attempt} exception: {exc}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
        else:
            print("[telegram] All send attempts failed for a chunk.")
            return False

    return True


def set_webhook(webhook_url: str) -> bool:
    """Register a Telegram webhook URL (call once after deploying to Render)."""
    token = _bot_token()
    url   = TELEGRAM_API.format(token=token, method="setWebhook")
    resp  = requests.post(url, json={"url": webhook_url}, timeout=10)
    data  = resp.json()
    if data.get("ok"):
        print(f"[telegram] Webhook set to {webhook_url}")
        return True
    print(f"[telegram] Failed to set webhook: {data}")
    return False


# ── Format daily message ──────────────────────────────────────────────────────

def _stars(conviction: int) -> str:
    c = max(1, min(5, int(conviction)))
    return "★" * c + "☆" * (5 - c)


def format_daily_message(picks: dict, config: dict) -> str:
    """Build the formatted daily Telegram message from Claude picks (stocks + crypto)."""
    today            = date.today().strftime("%a %b %d, %Y")
    short_budget     = config.get("short_term_budget", 25)
    long_budget      = config.get("long_term_budget", 50)
    crypto_st_budget = config.get("crypto_short_budget", 20)
    crypto_lt_budget = config.get("crypto_long_budget", 30)

    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})

    lines = [
        f"<b>📊 Daily Picks — {today}</b>",
        f"<i>{picks.get('daily_summary', '')}</i>",
        "",
        f"<b>📈 STOCKS — Short Term</b> (${short_budget}/trade)",
        "──────────────────",
    ]

    for i, s in enumerate(stocks.get("short_term", []), 1):
        lines += [
            f"{i}. <b>{s.get('ticker')}</b> — {s.get('company')}",
            f"   Entry: <code>${s.get('entry_price')}</code> | Target: <code>${s.get('target_price')}</code> | Stop: <code>${s.get('stop_loss')}</code>",
            f"   Alloc: ${s.get('allocation')} | {_stars(s.get('conviction', 3))}",
            f"   💡 {s.get('thesis')}",
            f"   ⚠️ {s.get('risk')}",
        ]

    lines += [
        "",
        f"<b>🏦 STOCKS — Long Term</b> (${long_budget}/mo DCA)",
        "──────────────────",
    ]
    for i, s in enumerate(stocks.get("long_term", []), 1):
        lines += [
            f"{i}. <b>{s.get('ticker')}</b> — {s.get('company')}",
            f"   Entry: <code>${s.get('entry_price')}</code> | Target: <code>${s.get('target_price')}</code>",
            f"   Alloc: ${s.get('allocation')} | Horizon: {s.get('horizon')} | {_stars(s.get('conviction', 3))}",
            f"   💡 {s.get('thesis')}",
        ]

    if crypto:
        lines += [
            "",
            f"<b>🪙 CRYPTO — Short Term</b> (${crypto_st_budget}/trade, HIGH RISK)",
            "──────────────────",
        ]
        for i, c in enumerate(crypto.get("short_term", []), 1):
            lines += [
                f"{i}. <b>{c.get('symbol')}</b> — {c.get('name')}",
                f"   Entry: <code>${c.get('entry_price')}</code> | Target: <code>${c.get('target_price')}</code> | Stop: <code>${c.get('stop_loss')}</code>",
                f"   Alloc: ${c.get('allocation')} | {_stars(c.get('conviction', 3))}",
                f"   💡 {c.get('thesis')}",
                f"   ⚠️ {c.get('risk')}",
            ]

        lines += [
            "",
            f"<b>💎 CRYPTO — Long Term</b> (${crypto_lt_budget}/mo DCA)",
            "──────────────────",
        ]
        for i, c in enumerate(crypto.get("long_term", []), 1):
            lines += [
                f"{i}. <b>{c.get('symbol')}</b> — {c.get('name')}",
                f"   Entry: <code>${c.get('entry_price')}</code> | Target: <code>${c.get('target_price')}</code>",
                f"   Alloc: ${c.get('allocation')} | Horizon: {c.get('horizon')} | {_stars(c.get('conviction', 3))}",
                f"   💡 {c.get('thesis')}",
            ]

    lines += [
        "",
        f"<code>ST=${short_budget} LT=${long_budget} CST=${crypto_st_budget} CLT=${crypto_lt_budget}</code>",
        "Commands: /set_st /set_lt /set_cst /set_clt /pause /resume /status /reset /help",
        "",
        "⏱ Stocks ~15min delayed | Crypto realtime",
        "⚠️ <i>Not financial advice. Crypto is highly volatile.</i>",
    ]

    return "\n".join(lines)


# ── Confirmation message (10:30 AM run) ──────────────────────────────────────

def format_confirmation_message(picks: dict, current_prices: dict) -> str:
    """
    Build the 10:30 AM check-in message.
    Compares entry prices from morning picks to current live prices.
    current_prices: { "AAPL": 185.20, "BTC": 66200, ... }
    """
    now = date.today().strftime("%a %b %d")
    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})

    def price_line(symbol: str, entry: float, target: float, stop: float | None) -> str:
        current = current_prices.get(symbol)
        if current is None or entry is None:
            return f"   {symbol}: <code>${entry}</code> → price unavailable"
        pct = ((current - entry) / entry) * 100
        arrow = "▲" if pct >= 0 else "▼"
        if stop and current <= stop:
            status = "🔴 STOP HIT"
        elif pct >= ((target - entry) / entry * 100) * 0.5:
            status = "✅ On track"
        elif pct < -2:
            status = "⚠️ Watch"
        else:
            status = "🟡 Neutral"
        return f"   {symbol}: <code>${entry}</code> → <code>${round(current,2)}</code> {arrow}{abs(pct):.1f}% {status}"

    lines = [
        f"<b>🕙 10:30 AM Check — {now}</b>",
        "",
        "<b>📈 STOCK SHORT TERM</b>",
    ]
    for s in stocks.get("short_term", []):
        lines.append(price_line(s.get("ticker",""), s.get("entry_price"), s.get("target_price"), s.get("stop_loss")))

    lines += ["", "<b>🏦 STOCK LONG TERM</b>"]
    for s in stocks.get("long_term", []):
        lines.append(price_line(s.get("ticker",""), s.get("entry_price"), s.get("target_price"), None))

    if crypto:
        lines += ["", "<b>🪙 CRYPTO SHORT TERM</b>"]
        for c in crypto.get("short_term", []):
            lines.append(price_line(c.get("symbol",""), c.get("entry_price"), c.get("target_price"), c.get("stop_loss")))

        lines += ["", "<b>💎 CRYPTO LONG TERM</b>"]
        for c in crypto.get("long_term", []):
            lines.append(price_line(c.get("symbol",""), c.get("entry_price"), c.get("target_price"), None))

    lines += [
        "",
        "🔴 Stop hit — exit  ✅ On track — hold  ⚠️ Watch closely",
        "<i>⚠️ Not financial advice.</i>",
    ]
    return "\n".join(lines)


# ── Command handler ───────────────────────────────────────────────────────────

def handle_incoming_command(message_text: str, chat_id: str | None = None) -> str:
    """Parse and execute a Telegram command. Sends reply and returns reply text."""
    text  = message_text.strip().upper()
    reply = _parse_and_execute(text)
    send_message(reply, chat_id=chat_id)
    return reply


def _parse_and_execute(text: str) -> str:
    """Parse command string and return reply."""

    # Telegram slash-commands (/help) or plain text (HELP) — normalise both
    text = text.lstrip("/").replace("_", " ")   # /set_st 30 → SET ST 30

    if text in ("HELP", "START"):
        return (
            "📋 <b>Available commands:</b>\n"
            "/set_st &lt;n&gt;   — stock short-term budget\n"
            "/set_lt &lt;n&gt;   — stock long-term budget\n"
            "/set_cst &lt;n&gt;  — crypto short-term budget\n"
            "/set_clt &lt;n&gt;  — crypto long-term budget\n"
            "/pause         — stop daily picks\n"
            "/resume        — restart daily picks\n"
            "/status        — show current config\n"
            "/reset         — restore default config\n"
            "/help          — show this list"
        )

    if text == "PAUSE":
        update_config("enabled", False)
        return "⏸ Agent paused. Daily picks suspended. Send /resume to restart."

    if text == "RESUME":
        update_config("enabled", True)
        return "▶️ Agent resumed. Daily picks will run tomorrow morning."

    if text == "RESET":
        config = reset_config()
        return (
            f"🔄 Config reset to defaults.\n"
            f"ST=${config['short_term_budget']} LT=${config['long_term_budget']}\n"
            f"CST=${config.get('crypto_short_budget', 20)} CLT=${config.get('crypto_long_budget', 30)}"
        )

    if text == "STATUS":
        config = get_config()
        status = "✅ Active" if config.get("enabled") else "⏸ Paused"
        return (
            f"<b>⚙️ Config ({status})</b>\n"
            f"Stock ST:   ${config.get('short_term_budget')}\n"
            f"Stock LT:   ${config.get('long_term_budget')}\n"
            f"Crypto ST:  ${config.get('crypto_short_budget', 20)}\n"
            f"Crypto LT:  ${config.get('crypto_long_budget', 30)}\n"
            f"Stop loss:  {config.get('stop_loss_pct')}%\n"
            f"Target gain:{config.get('target_gain_pct')}%"
        )

    # SET ST/LT/CST/CLT <n>
    if text.startswith("SET "):
        parts = text.split()
        key_map = {
            "ST":  "short_term_budget",
            "LT":  "long_term_budget",
            "CST": "crypto_short_budget",
            "CLT": "crypto_long_budget",
        }
        updates = {}
        i = 1
        while i < len(parts):
            if parts[i] in key_map and i + 1 < len(parts):
                try:
                    updates[key_map[parts[i]]] = float(parts[i + 1])
                    i += 2
                    continue
                except ValueError:
                    pass
            i += 1

        if updates:
            config = update_config_multi(updates)
            label_map = {
                "short_term_budget":   "Stock ST",
                "long_term_budget":    "Stock LT",
                "crypto_short_budget": "Crypto ST",
                "crypto_long_budget":  "Crypto LT",
            }
            lines = ["✅ <b>Config updated:</b>"]
            for k in updates:
                lines.append(f"{label_map.get(k, k)} → ${config[k]}")
            return "\n".join(lines)

    return "❓ Unknown command. Send /help for options."


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mock_picks = {
        "daily_summary": "Markets cautiously optimistic; crypto momentum building.",
        "stocks": {
            "short_term": [{
                "ticker": "AAPL", "company": "Apple Inc", "action": "BUY",
                "entry_price": 182.50, "target_price": 197.10, "stop_loss": 173.38,
                "allocation": 12.50, "conviction": 4,
                "thesis": "Breakout with volume confirms momentum.",
                "risk": "Macro headwinds could reverse quickly.",
            }],
            "long_term": [{
                "ticker": "MSFT", "company": "Microsoft Corp", "action": "BUY",
                "entry_price": 415.00, "target_price": 500.00,
                "allocation": 16.67, "conviction": 5,
                "thesis": "Cloud + AI growth drives long-term value.",
                "horizon": "2-3 years",
            }],
        },
        "crypto": {
            "short_term": [{
                "symbol": "BTC", "name": "Bitcoin", "action": "BUY",
                "entry_price": 65000, "target_price": 72000, "stop_loss": 61750,
                "allocation": 10.00, "conviction": 3,
                "thesis": "Momentum breakout above key resistance.",
                "risk": "High volatility; macro risk.",
            }],
            "long_term": [{
                "symbol": "ETH", "name": "Ethereum", "action": "BUY",
                "entry_price": 3200, "target_price": 5000,
                "allocation": 15.00, "conviction": 4,
                "thesis": "ETF inflows and staking yield drive demand.",
                "horizon": "12-18 months",
            }],
        },
        "disclaimer": "For informational purposes only. Not financial advice.",
    }
    mock_config = {
        "short_term_budget": 25, "long_term_budget": 50,
        "crypto_short_budget": 20, "crypto_long_budget": 30,
    }
    msg = format_daily_message(mock_picks, mock_config)
    print(msg)
    print(f"\nLength: {len(msg)} chars")
