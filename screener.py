"""
screener.py — Broad US stock screener using yfinance + ta + Finnhub fundamentals.

Covers up to 600 tickers across S&P 500 + NASDAQ 100 + S&P MidCap 400 via a
single yf.download() bulk call — deduped and capped at MAX_TICKERS.
Short-term and long-term candidates are selected independently:
  ST pool → top 30 by technical score   (momentum/breakout plays)
  LT pool → top 30 by dollar volume     (large caps + quality mid-caps)

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
from market_regime import get_market_regime, regime_pick_multiplier

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

MAX_TICKERS    = 600   # S&P 500 + NASDAQ 100 + MidCap 400, deduped, capped here
ST_CANDIDATE_N = 30    # Top N by technical score  → short-term pool
LT_CANDIDATE_N = 30    # Top N by dollar volume    → long-term pool (independent)
SLEEP_INFO     = 0.1   # Delay between individual .info calls


# ── Broad US stock universe ───────────────────────────────────────────────────
# Fallback list: S&P 500 core + NASDAQ 100 extras + S&P MidCap 400 highlights
# Used when live sources are unreachable. Covers large + quality mid-caps.

FALLBACK_TICKERS = [
    # ── S&P 500 / Large-cap core ─────────────────────────────────────────────
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B", "AVGO",
    "LLY", "JPM", "V", "UNH", "XOM", "MA", "PG", "JNJ", "COST", "HD",
    "MRK", "ABBV", "CVX", "CRM", "BAC", "NFLX", "AMD", "KO", "WMT", "PEP",
    "TMO", "ACN", "MCD", "CSCO", "ABT", "ADBE", "TXN", "DIS", "WFC", "NEE",
    "PM", "RTX", "UPS", "INTU", "AMGN", "MS", "SPGI", "GS", "LOW", "HON",
    "ISRG", "CAT", "ELV", "BKNG", "PLD", "NOW", "MDLZ", "TGT", "ZTS", "CB",
    "SHW", "CI", "MO", "DUK", "SO", "BMY", "GILD", "EOG", "SLB", "BDX",
    "ITW", "NOC", "APD", "AON", "CME", "ICE", "ECL", "REGN", "HUM", "F",
    "GM", "UBER", "MMC", "PNC", "USB", "AXP", "BLK", "SCHW", "TJX", "DE",
    "ETN", "EMR", "ADI", "KLAC", "LRCX", "MCHP", "AMAT", "SNPS", "CDNS", "FTNT",
    "ADP", "PAYX", "CTAS", "ROP", "IDXX", "FAST", "ODFL", "CPRT", "VRSK", "ANSS",
    "IQV", "CRL", "MTD", "A", "ILMN", "WAT", "BIIB", "VRTX", "MRNA", "DXCM",
    "CVS", "CNC", "MCK", "CAH", "HCA", "BAX", "BSX", "EW", "PODD", "PHM",
    "DHI", "LEN", "NVR", "TOL", "AMT", "CCI", "SBAC", "EQIX", "DLR", "PSA",
    "EXR", "AVB", "EQR", "ESS", "VTR", "WELL", "CFG", "KEY", "FITB", "MTB",
    "HBAN", "RF", "AEP", "EXC", "SRE", "PEG", "FE", "PPL", "CMS", "WEC",
    "XOM", "CVX", "COP", "EOG", "DVN", "MRO", "HES", "OXY", "VLO", "MPC",
    "PSX", "LIN", "PPG", "RPM", "VMC", "MLM", "CAT", "DE", "AGCO", "UAL",
    "DAL", "AAL", "LUV", "ALK", "UNP", "CSX", "NSC", "CP", "CNI", "FDX",
    "CHRW", "EXPD", "JBHT", "ODFL", "SAIA", "AZO", "ORLY", "GPC", "TSCO", "FIVE",
    "LMT", "GD", "BA", "NOC", "HII", "TDG", "LDOS", "SAIC", "DRS", "KTOS",
    "PFE", "NVO", "AZN", "SNY", "RHHBY", "HLN", "GSK", "TAK", "NVS", "BAYRY",
    "JPM", "BAC", "C", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "COF",
    "DFS", "SYF", "ALLY", "OMF", "WU", "FIS", "FI", "PYPL", "SQ", "AFRM",
    # ── NASDAQ 100 extras (not already above) ────────────────────────────────
    "QCOM", "INTC", "MU", "SMCI", "ON", "MRVL", "ARM", "CRWD", "PANW", "ZS",
    "OKTA", "NET", "DDOG", "MDB", "SNOW", "PLTR", "RBLX", "U", "HOOD", "COIN",
    "SHOP", "MELI", "SE", "GRAB", "BABA", "JD", "PDD", "BIDU", "TCEHY", "NTES",
    "ASML", "TSM", "SMSN", "SONY", "SAP", "ORCL", "IBM", "HPQ", "HPE", "DELL",
    "LOGI", "STX", "WDC", "NTAP", "PSTG", "ANET", "JNPR", "F5", "FFIV", "ZBRA",
    "TEAM", "HUBS", "ZM", "DOCU", "WIX", "BILL", "SMAR", "COUP", "APPF", "PCTY",
    "ABNB", "LYFT", "DASH", "RDFN", "OPEN", "CVNA", "CARVANA", "KMX", "AN", "PAG",
    "NDAQ", "CBOE", "MKTX", "VRTS", "LPLA", "RJF", "SF", "IBKR", "GCPAX", "BCRED",
    "SGEN", "BMRN", "ALNY", "IONS", "INCY", "NBIX", "EXAS", "NTRA", "PACB", "TWST",
    "CRSP", "NTLA", "BEAM", "EDIT", "FATE", "KYMR", "ARVN", "PRAX", "DNLI", "AKRO",
    # ── S&P MidCap 400 highlights ─────────────────────────────────────────────
    "DECK", "LULU", "PTON", "NKE", "UA", "SKX", "CROX", "HBI", "PVH", "RL",
    "TPR", "CPRI", "TIF", "SIG", "CAKE", "TXRH", "BJRI", "JACK", "WEN", "QSR",
    "YUM", "CMG", "SBUX", "DPZ", "PZZA", "FAT", "PLAY", "EAT", "DRI", "CBRL",
    "CHUY", "DENN", "FWRG", "KRUS", "NATH", "FRSH", "XPOF", "PLNT", "BODY", "FIT",
    "HIBB", "BOOT", "SHOO", "CATO", "AEO", "ANF", "URBN", "GPS", "BURL", "ROST",
    "TGT", "DLTR", "DG", "WMT", "COST", "BJ", "PRGO", "SFM", "CASY", "MUSA",
    "RH", "WSM", "BBBY", "PIR", "ARHAUS", "HVFD", "LOVE", "SNBR", "PRPL", "CSPR",
    "BLMN", "ELF", "ULTA", "COTY", "REVLONQ", "SPB", "CHD", "CLX", "ENR", "HPC",
    "MLI", "GFF", "APOG", "TREX", "AZEK", "AAON", "IBP", "BLDR", "BECN", "GMS",
    "STLD", "NUE", "RS", "CMC", "ZEUS", "KALU", "CENX", "CRS", "ATI", "HWM",
    "TKR", "GTLS", "FLOW", "GHM", "CECO", "FELE", "NNBR", "NN", "KRNT", "POWI",
    "FORM", "MKSI", "ONTO", "ICHR", "ACLS", "CCMP", "ENTG", "UCTT", "KLIC", "COHU",
    "EPC", "GEF", "SLGN", "BERY", "PTVE", "SILGAN", "SEE", "SON", "IP", "PKG",
    "CRUS", "SLAB", "DIOD", "LSCC", "ALGM", "MTSI", "MACOM", "LITE", "IIVI", "ACIA",
    "SMTC", "SWKS", "QRVO", "CIEN", "VIAV", "CALX", "INFN", "ADTRAN", "DCOM", "SHEN",
]


def get_stock_universe() -> list[str]:
    """
    Build a broad US stock universe: S&P 500 + NASDAQ 100 + S&P MidCap 400.
    Fetches live from multiple sources, deduplicates, caps at MAX_TICKERS.
    Falls back to the built-in FALLBACK_TICKERS list on any failure.
    """
    seen:    set[str]  = set()
    tickers: list[str] = []

    def _add(new_tickers: list[str]) -> None:
        for t in new_tickers:
            t = t.strip().replace(".", "-")
            if t and t not in seen:
                seen.add(t)
                tickers.append(t)

    # ── Source 1: S&P 500 via datahub.io ─────────────────────────────────────
    try:
        resp = requests.get(
            "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv",
            timeout=10,
        )
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()
        sp500 = [l.split(",")[0].strip() for l in lines[1:] if l.strip()]
        sp500 = [t for t in sp500 if t and not t.startswith('"')]
        if len(sp500) > 100:
            _add(sp500)
            print(f"[screener] S&P 500: {len(sp500)} tickers from datahub.io.")
    except Exception as exc:
        print(f"[screener] S&P 500 datahub.io failed ({exc}).")

    # ── Source 2: S&P 500 via Wikipedia (fallback) ────────────────────────────
    if len(tickers) < 100:
        try:
            df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
            _add(df["Symbol"].tolist())
            print(f"[screener] S&P 500: loaded from Wikipedia.")
        except Exception as exc:
            print(f"[screener] S&P 500 Wikipedia failed ({exc}).")

    # ── Source 3: NASDAQ 100 via Wikipedia ────────────────────────────────────
    try:
        df = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        col = next((c for c in df.columns if "ticker" in c.lower() or "symbol" in c.lower()), None)
        if col:
            before = len(tickers)
            _add(df[col].tolist())
            print(f"[screener] NASDAQ 100: added {len(tickers)-before} new tickers.")
    except Exception as exc:
        print(f"[screener] NASDAQ 100 Wikipedia failed ({exc}) — skipping.")

    # ── Source 4: S&P MidCap 400 via Wikipedia ───────────────────────────────
    try:
        df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")[0]
        col = next((c for c in df.columns if "ticker" in c.lower() or "symbol" in c.lower()), None)
        if col:
            before = len(tickers)
            _add(df[col].tolist())
            print(f"[screener] MidCap 400: added {len(tickers)-before} new tickers.")
    except Exception as exc:
        print(f"[screener] MidCap 400 Wikipedia failed ({exc}) — skipping.")

    if len(tickers) > 100:
        result = tickers[:MAX_TICKERS]
        print(f"[screener] Universe: {len(result)} tickers (capped at {MAX_TICKERS}).")
        return result

    # ── All live sources failed — use built-in fallback ───────────────────────
    print(f"[screener] All live sources failed. Using built-in fallback ({len(FALLBACK_TICKERS)} tickers).")
    return FALLBACK_TICKERS[:MAX_TICKERS]


# Keep old name as alias so nothing else breaks
def get_sp500_tickers() -> list[str]:
    return get_stock_universe()


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


# ── Finnhub analyst price targets ────────────────────────────────────────────

def _get_analyst_target(ticker: str) -> dict:
    """
    Fetch analyst consensus price target from Finnhub /stock/price-target.
    Returns dict with target_mean, target_high, target_low, upside_pct, or {}
    """
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return {}
    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/stock/price-target",
            params={"symbol": ticker, "token": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("targetMean"):
            return {}
        return {
            "analyst_target_mean": round(float(data["targetMean"]), 2),
            "analyst_target_high": round(float(data.get("targetHigh", 0)), 2),
            "analyst_target_low":  round(float(data.get("targetLow", 0)), 2),
        }
    except Exception:
        return {}


# ── Correlation filter ────────────────────────────────────────────────────────

def _deduplicate_by_correlation(
    picks: list[dict],
    hist_data,
    max_picks: int,
    threshold: float = 0.85,
) -> list[dict]:
    """
    Remove highly-correlated picks to improve portfolio diversification.
    Keeps the higher-scored pick when two are correlated above threshold.

    picks      — list of candidate dicts (must have 'ticker' and 'score' keys)
    hist_data  — DataFrame from yf.download (multi-level columns)
    max_picks  — final number of picks to return
    threshold  — correlation above this triggers deduplication (default 0.85)
    """
    if len(picks) <= 1:
        return picks[:max_picks]

    # Build close price matrix for candidate tickers
    close_dict = {}
    for p in picks:
        t = p["ticker"]
        try:
            if hasattr(hist_data.columns, "levels"):
                col = (t, "Close") if (t, "Close") in hist_data.columns else None
                if col:
                    close_dict[t] = hist_data[col].dropna()
            else:
                if t in hist_data.columns:
                    close_dict[t] = hist_data[t].dropna()
        except Exception:
            pass

    if len(close_dict) < 2:
        return picks[:max_picks]

    price_df  = pd.DataFrame(close_dict).dropna()
    corr_mat  = price_df.pct_change().corr()

    kept   = []
    removed = set()

    for p in picks:
        t = p["ticker"]
        if t in removed:
            continue
        kept.append(p)
        if len(kept) >= max_picks:
            break
        # Check correlation with all already-kept tickers
        for k in [x["ticker"] for x in kept[:-1]]:
            try:
                c = corr_mat.loc[t, k] if (t in corr_mat.index and k in corr_mat.columns) else 0
                if abs(c) >= threshold:
                    # Keep the higher-scored pick; remove the lower-scored duplicate
                    k_score = next((x["score"] for x in kept if x["ticker"] == k), 0)
                    lower   = t if p["score"] <= k_score else k
                    removed.add(lower)
                    if lower == t:
                        kept.pop()           # discard the one we just appended
                    else:
                        kept[:] = [x for x in kept if x["ticker"] != k]  # remove k from kept
                    break
            except Exception:
                pass

    print(f"[screener] Correlation filter: {len(picks)} → {len(kept)} picks "
          f"(removed {len(removed)} correlated duplicates)")
    return kept[:max_picks]


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

def run_screener(
    watchlist: list[str] | None = None,
    excluded_sectors: list[str] | None = None,
) -> dict:
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
      6. Apply sector exclusions, then return top 5 ST + top 5 LT.

    watchlist      — tickers always included in both pools regardless of score
    excluded_sectors — sectors to strip from final picks (e.g. ["Energy", "Utilities"])
    """
    watchlist        = [t.upper() for t in (watchlist or [])]
    excluded_sectors = [s.lower() for s in (excluded_sectors or [])]

    # ── Market regime: adjust pick aggressiveness ─────────────────────────────
    regime_info = get_market_regime()
    regime      = regime_info["regime"]
    multiplier  = regime_pick_multiplier(regime)
    max_st      = max(2, round(5 * multiplier))
    max_lt      = max(2, round(5 * multiplier))
    print(f"[screener] Market regime: {regime} (pick multiplier {multiplier}x, "
          f"max ST={max_st}, LT={max_lt})")

    tickers = get_sp500_tickers()

    # Add watchlist tickers not already in the S&P 500 list
    if watchlist:
        existing = set(tickers)
        extra = [t for t in watchlist if t not in existing]
        if extra:
            tickers = tickers + extra
            print(f"[screener] Watchlist added {len(extra)} extra tickers: {extra}")

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

    # Watchlist bypass — ensure watchlist tickers are in both pools
    if watchlist:
        scored_map = {s["ticker"]: s for s in all_scored}
        in_st = {s["ticker"] for s in st_pool}
        in_lt = {s["ticker"] for s in lt_pool}
        for ticker in watchlist:
            if ticker in scored_map:
                if ticker not in in_st:
                    st_pool.append(scored_map[ticker])
                if ticker not in in_lt:
                    lt_pool.append(scored_map[ticker])
        if watchlist:
            print(f"[screener] Watchlist tickers guaranteed in pools: "
                  f"{[t for t in watchlist if t in scored_map]}")

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
            analyst = _get_analyst_target(ticker)
        except Exception:
            analyst = {}

        try:
            lt_score, lt_metrics = _long_term_score(info, fh_metrics)
        except Exception as exc:
            print(f"[screener] LT score failed for {ticker}: {exc}")
            lt_score, lt_metrics = 0, {}

        # Boost score slightly if analyst consensus target is >10% above current price
        if analyst.get("analyst_target_mean") and candidate["current_price"] > 0:
            upside = (analyst["analyst_target_mean"] - candidate["current_price"]) / candidate["current_price"]
            analyst["analyst_upside_pct"] = round(upside * 100, 1)
            if upside > 0.10:
                lt_score = min(100, lt_score + 5)

        entry = {
            "ticker":        ticker,
            "company":       company,
            "sector":        sector,
            "current_price": candidate["current_price"],
            "st_score":      candidate["score"],
            "lt_score":      lt_score,
            "st_metrics":    {k: v for k, v in candidate.items()
                              if k not in ("ticker", "current_price", "score", "avg_dollar_vol")},
            "lt_metrics":    {**lt_metrics, **analyst},
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

    # Apply sector exclusions
    if excluded_sectors:
        before = len(enriched)
        enriched = {
            k: v for k, v in enriched.items()
            if v.get("sector", "").lower() not in excluded_sectors
        }
        removed = before - len(enriched)
        if removed:
            print(f"[screener] Removed {removed} tickers from excluded sectors.")

    # ST top-N: from the ST pool only (ranked by technical score)
    short_candidates = [_flatten_short(enriched[s["ticker"]]) for s in st_pool
                        if s["ticker"] in enriched]
    short_candidates = sorted(short_candidates, key=lambda x: x["score"], reverse=True)

    # LT top-N: from the LT pool only (ranked by fundamental score)
    long_candidates = [_flatten_long(enriched[s["ticker"]]) for s in lt_pool
                       if s["ticker"] in enriched]
    long_candidates = sorted(long_candidates, key=lambda x: x["score"], reverse=True)

    # Apply correlation filter to remove redundant picks
    short_top = _deduplicate_by_correlation(short_candidates, raw, max_st)
    long_top  = _deduplicate_by_correlation(long_candidates,  raw, max_lt)

    print(f"[screener] Top short-term: {[s['ticker'] for s in short_top]}")
    print(f"[screener] Top long-term:  {[s['ticker'] for s in long_top]}")
    print(f"[screener] Regime: {regime} — {regime_info['note']}")

    return {
        "short_term": short_top,
        "long_term":  long_top,
        "regime":     regime_info,
    }


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    results = run_screener()
    print(json.dumps(results, indent=2, default=str))
