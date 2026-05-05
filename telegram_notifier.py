"""
telegram_notifier.py — Telegram Bot send/receive helpers + command parser.
Replaces whatsapp.py. Uses Telegram Bot API via plain requests (no heavy SDK).
"""

import os
import time
import html
import threading
import requests
from datetime import date

from config_manager import (
    get_config, update_config, update_config_multi, reset_config, load_picks,
    load_pending_state, save_pending_state, clear_pending_state,
)


def _esc(text) -> str:
    """HTML-escape dynamic content so <, >, & don't break Telegram's parser."""
    return html.escape(str(text)) if text else ""

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

    # Split long messages — always break at newlines to avoid splitting inside HTML tags
    def _safe_split(txt: str, limit: int) -> list[str]:
        if len(txt) <= limit:
            return [txt]
        parts = []
        while txt:
            if len(txt) <= limit:
                parts.append(txt)
                break
            split_at = txt.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit        # no newline found — hard cut as last resort
            parts.append(txt[:split_at])
            txt = txt[split_at:].lstrip("\n")
        return parts

    chunks = _safe_split(text, MAX_MESSAGE_LENGTH)

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


def send_inline_keyboard(text: str, buttons: list[list[dict]],
                         chat_id: str | None = None) -> bool:
    """Send a message with an inline keyboard for user selection."""
    token   = _bot_token()
    chat_id = chat_id or _chat_id()
    url     = TELEGRAM_API.format(token=token, method="sendMessage")
    payload = {
        "chat_id":      chat_id,
        "text":         text,
        "parse_mode":   "HTML",
        "reply_markup": {"inline_keyboard": buttons},
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.status_code == 200
    except Exception as exc:
        print(f"[telegram] send_inline_keyboard error: {exc}")
        return False


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a Telegram callback query (dismisses the loading spinner)."""
    token = _bot_token()
    url   = TELEGRAM_API.format(token=token, method="answerCallbackQuery")
    try:
        requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=10)
    except Exception:
        pass


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

    # ── Macro context line ────────────────────────────────────────────────────
    macro_parts = []
    m = picks.get("macro_context", {})
    if m.get("spy_pct") is not None:
        sign = "+" if m["spy_pct"] >= 0 else ""
        macro_parts.append(f"SPY {sign}{m['spy_pct']}%")
    if m.get("tnx_yield") is not None:
        macro_parts.append(f"10Y {m['tnx_yield']}%")
    if m.get("vix") is not None:
        macro_parts.append(f"VIX {m['vix']}")
    macro_line = f"📉 <b>Macro:</b> {' · '.join(macro_parts)}" if macro_parts else ""

    lines = [
        f"<b>📊 Daily Picks — {today}</b>",
        f"<i>{_esc(picks.get('daily_summary', ''))}</i>",
    ]
    if macro_line:
        lines.append(macro_line)

    def _pick_row_st(i, s):
        entry, target, stop = s.get("entry_price"), s.get("target_price"), s.get("stop_loss")
        earnings_tag = f"  🗓 {_esc(s['earnings_date'])}" if s.get("earnings_date") else ""
        alloc = s.get("allocation")
        alloc_str = f"  <code>${_p(alloc)}</code>" if alloc is not None else ""
        return (
            f"<b>{_esc(s.get('ticker'))}</b>  {_stars(s.get('conviction', 3))}  "
            f"<i>{_esc(_short_company(s.get('company', '')))}</i>{earnings_tag}\n"
            f"<code>${_p(entry)}</code> → <code>${_p(target)}</code>  "
            f"<i>{_upside(entry, target)}</i>  ·  stop <code>${_p(stop)}</code>{alloc_str}\n"
            f"<i>{_esc(s.get('thesis'))}</i>"
        )

    def _pick_row_lt(i, s):
        entry, target = s.get("entry_price"), s.get("target_price")
        alloc = s.get("allocation")
        alloc_str = f"  <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
        return (
            f"<b>{_esc(s.get('ticker'))}</b>  {_stars(s.get('conviction', 3))}  "
            f"<i>{_esc(_short_company(s.get('company', '')))}</i>\n"
            f"<code>${_p(entry)}</code> → <code>${_p(target)}</code>  "
            f"<i>{_upside(entry, target)}</i>  ·  {_esc(s.get('horizon'))}{alloc_str}\n"
            f"<i>{_esc(s.get('thesis'))}</i>"
        )

    def _pick_row_cst(i, c):
        entry, target, stop = c.get("entry_price"), c.get("target_price"), c.get("stop_loss")
        alloc = c.get("allocation")
        alloc_str = f"  <code>${_p(alloc)}</code>" if alloc is not None else ""
        return (
            f"<b>{_esc(c.get('symbol'))}</b>  {_stars(c.get('conviction', 3))}  "
            f"<i>{_esc(_short_company(c.get('name', '')))}</i>\n"
            f"<code>${_p(entry)}</code> → <code>${_p(target)}</code>  "
            f"<i>{_upside(entry, target)}</i>  ·  stop <code>${_p(stop)}</code>{alloc_str}\n"
            f"<i>{_esc(c.get('thesis'))}</i>"
        )

    def _pick_row_clt(i, c):
        entry, target = c.get("entry_price"), c.get("target_price")
        alloc = c.get("allocation")
        alloc_str = f"  <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
        return (
            f"<b>{_esc(c.get('symbol'))}</b>  {_stars(c.get('conviction', 3))}  "
            f"<i>{_esc(_short_company(c.get('name', '')))}</i>\n"
            f"<code>${_p(entry)}</code> → <code>${_p(target)}</code>  "
            f"<i>{_upside(entry, target)}</i>  ·  {_esc(c.get('horizon'))}{alloc_str}\n"
            f"<i>{_esc(c.get('thesis'))}</i>"
        )

    # ── Short-term stocks — green tinted blockquote ───────────────────────────
    if st_picks:
        body = "\n\n".join(_pick_row_st(i, s) for i, s in enumerate(st_picks, 1))
        lines += [
            "",
            f"<blockquote expandable>📈 <b>SHORT TERM</b>  <code>${short_budget} / trade</code>\n\n{body}</blockquote>",
        ]

    # ── Long-term stocks — blue tinted blockquote ─────────────────────────────
    if lt_picks:
        body = "\n\n".join(_pick_row_lt(i, s) for i, s in enumerate(lt_picks, 1))
        lines += [
            "",
            f"<blockquote expandable>🏦 <b>LONG TERM</b>  <code>${long_budget} / mo DCA</code>\n\n{body}</blockquote>",
        ]

    # ── Crypto short-term — orange tinted blockquote ──────────────────────────
    if cst_picks:
        body = "\n\n".join(_pick_row_cst(i, c) for i, c in enumerate(cst_picks, 1))
        lines += [
            "",
            f"<blockquote expandable>🪙 <b>CRYPTO ST</b>  <code>${crypto_st_budget} / trade</code>  ⚡ HIGH RISK\n\n{body}</blockquote>",
        ]

    # ── Crypto long-term — purple tinted blockquote ───────────────────────────
    if clt_picks:
        body = "\n\n".join(_pick_row_clt(i, c) for i, c in enumerate(clt_picks, 1))
        lines += [
            "",
            f"<blockquote expandable>💎 <b>CRYPTO LT</b>  <code>${crypto_lt_budget} / mo DCA</code>\n\n{body}</blockquote>",
        ]

    # ── Footer ────────────────────────────────────────────────────────────────
    seen_sectors: set = set()
    sector_list: list = []
    for p in st_picks + lt_picks:
        s = p.get("sector", "")
        if s and s != "Unknown" and s not in seen_sectors:
            sector_list.append(s)
            seen_sectors.add(s)
    sector_line = f"🏭 <i>Sectors: {_esc(', '.join(sector_list))}</i>" if sector_list else ""

    lines += ["", "⚠️ <i>Not financial advice. Send /help for all commands.</i>"]
    if sector_line:
        lines.append(sector_line)

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
    chat_id = chat_id or _chat_id()
    text    = message_text.strip()

    # Non-slash message while a command is waiting for a param → handle as reply
    if not text.startswith("/"):
        state = load_pending_state(chat_id)
        if state:
            reply = _handle_pending_reply(state, text, chat_id)
            if reply:
                send_message(reply, chat_id=chat_id)
            return reply
    else:
        # Any new slash command cancels pending state
        clear_pending_state(chat_id)

    reply = _parse_and_execute(text.upper(), original=text, chat_id=chat_id)
    if reply:
        send_message(reply, chat_id=chat_id)
    return reply


def _explain_pick(query: str) -> str:
    """
    Use Claude Haiku to answer a plain-English question about today's picks.
    Fuzzy-matches the query to a specific pick when possible.
    """
    import anthropic
    import json

    picks = load_picks()
    if not picks:
        return "📭 No picks for today yet. Check back after 8 AM ET."

    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})
    all_picks = (
        [("Short-term stock", p) for p in stocks.get("short_term", [])] +
        [("Long-term stock",  p) for p in stocks.get("long_term",  [])] +
        [("Short-term crypto", p) for p in crypto.get("short_term", [])] +
        [("Long-term crypto",  p) for p in crypto.get("long_term",  [])]
    )

    if not all_picks:
        return "📭 No picks found in today's message."

    # Fuzzy-match query against ticker / company / name
    q = query.lower()
    matched_label, matched_pick = None, None
    for label, p in all_picks:
        ticker  = (p.get("ticker") or p.get("symbol") or "").lower()
        company = (p.get("company") or p.get("name") or "").lower()
        if ticker in q or q in ticker or q in company or any(w in company for w in q.split()):
            matched_label, matched_pick = label, p
            break

    if matched_pick:
        context = f"Category: {matched_label}\nPick data: {json.dumps(matched_pick, indent=2)}"
        system  = (
            "You are a friendly financial analyst explaining a stock or crypto pick to a "
            "retail investor. Answer in plain English — no jargon, 3-5 sentences max. "
            "Focus on: why this pick was chosen today, key risk to watch, and one thing "
            "to monitor. Do NOT give general financial advice disclaimers."
        )
    else:
        context = f"Today's picks:\n{json.dumps([p for _, p in all_picks], indent=2)}"
        system  = (
            "You are a friendly financial analyst. Answer questions about today's stock and "
            "crypto picks in plain English — no jargon, 3-5 sentences max. "
            "If the question is about something not in today's picks, say so briefly."
        )

    user_msg = f"{context}\n\nUser question: {query}"

    try:
        client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return f"💬 {message.content[0].text.strip()}"
    except Exception as exc:
        return f"⚠️ Could not generate explanation: {exc}"


def _nl_param(command: str, raw: str) -> str:
    """
    Use Claude Haiku to normalize a natural-language parameter for a slash command.
    Only called when the parameter isn't an obvious exact match.

    command="exclude" → returns JSON array of sector names  e.g. '["Energy","Utilities"]'
    command="watch"   → returns JSON array of ticker symbols e.g. '["TSLA","MSFT","BRK-B"]'
    command="risk"    → returns one word: conservative | moderate | aggressive
    """
    import anthropic
    prompts = {
        "exclude": (
            f'Map "{raw}" to a JSON array of standard US stock sector names. '
            'Valid values: Technology, Financials, Health Care, Energy, Utilities, '
            'Consumer Discretionary, Consumer Staples, Industrials, Materials, '
            'Real Estate, Communication Services. '
            'Return ONLY a JSON array, e.g. ["Energy"] or ["Financials","Utilities"].'
        ),
        "watch": (
            f'Map "{raw}" to a JSON array of US stock ticker symbols. '
            'Use official NYSE/NASDAQ tickers. Examples: Tesla→TSLA, Microsoft→MSFT, '
            'Berkshire→BRK-B, Google/Alphabet→GOOGL, Meta→META, Amazon→AMZN, '
            'Nvidia→NVDA, Apple→AAPL, JPMorgan→JPM, Pepsi→PEP. '
            'Return ONLY a JSON array, e.g. ["TSLA","MSFT"].'
        ),
        "risk": (
            f'Map "{raw}" to exactly one of: conservative, moderate, aggressive. '
            'Examples: "safe/careful/low risk" → conservative, '
            '"bold/risky/go big" → aggressive, "normal/balanced" → moderate. '
            'Return ONLY the single word.'
        ),
    }
    try:
        client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompts[command]}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        print(f"[telegram] _nl_param failed for {command!r}: {exc}")
        return raw


def _resolve_ticker_candidates(name_or_ticker: str) -> list[dict]:
    """
    Resolve a company name or ticker to a list of candidate dicts:
      [{"ticker": "AAPL", "name": "Apple Inc"}, ...]
    Returns a single-item list for unambiguous matches, multiple for ambiguous ones.
    """
    import re as _re
    import json as _j
    import anthropic as _ant

    raw = name_or_ticker.strip()

    # Already looks like a ticker — return directly, no Haiku needed
    if _re.match(r"^[A-Za-z.\-]{1,6}$", raw):
        return [{"ticker": raw.upper(), "name": raw.upper()}]

    # Ask Haiku for up to 4 candidates with full names
    prompt = (
        f'The user typed "{raw}" as a stock or crypto to trade. '
        'Return up to 4 matching US stock/crypto candidates as a JSON array of objects. '
        'Each object must have "ticker" (official symbol) and "name" (short company name). '
        'Order by most likely match first. '
        'Examples: "apple" → [{"ticker":"AAPL","name":"Apple Inc"}], '
        '"bank" → [{"ticker":"JPM","name":"JPMorgan"},{"ticker":"BAC","name":"Bank of America"},'
        '{"ticker":"WFC","name":"Wells Fargo"},{"ticker":"C","name":"Citigroup"}]. '
        'Return ONLY the JSON array.'
    )
    try:
        client  = _ant.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        candidates = _j.loads(message.content[0].text.strip())
        if isinstance(candidates, list) and candidates:
            return candidates
    except Exception as exc:
        print(f"[telegram] _resolve_ticker_candidates failed: {exc}")

    return [{"ticker": raw.upper(), "name": raw.upper()}]


def _fetch_live_price(ticker: str) -> float | None:
    """Fetch the latest price for a ticker via yfinance."""
    import yfinance as _yf
    try:
        data = _yf.download(ticker, period="1d", interval="1m",
                            progress=False, auto_adjust=True)
        return float(data["Close"].dropna().iloc[-1])
    except Exception:
        return None


def _resolve_ticker_and_price(name_or_ticker: str, price_str: str | None) -> tuple[str, float | None]:
    """Single-result convenience wrapper used when caller doesn't need multi-select."""
    candidates = _resolve_ticker_candidates(name_or_ticker)
    ticker = candidates[0]["ticker"]
    price: float | None = None
    if price_str:
        try:
            price = float(price_str)
        except ValueError:
            pass
    if price is None:
        price = _fetch_live_price(ticker)
    return ticker, price


def handle_callback_query(callback_query: dict) -> None:
    """
    Handle inline keyboard button taps.
    callback_data format:
      buy|TICKER|price|shares   (price/shares may be empty string)
      sell|TICKER|price
    """
    from trade_logger import manual_open_trade, manual_close_trade

    cq_id   = callback_query.get("id", "")
    data    = callback_query.get("data", "")
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))

    answer_callback_query(cq_id)   # dismiss spinner immediately

    parts = data.split("|")
    action = parts[0] if parts else ""

    if action == "cancel_pending":
        target_chat = parts[1] if len(parts) > 1 else chat_id
        clear_pending_state(target_chat)
        send_message("👍 Cancelled.", chat_id=chat_id)
        return

    if action == "buy":
        ticker     = parts[1] if len(parts) > 1 else ""
        price_raw  = parts[2] if len(parts) > 2 else ""
        shares_raw = parts[3] if len(parts) > 3 else ""

        price = float(price_raw) if price_raw else _fetch_live_price(ticker)
        if not price:
            send_message(f"⚠️ Could not fetch price for <b>{ticker}</b>. Try: <code>/bought {ticker} 182.50</code>", chat_id=chat_id)
            return

        shares = float(shares_raw) if shares_raw else None

        # Pull target/stop from today's picks
        target = stop = None
        picks  = load_picks()
        if picks:
            all_st = (picks.get("stocks", {}).get("short_term", []) +
                      picks.get("crypto", {}).get("short_term", []))
            for p in all_st:
                sym = p.get("ticker") or p.get("symbol", "")
                if sym.upper() == ticker:
                    target = p.get("target_price")
                    stop   = p.get("stop_loss")
                    break

        crypto_symbols = {
            "BTC","ETH","SOL","BNB","XRP","ADA","DOGE","AVAX","DOT","MATIC",
            "LINK","UNI","ATOM","LTC","BCH","ALGO","XLM","VET","ICP","FIL",
        }
        asset_type = "crypto" if ticker in crypto_symbols else "stock"

        trade = manual_open_trade(ticker, price, asset_type=asset_type,
                                  shares=shares, target_price=target, stop_loss=stop)

        alloc_str  = f"  · <code>${trade['allocation']:.2f}</code> deployed" if trade.get("allocation") else ""
        shares_str = f"  · {shares} shares" if shares else ""
        send_message(
            f"✅ <b>Logged: bought {ticker}</b>\n"
            f"Entry:  <code>${trade['entry_price']}</code>{shares_str}{alloc_str}\n"
            f"Target: <code>${trade['target_price']}</code>  "
            f"<i>(+{((trade['target_price']/trade['entry_price'])-1)*100:.1f}%)</i>\n"
            f"Stop:   <code>${trade['stop_loss']}</code>  "
            f"<i>({((trade['stop_loss']/trade['entry_price'])-1)*100:.1f}%)</i>\n"
            f"<i>I'll track this and alert you at target/stop.</i>",
            chat_id=chat_id,
        )

    elif action == "cancel_abort":
        send_message("👍 No changes made.", chat_id=chat_id)

    elif action == "confirm_cancel":
        from trade_logger import cancel_trade
        ticker  = parts[1] if len(parts) > 1 else ""
        removed = cancel_trade(ticker)
        if not removed:
            send_message(f"⚠️ No open position found for <b>{ticker}</b>.", chat_id=chat_id)
        else:
            send_message(
                f"🗑 <b>Cancelled buy: {ticker}</b>\n"
                f"Entry <code>${removed.get('entry_price')}</code> removed — not counted in P&amp;L.",
                chat_id=chat_id,
            )

    elif action == "confirm_reopen":
        from trade_logger import reopen_trade
        ticker   = parts[1] if len(parts) > 1 else ""
        reopened = reopen_trade(ticker)
        if not reopened:
            send_message(f"⚠️ No closed trade found for <b>{ticker}</b> to reopen.", chat_id=chat_id)
        else:
            send_message(
                f"↩️ <b>Undid sell: {ticker}</b>\n"
                f"Entry <code>${reopened.get('entry_price')}</code> moved back to open positions.",
                chat_id=chat_id,
            )

    elif action in ("cancel", "cancel_auto"):
        from trade_logger import cancel_trade, reopen_trade
        from config_manager import load_trade_log
        ticker = parts[1] if len(parts) > 1 else ""

        if action == "cancel_auto":
            log        = load_trade_log()
            has_open   = any(t["ticker"] == ticker for t in log.get("open", []))
            has_closed = any(t["ticker"] == ticker for t in log.get("closed", []))
            if has_open and has_closed:
                send_inline_keyboard(
                    f"↩️ What do you want to undo for <b>{ticker}</b>?",
                    [[
                        {"text": "❌ Undo buy",  "callback_data": f"confirm_cancel|{ticker}"},
                        {"text": "↩️ Undo sell", "callback_data": f"confirm_reopen|{ticker}"},
                    ]],
                    chat_id=chat_id,
                )
                return
            if has_open:
                action = "confirm_cancel"
            elif has_closed:
                action = "confirm_reopen"

    elif action == "sell":
        ticker    = parts[1] if len(parts) > 1 else ""
        price_raw = parts[2] if len(parts) > 2 else ""

        price = float(price_raw) if price_raw else _fetch_live_price(ticker)
        if not price:
            send_message(f"⚠️ Could not fetch price for <b>{ticker}</b>. Try: <code>/sold {ticker} 197.10</code>", chat_id=chat_id)
            return

        closed = manual_close_trade(ticker, price)
        if not closed:
            send_message(f"⚠️ No open position found for <b>{ticker}</b>. Use /positions to see open trades.", chat_id=chat_id)
            return

        ret   = closed["return_pct"]
        gain  = closed["gain_usd"]
        emoji = "✅" if ret >= 0 else "🔴"
        sign  = "+" if ret >= 0 else ""
        gsign = "+" if gain >= 0 else ""
        send_message(
            f"{emoji} <b>Closed: {ticker}</b>\n"
            f"Entry:  <code>${closed['entry_price']}</code>\n"
            f"Exit:   <code>${closed['closed_price']}</code>\n"
            f"Return: <b>{sign}{ret}%</b>  P&amp;L: <code>{gsign}${abs(gain):.2f}</code>\n"
            f"<i>Saved to trade history.</i>",
            chat_id=chat_id,
        )


