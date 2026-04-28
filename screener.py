"""
screener.py — S&P 500 stock screener using yfinance + ta + Finnhub fundamentals.

Covers up to 400 S&P 500 tickers via a single yf.download() bulk call.
Short-term and long-term candidates are selected independently:
  ST pool → top 30 by technical score   (momentum/breakout plays)
  LT pool → top 30 by dollar volume     (large caps, fundamental quality)

Fundamental scoring uses Finnhub basic metrics (/stock/metric) when the
API key is available — more reliable than yfinance.info which has ~30% null
rates on P/E, revenue growth, and free cash flow. Falls back to yfinance
gracefully if the key is absent or a call fails.
"""

import os
import time
import warnings
import requests
import pandas as pd
import yfinance as yf
import ta

from earnings_checker import get_upcoming_earnings

FINNHUB_BASE = "https://finnhub.io/api/v1"

warnings.filterwarnings("ignore")

# Sector median P/E ratios (approximate)
SECTOR_MEDIAN_PE = {
    "Technology": 28,
    "Health Care": 22,
    "Financials": 14,
    "Consumer Discretionary": 24,
    "Communication Services": 20,
    "Industrials": 20,
    "Consumer Staples": 22,
    "Energy": 12,
    "Utilities": 18,
    "Real Estate": 35,
    "Materials": 17,
    "Unknown": 20,
}

MAX_TICKERS    = 400   # Covered via bulk download — ~80% of index by weight
ST_CANDIDATE_N = 30    # Top N by technical score  → short-term pool
LT_CANDIDATE_N = 30    # Top N by dollar volume    → long-term pool (independent)
SLEEP_INFO     = 0.1   # Delay between individual .info calls


# ── S&P 500 ticker list ───────────────────────────────────────────────────────

# Fallback list (used if Wikipedia is unreachable)
FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "UNH", "LLY", "JPM", "V", "XOM", "MA", "AVGO", "PG", "HD", "CVX",
    "MRK", "ABBV", "COST", "PEP", "KO", "WMT", "BAC", "CRM", "ACN",
    "MCD", "TMO", "CSCO", "ABT", "ADBE", "DIS", "NKE", "TXN", "NEE",
    "WFC", "PM", "RTX", "UPS", "INTU", "AMGN", "MS", "SPGI", "GS",
    "LOW", "HON", "ISRG", "CAT", "ELV", "BKNG", "PLD", "AMD", "NOW",
    "MDLZ", "TGT", "MMC", "ZTS", "CB", "SHW", "CI", "MO", "DUK",
    "SO", "BMY", "GILD", "EOG", "SLB", "BDX", "ITW", "NOC", "APD",
    "AON", "CME", "ICE", "ECL", "REGN", "HUM", "F", "GM", "UBER",
]


def get_sp500_tickers() -> list[str]:
    """Pull S&P 500 tickers from Wikipedia. Returns up to MAX_TICKERS."""
    try:
        tables  = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df      = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"[screener] Fetched {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers[:MAX_TICKERS]
    except Exception as exc:
        print(f"[screener] WARNING: Could not fetch S&P 500 list ({exc}). Using fallback list.")
        return FALLBACK_TICKERS[:MAX_TICKERS]


# ── Technical indicators (short-term scoring) ─────────────────────────────────

