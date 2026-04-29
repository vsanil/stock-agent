"""
telegram_notifier.py — Telegram Bot send/receive helpers + command parser.
Replaces whatsapp.py. Uses Telegram Bot API via plain requests (no heavy SDK).
"""

import os
import time
import requests
from datetime import date

from config_manager import get_config, update_config, update_config_multi, reset_config, load_picks

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


def _p(price) -> str:
    """Format a price cleanly: strip .00 only, commas for thousands."""
    if price is None:
        return "—"
    f = float(price)
    if f >= 1000:
        # 65000 → 65,000  |  65432.5 → 65,432.50
        return f"{f:,.0f}" if f == int(f) else f"{f:,.2f}"
    # 478.14 → 478.14  |  495.00 → 495  |  244.30 → 244.30
    s = f"{f:.2f}"
    return s[:-3] if s.endswith(".00") else s


def _upside(entry, target) -> str:
    """Return (+X.X%) or (-X.X%) string."""
    try:
        pct = (float(target) - float(entry)) / float(entry) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"
    except Exception:
        return ""


def _short_company(name: str, max_len: int = 22) -> str:
    """Trim long company names at a word boundary so lines stay compact."""
    if not name:
        return ""
    # Strip common suffixes first to save characters
    for suffix in (", Inc.", " Inc.", " Corp.", " Corporation", " & Co.", " Co.", " Ltd.", " plc"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name if len(name) <= max_len else name[:max_len].rsplit(" ", 1)[0] + "…"


def format_daily_message(picks: dict, config: dict) -> str:
    """Build the formatted daily Telegram message from Claude picks (stocks + crypto)."""
    today            = date.today().strftime("%a %b %d, %Y")
    short_budget     = config.get("short_term_budget", 25)
    long_budget      = config.get("long_term_budget", 50)
    crypto_st_budget = config.get("crypto_short_budget", 20)
    crypto_lt_budget = config.get("crypto_long_budget", 30)

    stocks    = picks.get("stocks", picks)
    crypto    = picks.get("crypto", {})
    st_picks  = stocks.get("short_term", [])
    lt_picks  = stocks.get("long_term", [])
    cst_picks = crypto.get("short_term", [])
    clt_picks = crypto.get("long_term", [])

    lines = [
        f"<b>📊 Daily Picks — {today}</b>",
        f"<i>{picks.get('daily_summary', '')}</i>",
    ]

    # ── Short-term stocks ─────────────────────────────────────────────────────
    if st_picks:
        lines += ["", f"<b>📈 Short Term</b>  <i>${short_budget}/trade</i>"]
        for i, s in enumerate(st_picks, 1):
            entry, target, stop = s.get("entry_price"), s.get("target_price"), s.get("stop_loss")
            earnings_tag = f"  🗓️ Earnings {s['earnings_date']}" if s.get("earnings_date") else ""
            alloc = s.get("allocation")
            alloc_str = f"  · invest <code>${_p(alloc)}</code>" if alloc is not None else ""
            lines += [
                f"{i}. <b>{s.get('ticker')}</b> · {_short_company(s.get('company', ''))}  {_stars(s.get('conviction', 3))}{earnings_tag}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  stop <code>${_p(stop)}</code>{alloc_str}",
                f"   {s.get('thesis')}",
            ]

    # ── Long-term stocks ──────────────────────────────────────────────────────
    if lt_picks:
        lines += ["", f"<b>🏦 Long Term</b>  <i>${long_budget}/mo DCA</i>"]
        for i, s in enumerate(lt_picks, 1):
            entry, target = s.get("entry_price"), s.get("target_price")
            alloc = s.get("allocation")
            alloc_str = f"  · DCA <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
            lines += [
                f"{i}. <b>{s.get('ticker')}</b> · {_short_company(s.get('company', ''))}  {_stars(s.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  · {s.get('horizon')}{alloc_str}",
                f"   {s.get('thesis')}",
            ]

    # ── Crypto short-term ─────────────────────────────────────────────────────
    if cst_picks:
        lines += ["", f"<b>🪙 Crypto Short Term</b>  <i>${crypto_st_budget}/trade · HIGH RISK</i>"]
        for i, c in enumerate(cst_picks, 1):
            entry, target, stop = c.get("entry_price"), c.get("target_price"), c.get("stop_loss")
            alloc = c.get("allocation")
            alloc_str = f"  · invest <code>${_p(alloc)}</code>" if alloc is not None else ""
            lines += [
                f"{i}. <b>{c.get('symbol')}</b> · {_short_company(c.get('name', ''))}  {_stars(c.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  stop <code>${_p(stop)}</code>{alloc_str}",
                f"   {c.get('thesis')}",
            ]

    # ── Crypto long-term ──────────────────────────────────────────────────────
    if clt_picks:
        lines += ["", f"<b>💎 Crypto Long Term</b>  <i>${crypto_lt_budget}/mo DCA</i>"]
        for i, c in enumerate(clt_picks, 1):
            entry, target = c.get("entry_price"), c.get("target_price")
            alloc = c.get("allocation")
            alloc_str = f"  · DCA <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
            lines += [
                f"{i}. <b>{c.get('symbol')}</b> · {_short_company(c.get('name', ''))}  {_stars(c.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  · {c.get('horizon')}{alloc_str}",
                f"   {c.get('thesis')}",
            ]

    # ── Footer ────────────────────────────────────────────────────────────────
    has_crypto_picks = bool(cst_picks or clt_picks)
    if has_crypto_picks:
        budget_line = (f"<code>ST ${short_budget} · LT ${long_budget}/mo · "
                       f"CST ${crypto_st_budget} · CLT ${crypto_lt_budget}/mo</code>")
    else:
        budget_line = f"<code>ST ${short_budget}/trade · LT ${long_budget}/mo DCA</code>"

    lines += [
        "",
        budget_line,
        "<i>⚠️ Not financial advice. /status · /help</i>",
    ]
    return "\n".join(lines)


# ── Confirmation message (10:30 AM run) ──────────────────────────────────────

def format_confirmation_message(picks: dict, current_prices: dict) -> str:
    """
    Build the 10:30 AM check-in message.
    Compares entry prices from morning picks to current live prices.
    """
    now    = date.today().strftime("%a %b %d")
    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})

    def price_line(symbol: str, entry, target, stop) -> str:
        current = current_prices.get(symbol)
        if current is None or entry is None:
            return f"   <b>{symbol}</b>  price unavailable"
        pct   = (current - float(entry)) / float(entry) * 100
        arrow = "▲" if pct >= 0 else "▼"
        sign  = ""   # arrow already implies direction
        if stop and current <= float(stop):
            badge = "🔴 STOP HIT"
        elif target and pct >= (float(target) - float(entry)) / float(entry) * 100 * 0.5:
            badge = "✅ On track"
        elif pct < -2:
            badge = "⚠️ Watch"
        else:
            badge = "🟡 Neutral"
        return (f"   <b>{symbol}</b>  <code>${_p(entry)}</code> → <code>${_p(current)}</code> "
                f"{arrow}{sign}{abs(pct):.1f}%  {badge}")

    st = stocks.get("short_term", [])
    lt = stocks.get("long_term", [])
    cst = crypto.get("short_term", [])
    clt = crypto.get("long_term", [])

    lines = [f"<b>🕙 10:30 AM Check — {now}</b>"]

    if st:
        lines += ["", "<b>📈 Short Term</b>"]
        for s in st:
            lines.append(price_line(s.get("ticker", ""), s.get("entry_price"), s.get("target_price"), s.get("stop_loss")))

    if lt:
        lines += ["", "<b>🏦 Long Term</b>"]
        for s in lt:
            lines.append(price_line(s.get("ticker", ""), s.get("entry_price"), s.get("target_price"), None))

    if cst:
        lines += ["", "<b>🪙 Crypto Short Term</b>"]
        for c in cst:
            lines.append(price_line(c.get("symbol", ""), c.get("entry_price"), c.get("target_price"), c.get("stop_loss")))

    if clt:
        lines += ["", "<b>💎 Crypto Long Term</b>"]
        for c in clt:
            lines.append(price_line(c.get("symbol", ""), c.get("entry_price"), c.get("target_price"), None))

    lines += ["", "🔴 exit  ✅ hold  ⚠️ watch  🟡 wait", "<i>⚠️ Not financial advice.</i>"]
    return "\n".join(lines)