# ── Prompts for param commands ────────────────────────────────────────────────

_PARAM_PROMPTS: dict[str, str] = {
    "bought":   ("🛒 <b>What did you buy?</b>\n"
                 "<i>e.g.</i>  <code>apple</code>  ·  <code>AAPL 182.50</code>  ·  <code>AAPL 182.50 5</code>"),
    "sold":     ("💸 <b>What did you sell?</b>\n"
                 "<i>e.g.</i>  <code>apple</code>  ·  <code>AAPL 197.10</code>"),
    "cancel":   ("↩️ <b>Which trade to undo?</b>\n"
                 "<i>e.g.</i>  <code>apple</code>  ·  <code>AAPL</code>"),
    "explain":  ("💬 <b>What would you like to know?</b>\n"
                 "<i>e.g.</i>  <code>why is NVDA picked?</code>  ·  <code>apple thesis</code>"),
    "watch":    ("👀 <b>Which tickers to watch?</b>\n"
                 "<i>e.g.</i>  <code>NVDA TSLA</code>  ·  <code>nvidia tesla</code>"),
    "exclude":  ("🚫 <b>Which sector to exclude?</b>\n"
                 "<i>e.g.</i>  <code>energy</code>  ·  <code>oil stocks</code>"),
    "set_risk": ("⚖️ <b>Risk level?</b>\n"
                 "<code>conservative</code>   ·   <code>moderate</code>   ·   <code>aggressive</code>"),
    "set_st":    "💰 <b>Stock short-term budget per trade?</b>  <i>e.g.</i>  <code>30</code>",
    "set_lt":    "💰 <b>Stock long-term monthly budget?</b>  <i>e.g.</i>  <code>50</code>",
    "set_cst":   "💰 <b>Crypto short-term budget per trade?</b>  <i>e.g.</i>  <code>20</code>",
    "set_clt":   "💰 <b>Crypto long-term monthly budget?</b>  <i>e.g.</i>  <code>30</code>",
    "alert":     ("🔔 <b>Set a price alert</b>\n"
                  "<i>e.g.</i>  <code>NVDA 1000</code>  ·  <code>AAPL below 175</code>  ·  <code>TSLA above 300</code>"),
    "unalert":   ("🔕 <b>Remove which alert?</b>\n"
                  "<i>e.g.</i>  <code>NVDA</code>  (removes all NVDA alerts)  ·  <code>NVDA 1000</code>"),
    "paper_buy": ("📄 <b>Paper buy — what to simulate?</b>\n"
                  "<i>e.g.</i>  <code>AAPL 10</code>  ·  <code>AAPL 182.50 10</code>"),
    "paper_sell":("📄 <b>Paper sell — which position?</b>\n"
                  "<i>e.g.</i>  <code>AAPL</code>  ·  <code>AAPL 5</code>  (partial sell)"),
}