def _short_term_score(hist: pd.DataFrame) -> tuple[int, dict]:
    """Score a ticker for short-term trading (out of 100). Returns (score, metrics)."""
    score   = 0
    metrics = {}

    try:
        close  = hist["Close"].squeeze()
        volume = hist["Volume"].squeeze()

        # RSI (14-day) — sweet spot 35-55: momentum building, not overbought
        rsi_val = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        rsi     = round(float(rsi_val), 2) if not pd.isna(rsi_val) else None
        metrics["rsi"] = rsi
        if rsi and 35 <= rsi <= 55:
            score += 25

        # MACD crossover in last 3 days
        macd_ind  = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
        macd_line = macd_ind.macd()
        macd_sig  = macd_ind.macd_signal()
        crossed   = False
        for i in range(-3, 0):
            if (not pd.isna(macd_line.iloc[i]) and not pd.isna(macd_sig.iloc[i]) and
                    macd_line.iloc[i] > macd_sig.iloc[i] and
                    macd_line.iloc[i - 1] <= macd_sig.iloc[i - 1]):
                crossed = True
                break
        metrics["macd_crossover"] = crossed
        if crossed:
            score += 25

        # Volume surge (today vs 20-day avg)
        vol_ratio = float(volume.iloc[-1] / volume.iloc[-21:-1].mean()) if len(volume) >= 21 else None
        metrics["volume_ratio"] = round(vol_ratio, 2) if vol_ratio else None
        if vol_ratio and vol_ratio > 1.5:
            score += 20

        # Price above 20-day EMA (uptrend confirmation)
        ema20_val     = ta.trend.EMAIndicator(close, window=20).ema_indicator().iloc[-1]
        current_price = float(close.iloc[-1])
        week_high     = float(close.rolling(252).max().iloc[-1])
        if not pd.isna(ema20_val):
            ema_val        = float(ema20_val)
            metrics["ema20"] = round(ema_val, 2)
            if ema_val <= current_price <= week_high:
                score += 15

        # Near Bollinger lower band (potential bounce)
        bb         = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        lower_band = float(bb.bollinger_lband().iloc[-1])
        metrics["bb_lower"] = round(lower_band, 2)
        if not pd.isna(lower_band) and current_price <= lower_band * 1.05:
            score += 15

    except Exception as exc:
        print(f"[screener] Short-term indicator error: {exc}")

    return score, metrics


# ── Finnhub fundamental metrics ───────────────────────────────────────────────

def _get_finnhub_metrics(ticker: str) -> dict:
    """
    Fetch basic financial metrics from Finnhub /stock/metric.
    Returns the 'metric' dict, or {} if key is missing / call fails.

    Key fields used:
      peBasicExclExtraTTM        — trailing P/E
      revenueGrowthTTMYoy        — revenue growth YoY (decimal, e.g. 0.17)
      netMarginTTM               — net profit margin (decimal)
      totalDebt/totalEquityAnnual — D/E ratio (ratio, e.g. 1.2 = 120%)
      marketCapitalization       — market cap in $ millions
    """
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {}
    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get("metric", {})
    except Exception as exc:
        print(f"[screener] Finnhub metrics error for {ticker}: {exc}")
        return {}


# ── Fundamental scoring (long-term) ──────────────────────────────────────────

