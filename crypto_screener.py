"""
crypto_screener.py — Crypto screener using CoinGecko free API (no key needed).
Uses sparkline data bundled in the single /coins/markets call — no per-coin requests,
no rate limiting. Returns top short-term and long-term crypto candidates.
"""

import statistics
import requests

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
MAX_COINS = 100   # All fetched in ONE API call via sparkline=true
TOP_N = 5

# Min market cap filter — exclude micro-caps and suspicious tokens
MIN_MARKET_CAP = 200_000_000   # $200M

# Stablecoins, wrapped tokens, and liquid staking tokens to exclude
EXCLUDE_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "frax", "true-usd",
    "usdd", "gemini-dollar", "paxos-standard", "wrapped-bitcoin",
    "wrapped-ethereum", "staked-ether", "rocket-pool-eth",
    "coinbase-wrapped-staked-eth", "mantle-staked-ether",
    "bridged-usdc-polygon-pos-bridge", "first-digital-usd",
    "paypal-usd", "eurc", "lido-staked-ether",
}


# ── CoinGecko — single bulk call ──────────────────────────────────────────────

def _get_top_coins(limit: int = MAX_COINS) -> list[dict]:
    """
    Fetch top coins by market cap WITH 7-day sparkline prices included.
    sparkline=true returns ~168 hourly price points — enough for RSI + MA.
    This is a SINGLE API call — no per-coin requests needed.
    """
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": True,                      # 7-day hourly prices bundled in
        "price_change_percentage": "24h,7d,30d",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ── Technical indicators (from sparkline hourly data) ────────────────────────

def _simple_rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    deltas   = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains    = [d for d in deltas[-period:] if d > 0]
    losses   = [-d for d in deltas[-period:] if d < 0]
    avg_gain = statistics.mean(gains)  if gains  else 0
    avg_loss = statistics.mean(losses) if losses else 1e-9
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _simple_ma(prices: list[float], period: int) -> float | None:
    if len(prices) < period:
        return None
    return round(statistics.mean(prices[-period:]), 8)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _short_term_score(coin: dict, prices: list[float]) -> tuple[int, dict]:
    score = 0
    metrics = {}
    current_price = coin.get("current_price", 0)

    # RSI (last 14 hourly closes → ~14h RSI as proxy for day-level)
    rsi = _simple_rsi(prices[-30:], period=14)
    metrics["rsi"] = rsi
    if rsi and 40 <= rsi <= 65:
        score += 25

    # 24h price change > 2%
    chg_24h = coin.get("price_change_percentage_24h_in_currency", 0) or 0
    metrics["price_change_24h_pct"] = round(chg_24h, 2)
    if chg_24h > 2:
        score += 20

    # Price above 48-hour MA (short-term uptrend; 48 hourly points ≈ 2 days)
    ma48 = _simple_ma(prices, 48)
    metrics["ma48"] = ma48
    if ma48 and current_price > ma48:
        score += 20

    # 7d change positive but < 30% (momentum without over-extension)
    chg_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
    metrics["price_change_7d_pct"] = round(chg_7d, 2)
    if 0 < chg_7d < 30:
        score += 20

    # 24h volume above $50M (sufficient liquidity)
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

    # Market cap > $10B
    metrics["market_cap_usd"] = market_cap
    if market_cap and market_cap > 10_000_000_000:
        score += 30

    # Price above 7-day MA (using full sparkline)
    ma_all = _simple_ma(prices, len(prices))
    metrics["ma7d"] = ma_all
    if ma_all and current_price > ma_all:
        score += 25

    # 30d price change positive
    chg_30d = coin.get("price_change_percentage_30d_in_currency", 0) or 0
    metrics["price_change_30d_pct"] = round(chg_30d, 2)
    if chg_30d > 0:
        score += 20

    # Within 60% of ATH
    metrics["ath_usd"] = ath
    if ath and current_price > 0:
        pct_from_ath = ((ath - current_price) / ath) * 100
        metrics["pct_below_ath"] = round(pct_from_ath, 1)
        if pct_from_ath < 60:
            score += 15

    # Room to grow (ATH > 30% above current)
    if ath and current_price > 0 and ath > current_price * 1.3:
        score += 10

    return score, metrics


# ── Main screener ─────────────────────────────────────────────────────────────

def run_crypto_screener() -> dict:
    """
    Screen top coins using a SINGLE CoinGecko API call (sparkline bundled).
    No per-coin requests, no rate limiting.
    """
    print(f"[crypto_screener] Fetching top {MAX_COINS} coins from CoinGecko (1 API call)...")
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
        and c.get("sparkline_in_7d", {}).get("price")   # must have price data
    ]
    print(f"[crypto_screener] Scoring {len(coins)} coins after exclusions...")

    short_results = []
    long_results  = []

    for coin in coins:
        prices = coin["sparkline_in_7d"]["price"]   # ~168 hourly prices
        symbol = coin.get("symbol", "").upper()
        name   = coin.get("name", coin["id"])
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