def _prompt_for_param(command: str, chat_id: str) -> None:
    """Save pending state and send the parameter-request prompt with a Cancel button."""
    prompt = _PARAM_PROMPTS.get(command, f"What value for /{command}?")
    save_pending_state(chat_id, command)
    send_inline_keyboard(
        prompt,
        [[{"text": "❌ Cancel", "callback_data": f"cancel_pending|{chat_id}"}]],
        chat_id=chat_id,
    )


# ── Extracted buy/sell execution (shared by direct + conversational paths) ────

def _execute_bought(ticker: str, price_raw, shares_raw, chat_id: str) -> str:
    from trade_logger import manual_open_trade
    price: float | None = None
    if price_raw:
        try:
            price = float(str(price_raw).strip())
        except ValueError:
            pass
    if price is None:
        price = _fetch_live_price(ticker)
    if price is None:
        return (f"⚠️ Could not fetch price for <b>{ticker}</b>. "
                f"Reply with the price, e.g. <code>182.50</code>")

    shares: float | None = None
    if shares_raw:
        try:
            shares = float(str(shares_raw).strip())
        except (ValueError, TypeError):
            pass

    target = stop = None
    picks  = load_picks()
    if picks:
        all_st = (picks.get("stocks", {}).get("short_term", []) +
                  picks.get("crypto", {}).get("short_term", []))
        for p in all_st:
            sym = p.get("ticker") or p.get("symbol", "")
            if sym.upper() == ticker:
                target = p.get("target_price")
                stop   = p.get("stop_loss")
                break

    crypto_symbols = {
        "BTC","ETH","SOL","BNB","XRP","ADA","DOGE","AVAX","DOT","MATIC",
        "LINK","UNI","ATOM","LTC","BCH","ALGO","XLM","VET","ICP","FIL",
    }
    asset_type = "crypto" if ticker in crypto_symbols else "stock"

    trade = manual_open_trade(ticker, price, asset_type=asset_type,
                              shares=shares, target_price=target, stop_loss=stop)

    alloc_str  = f"  · <code>${trade['allocation']:.2f}</code> deployed" if trade.get("allocation") else ""
    shares_str = f"  · {shares} shares" if shares else ""
    return (
        f"✅ <b>Logged: bought {ticker}</b>\n"
        f"Entry:  <code>${trade['entry_price']}</code>{shares_str}{alloc_str}\n"
        f"Target: <code>${trade['target_price']}</code>  "
        f"<i>(+{((trade['target_price']/trade['entry_price'])-1)*100:.1f}%)</i>\n"
        f"Stop:   <code>${trade['stop_loss']}</code>  "
        f"<i>({((trade['stop_loss']/trade['entry_price'])-1)*100:.1f}%)</i>\n"
        f"<i>I'll check this at 10:30 AM and 3:30 PM and alert if target/stop is hit.</i>"
    )


