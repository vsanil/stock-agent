"""
crypto_screener.py — Crypto screener using CoinGecko free API (no key needed).
Returns top short-term and long-term crypto candidates.
"""

import time
import statistics
import requests

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
SLEEP_BETWEEN_CALLS = 1.5   # CoinGecko free tier: ~10-30 req/min
MAX_COINS = 100              # Top 100 by market cap
TOP_N = 5                    # Candidates to return per category

# Stablecoins and wrapped tokens to exclude from picks
EXCLUDE_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "frax", "true-usd",
    "usdd", "gemini-dollar", "paxos-standard", "wrapped-bitcoin",
    "wrapped-ethereum", "staked-ether", "rocket-pool-eth",
    "coinbase-wrapped-staked-eth", "mantle-staked-ether",
}


# ── CoinGecko helpers ─────────────────────────────────────────────────────────

def _get_top_coins(limit: int = MAX_COINS) -> list[dict]:
    """Fetch top coins by market cap from CoinGecko /coins/markets."""
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h,7d,30d",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _get_market_chart(coin_id: str, days: int = 30) -> dict:
    """Fetch historical OHLC-style price data for RSI/MA calculation."""
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Technical indicators ──────────────────────────────────────────────────────

def _simple_rsi(prices: list[float], period: int = 14) -> float | None:
    """Compute RSI from a list of daily closing prices."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains  = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]
    avg_gain = statistics.mean(gains) if gains else 0
    avg_loss = statistics.mean(losses) if losses else 1e-9
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _simple_ma(prices: list[float], period: int) -> float | None:
    """Simple moving average over last `period` prices."""
    if len(prices) < period:
        return None
    return round(statistics.mean(prices[-period:]), 6)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _short_term_score(coin: dict, chart: dict) -> tuple[int, dict]:
    """Score a coin for short-term trading (out of 100)."""
    score = 0
    metrics = {}

    prices = [p[1] for p in chart.get("prices", [])]
    volumes = [v[1] for v in chart.get("total_volumes", [])]
    current_price = coin.get("current_price", 0)

    # RSI 14-day between 40–65 (momentum sweet spot, not overbought)
    rsi = _simple_rsi(prices)
    metrics["rsi"] = rsi
    if rsi and 40 <= rsi <= 65:
        score += 25

    # 24h price change > 2% (near-term momentum)
    chg_24h = coin.get("price_change_percentage_24h_in_currency", 0) or 0
    metrics["price_change_24h_pct"] = round(chg_24h, 2)
    if chg_24h > 2:
        score += 20

    # Volume spike: today vs 7-day avg
    if len(volumes) >= 8:
        avg_vol = statistics.mean(volumes[-8:-1])
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 0
        metrics["volume_ratio"] = round(vol_ratio, 2)
        if vol_ratio > 1.5:
            score += 20
    else:
        metrics["volume_ratio"] = None

    # Price above 7-day MA (short-term uptrend)
    ma7 = _simple_ma(prices, 7)
    metrics["ma7"] = ma7
    if ma7 and current_price > ma7:
        score += 20

    # 7d change positive but < 25% (not already over-extended)
    chg_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
    metrics["price_change_7d_pct"] = round(chg_7d, 2)
    if 0 < chg_7d < 25:
        score += 15

    return score, metrics


def _long_term_score(coin: dict, chart: dict) -> tuple[int, dict]:
    """Score a coin for long-term holding (out of 100)."""
    score = 0
    metrics = {}

    prices = [p[1] for p in chart.get("prices", [])]
    current_price = coin.get("current_price", 0)
    market_cap = coin.get("market_cap", 0)
    ath = coin.get("ath", 0)

    # Market cap > $10B (established, liquid)
    metrics["market_cap_usd"] = market_cap
    if market_cap and market_cap > 10_000_000_000:
        score += 30

    # Price above 30-day MA (sustained uptrend)
    ma30 = _simple_ma(prices, 30)
    metrics["ma30"] = ma30
    if ma30 and current_price > ma30:
        score += 25

    # 30-day price change positive (momentum)
    chg_30d = coin.get("price_change_percentage_30d_in_currency", 0) or 0
    metrics["price_change_30d_pct"] = round(chg_30d, 2)
    if chg_30d > 0:
        score += 20

    # Price within 60% of ATH (not a zombie coin, not in peak mania)
    metrics["ath_usd"] = ath
    if ath and current_price > 0:
        pct_from_ath = ((ath - current_price) / ath) * 100
        metrics["pct_below_ath"] = round(pct_from_ath, 1)
        if pct_from_ath < 60:
            score += 15

    # ATH > 30% above current price (room to grow)
    if ath and current_price > 0 and ath > current_price * 1.3:
        score += 10

    return score, metrics


# ── Main screener ─────────────────────────────────────────────────────────────

def run_crypto_screener() -> dict:
    """
    Screen top 100 crypto coins and return top candidates.
    Returns:
        {
            "short_term": [ {id, symbol, name, price, score, ...metrics}, ... ],
            "long_term":  [ {id, symbol, name, price, score, ...metrics}, ... ],
        }
    """
    print(f"[crypto_screener] Fetching top {MAX_COINS} coins from CoinGecko...")
    try:
        coins = _get_top_coins(MAX_COINS)
    except Exception as exc:
        print(f"[crypto_screener] ERROR fetching coin list: {exc}")
        return {"short_term": [], "long_term": []}

    # Filter out stablecoins/wrapped tokens
    coins = [c for c in coins if c.get("id") not in EXCLUDE_IDS]
    print(f"[crypto_screener] Screening {len(coins)} coins after exclusions...")

    short_results = []
    long_results  = []

    for i, coin in enumerate(coins):
        coin_id = coin["id"]
        try:
            chart = _get_market_chart(coin_id, days=30)
            time.sleep(SLEEP_BETWEEN_CALLS)

            current_price = coin.get("current_price", 0)
            symbol = coin.get("symbol", "").upper()
            name   = coin.get("name", coin_id)

            st_score, st_metrics = _short_term_score(coin, chart)
            short_results.append({
                "id": coin_id,
                "symbol": symbol,
                "name": name,
                "current_price": current_price,
                "market_cap": coin.get("market_cap"),
                "score": st_score,
                **st_metrics,
            })

            lt_score, lt_metrics = _long_term_score(coin, chart)
            long_results.append({
                "id": coin_id,
                "symbol": symbol,
                "name": name,
                "current_price": current_price,
                "market_cap": coin.get("market_cap"),
                "score": lt_score,
                **lt_metrics,
            })

            if (i + 1) % 10 == 0:
                print(f"[crypto_screener] Processed {i + 1}/{len(coins)} coins...")

        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                print("[crypto_screener] Rate limited — sleeping 60s...")
                time.sleep(60)
            else:
                print(f"[crypto_screener] Skipping {coin_id}: {exc}")
            continue
        except Exception as exc:
            print(f"[crypto_screener] Skipping {coin_id}: {exc}")
            continue

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