def _long_term_score(info: dict, fh: dict) -> tuple[int, dict]:
    """
    Score a ticker for long-term investing (out of 100).
    Prioritises Finnhub metrics (fh) — more reliable than yfinance info.
    Falls back to yfinance info fields when Finnhub returns None.
    """
    score   = 0
    metrics = {}

    sector    = info.get("sector", "Unknown")
    median_pe = SECTOR_MEDIAN_PE.get(sector, SECTOR_MEDIAN_PE["Unknown"])

    # ── P/E vs sector median (30 pts) ────────────────────────────────────────
    pe = fh.get("peBasicExclExtraTTM") or info.get("trailingPE")
    metrics["pe_ratio"] = round(pe, 1) if pe else None
    if pe and 0 < pe < median_pe:
        score += 30

    # ── Revenue growth > 10% YoY (25 pts) ────────────────────────────────────
    rev_growth = fh.get("revenueGrowthTTMYoy") or info.get("revenueGrowth")
    metrics["revenue_growth"] = rev_growth
    if rev_growth and rev_growth > 0.10:
        score += 25

    # ── Net margin > 10% — replaces FCF (more reliably available) (20 pts) ───
    net_margin = fh.get("netMarginTTM") or info.get("profitMargins")
    metrics["net_margin"] = round(net_margin, 3) if net_margin else None
    if net_margin and net_margin > 0.10:
        score += 20

    # ── Debt-to-equity < 1.0 (15 pts) ────────────────────────────────────────
    # Finnhub: ratio (1.2 = 120%)  |  yfinance: percentage (120 = 1.2x)
    dte_fh = fh.get("totalDebt/totalEquityAnnual")
    dte_yf = info.get("debtToEquity")
    if dte_fh is not None:
        dte = dte_fh          # already a ratio
        dte_ok = dte_fh < 1.0
    elif dte_yf is not None:
        dte = round(dte_yf / 100, 2)
        dte_ok = dte_yf < 100
    else:
        dte, dte_ok = None, False
    metrics["debt_to_equity"] = dte
    if dte_ok:
        score += 15

    # ── Market cap > $10B (10 pts) ────────────────────────────────────────────
    # Finnhub returns in $ millions; yfinance returns full dollars
    fh_mcap = fh.get("marketCapitalization")
    mktcap  = (fh_mcap * 1_000_000) if fh_mcap else info.get("marketCap", 0)
    metrics["market_cap"] = int(mktcap) if mktcap else None
    if mktcap and mktcap > 10_000_000_000:
        score += 10

    return score, metrics


# ── Main screener ─────────────────────────────────────────────────────────────