def _execute_sold(ticker: str, price_raw, chat_id: str) -> str:
    from trade_logger import manual_close_trade
    price: float | None = None
    if price_raw:
        try:
            price = float(str(price_raw).strip())
        except ValueError:
            pass
    if price is None:
        price = _fetch_live_price(ticker)
    if price is None:
        return (f"⚠️ Could not fetch price for <b>{ticker}</b>. "
                f"Reply with the price, e.g. <code>197.10</code>")

    closed = manual_close_trade(ticker, price)
    if not closed:
        return f"⚠️ No open position found for <b>{ticker}</b>. Use /portfolio to see open trades."

    ret   = closed["return_pct"]
    gain  = closed["gain_usd"]
    emoji = "✅" if ret >= 0 else "🔴"
    sign  = "+" if ret >= 0 else ""
    gsign = "+" if gain >= 0 else ""
    return (
        f"{emoji} <b>Closed: {ticker}</b>\n"
        f"Entry:  <code>${closed['entry_price']}</code>\n"
        f"Exit:   <code>${closed['closed_price']}</code>\n"
        f"Return: <b>{sign}{ret}%</b>  P&amp;L: <code>{gsign}${abs(gain):.2f}</code>\n"
        f"<i>Saved to trade history.</i>"
    )


# ── Pending reply handler ─────────────────────────────────────────────────────

def _handle_pending_reply(state: dict, text: str, chat_id: str) -> str:
    """
    Called when the user sends a plain message while a pending command state exists.
    Routes to the appropriate handler based on the saved command + step.
    """
    command = state["command"]
    step    = state.get("step", 1)
    data    = state.get("data", {})

    # State already consumed — always clear it first
    clear_pending_state(chat_id)

    # ── /bought multi-step ────────────────────────────────────────────────────
    if command == "bought":
        if step == 2:
            # User is replying with a price (or blank = live price)
            ticker     = data.get("ticker", "")
            shares_raw = data.get("shares")
            price_raw  = text.strip() or None
            return _execute_bought(ticker, price_raw, shares_raw, chat_id)

        # Step 1: parse "apple" / "AAPL 182.50" / "AAPL 182.50 5"
        parts     = text.strip().split()
        name_raw  = parts[0] if parts else ""
        price_raw = parts[1] if len(parts) >= 2 else None
        shares_raw = parts[2] if len(parts) >= 3 else None

        if not name_raw:
            return "⚠️ Please tell me which stock you bought."

        candidates = _resolve_ticker_candidates(name_raw)
        if len(candidates) > 1:
            price_enc  = price_raw  or ""
            shares_enc = shares_raw or ""
            buttons = [[{"text": f"{c['ticker']} — {c['name']}",
                         "callback_data": f"buy|{c['ticker']}|{price_enc}|{shares_enc}"}]
                       for c in candidates]
            send_inline_keyboard(f"🔍 Which stock did you mean by <b>{_esc(name_raw)}</b>?",
                                 buttons, chat_id=chat_id)
            return ""

        ticker = candidates[0]["ticker"]
        if price_raw is None:
            # Need price — go to step 2
            save_pending_state(chat_id, "bought", step=2, data={"ticker": ticker})
            send_inline_keyboard(
                f"Got it — <b>{ticker}</b>. At what price did you buy?\n"
                f"<i>Send blank to use live price</i>",
                [[{"text": "❌ Cancel", "callback_data": f"cancel_pending|{chat_id}"}]],
                chat_id=chat_id,
            )
            return ""

        return _execute_bought(ticker, price_raw, shares_raw, chat_id)

    # ── /sold multi-step ──────────────────────────────────────────────────────
    if command == "sold":
        if step == 2:
            ticker    = data.get("ticker", "")
            price_raw = text.strip() or None
            return _execute_sold(ticker, price_raw, chat_id)

        parts     = text.strip().split()
        name_raw  = parts[0] if parts else ""
        price_raw = parts[1] if len(parts) >= 2 else None

        if not name_raw:
            return "⚠️ Please tell me which stock you sold."

        candidates = _resolve_ticker_candidates(name_raw)
        if len(candidates) > 1:
            price_enc = price_raw or ""
            buttons = [[{"text": f"{c['ticker']} — {c['name']}",
                         "callback_data": f"sell|{c['ticker']}|{price_enc}"}]
                       for c in candidates]
            send_inline_keyboard(f"🔍 Which stock did you mean?", buttons, chat_id=chat_id)
            return ""

        ticker = candidates[0]["ticker"]
        if price_raw is None:
            save_pending_state(chat_id, "sold", step=2, data={"ticker": ticker})
            send_inline_keyboard(
                f"Got it — <b>{ticker}</b>. At what price did you sell?\n"
                f"<i>Send blank to use live price</i>",
                [[{"text": "❌ Cancel", "callback_data": f"cancel_pending|{chat_id}"}]],
                chat_id=chat_id,
            )
            return ""

        return _execute_sold(ticker, price_raw, chat_id)

    # ── Single-step param commands ────────────────────────────────────────────
    if command == "cancel":
        return _parse_and_execute(f"CANCEL {text}", original=f"/cancel {text}", chat_id=chat_id)

    if command == "explain":
        return _explain_pick(text)

    if command == "watch":
        return _parse_and_execute(f"WATCH {text}", original=f"/watch {text}", chat_id=chat_id)

    if command == "exclude":
        return _parse_and_execute(f"EXCLUDE {text}", original=f"/exclude {text}", chat_id=chat_id)

    if command == "set_risk":
        return _parse_and_execute(f"SET RISK {text}", original=text, chat_id=chat_id)

    key_map = {"set_st": "ST", "set_lt": "LT", "set_cst": "CST", "set_clt": "CLT"}
    if command in key_map:
        return _parse_and_execute(f"SET {key_map[command]} {text}", original=text, chat_id=chat_id)

    if command == "alert":
        return _parse_and_execute(f"ALERT {text}", original=f"/alert {text}", chat_id=chat_id)

    if command == "unalert":
        return _parse_and_execute(f"UNALERT {text}", original=f"/unalert {text}", chat_id=chat_id)

    if command == "paper_buy":
        return _parse_and_execute(f"PAPER BUY {text}", original=f"/paper_buy {text}", chat_id=chat_id)

    if command == "paper_sell":
        return _parse_and_execute(f"PAPER SELL {text}", original=f"/paper_sell {text}", chat_id=chat_id)

    return _handle_natural_language(text)


