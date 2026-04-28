"""
price_checker.py — Fetch current prices for the 10:30 AM confirmation run.
Uses yfinance for stocks and CoinGecko for crypto (single bulk call each).
"""

import requests
import yfinance as yf

COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price"


def get_current_prices(picks: dict) -> dict:
    """
    Given the morning picks dict, fetch current prices for all tickers/symbols.
    Returns { "AAPL": 185.20, "MSFT": 418.50, "BTC": 66200, ... }
    """
    prices = {}

    stocks = picks.get("stocks", picks)
    crypto = picks.get("crypto", {})

    # ── Stock prices via yfinance (one call per ticker, fast) ─────────────────
    stock_tickers = set()
    for section in ("short_term", "long_term"):
        for s in stocks.get(section, []):
            if s.get("ticker"):
                stock_tickers.add(s["ticker"])

    for ticker in stock_tickers:
        try:
            data = yf.Ticker(ticker).fast_info
            price = getattr(data, "last_price", None) or getattr(data, "regular_market_price", None)
            if price:
                prices[ticker] = round(float(price), 2)
        except Exception as exc:
            print(f"[price_checker] Could not fetch {ticker}: {exc}")

    # ── Crypto prices via CoinGecko simple/price (one bulk call) ─────────────
    # Map symbol → CoinGecko id from the picks
    symbol_to_id = {}
    for section in ("short_term", "long_term"):
        for c in crypto.get(section, []):
            sym = c.get("symbol", "").upper()
            cid = c.get("id", "")
            if sym and cid:
                symbol_to_id[sym] = cid

    if symbol_to_id:
        try:
            ids = ",".join(symbol_to_id.values())
            resp = requests.get(
                COINGECKO_SIMPLE,
                params={"ids": ids, "vs_currencies": "usd"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            for sym, cid in symbol_to_id.items():
                price = data.get(cid, {}).get("usd")
                if price:
                    prices[sym] = float(price)
        except Exception as exc:
            print(f"[price_checker] Could not fetch crypto prices: {exc}")

    print(f"[price_checker] Current prices: {prices}")
    return prices
