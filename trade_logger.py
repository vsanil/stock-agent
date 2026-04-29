"""
trade_logger.py — Persistent trade tracking for short-term picks.

Lifecycle:
  Morning run   → open_trades(picks)          — log each ST pick
  Confirmation  → check_and_close_trades()    — close if target/stop hit
  /perf command → get_performance_stats()     — all-time stats
  Saturday      → get_weekly_closed_trades()  — this week's closed trades

Only short-term picks are tracked (they have clear entry/target/stop).
Long-term DCA picks are tracked separately via weekly_picks.json.
Trades expire after 28 days if neither target nor stop is hit.
"""

from datetime import date
from config_manager import load_trade_log, save_trade_log


# ── Open trades (morning run) ─────────────────────────────────────────────────

def open_trades(picks: dict) -> None:
    """
    Add today's short-term picks (stocks + crypto) to the open trades list.
    Skips duplicates — safe to call multiple times.
    """
    today = date.today().isoformat()
    log   = load_trade_log()

    open_tickers = {t["ticker"] for t in log["open"]}
    new_count    = 0

    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})

    for s in stocks.get("short_term", []):
        ticker = s.get("ticker")
        if not ticker or ticker in open_tickers:
            continue
        log["open"].append({
            "ticker":       ticker,
            "asset_type":   "stock",
            "entry_price":  s.get("entry_price"),
            "target_price": s.get("target_price"),
            "stop_loss":    s.get("stop_loss"),
            "allocation":   s.get("allocation"),
            "conviction":   s.get("conviction"),
            "thesis":       s.get("thesis", ""),
            "opened_date":  today,
        })
        open_tickers.add(ticker)
        new_count += 1

    for c in crypto.get("short_term", []):
        ticker = c.get("symbol", "").upper()
        if not ticker or ticker in open_tickers:
            continue
        log["open"].append({
            "ticker":       ticker,
            "asset_type":   "crypto",
            "entry_price":  c.get("entry_price"),
            "target_price": c.get("target_price"),
            "stop_loss":    c.get("stop_loss"),
            "allocation":   c.get("allocation"),
            "conviction":   c.get("conviction"),
            "thesis":       c.get("thesis", ""),
            "opened_date":  today,
        })
        open_tickers.add(ticker)
        new_count += 1

    if new_count:
        save_trade_log(log)
        print(f"[trade_logger] Opened {new_count} new trade(s).")
    else:
        print("[trade_logger] No new trades to open (already logged or no picks).")


# ── Close trades (confirmation run) ──────────────────────────────────────────

def check_and_close_trades(current_prices: dict) -> list[dict]:
    """
    Compare open trades against current prices.
    Closes trades where target hit, stop hit, or open > 28 days.
    Returns list of newly closed trades (empty if none).
    """
    today = date.today().isoformat()
    log   = load_trade_log()

    if not log["open"]:
        return []

    still_open    = []
    newly_closed  = []

    for trade in log["open"]:
        ticker  = trade["ticker"]
        current = current_prices.get(ticker)

        if current is None:
            still_open.append(trade)
            continue

        entry  = trade.get("entry_price")
        target = trade.get("target_price")
        stop   = trade.get("stop_loss")

        if not entry:
            still_open.append(trade)
            continue

        outcome = None

        # Check stop first (worst case priority)
        if stop and float(current) <= float(stop):
            outcome = "stop"
        elif target and float(current) >= float(target):
            outcome = "target"
        else:
            # Expire after 28 calendar days
            try:
                days_open = (date.today() - date.fromisoformat(trade["opened_date"])).days
                if days_open >= 28:
                    outcome = "expired"
            except Exception:
                pass

        if outcome:
            return_pct  = (float(current) - float(entry)) / float(entry) * 100
            allocation  = float(trade.get("allocation") or 0)
            gain_usd    = round(allocation * return_pct / 100, 2)
            closed      = {
                **trade,
                "closed_date":  today,
                "closed_price": round(float(current), 2),
                "outcome":      outcome,
                "return_pct":   round(return_pct, 2),
                "gain_usd":     gain_usd,
            }
            log["closed"].append(closed)
            newly_closed.append(closed)
            print(f"[trade_logger] Closed {ticker} — {outcome} "
                  f"@ ${current} ({return_pct:+.1f}%)")
        else:
            still_open.append(trade)

    if newly_closed:
        log["open"] = still_open
        save_trade_log(log)

    return newly_closed


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_performance_stats(asset_type: str | None = None) -> dict | None:
    """
    Compute all-time stats from closed trades.
    Pass asset_type="stock" or "crypto" to filter, or None for combined.
    """
    log    = load_trade_log()
    closed = log.get("closed", [])

    if asset_type:
        closed = [t for t in closed if t.get("asset_type") == asset_type]

    if not closed:
        return None

    returns          = [(t["ticker"], t["return_pct"]) for t in closed]
    wins             = sum(1 for _, r in returns if r > 0)
    avg_return       = sum(r for _, r in returns) / len(returns)
    total_gain_usd   = sum(t.get("gain_usd", 0) for t in closed)
    total_deployed   = sum(t.get("allocation", 0) for t in closed)
    open_count       = len(log.get("open", []))

    by_outcome = {}
    for t in closed:
        o = t.get("outcome", "unknown")
        by_outcome[o] = by_outcome.get(o, 0) + 1

    return {
        "count":              len(closed),
        "wins":               wins,
        "win_rate":           round(wins / len(closed) * 100),
        "avg_return":         round(avg_return, 1),
        "best":               max(returns, key=lambda x: x[1]),
        "worst":              min(returns, key=lambda x: x[1]),
        "total_gain_usd":     round(total_gain_usd, 2),
        "total_deployed_usd": round(total_deployed, 2),
        "targets_hit":        by_outcome.get("target", 0),
        "stops_hit":          by_outcome.get("stop", 0),
        "expired":            by_outcome.get("expired", 0),
        "open_count":         open_count,
    }


def get_weekly_closed_trades() -> list[dict]:
    """Return trades closed this calendar week (Mon–today)."""
    from datetime import timedelta
    today    = date.today()
    week_start = today - timedelta(days=today.weekday())   # Monday

    log    = load_trade_log()
    closed = log.get("closed", [])

    result = []
    for t in closed:
        try:
            d = date.fromisoformat(t.get("closed_date", ""))
            if week_start <= d <= today:
                result.append(t)
        except ValueError:
            pass
    return result