def _handle_natural_language(query: str) -> str:
    """
    Parse a free-text message into a bot command using Claude Haiku, then execute it.
    Used as a fallback when no slash-command pattern matches.
    Examples:
      "make my picks more aggressive"    → set_risk aggressive
      "add nvidia and apple to watchlist" → watch NVDA AAPL
      "never show me energy stocks"       → exclude Energy
      "increase my short term budget to 50" → set_budget short_term_budget 50
      "why was microsoft picked today?"   → explain query
    """
    import anthropic
    import json

    SYSTEM = """You are a command parser for a personal stock advisor Telegram bot.
Parse the user's natural language message into a JSON command. Return ONLY valid JSON — no text before or after.

Available intents and their exact JSON format:
{"intent": "set_risk",    "value": "conservative|moderate|aggressive"}
{"intent": "watch",       "tickers": ["NVDA", "TSLA"]}
{"intent": "watch_clear"}
{"intent": "exclude",     "sectors": ["Energy", "Utilities"]}
{"intent": "exclude_clear"}
{"intent": "set_budget",  "key": "short_term_budget|long_term_budget|crypto_short_budget|crypto_long_budget", "value": 50}
{"intent": "pause"}
{"intent": "resume"}
{"intent": "status"}
{"intent": "today"}
{"intent": "prices"}
{"intent": "perf"}
{"intent": "watchlist"}
{"intent": "reset"}
{"intent": "explain",     "query": "the user's question verbatim"}
{"intent": "unknown"}

Rules:
- Map "aggressive/risky/bold" → set_risk aggressive
- Map "conservative/safe/careful" → set_risk conservative
- Map "add X to watchlist/watch X" → watch with tickers in uppercase
- Map "remove/clear watchlist" → watch_clear
- Map "exclude/skip/never pick sector" → exclude with proper sector name
- Map "increase/set/change budget" → set_budget with correct key and numeric value
- Budget keys: "short term" → short_term_budget, "long term" → long_term_budget,
  "crypto short" → crypto_short_budget, "crypto long" → crypto_long_budget
- If the message is a question about picks, use explain
- If truly unclear, use unknown"""

    try:
        client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            system=SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        parsed = json.loads(message.content[0].text.strip())
    except Exception as exc:
        print(f"[telegram] NL parse failed ({exc}) — treating as explain query")
        return _explain_pick(query)

    intent = parsed.get("intent", "unknown")
    print(f"[telegram] NL intent: {intent} from: {query!r}")

    if intent == "set_risk":
        return _parse_and_execute(f"SET RISK {parsed.get('value','moderate').upper()}", original=query)
    if intent == "watch":
        tickers = " ".join(parsed.get("tickers", []))
        return _parse_and_execute(f"WATCH {tickers}", original=f"/watch {tickers}")
    if intent == "watch_clear":
        return _parse_and_execute("WATCH NONE", original="/watch none")
    if intent == "exclude":
        sectors = " ".join(parsed.get("sectors", []))
        return _parse_and_execute(f"EXCLUDE {sectors.upper()}", original=f"/exclude {sectors}")
    if intent == "exclude_clear":
        return _parse_and_execute("EXCLUDE NONE", original="/exclude none")
    if intent == "set_budget":
        key = parsed.get("key", "")
        val = parsed.get("value", 0)
        key_to_cmd = {
            "short_term_budget":   f"SET ST {val}",
            "long_term_budget":    f"SET LT {val}",
            "crypto_short_budget": f"SET CST {val}",
            "crypto_long_budget":  f"SET CLT {val}",
        }
        cmd = key_to_cmd.get(key)
        if cmd:
            return _parse_and_execute(cmd, original=query)
    if intent == "pause":
        return _parse_and_execute("PAUSE", original=query)
    if intent == "resume":
        return _parse_and_execute("RESUME", original=query)
    if intent == "status":
        return _parse_and_execute("STATUS", original=query)
    if intent == "today":
        return _parse_and_execute("TODAY", original=query)
    if intent == "prices":
        return _parse_and_execute("PRICES", original=query)
    if intent == "perf":
        return _parse_and_execute("PERF", original=query)
    if intent == "watchlist":
        return _parse_and_execute("WATCHLIST", original=query)
    if intent == "reset":
        return _parse_and_execute("RESET", original=query)
    if intent == "explain":
        return _explain_pick(parsed.get("query", query))

    # True unknown — still try explain as last resort for questions
    return _explain_pick(query)