# ── Weekly recap (Saturday morning) ──────────────────────────────────────────

def format_weekly_recap_message(recap: dict) -> str:
    """
    Compact Saturday recap. recap comes from performance_tracker.build_weekly_recap().
    Keeps it to ~12 lines — wins, avg return vs S&P, best/worst pick.
    """
    from datetime import date
    week_end = date.today().strftime("%b %d")

    def _section(label: str, stats: dict | None, spy: float | None = None) -> list[str]:
        if not stats:
            return [f"{label}: no data this week"]
        win_pct = int(stats["wins"] / stats["count"] * 100)
        avg     = stats["avg_return"]
        sign    = "+" if avg >= 0 else ""
        emoji   = "🟢" if avg > 0 else ("🔴" if avg < -1 else "🟡")

        best_sym,  best_r  = stats["best"]
        worst_sym, worst_r = stats["worst"]
        best_sign  = "+" if best_r  >= 0 else ""
        worst_sign = "+" if worst_r >= 0 else ""

        bench = ""
        if spy is not None:
            vs      = round(avg - spy, 1)
            vs_sign = "+" if vs >= 0 else ""
            spy_sign = "+" if spy >= 0 else ""
            bench = f" vs S&P {spy_sign}{spy}% ({vs_sign}{vs}%)"

        return [
            f"<b>{label}</b> — {stats['count']} picks, {win_pct}% wins",
            f"Best: <b>{best_sym}</b> {best_sign}{best_r}%  Worst: <b>{worst_sym}</b> {worst_sign}{worst_r}%",
            f"Avg: {sign}{avg}%{bench} {emoji}",
        ]

    lines = [
        f"<b>📅 Week of {week_end} — Recap</b>",
        "",
    ]
    lines += _section("📈 Stocks", recap.get("stocks"), recap.get("spy_return"))
    lines += [""]
    lines += _section("🪙 Crypto", recap.get("crypto"))
    lines += [
        "",
        "<i>Entry vs Friday close — not actual trade results.</i>",
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

    if text == "PERF":
        from trade_logger import get_performance_stats
        stock_stats  = get_performance_stats("stock")
        crypto_stats = get_performance_stats("crypto")

        if not stock_stats and not crypto_stats:
            return "📭 No closed trades yet. Check back after your first picks are resolved."

        def _stat_block(label: str, s: dict) -> str:
            if not s:
                return f"{label}: no closed trades yet"
            sign     = "+" if s["avg_return"] >= 0 else ""
            gain_sign = "+" if s["total_gain_usd"] >= 0 else ""
            best_sym, best_r   = s["best"]
            worst_sym, worst_r = s["worst"]
            return (
                f"<b>{label}</b> — {s['count']} trades  {s['win_rate']}% wins\n"
                f"Avg: {sign}{s['avg_return']}%  "
                f"Best: <b>{best_sym}</b> {'+' if best_r >= 0 else ''}{best_r}%  "
                f"Worst: <b>{worst_sym}</b> {'+' if worst_r >= 0 else ''}{worst_r}%\n"
                f"✅ {s['targets_hit']} targets  🔴 {s['stops_hit']} stops  ⏱ {s['expired']} expired\n"
                f"P&L: <code>{gain_sign}${abs(s['total_gain_usd']):.2f}</code> "
                f"on <code>${s['total_deployed_usd']:.0f}</code> deployed"
            )

        open_line = ""
        if stock_stats and stock_stats["open_count"]:
            open_line = f"\n\n<i>{stock_stats['open_count']} trade(s) still open</i>"

        lines = ["<b>📊 All-Time Performance</b>", ""]
        lines.append(_stat_block("📈 Stocks", stock_stats))
        lines += ["", _stat_block("🪙 Crypto", crypto_stats)]
        if open_line:
            lines.append(open_line)
        return "\n".join(lines)

    if text == "PRICES":
        picks = load_picks()
        if not picks:
            return "📭 No picks found for today yet. Check back after 8 AM ET."
        try:
            from price_checker import get_current_prices
            current_prices = get_current_prices(picks)
            return format_confirmation_message(picks, current_prices)
        except Exception as exc:
            return f"⚠️ Could not fetch prices: {exc}"

    if text in ("HELP", "START"):
        return (
            "📋 <b>Available commands:</b>\n"
            "/prices        — live prices for today's picks\n"
            "/perf          — all-time performance stats\n"
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
