"""
performance_tracker.py — Saturday weekly P&L recap.

Loads this week's picks from the Gist, fetches current prices via yfinance
(stocks) and CoinGecko (crypto), then computes compact performance stats.
"""

import requests
import yfinance as yf

from config_manager import load_weekly_picks

COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price"


def build_weekly_recap() -> dict | None:
    """
    Returns a recap dict, or None if there are no picks this week.

    Shape:
    {
        "days_tracked": 4,
        "stocks":  { "count": 8, "wins": 6, "avg_return": 1.9,
                     "best": ("NVDA", 4.8), "worst": ("AAPL", -1.2) },
        "crypto":  { ... same ... },
        "spy_return": 0.6,   # S&P 500 weekly return %, or None
    }
    """
    weekly = load_weekly_picks()
    if not weekly:
        print("[performance_tracker] No weekly picks found.")
        return None

    print(f"[performance_tracker] Loaded picks for {len(weekly)} day(s).")

    # ── Collect all entry prices ───────────────────────────────────────────────
    stock_entries: dict[str, list[float]] = {}  # ticker → [entry_price, ...]
    crypto_entries: dict[str, dict] = {}         # symbol → {id, entries: [...]}

    for _date, picks in weekly.items():
        stocks = picks.get("stocks", picks)
        crypto = picks.get("crypto", {})

        for section in ("short_term", "long_term"):
            for s in stocks.get(section, []):
                t  = s.get("ticker")
                ep = s.get("entry_price")
                if t and ep:
                    stock_entries.setdefault(t, []).append(float(ep))

            for c in crypto.get(section, []):
                sym = c.get("symbol", "").upper()
                cid = c.get("id", "")
                ep  = c.get("entry_price")
                if sym and ep:
                    if sym not in crypto_entries:
                        crypto_entries[sym] = {"id": cid, "entries": []}
                    crypto_entries[sym]["entries"].append(float(ep))

    # ── Fetch current prices ───────────────────────────────────────────────────
    current: dict[str, float] = {}

    # Stocks + SPY via yfinance
    all_tickers = list(stock_entries.keys()) + ["SPY"]
    for ticker in all_tickers:
        try:
            price = yf.Ticker(ticker).fast_info.last_price
            if price:
                current[ticker] = float(price)
        except Exception as exc:
            print(f"[performance_tracker] Could not fetch {ticker}: {exc}")

    # S&P 500 weekly return (5-day window)
    spy_return = None
    try:
        hist = yf.Ticker("SPY").history(period="5d")
        if len(hist) >= 2:
            spy_return = (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100
    except Exception as exc:
        print(f"[performance_tracker] SPY benchmark failed: {exc}")

    # Crypto via CoinGecko bulk call
    if crypto_entries:
        try:
            ids  = ",".join(v["id"] for v in crypto_entries.values() if v["id"])
            resp = requests.get(
                COINGECKO_SIMPLE,
                params={"ids": ids, "vs_currencies": "usd"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            for sym, info in crypto_entries.items():
                price = data.get(info["id"], {}).get("usd")
                if price:
                    current[sym] = float(price)
        except Exception as exc:
            print(f"[performance_tracker] Could not fetch crypto prices: {exc}")

    # ── Compute returns ────────────────────────────────────────────────────────
    def calc_returns(entries_map, key_field="ticker"):
        result = []
        for key, val in entries_map.items():
            entries = val if isinstance(val, list) else val["entries"]
            cp = current.get(key)
            if cp and entries:
                avg_entry = sum(entries) / len(entries)
                ret = (cp - avg_entry) / avg_entry * 100
                result.append((key, round(ret, 1)))
        return result

    stock_returns  = calc_returns(stock_entries)
    crypto_returns = calc_returns(crypto_entries)

    def stats(returns):
        if not returns:
            return None
        wins = sum(1 for _, r in returns if r > 0)
        avg  = sum(r for _, r in returns) / len(returns)
        return {
            "count":      len(returns),
            "wins":       wins,
            "avg_return": round(avg, 1),
            "best":       max(returns, key=lambda x: x[1]),
            "worst":      min(returns, key=lambda x: x[1]),
        }

    return {
        "days_tracked": len(weekly),
        "stocks":       stats(stock_returns),
        "crypto":       stats(crypto_returns),
        "spy_return":   round(spy_return, 1) if spy_return is not None else None,
    }
