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
        f"<i>{picks.get('daily_summary', '')}</i>",
    ]
    if macro_line:
        lines.append(macro_line)

    # ── Short-term stocks  ▸▸▸ collapsible ───────────────────────────────────
    if st_picks:
        st_body = []
        for i, s in enumerate(st_picks, 1):
            entry, target, stop = s.get("entry_price"), s.get("target_price"), s.get("stop_loss")
            earnings_tag = f"  🗓️ Earnings {s['earnings_date']}" if s.get("earnings_date") else ""
            alloc = s.get("allocation")
            alloc_str = f"  · invest <code>${_p(alloc)}</code>" if alloc is not None else ""
            st_body += [
                f"{i}. <b>{s.get('ticker')}</b> · {_short_company(s.get('company', ''))}  {_stars(s.get('conviction', 3))}{earnings_tag}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  stop <code>${_p(stop)}</code>{alloc_str}",
                f"   {s.get('thesis')}",
            ]
        lines += [
            "",
            "▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸",
            f"📈 <b>Short Term Stocks</b>  <code>${short_budget}/trade</code>  <i>👆 tap to reveal</i>",
            "<tg-spoiler>" + "\n".join(st_body) + "</tg-spoiler>",
        ]

    # ── Long-term stocks  ━━━ collapsible ────────────────────────────────────
    if lt_picks:
        lt_body = []
        for i, s in enumerate(lt_picks, 1):
            entry, target = s.get("entry_price"), s.get("target_price")
            alloc = s.get("allocation")
            alloc_str = f"  · DCA <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
            lt_body += [
                f"{i}. <b>{s.get('ticker')}</b> · {_short_company(s.get('company', ''))}  {_stars(s.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  · {s.get('horizon')}{alloc_str}",
                f"   {s.get('thesis')}",
            ]
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🏦 <b>Long Term Stocks</b>  <code>${long_budget}/mo DCA</code>  <i>👆 tap to reveal</i>",
            "<tg-spoiler>" + "\n".join(lt_body) + "</tg-spoiler>",
        ]

    # ── Crypto short-term  ┈ ┈ ┈ collapsible ────────────────────────────────
    if cst_picks:
        cst_body = []
        for i, c in enumerate(cst_picks, 1):
            entry, target, stop = c.get("entry_price"), c.get("target_price"), c.get("stop_loss")
            alloc = c.get("allocation")
            alloc_str = f"  · invest <code>${_p(alloc)}</code>" if alloc is not None else ""
            cst_body += [
                f"{i}. <b>{c.get('symbol')}</b> · {_short_company(c.get('name', ''))}  {_stars(c.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  stop <code>${_p(stop)}</code>{alloc_str}",
                f"   {c.get('thesis')}",
            ]
        lines += [
            "",
            "┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈",
            f"🪙 <b>Crypto Short Term</b>  <code>${crypto_st_budget}/trade</code>  <i>⚡ HIGH RISK · 👆 tap</i>",
            "<tg-spoiler>" + "\n".join(cst_body) + "</tg-spoiler>",
        ]

    # ── Crypto long-term  ◆ ◆ ◆ collapsible ─────────────────────────────────
    if clt_picks:
        clt_body = []
        for i, c in enumerate(clt_picks, 1):
            entry, target = c.get("entry_price"), c.get("target_price")
            alloc = c.get("allocation")
            alloc_str = f"  · DCA <code>${_p(alloc)}/mo</code>" if alloc is not None else ""
            clt_body += [
                f"{i}. <b>{c.get('symbol')}</b> · {_short_company(c.get('name', ''))}  {_stars(c.get('conviction', 3))}",
                f"   <code>${_p(entry)}</code> → <code>${_p(target)}</code> <i>({_upside(entry, target)})</i>  · {c.get('horizon')}{alloc_str}",
                f"   {c.get('thesis')}",
            ]
        lines += [
            "",
            "◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆",
            f"💎 <b>Crypto Long Term</b>  <code>${crypto_lt_budget}/mo DCA</code>  <i>👆 tap to reveal</i>",
            "<tg-spoiler>" + "\n".join(clt_body) + "</tg-spoiler>",
        ]

    # ── Footer ────────────────────────────────────────────────────────────────
    has_crypto_picks = bool(cst_picks or clt_picks)
    if has_crypto_picks:
        budget_line = (f"💰 <b>Budgets:</b> ST <code>${short_budget}/trade</code> · "
                       f"LT <code>${long_budget}/mo DCA</code> · "
                       f"CST <code>${crypto_st_budget}/trade</code> · "
                       f"CLT <code>${crypto_lt_budget}/mo DCA</code>")
        adjust_line = (f"<i>To adjust: /set_st {short_budget} · /set_lt {long_budget} · "
                       f"/set_cst {crypto_st_budget} · /set_clt {crypto_lt_budget}</i>")
    else:
        budget_line = (f"💰 <b>Budgets:</b> ST <code>${short_budget}/trade</code> · "
                       f"LT <code>${long_budget}/mo DCA</code>")
        adjust_line = (f"<i>To adjust: /set_st {short_budget} · /set_lt {long_budget} "
                       f"— replace with your amount (e.g. /set_st 50)</i>")

    # ── Sector rotation insight ───────────────────────────────────────────────
    seen_sectors: set = set()
    sector_list: list = []
    for p in st_picks + lt_picks:
        s = p.get("sector", "")
        if s and s != "Unknown" and s not in seen_sectors:
            sector_list.append(s)
            seen_sectors.add(s)
    sector_line = f"🏭 <b>Sectors today:</b> {', '.join(sector_list)}" if sector_list else ""

    lines += [
        "",
        budget_line,
        adjust_line,
    ]
    if sector_line:
        lines.append(sector_line)
    lines += [
        "",
        "⚠️ <i>Not financial advice.</i>",
        "",
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
        "📋 <b>Commands</b>  <i>👆 tap to expand</i>",
        "<tg-spoiler>"
        "── Daily ──\n"
        "/today · /prices · /perf\n"
        "/explain microsoft  — ask about any pick\n"
        "\n── Watchlist &amp; Filters ──\n"
        "/watch tesla nvidia  — always include these\n"
        "/watch none  — clear watchlist\n"
        "/exclude energy  — skip a sector\n"
        "/exclude none  — clear exclusions\n"
        "/watchlist  — show current AI settings\n"
        "\n── Risk &amp; Budgets ──\n"
        "/set_risk aggressive  — conservative | moderate | aggressive\n"
        "/set_st 50 · /set_lt 100\n"
        "/set_cst 30 · /set_clt 50\n"
        "\n── Control ──\n"
        "/status · /pause · /resume · /reset · /help"
        "</tg-spoiler>",
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
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
    reply = _parse_and_execute(text, original=message_text.strip())
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


def _parse_and_execute(text: str, original: str = "") -> str:
    """Parse command string and return reply."""

    # Telegram slash-commands (/help) or plain text (HELP) — normalise both
    text = text.lstrip("/").replace("_", " ")   # /set_st 30 → SET ST 30

    if text == "TODAY":
        picks = load_picks()
        if not picks:
            return "📭 No picks for today yet. Check back after 8 AM ET."
        config = get_config()
        return format_daily_message(picks, config)

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
            "\n<b>— Control —</b>\n"
            "/pause                    — stop daily picks\n"
            "/resume                   — restart daily picks\n"
            "/status                   — show full config\n"
            "/reset                    — restore default config\n"
            "/help                     — show this list"
        )

    # /set_risk conservative | moderate | aggressive  (or natural language)
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
