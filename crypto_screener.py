"""
crypto_screener.py — Crypto screener using CoinGecko free API (no key needed).

Two-phase approach for reliable RSI + MA scoring:
  Phase 1: Single bulk call → filter + basic scoring → top CANDIDATE_N coins
  Phase 2: Individual market_chart calls for those candidates → full RSI/MA scoring

If the bulk call already includes sparkline data, Phase 2 is skipped entirely.
CoinGecko free tier: ~30 calls/min. Phase 2 adds ~15 calls with 0.5s delays = ~10s.
"""

import time
import statistics
import requests

COINGECKO_BASE  = "https://api.coingecko.com/api/v3"
MAX_COINS       = 100    # Fetched in the bulk call
CANDIDATE_N     = 15     # Fetch individual price history for this many candidates
TOP_N           = 5      # Final picks returned per category
HISTORY_DELAY   = 0.5    # Seconds between individual market_chart calls

# Min market cap filter — exclude micro-caps
MIN_MARKET_CAP = 200_000_000   # $200M

# Stablecoins, wrapped tokens, liquid staking tokens to exclude
EXCLUDE_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "frax", "true-usd",
    "usdd", "gemini-dollar", "paxos-standard", "wrapped-bitcoin",
    "wrapped-ethereum", "staked-ether", "rocket-pool-eth",
    "coinbase-wrapped-staked-eth", "mantle-staked-ether",
    "bridged-usdc-polygon-pos-bridge", "first-digital-usd",
    "paypal-usd", "eurc", "lido-staked-ether",
}


# ── CoinGecko API calls ───────────────────────────────────────────────────────