def run_screener() -> dict:
    """
    Screen S&P 500 stocks and return top candidates.

    Short-term and long-term candidates are chosen independently:
      ST pool: top 30 by technical score     (momentum/breakout plays)
      LT pool: top 30 by avg dollar volume   (large, liquid, fundamentally screened)

    Steps:
      1. Bulk-download 3 months of price history for 400 tickers (1 API call).
      2. Score all for short-term technicals + compute dollar volume.
      3. Fetch earnings calendar (1 Finnhub call).
      4. Fetch yfinance .info (name/sector) + Finnhub metrics (financials) for
         the union of ST pool + LT pool (~40-50 unique tickers).
      5. Score those for long-term fundamentals using Finnhub data.
      6. Return top 5 short-term (by ST score) + top 5 long-term (by LT score).
    """
    tickers = get_sp500_tickers()

    # ── Step 1: Bulk price history download ──────────────────────────────────
    print(f"[screener] Bulk downloading {len(tickers)} tickers (one API call)...")
    try:
        raw = yf.download(
            tickers,
            period="3mo",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        print(f"[screener] Bulk download failed: {exc}")
        return {"short_term": [], "long_term": []}

    if hasattr(raw.columns, "levels"):
        available = set(raw.columns.get_level_values(0))
    else:
        available = set(tickers[:1])

    # ── Step 2: Score all tickers + compute dollar volume ─────────────────────
    all_scored: list[dict] = []
    for ticker in tickers:
        try:
            if ticker not in available:
                continue
            hist = raw[ticker].dropna(how="all")
            if len(hist) < 30:
                continue
            current_price = float(hist["Close"].iloc[-1])
            if pd.isna(current_price):
                continue

            st_score, st_metrics = _short_term_score(hist)

            # Dollar volume = avg(close × volume) over last 30 days
            # High dollar volume ≈ large, liquid, established company
            avg_dollar_vol = float((hist["Close"] * hist["Volume"]).tail(30).mean())

            all_scored.append({
                "ticker":          ticker,
                "current_price":   round(current_price, 2),
                "score":           st_score,
                "avg_dollar_vol":  avg_dollar_vol,
                **st_metrics,
            })
        except Exception:
            continue

    print(f"[screener] Scored {len(all_scored)} tickers.")

    # ── Step 3: Build independent ST and LT candidate pools ──────────────────
    # ST pool: highest technical scores (momentum/breakout plays)
    st_pool = sorted(all_scored, key=lambda x: x["score"], reverse=True)[:ST_CANDIDATE_N]

    # LT pool: highest dollar volume (large caps worth holding long term)
    lt_pool = sorted(all_scored, key=lambda x: x["avg_dollar_vol"], reverse=True)[:LT_CANDIDATE_N]

    # ── Step 4: Earnings calendar ─────────────────────────────────────────────
    all_pool_tickers = list({s["ticker"] for s in st_pool + lt_pool})
    upcoming_earnings = get_upcoming_earnings(all_pool_tickers, days_ahead=5)

    # ── Step 5: Fetch .info for union of both pools (deduplicated) ────────────
    seen_tickers: set[str] = set()
    enriched: dict[str, dict] = {}   # ticker → enriched entry

    all_candidates = st_pool + [c for c in lt_pool if c["ticker"] not in {s["ticker"] for s in st_pool}]
    print(f"[screener] Fetching fundamentals for {len(all_candidates)} unique candidates...")

    for candidate in all_candidates:
        ticker = candidate["ticker"]
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        try:
            info    = yf.Ticker(ticker).info or {}
            company = info.get("longName", ticker)
            sector  = info.get("sector", "Unknown")
        except Exception as exc:
            print(f"[screener] yfinance info failed for {ticker}: {exc}")
            info, company, sector = {}, ticker, "Unknown"

        try:
            fh_metrics = _get_finnhub_metrics(ticker)
        except Exception:
            fh_metrics = {}

        try:
            lt_score, lt_metrics = _long_term_score(info, fh_metrics)
        except Exception as exc:
            print(f"[screener] LT score failed for {ticker}: {exc}")
            lt_score, lt_metrics = 0, {}

        entry = {
            "ticker":        ticker,
            "company":       company,
            "sector":        sector,
            "current_price": candidate["current_price"],
            "st_score":      candidate["score"],
            "lt_score":      lt_score,
            "st_metrics":    {k: v for k, v in candidate.items()
                              if k not in ("ticker", "current_price", "score", "avg_dollar_vol")},
            "lt_metrics":    lt_metrics,
        }
        if ticker in upcoming_earnings:
            entry["earnings_date"] = upcoming_earnings[ticker]

        enriched[ticker] = entry
        time.sleep(SLEEP_INFO)

    # ── Step 6: Build final top-5 lists ───────────────────────────────────────
    def _opt_earnings(e: dict) -> dict:
        return {"earnings_date": e["earnings_date"]} if "earnings_date" in e else {}

    def _flatten_short(e: dict) -> dict:
        return {"ticker": e["ticker"], "company": e["company"], "sector": e["sector"],
                "current_price": e["current_price"], "score": e["st_score"],
                **e["st_metrics"], **_opt_earnings(e)}

    def _flatten_long(e: dict) -> dict:
        return {"ticker": e["ticker"], "company": e["company"], "sector": e["sector"],
                "current_price": e["current_price"], "score": e["lt_score"],
                **e["lt_metrics"], **_opt_earnings(e)}

    # ST top-5: from the ST pool only (ranked by technical score)
    short_top5 = [_flatten_short(enriched[s["ticker"]]) for s in st_pool
                  if s["ticker"] in enriched]
    short_top5 = sorted(short_top5, key=lambda x: x["score"], reverse=True)[:5]

    # LT top-5: from the LT pool only (ranked by fundamental score)
    long_top5 = [_flatten_long(enriched[s["ticker"]]) for s in lt_pool
                 if s["ticker"] in enriched]
    long_top5 = sorted(long_top5, key=lambda x: x["score"], reverse=True)[:5]

    print(f"[screener] Top short-term: {[s['ticker'] for s in short_top5]}")
    print(f"[screener] Top long-term:  {[s['ticker'] for s in long_top5]}")

    return {"short_term": short_top5, "long_term": long_top5}


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    results = run_screener()
    print(json.dumps(results, indent=2, default=str))
