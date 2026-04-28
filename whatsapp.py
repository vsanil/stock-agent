"""
whatsapp.py — CallMeBot send/receive helpers + WhatsApp command parser.
Supports stocks and crypto picks in the daily message.
"""

import os
import time
import urllib.parse
from datetime import date

import requests

from config_manager import get_config, update_config, update_config_multi, reset_config

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
MAX_MESSAGE_LENGTH = 1500
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


# ── Send message ──────────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    """
    Send a WhatsApp message via CallMeBot.
    Truncates to 1500 chars. Retries up to 3 times on failure.
    Returns True on success, False on all failures.
    """
    phone  = os.environ.get("CALLMEBOT_PHONE", "")
    apikey = os.environ.get("CALLMEBOT_APIKEY", "")

    if not phone or not apikey:
        print("[whatsapp] ERROR: CALLMEBOT_PHONE or CALLMEBOT_APIKEY not set.")
        return False

    # Truncate if needed
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

    encoded = urllib.parse.quote(text)
    url = f"{CALLMEBOT_URL}?phone={phone}&text={encoded}&apikey={apikey}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                print(f"[whatsapp] Message sent successfully (attempt {attempt}).")
                return True
            else:
                print(f"[whatsapp] Attempt {attempt} failed: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"[whatsapp] Attempt {attempt} exception: {exc}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    print("[whatsapp] All send attempts failed.")
    return False


# ── Format daily message ──────────────────────────────────────────────────────

def _conviction_bar(conviction: int) -> str:
    c = max(1, min(5, int(conviction)))
    return "★" * c + "☆" * (5 - c)


def format_daily_message(picks: dict, config: dict) -> str:
    """Build the formatted daily WhatsApp message from Claude picks (stocks + crypto)."""
    today = date.today().strftime("%a %b %d, %Y")
    short_budget       = config.get("short_term_budget", 25)
    long_budget        = config.get("long_term_budget", 50)
    crypto_st_budget   = config.get("crypto_short_budget", 20)
    crypto_lt_budget   = config.get("crypto_long_budget", 30)

    # Support both old flat structure and new nested stocks/crypto structure
    stocks = picks.get("stocks", picks)  # fallback to flat if no crypto
    crypto = picks.get("crypto", {})

    lines = [
        f"📊 Daily Picks — {today}",
        picks.get("daily_summary", ""),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📈 STOCKS — Short Term (${short_budget}/trade)",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, s in enumerate(stocks.get("short_term", []), 1):
        lines += [
            f"{i}. {s.get('ticker')} — {s.get('company')}",
            f"   Entry: ${s.get('entry_price')} | Target: ${s.get('target_price')} | Stop: ${s.get('stop_loss')}",
            f"   Alloc: ${s.get('allocation')} | {_conviction_bar(s.get('conviction', 3))}",
            f"   Why: {s.get('thesis')}",
            f"   Risk: {s.get('risk')}",
        ]

    lines += [
        "",
        f"🏦 STOCKS — Long Term (${long_budget}/mo DCA)",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, s in enumerate(stocks.get("long_term", []), 1):
        lines += [
            f"{i}. {s.get('ticker')} — {s.get('company')}",
            f"   Entry: ${s.get('entry_price')} | Target: ${s.get('target_price')}",
            f"   Alloc: ${s.get('allocation')} | Horizon: {s.get('horizon')} | {_conviction_bar(s.get('conviction', 3))}",
            f"   Why: {s.get('thesis')}",
        ]

    # Crypto section (only if picks contain crypto)
    if crypto:
        lines += [
            "",
            f"🪙 CRYPTO — Short Term (${crypto_st_budget}/trade, HIGH RISK)",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for i, c in enumerate(crypto.get("short_term", []), 1):
            lines += [
                f"{i}. {c.get('symbol')} — {c.get('name')}",
                f"   Entry: ${c.get('entry_price')} | Target: ${c.get('target_price')} | Stop: ${c.get('stop_loss')}",
                f"   Alloc: ${c.get('allocation')} | {_conviction_bar(c.get('conviction', 3))}",
                f"   Why: {c.get('thesis')}",
                f"   Risk: {c.get('risk')}",
            ]

        lines += [
            "",
            f"💎 CRYPTO — Long Term (${crypto_lt_budget}/mo DCA)",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for i, c in enumerate(crypto.get("long_term", []), 1):
            lines += [
                f"{i}. {c.get('symbol')} — {c.get('name')}",
                f"   Entry: ${c.get('entry_price')} | Target: ${c.get('target_price')}",
                f"   Alloc: ${c.get('allocation')} | Horizon: {c.get('horizon')} | {_conviction_bar(c.get('conviction', 3))}",
                f"   Why: {c.get('thesis')}",
            ]

    lines += [
        "",
        f"⚙ ST=${short_budget} LT=${long_budget} CST=${crypto_st_budget} CLT={crypto_lt_budget}",
        "💬 SET ST 30 | SET LT 75 | SET CST 20 | SET CLT 30",
        "   PAUSE | RESUME | STATUS | RESET | HELP",
        "",
        "⏱ Stocks ~15min delayed | Crypto realtime (CoinGecko)",
        "⚠ Not financial advice. Crypto is highly volatile.",
    ]

    return "\n".join(lines)


# ── Command handler ───────────────────────────────────────────────────────────

def handle_incoming_command(message_text: str) -> str:
    """
    Parse and execute a WhatsApp command string.
    Sends a confirmation message back and returns the reply text.
    """
    text = message_text.strip().upper()
    reply = _parse_and_execute(text)
    send_message(reply)
    return reply


def _parse_and_execute(text: str) -> str:
    """Parse command and return reply string."""

    # HELP
    if text == "HELP":
        return (
            "📋 Available commands:\n"
            "SET ST <n>       — stock short-term budget\n"
            "SET LT <n>       — stock long-term budget\n"
            "SET CST <n>      — crypto short-term budget\n"
            "SET CLT <n>      — crypto long-term budget\n"
            "SET ST 30 LT 75  — set multiple at once\n"
            "PAUSE            — stop daily picks\n"
            "RESUME           — restart daily picks\n"
            "STATUS           — show current config\n"
            "RESET            — restore default config\n"
            "HELP             — show this list"
        )

    # PAUSE
    if text == "PAUSE":
        update_config("enabled", False)
        return "⏸ Agent paused. Daily picks suspended. Send RESUME to restart."

    # RESUME
    if text == "RESUME":
        update_config("enabled", True)
        return "▶ Agent resumed. Daily picks will run tomorrow morning."

    # RESET
    if text == "RESET":
        config = reset_config()
        return (
            f"🔄 Config reset to defaults.\n"
            f"ST=${config['short_term_budget']} LT=${config['long_term_budget']}\n"
            f"Stop loss: {config['stop_loss_pct']}% | Target gain: {config['target_gain_pct']}%"
        )

    # STATUS
    if text == "STATUS":
        config = get_config()
        status = "✅ Active" if config.get("enabled") else "⏸ Paused"
        return (
            f"⚙ Current Config ({status}):\n"
            f"Stock ST budget:  ${config.get('short_term_budget')}\n"
            f"Stock LT budget:  ${config.get('long_term_budget')}\n"
            f"Crypto ST budget: ${config.get('crypto_short_budget', 20)}\n"
            f"Crypto LT budget: ${config.get('crypto_long_budget', 30)}\n"
            f"Max stock ST:     {config.get('max_short_picks')}\n"
            f"Max stock LT:     {config.get('max_long_picks')}\n"
            f"Max crypto ST:    {config.get('max_crypto_short_picks', 2)}\n"
            f"Max crypto LT:    {config.get('max_crypto_long_picks', 2)}\n"
            f"Stop loss:        {config.get('stop_loss_pct')}%\n"
            f"Target gain:      {config.get('target_gain_pct')}%"
        )

    # SET ST/LT/CST/CLT <n>  — supports multiple keys at once
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
                "short_term_budget":  "Stock ST budget",
                "long_term_budget":   "Stock LT budget",
                "crypto_short_budget": "Crypto ST budget",
                "crypto_long_budget":  "Crypto LT budget",
            }
            lines = ["✅ Config updated:"]
            for k, v in updates.items():
                lines.append(f"{label_map.get(k, k)} → ${config[k]}")
            return "\n".join(lines)

    return "❓ Unknown command. Send HELP for options."


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test formatting with mock data
    mock_picks = {
        "daily_summary": "Market shows cautious optimism amid mixed earnings signals.",
        "short_term": [
            {
                "ticker": "AAPL", "company": "Apple Inc", "action": "BUY",
                "entry_price": 182.50, "target_price": 197.10, "stop_loss": 173.38,
                "allocation": 12.50, "conviction": 4,
                "thesis": "Technical breakout with strong volume confirms momentum.",
                "risk": "Macro headwinds could reverse trend quickly.",
            }
        ],
        "long_term": [
            {
                "ticker": "MSFT", "company": "Microsoft Corp", "action": "BUY",
                "entry_price": 415.00, "target_price": 500.00,
                "allocation": 16.67, "conviction": 5,
                "thesis": "Cloud growth and AI integration drive long-term value.",
                "horizon": "2-3 years",
            }
        ],
        "disclaimer": "For informational purposes only. Not financial advice.",
    }
    mock_config = {"short_term_budget": 25, "long_term_budget": 50}
    msg = format_daily_message(mock_picks, mock_config)
    print(msg)
    print(f"\nMessage length: {len(msg)} chars")