def _get_top_coins(limit: int = MAX_COINS) -> list[dict]:
    """Bulk fetch top coins by market cap. Requests sparkline but doesn't require it."""
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency":            "usd",
        "order":                  "market_cap_desc",
        "per_page":               limit,
        "page":                   1,
        "sparkline":              True,
        "price_change_percentage": "24h,7d,30d",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _get_price_history(coin_id: str, days: int = 7) -> list[float]:
    """
    Fetch hourly price history for a single coin via /coins/{id}/market_chart.
    Returns a flat list of prices, or [] on failure.
    This endpoint reliably returns data regardless of sparkline availability.
    """
    try:
        url  = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
        resp = requests.get(
            url,
            params={"vs_currency": "usd", "days": days, "interval": "hourly"},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json().get("prices", [])
        return [p[1] for p in raw]   # [[timestamp, price], ...] → [price, ...]
    except Exception as exc:
        print(f"[crypto_screener] Price history fetch failed for {coin_id}: {exc}")
        return []


# ── Technical indicators ──────────────────────────────────────────────────────

def _simple_rsi(prices: list[float], period: int = 14) -> float | None:
    if not prices or len(prices) < period + 1:
        return None
    deltas   = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains    = [d for d in deltas[-period:] if d > 0]
    losses   = [-d for d in deltas[-period:] if d < 0]
    avg_gain = statistics.mean(gains)  if gains  else 0
    avg_loss = statistics.mean(losses) if losses else 1e-9
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _simple_ma(prices: list[float], period: int) -> float | None:
    if not prices or len(prices) < max(period, 1):
        return None
    return round(statistics.mean(prices[-period:]), 8)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _short_term_score(coin: dict, prices: list[float]) -> tuple[int, dict]:
    score = 0
    metrics = {}
    current_price = coin.get("current_price", 0)

    # RSI — needs price history (25 pts)
    rsi = _simple_rsi(prices[-30:], period=14) if prices else None
    metrics["rsi"] = rsi
    if rsi and 40 <= rsi <= 65:
        score += 25

    # 24h price change > 2% (20 pts)
    chg_24h = coin.get("price_change_percentage_24h_in_currency", 0) or 0
    metrics["price_change_24h_pct"] = round(chg_24h, 2)
    if chg_24h > 2:
        score += 20

    # Price above 48h MA — needs price history (20 pts)
    ma48 = _simple_ma(prices, 48) if prices else None
    metrics["ma48"] = ma48
    if ma48 and current_price > ma48:
        score += 20

    # 7d change positive but < 30% (20 pts)
    chg_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
    metrics["price_change_7d_pct"] = round(chg_7d, 2)
    if 0 < chg_7d < 30:
        score += 20

    # 24h volume above $50M (15 pts)
    vol_24h = coin.get("total_volume", 0) or 0
    metrics["volume_24h_usd"] = vol_24h
    if vol_24h > 50_000_000:
        score += 15

    return score, metrics


def _long_term_score(coin: dict, prices: list[float]) -> tuple[int, dict]:
    score = 0
    metrics = {}
    current_price = coin.get("current_price", 0)
    market_cap    = coin.get("market_cap", 0)
    ath           = coin.get("ath", 0)

    # Market cap > $10B (30 pts)
    metrics["market_cap_usd"] = market_cap
    if market_cap and market_cap > 10_000_000_000:
        score += 30

    # Price above 7-day MA — needs price history (25 pts)
    ma_7d = _simple_ma(prices, len(prices)) if prices else None
    metrics["ma7d"] = ma_7d
    if ma_7d and current_price > ma_7d:
        score += 25

    # 30d price change positive (20 pts)
    chg_30d = coin.get("price_change_percentage_30d_in_currency", 0) or 0
    metrics["price_change_30d_pct"] = round(chg_30d, 2)
    if chg_30d > 0:
        score += 20

    # Within 60% of ATH (15 pts)
    metrics["ath_usd"] = ath
    if ath and current_price > 0:
        pct_from_ath = ((ath - current_price) / ath) * 100
        metrics["pct_below_ath"] = round(pct_from_ath, 1)
        if pct_from_ath < 60:
            score += 15

    # Room to grow — ATH > 30% above current (10 pts)
    if ath and current_price > 0 and ath > current_price * 1.3:
        score += 10

    return score, metrics


# ── Main screener ─────────────────────────────────────────────────────────────

def run_crypto_screener() -> dict:
    """
    Two-phase crypto screening:
      Phase 1 — Bulk call: filter + basic score → pick top CANDIDATE_N
      Phase 2 — Individual price history: full RSI/MA scoring for candidates
                 (skipped if sparkline already present in bulk response)
    """
    print(f"[crypto_screener] Fetching top {MAX_COINS} coins from CoinGecko...")
    try:
        coins = _get_top_coins(MAX_COINS)
    except Exception as exc:
        print(f"[crypto_screener] ERROR fetching coin list: {exc}")
        return {"short_term": [], "long_term": []}

    # Filter stablecoins, wrapped tokens, micro-caps
    coins = [
        c for c in coins
        if c.get("id") not in EXCLUDE_IDS
        and (c.get("market_cap") or 0) >= MIN_MARKET_CAP
    ]

    has_sparkline = sum(1 for c in coins
                        if (c.get("sparkline_in_7d") or {}).get("price"))
    print(f"[crypto_screener] {len(coins)} coins after exclusions, "
          f"{has_sparkline} with sparkline data.")

    # Phase 1: basic score on all coins (no price history needed)
    basic_scores = []
    for coin in coins:
        prices    = (coin.get("sparkline_in_7d") or {}).get("price") or []
        st_score, _ = _short_term_score(coin, prices)
        lt_score, _ = _long_term_score(coin, prices)
        basic_scores.append((coin, st_score, lt_score))

    # Pick top CANDIDATE_N by combined score for price history fetch
    combined = sorted(basic_scores, key=lambda x: x[1] + x[2], reverse=True)
    candidates = [c[0] for c in combined[:CANDIDATE_N]]

    # Phase 2: fetch individual price history if sparkline was missing
    needs_history = has_sparkline < len(candidates)
    if needs_history:
        print(f"[crypto_screener] Fetching price history for "
              f"{len(candidates)} candidates (sparkline unavailable)...")
        for coin in candidates:
            existing = (coin.get("sparkline_in_7d") or {}).get("price") or []
            if not existing:
                prices = _get_price_history(coin["id"], days=7)
                coin["_fetched_prices"] = prices
                time.sleep(HISTORY_DELAY)
    else:
        print("[crypto_screener] Sparkline data present — skipping individual fetches.")

    # Final scoring with full price data
    short_results = []
    long_results  = []

    for coin in candidates:
        # Prefer fetched prices, then sparkline, then empty
        prices = (coin.get("_fetched_prices")
                  or (coin.get("sparkline_in_7d") or {}).get("price")
                  or [])

        symbol        = coin.get("symbol", "").upper()
        name          = coin.get("name", coin["id"])
        current_price = coin.get("current_price", 0)

        st_score, st_metrics = _short_term_score(coin, prices)
        short_results.append({
            "id": coin["id"], "symbol": symbol, "name": name,
            "current_price": current_price,
            "market_cap": coin.get("market_cap"),
            "score": st_score, **st_metrics,
        })

        lt_score, lt_metrics = _long_term_score(coin, prices)
        long_results.append({
            "id": coin["id"], "symbol": symbol, "name": name,
            "current_price": current_price,
            "market_cap": coin.get("market_cap"),
            "score": lt_score, **lt_metrics,
        })

    short_top = sorted(short_results, key=lambda x: x["score"], reverse=True)[:TOP_N]
    long_top  = sorted(long_results,  key=lambda x: x["score"], reverse=True)[:TOP_N]

    print(f"[crypto_screener] Top short-term: {[c['symbol'] for c in short_top]}")
    print(f"[crypto_screener] Top long-term:  {[c['symbol'] for c in long_top]}")

    return {"short_term": short_top, "long_term": long_top}


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    results = run_crypto_screener()
    print(json.dumps(results, indent=2, default=str))
