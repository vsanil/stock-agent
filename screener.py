"""
screener.py — S&P 500 stock screener using yfinance + pandas-ta.
Returns top 5 short-term and top 5 long-term candidates.
"""

import time
import warnings
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Sector median P/E ratios (approximate, used for long-term value scoring)
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

MAX_TICKERS = 50          # Keeps run under ~4 min on GitHub Actions
SLEEP_BETWEEN_CALLS = 0.1


# ── S&P 500 tickers ───────────────────────────────────────────────────────────

def get_sp500_tickers() -> list[str]:
    """Pull S&P 500 tickers from Wikipedia."""
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        return tickers[:MAX_TICKERS]
    except Exception as exc:
        print(f"[screener] WARNING: Could not fetch S&P 500 list ({exc}). Using fallback tickers.")
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
            "UNH", "LLY", "JPM", "V", "XOM", "MA", "AVGO", "PG", "HD", "CVX",
            "MRK", "ABBV", "COST", "PEP", "KO", "WMT", "BAC", "CRM", "ACN",
            "MCD", "TMO", "CSCO", "ABT", "ADBE", "DIS", "NKE", "TXN", "NEE",
            "WFC", "PM", "RTX", "UPS", "INTU", "AMGN", "MS", "SPGI", "GS",
            "LOW", "HON", "ISRG", "CAT", "ELV",
        ][:MAX_TICKERS]


# ── Technical indicators (short-term scoring) ─────────────────────────────────

def _short_term_score(hist: pd.DataFrame) -> tuple[int, dict]:
    """Score a ticker for short-term trading (out of 100). Returns (score, metrics)."""
    score = 0
    metrics = {}

    try:
        import pandas_ta as ta

        close = hist["Close"].squeeze()
        volume = hist["Volume"].squeeze()

        # RSI (14-day)
        rsi_series = ta.rsi(close, length=14)
        rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else None
        metrics["rsi"] = round(rsi, 2) if rsi else None
        if rsi and 35 <= rsi <= 55:
            score += 25

        # MACD
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_col = [c for c in macd_df.columns if c.startswith("MACD_")][0]
            sig_col  = [c for c in macd_df.columns if c.startswith("MACDs_")][0]
            macd_vals = macd_df[macd_col]
            sig_vals  = macd_df[sig_col]
            # Crossed above in last 3 days?
            crossed = False
            for i in range(-3, 0):
                if (macd_vals.iloc[i] > sig_vals.iloc[i] and
                        macd_vals.iloc[i - 1] <= sig_vals.iloc[i - 1]):
                    crossed = True
                    break
            metrics["macd_crossover"] = crossed
            if crossed:
                score += 25

        # Volume ratio (today vs 20-day avg)
        vol_ratio = float(volume.iloc[-1] / volume.iloc[-21:-1].mean()) if len(volume) >= 21 else None
        metrics["volume_ratio"] = round(vol_ratio, 2) if vol_ratio else None
        if vol_ratio and vol_ratio > 1.5:
            score += 20

        # 20-day EMA
        ema20 = ta.ema(close, length=20)
        current_price = float(close.iloc[-1])
        week_high = float(close.rolling(252).max().iloc[-1])
        if ema20 is not None and not ema20.empty:
            ema_val = float(ema20.iloc[-1])
            metrics["ema20"] = round(ema_val, 2)
            if ema_val <= current_price <= week_high:
                score += 15

        # Bollinger Band position
        bb = ta.bbands(close, length=20, std=2)
        if bb is not None and not bb.empty:
            lower_col = [c for c in bb.columns if "BBL" in c][0]
            lower_band = float(bb[lower_col].iloc[-1])
            metrics["bb_lower"] = round(lower_band, 2)
            if current_price <= lower_band * 1.05:
                score += 15

    except Exception as exc:
        print(f"[screener] Short-term indicator error: {exc}")

    return score, metrics


# ── Fundamental scoring (long-term) ──────────────────────────────────────────

def _long_term_score(info: dict) -> tuple[int, dict]:
    """Score a ticker for long-term investing (out of 100). Returns (score, metrics)."""
    score = 0
    metrics = {}

    sector = info.get("sector", "Unknown")
    median_pe = SECTOR_MEDIAN_PE.get(sector, SECTOR_MEDIAN_PE["Unknown"])

    # P/E vs sector median
    pe = info.get("trailingPE")
    metrics["pe_ratio"] = pe
    if pe and pe < median_pe:
        score += 30

    # Revenue growth > 10% YoY
    rev_growth = info.get("revenueGrowth")
    metrics["revenue_growth"] = rev_growth
    if rev_growth and rev_growth > 0.10:
        score += 25

    # Free cash flow positive
    fcf = info.get("freeCashflow")
    metrics["free_cashflow"] = fcf
    if fcf and fcf > 0:
        score += 20

    # Debt-to-equity < 1.0
    dte = info.get("debtToEquity")
    metrics["debt_to_equity"] = dte
    if dte and dte < 100:  # yfinance returns as percentage (100 = 1.0)
        score += 15

    # Market cap > $10B
    mktcap = info.get("marketCap", 0)
    metrics["market_cap"] = mktcap
    if mktcap and mktcap > 10_000_000_000:
        score += 10

    return score, metrics


# ── Main screener ─────────────────────────────────────────────────────────────

def run_screener() -> dict:
    """
    Screen S&P 500 stocks and return top candidates.
    Returns:
        {
            "short_term": [ {ticker, company, sector, price, score, ...metrics}, ... ],
            "long_term":  [ {ticker, company, sector, price, score, ...metrics}, ... ],
        }
    """
    tickers = get_sp500_tickers()
    print(f"[screener] Screening {len(tickers)} tickers...")

    short_results = []
    long_results  = []

    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            hist  = stock.history(period="6mo")

            if hist.empty or len(hist) < 30:
                continue

            info = stock.info or {}
            current_price = float(hist["Close"].iloc[-1])
            company = info.get("longName", ticker)
            sector  = info.get("sector", "Unknown")

            # Short-term score
            st_score, st_metrics = _short_term_score(hist)
            short_results.append({
                "ticker": ticker,
                "company": company,
                "sector": sector,
                "current_price": round(current_price, 2),
                "score": st_score,
                **st_metrics,
            })

            # Long-term score
            lt_score, lt_metrics = _long_term_score(info)
            long_results.append({
                "ticker": ticker,
                "company": company,
                "sector": sector,
                "current_price": round(current_price, 2),
                "score": lt_score,
                **lt_metrics,
            })

            if (i + 1) % 10 == 0:
                print(f"[screener] Processed {i + 1}/{len(tickers)} tickers...")

            time.sleep(SLEEP_BETWEEN_CALLS)

        except Exception as exc:
            print(f"[screener] Skipping {ticker}: {exc}")
            # Rate-limit handling
            if "429" in str(exc) or "Too Many Requests" in str(exc):
                print("[screener] Rate limited — sleeping 30s...")
                time.sleep(30)
            continue

    # Sort and take top 5
    short_top5 = sorted(short_results, key=lambda x: x["score"], reverse=True)[:5]
    long_top5  = sorted(long_results,  key=lambda x: x["score"], reverse=True)[:5]

    print(f"[screener] Top short-term: {[s['ticker'] for s in short_top5]}")
    print(f"[screener] Top long-term:  {[s['ticker'] for s in long_top5]}")

    return {"short_term": short_top5, "long_term": long_top5}


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    results = run_screener()
    print(json.dumps(results, indent=2, default=str))