def _parse_and_execute(text: str, original: str = "", chat_id: str | None = None) -> str:
    """Parse command string and return reply."""
    chat_id = chat_id or _chat_id()

    # Telegram slash-commands (/help) or plain text (HELP) — normalise both
    text = text.lstrip("/").replace("_", " ")   # /set_st 30 → SET ST 30

    if text == "TODAY":
        picks = load_picks()
        if not picks:
            return "📭 No picks for today yet. Check back after 8 AM ET."
        config = get_config()
        return format_daily_message(picks, config)

    if text == "EXPLAIN":
        _prompt_for_param("explain", chat_id)
        return ""

    if text.startswith("EXPLAIN "):
        # Preserve original casing for the query — strip the command prefix
        raw = original.lstrip("/")
        query = raw.split(" ", 1)[1].strip() if " " in raw else raw
        return _explain_pick(query)

    if text == "PERF":
        from trade_logger import get_performance_stats
        stock_stats  = get_performance_stats("stock")
        crypto_stats = get_performance_stats("crypto")

        if not stock_stats and not crypto_stats:
            return "📭 No closed trades yet. Check back after your first picks are resolved."

        def _stat_block(label: str, s: dict) -> str:
            if not s:
                return f"{label}: no closed trades yet"
            sign      = "+" if s["avg_return"] >= 0 else ""
            gain_sign = "+" if s["total_gain_usd"] >= 0 else ""
            cum_sign  = "+" if s.get("cumulative_return_pct", 0) >= 0 else ""
            best_sym,  best_r  = s["best"]
            worst_sym, worst_r = s["worst"]
            streak = s.get("streak", 0)
            streak_str = f"  🔥 {streak}-win streak" if streak >= 2 else ""
            return (
                f"<b>{label}</b> — {s['count']} trades  {s['win_rate']}% wins{streak_str}\n"
                f"Avg/trade: {sign}{s['avg_return']}%  "
                f"Cumulative: <b>{cum_sign}{s['cumulative_return_pct']}%</b>\n"
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

    # ── Market regime ─────────────────────────────────────────────────────────
    if text == "REGIME":
        try:
            from market_regime import get_market_regime, regime_emoji
            r = get_market_regime()
            emoji = regime_emoji(r["regime"])
            return (
                f"{emoji} <b>MARKET REGIME: {r['regime'].upper()}</b>\n\n"
                f"<b>VIX:</b> {r['vix'] or 'N/A'}\n"
                f"<b>SPY vs 50-day MA:</b> {'Above ✅' if r['spy_above_50ma'] else 'Below ⚠️' if r['spy_above_50ma'] is not None else 'N/A'}\n"
                f"<b>SPY vs 200-day MA:</b> {'Above ✅' if r['spy_above_200ma'] else 'Below 🔴' if r['spy_above_200ma'] is not None else 'N/A'}\n\n"
                f"<i>{r['note']}</i>"
            )
        except Exception as exc:
            return f"⚠️ Could not fetch market regime: {exc}"

    # ── Price alerts ──────────────────────────────────────────────────────────
    if text == "ALERTS":
        from price_alert_manager import list_alerts
        return list_alerts(chat_id)

    if text == "ALERT":
        _prompt_for_param("alert", chat_id)
        return ""

    if text.startswith("ALERT "):
        from price_alert_manager import add_alert
        parts = text[6:].strip().split()
        # Formats: ALERT NVDA 1000  |  ALERT NVDA ABOVE 1000  |  ALERT NVDA BELOW 900
        try:
            if len(parts) >= 3 and parts[1].upper() in ("ABOVE", "BELOW"):
                ticker, direction, price_str = parts[0], parts[1].lower(), parts[2]
            elif len(parts) >= 2:
                ticker, price_str = parts[0], parts[1]
                direction = "auto"
            else:
                return "⚠️ Usage: /alert NVDA 1000  or  /alert NVDA below 900"
            return add_alert(chat_id, ticker, float(price_str.replace(",", "")), direction)
        except ValueError:
            return "⚠️ Usage: /alert NVDA 1000  or  /alert NVDA below 900"

    if text == "UNALERT":
        _prompt_for_param("unalert", chat_id)
        return ""

    if text.startswith("UNALERT "):
        from price_alert_manager import remove_alert
        parts = text[8:].strip().split()
        ticker = parts[0] if parts else ""
        price  = float(parts[1]) if len(parts) >= 2 else None
        if not ticker:
            return "⚠️ Usage: /unalert NVDA  or  /unalert NVDA 1000"
        return remove_alert(chat_id, ticker, price)

    # ── Paper trading ─────────────────────────────────────────────────────────
    if text in ("PAPER BUY",):
        _prompt_for_param("paper_buy", chat_id)
        return ""

    if text.startswith("PAPER BUY "):
        from paper_trader import paper_buy
        parts = text[10:].strip().split()
        # Formats: PAPER BUY AAPL 10  |  PAPER BUY AAPL 182.50 10
        try:
            if len(parts) == 2:
                ticker, shares = parts[0], float(parts[1])
                return paper_buy(ticker, shares)
            elif len(parts) == 3:
                ticker, price, shares = parts[0], float(parts[1]), float(parts[2])
                return paper_buy(ticker, shares, price)
            else:
                return "⚠️ Usage: /paper_buy AAPL 10  or  /paper_buy AAPL 182.50 10"
        except ValueError:
            return "⚠️ Usage: /paper_buy AAPL 10  or  /paper_buy AAPL 182.50 10"

    if text in ("PAPER SELL",):
        _prompt_for_param("paper_sell", chat_id)
        return ""

    if text.startswith("PAPER SELL "):
        from paper_trader import paper_sell
        parts = text[11:].strip().split()
        try:
            ticker = parts[0] if parts else ""
            if not ticker:
                return "⚠️ Usage: /paper_sell AAPL  or  /paper_sell AAPL 5"
            shares = float(parts[1]) if len(parts) >= 2 else None
            price  = float(parts[2]) if len(parts) >= 3 else None
            return paper_sell(ticker, shares, price)
        except ValueError:
            return "⚠️ Usage: /paper_sell AAPL  or  /paper_sell AAPL 5"

    if text == "PAPER PORTFOLIO":
        from paper_trader import paper_portfolio
        return paper_portfolio()

    if text == "PAPER PERF":
        from paper_trader import paper_performance
        return paper_performance()

    if text == "PAPER RESET":
        from paper_trader import paper_reset
        return paper_reset()

    # ── Backtest ──────────────────────────────────────────────────────────────
    if text == "BACKTEST":
        send_message(
            "⏳ <b>Backtest running…</b>\n\n"
            "Scoring ~600 tickers across 26 weekly intervals (1-year history).\n"
            "Results will arrive in this chat in <b>1–3 minutes</b> — no need to wait here.",
            chat_id=chat_id,
        )

        def _run_and_send():
            try:
                from backtester import run_backtest, format_backtest_message
                result = run_backtest()
                send_message(format_backtest_message(result), chat_id=chat_id)
            except Exception as exc:
                send_message(f"⚠️ Backtest failed: {exc}", chat_id=chat_id)

        threading.Thread(target=_run_and_send, daemon=True).start()
        return None  # webhook already got its "200 OK" — no second message from here

    if text in ("HELP", "START"):
        return (
            "📋 <b>Available commands:</b>\n"
            "\n<b>— Daily —</b>\n"
            "/today                    — re-send today's picks\n"
            "/prices                   — live prices for today's picks\n"
            "/perf                     — all-time performance stats\n"
            "/explain &lt;question&gt;       — ask anything about a pick\n"
            "  e.g. /explain microsoft\n"
            "  e.g. /explain why is doge picked\n"
            "\n<b>— My Trades —</b>\n"
            "/bought AAPL 182.50       — log a purchase\n"
            "/bought AAPL 182.50 5     — with share count\n"
            "/sold AAPL 197.10         — log a sale + see P&amp;L\n"
            "/positions                — live P&amp;L on all open trades\n"
            "/cancel apple             — undo accidental /bought or /sold\n"
            "\n<b>— Budgets —</b>\n"
            "/set_st &lt;n&gt;               — stock short-term budget\n"
            "/set_lt &lt;n&gt;               — stock long-term budget\n"
            "/set_cst &lt;n&gt;              — crypto short-term budget\n"
            "/set_clt &lt;n&gt;              — crypto long-term budget\n"
            "\n<b>— AI Intelligence —</b>\n"
            "/set_risk &lt;profile&gt;       — conservative | moderate | aggressive\n"
            "/watch NVDA TSLA          — always evaluate these tickers\n"
            "/watch none               — clear watchlist\n"
            "/exclude energy utils     — never pick from these sectors\n"
            "/exclude none             — clear sector exclusions\n"
            "/watchlist                — show AI settings summary\n"
            "\n<b>— Market Intelligence —</b>\n"
            "/regime                   — current market regime (bull/bear/volatile)\n"
            "/backtest                 — historical strategy backtest\n"
            "\n<b>— Price Alerts —</b>\n"
            "/alert NVDA 1000          — notify when NVDA crosses $1000\n"
            "/alert NVDA below 900     — notify when NVDA drops below $900\n"
            "/alerts                   — list all active alerts\n"
            "/unalert NVDA             — remove NVDA alerts\n"
            "\n<b>— Paper Trading —</b>\n"
            "/paper_buy AAPL 10        — simulate buying 10 shares of AAPL\n"
            "/paper_sell AAPL          — simulate selling AAPL position\n"
            "/paper_portfolio          — paper P&amp;L summary\n"
            "/paper_perf               — paper trading win rate\n"
            "/paper_reset              — reset paper portfolio to $10k\n"
            "\n<b>— Control —</b>\n"
            "/pause                    — stop daily picks\n"
            "/resume                   — restart daily picks\n"
            "/status                   — show full config\n"
            "/reset                    — restore default config\n"
            "/help                     — show this list"
        )

    # /set_risk conservative | moderate | aggressive  (or natural language)
    if text == "SET RISK":
        _prompt_for_param("set_risk", chat_id)
        return ""

    if text.startswith("SET RISK "):
        raw     = text[len("SET RISK "):].strip().lower()
        profile = raw if raw in ("conservative", "moderate", "aggressive") else _nl_param("risk", raw).lower()
        if profile not in ("conservative", "moderate", "aggressive"):
            profile = "moderate"
        update_config("risk_profile", profile)
        descriptions = {
            "conservative": "Fewer picks, tighter stops, low-volatility sectors, reduced crypto.",
            "moderate":     "Balanced approach — default settings.",
            "aggressive":   "More picks, wider stops, all sectors, full crypto allocation.",
        }
        return f"✅ Risk profile → <b>{profile}</b>\n<i>{descriptions[profile]}</i>\nTakes effect tomorrow."

    # /exclude energy stocks  |  /exclude oil companies  |  /exclude none
    if text == "EXCLUDE":
        _prompt_for_param("exclude", chat_id)
        return ""

    if text.startswith("EXCLUDE "):
        raw_query     = original.lstrip("/")
        sectors_input = raw_query.split(" ", 1)[1].strip() if " " in raw_query else ""
        if sectors_input.lower() in ("none", "clear", "reset", ""):
            update_config("excluded_sectors", [])
            return "✅ Sector exclusions cleared — all sectors eligible again."
        # Use Haiku to map natural language → proper sector names
        import json as _json
        try:
            excluded = _json.loads(_nl_param("exclude", sectors_input))
        except Exception:
            excluded = [sectors_input.title()]
        update_config("excluded_sectors", excluded)
        return (f"✅ Excluding sectors: <b>{', '.join(excluded)}</b>\n"
                f"These sectors will be skipped in tomorrow's picks.\n"
                f"<i>To clear: /exclude none</i>")

    # /watch tesla/microsoft  |  /watch NVDA TSLA  |  /watch none
    if text == "WATCH":
        _prompt_for_param("watch", chat_id)
        return ""

    if text.startswith("WATCH "):
        raw_query     = original.lstrip("/")
        tickers_input = raw_query.split(" ", 1)[1].strip() if " " in raw_query else ""
        if tickers_input.upper() in ("NONE", "CLEAR", "RESET", ""):
            update_config("watchlist", [])
            return "✅ Watchlist cleared."
        # Split on spaces, commas, or slashes — support "tesla/microsoft", "NVDA, TSLA"
        import re as _re, json as _json
        parts = [p.strip() for p in _re.split(r"[,/\s]+", tickers_input) if p.strip()]
        # If all parts look like tickers (short, letters/hyphens only), use directly
        looks_like_tickers = all(len(p) <= 5 and _re.match(r"^[A-Za-z.\-]+$", p) for p in parts)
        if looks_like_tickers:
            tickers = [p.upper() for p in parts]
        else:
            # Natural language — resolve via Haiku
            try:
                tickers = _json.loads(_nl_param("watch", tickers_input))
            except Exception:
                tickers = [p.upper() for p in parts]
        update_config("watchlist", tickers)
        return (f"✅ Watchlist set: <b>{', '.join(tickers)}</b>\n"
                f"These tickers will always be evaluated in tomorrow's screener.\n"
                f"<i>To clear: /watch none</i>")

    if text == "WATCHLIST":
        config = get_config()
        wl = config.get("watchlist", [])
        ex = config.get("excluded_sectors", [])
        rp = config.get("risk_profile", "moderate")
        lines = [f"<b>🎯 AI Settings</b>",
                 f"Risk profile: <b>{rp}</b>",
                 f"Watchlist: <b>{', '.join(wl) if wl else 'none'}</b>",
                 f"Excluded sectors: <b>{', '.join(ex) if ex else 'none'}</b>"]
        return "\n".join(lines)

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
        wl = config.get("watchlist", [])
        ex = config.get("excluded_sectors", [])
        return (
            f"<b>⚙️ Config ({status})</b>\n"
            f"Stock ST:         ${config.get('short_term_budget')}\n"
            f"Stock LT:         ${config.get('long_term_budget')}\n"
            f"Crypto ST:        ${config.get('crypto_short_budget', 20)}\n"
            f"Crypto LT:        ${config.get('crypto_long_budget', 30)}\n"
            f"Risk profile:     {config.get('risk_profile', 'moderate')}\n"
            f"Watchlist:        {', '.join(wl) if wl else 'none'}\n"
            f"Excluded sectors: {', '.join(ex) if ex else 'none'}\n"
            f"Stop loss:        {config.get('stop_loss_pct')}%\n"
            f"Target gain:      {config.get('target_gain_pct')}%"
        )

    # Bare budget commands — prompt for the value
    if text in ("SET ST", "SET LT", "SET CST", "SET CLT"):
        cmd_map = {"SET ST": "set_st", "SET LT": "set_lt",
                   "SET CST": "set_cst", "SET CLT": "set_clt"}
        _prompt_for_param(cmd_map[text], chat_id)
        return ""

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

    # ── /bought [TICKER|name [price] [shares]] ───────────────────────────────
    if text == "BOUGHT":
        _prompt_for_param("bought", chat_id)
        return ""

    if text.startswith("BOUGHT "):
        parts      = text.split()
        name_raw   = parts[1]
        price_raw  = parts[2] if len(parts) >= 3 else None
        shares_raw = parts[3] if len(parts) >= 4 else None

        candidates = _resolve_ticker_candidates(name_raw)
        if len(candidates) > 1:
            price_enc  = price_raw  or ""
            shares_enc = shares_raw or ""
            buttons = [[{"text": f"{c['ticker']} — {c['name']}",
                         "callback_data": f"buy|{c['ticker']}|{price_enc}|{shares_enc}"}]
                       for c in candidates]
            send_inline_keyboard(f"🔍 Which stock did you mean by <b>{_esc(name_raw)}</b>?",
                                 buttons, chat_id=chat_id)
            return ""

        return _execute_bought(candidates[0]["ticker"], price_raw, shares_raw, chat_id)

    # ── /sold [TICKER|name [price]] ──────────────────────────────────────────
    if text == "SOLD":
        _prompt_for_param("sold", chat_id)
        return ""

    if text.startswith("SOLD "):
        parts     = text.split()
        name_raw  = parts[1]
        price_raw = parts[2] if len(parts) >= 3 else None

        candidates = _resolve_ticker_candidates(name_raw)
        if len(candidates) > 1:
            price_enc = price_raw or ""
            buttons = [[{"text": f"{c['ticker']} — {c['name']}",
                         "callback_data": f"sell|{c['ticker']}|{price_enc}"}]
                       for c in candidates]
            send_inline_keyboard(f"🔍 Which stock did you mean by <b>{_esc(name_raw)}</b>?",
                                 buttons, chat_id=chat_id)
            return ""

        return _execute_sold(candidates[0]["ticker"], price_raw, chat_id)

    # ── /cancel — undo accidental /bought or /sold ───────────────────────────
    if text == "CANCEL":
        _prompt_for_param("cancel", chat_id)
        return ""

    if text.startswith("CANCEL "):
        from trade_logger import cancel_trade, reopen_trade
        from config_manager import load_trade_log

        name_raw   = text.split(None, 1)[1].strip()
        candidates = _resolve_ticker_candidates(name_raw)

        # Show ticker picker if ambiguous
        if len(candidates) > 1:
            buttons = [[{
                "text": f"{c['ticker']} — {c['name']}",
                "callback_data": f"cancel_auto|{c['ticker']}",
            }] for c in candidates]
            send_inline_keyboard(
                f"🔍 Which stock did you mean?", buttons, chat_id=chat_id,
            )
            return ""

        ticker = candidates[0]["ticker"]
        log    = load_trade_log()
        has_open   = any(t["ticker"] == ticker for t in log.get("open", []))
        has_closed = any(t["ticker"] == ticker for t in log.get("closed", []))

        if not has_open and not has_closed:
            return f"⚠️ No trade found for <b>{ticker}</b>. Use /positions to see open trades."

        # Build a descriptive confirmation message
        if has_open and has_closed:
            # Show what-to-undo choice first, confirmation happens after
            open_trade   = next(t for t in log["open"] if t["ticker"] == ticker)
            closed_trade = next(t for t in reversed(log["closed"]) if t["ticker"] == ticker)
            send_inline_keyboard(
                f"↩️ What do you want to undo for <b>{ticker}</b>?\n\n"
                f"Open:   entry <code>${open_trade.get('entry_price')}</code>\n"
                f"Closed: sold <code>${closed_trade.get('closed_price')}</code>  "
                f"({'+' if closed_trade.get('return_pct',0)>=0 else ''}{closed_trade.get('return_pct',0)}%)",
                [[
                    {"text": "❌ Undo buy",  "callback_data": f"confirm_cancel|{ticker}"},
                    {"text": "↩️ Undo sell", "callback_data": f"confirm_reopen|{ticker}"},
                ]],
                chat_id=chat_id,
            )
            return ""

        if has_open:
            open_trade = next(t for t in log["open"] if t["ticker"] == ticker)
            send_inline_keyboard(
                f"⚠️ Confirm: remove open position for <b>{ticker}</b>?\n"
                f"Entry <code>${open_trade.get('entry_price')}</code> · "
                f"opened {open_trade.get('opened_date')}",
                [[
                    {"text": "✅ Yes, undo buy",  "callback_data": f"confirm_cancel|{ticker}"},
                    {"text": "❌ No, keep it",    "callback_data": "cancel_abort"},
                ]],
                chat_id=chat_id,
            )
            return ""

        if has_closed:
            closed_trade = next(t for t in reversed(log["closed"]) if t["ticker"] == ticker)
            ret  = closed_trade.get('return_pct', 0)
            sign = "+" if ret >= 0 else ""
            send_inline_keyboard(
                f"⚠️ Confirm: reopen <b>{ticker}</b> as if the sale never happened?\n"
                f"Was sold at <code>${closed_trade.get('closed_price')}</code>  ({sign}{ret}%)",
                [[
                    {"text": "✅ Yes, undo sell", "callback_data": f"confirm_reopen|{ticker}"},
                    {"text": "❌ No, keep it",    "callback_data": "cancel_abort"},
                ]],
                chat_id=chat_id,
            )
            return ""

    # ── /positions ────────────────────────────────────────────────────────────
    if text == "PORTFOLIO":
        from config_manager import load_trade_log
        import yfinance as yf

        log  = load_trade_log()
        open_trades = log.get("open", [])
        if not open_trades:
            return "📭 No open positions. Use <code>/bought AAPL 182.50</code> to log a trade."

        # Fetch current prices for all tickers
        tickers_list = [t["ticker"] for t in open_trades]
        try:
            raw = yf.download(
                " ".join(tickers_list), period="1d", interval="1m",
                progress=False, auto_adjust=True,
            )
            if hasattr(raw["Close"], "iloc"):
                prices = {t: float(raw["Close"][t].dropna().iloc[-1])
                          for t in tickers_list if t in raw["Close"].columns}
            else:
                prices = {tickers_list[0]: float(raw["Close"].dropna().iloc[-1])}
        except Exception:
            prices = {}

        # Build position summaries + get AI guidance in one Haiku call
        position_data = []
        for t in open_trades:
            ticker  = t["ticker"]
            entry   = float(t.get("entry_price") or 0)
            target  = float(t.get("target_price") or 0)
            stop    = float(t.get("stop_loss") or 0)
            current = prices.get(ticker)
            if current and entry:
                ret_pct    = (current - entry) / entry * 100
                to_target  = (target / current - 1) * 100 if target else None
                to_stop    = (stop   / current - 1) * 100 if stop   else None
                position_data.append({
                    "ticker":     ticker,
                    "entry":      entry,
                    "current":    round(current, 2),
                    "target":     target or None,
                    "stop":       stop or None,
                    "return_pct": round(ret_pct, 2),
                    "to_target":  round(to_target, 2) if to_target is not None else None,
                    "to_stop":    round(to_stop,  2) if to_stop  is not None else None,
                })

        # Ask Haiku for one-line guidance per position
        guidance: dict[str, str] = {}
        if position_data:
            try:
                import anthropic as _ant, json as _j
                prompt = (
                    "You are a brief trading advisor. For each position below give ONE short action line "
                    "(max 10 words): HOLD / ADD MORE / TAKE PROFIT / TIGHTEN STOP / CONSIDER SELLING / etc. "
                    "Be direct. Consider proximity to target/stop and current return.\n\n"
                    f"Positions: {_j.dumps(position_data)}\n\n"
                    'Return ONLY a JSON object keyed by ticker, e.g. {"AAPL": "Hold — strong, 3.2% from target"}'
                )
                client  = _ant.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
                message = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                guidance = _j.loads(message.content[0].text.strip())
            except Exception as exc:
                print(f"[portfolio] Guidance fetch failed (non-critical): {exc}")

        lines = ["<b>📂 Portfolio</b>", ""]
        for t in open_trades:
            ticker  = t["ticker"]
            entry   = float(t.get("entry_price") or 0)
            target  = t.get("target_price")
            stop    = t.get("stop_loss")
            current = prices.get(ticker)
            manual  = "  <i>(manual)</i>" if t.get("manual") else ""

            if current and entry:
                ret_pct   = (current - entry) / entry * 100
                sign      = "+" if ret_pct >= 0 else ""
                pnl_emoji = "🟢" if ret_pct >= 0 else "🔴"
                stop_warn = "  ⚠️ <b>NEAR STOP</b>" if stop and current <= float(stop) * 1.01 else ""
                hit_target = "  🎯 <b>NEAR TARGET</b>" if target and current >= float(target) * 0.99 else ""
                to_target = f"{((float(target)/current-1)*100):+.1f}% to target" if target else ""
                to_stop   = f"{((float(stop)/current-1)*100):+.1f}% to stop"   if stop   else ""
                price_line = " · ".join(filter(None, [to_target, to_stop]))

                lines.append(
                    f"{pnl_emoji} <b>{ticker}</b>  <code>${current:.2f}</code>  "
                    f"<i>({sign}{ret_pct:.1f}%)</i>{stop_warn}{hit_target}{manual}"
                )
                lines.append(f"   entry <code>${entry:.2f}</code>  {price_line}")
                if ticker in guidance:
                    lines.append(f"   💡 <i>{guidance[ticker]}</i>")
            else:
                lines.append(f"⬜ <b>{ticker}</b>  entry <code>${entry:.2f}</code>  "
                             f"<i>(price unavailable)</i>{manual}")
                if target or stop:
                    lines.append(f"   target <code>${target}</code>  stop <code>${stop}</code>")
            lines.append("")

        lines.append("<i>Use <code>/sold TICKER price</code> to close a position.</i>")
        return "\n".join(lines)

    # ── Natural language fallback ─────────────────────────────────────────────
    return _handle_natural_language(original or text)


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
