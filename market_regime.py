"""
market_regime.py — Detect current market regime using VIX + SPY trend.

Regime classification:
  bull     → SPY above 50 & 200 MA, VIX < 20
  volatile → VIX > 30 (regardless of trend)
  bear     → SPY below 200 MA
  neutral  → everything else

Used by screener and AI analyzer to adjust pick behavior:
  bull     → normal operation
  neutral  → normal, add caution note
  volatile → reduce pick count, prefer defensive sectors
  bear     → defensive only, skip aggressive momentum plays
"""

import yfinance as yf

# VIX thresholds
VIX_LOW      = 15   # calm market
VIX_ELEVATED = 20   # caution zone
VIX_HIGH     = 30   # high fear / volatile regime


def get_market_regime() -> dict:
    """
    Fetch VIX and SPY MAs, classify market regime.

    Returns:
        {
            "regime":          "bull" | "bear" | "volatile" | "neutral",
            "vix":             float | None,
            "spy_price":       float | None,
            "spy_ma50":        float | None,
            "spy_ma200":       float | None,
            "spy_above_50ma":  bool | None,
            "spy_above_200ma": bool | None,
            "note":            str,
        }
    """
    vix            = None
    spy_price      = None
    spy_ma50       = None
    spy_ma200      = None
    spy_above_50   = None
    spy_above_200  = None

    # ── VIX ───────────────────────────────────────────────────────────────────
    try:
        vix = float(yf.Ticker("^VIX").fast_info.last_price)
    except Exception as exc:
        print(f"[market_regime] VIX fetch failed: {exc}")

    # ── SPY moving averages ───────────────────────────────────────────────────
    try:
        hist = yf.Ticker("SPY").history(period="1y")
        if len(hist) >= 200:
            spy_price    = float(hist["Close"].iloc[-1])
            spy_ma50     = float(hist["Close"].rolling(50).mean().iloc[-1])
            spy_ma200    = float(hist["Close"].rolling(200).mean().iloc[-1])
            spy_above_50  = spy_price > spy_ma50
            spy_above_200 = spy_price > spy_ma200
    except Exception as exc:
        print(f"[market_regime] SPY history fetch failed: {exc}")

    # ── Classify ──────────────────────────────────────────────────────────────
    if vix is not None and vix >= VIX_HIGH:
        regime = "volatile"
        note   = f"VIX={vix:.1f} — extreme fear, tighten stops, reduce size"
    elif spy_above_200 is False:
        regime = "bear"
        note   = (f"SPY below 200-day MA (${spy_price:.0f} vs MA ${spy_ma200:.0f}) "
                  "— defensive posture, avoid momentum plays")
    elif spy_above_50 is True and spy_above_200 is True and (vix is None or vix < VIX_ELEVATED):
        regime = "bull"
        vix_str = f", VIX={vix:.1f}" if vix else ""
        note    = f"SPY in uptrend{vix_str} — favorable conditions"
    else:
        regime = "neutral"
        vix_str = f", VIX={vix:.1f}" if vix else ""
        note    = f"Mixed signals{vix_str} — normal caution applies"

    return {
        "regime":          regime,
        "vix":             round(vix, 1) if vix is not None else None,
        "spy_price":       round(spy_price, 2) if spy_price else None,
        "spy_ma50":        round(spy_ma50, 2) if spy_ma50 else None,
        "spy_ma200":       round(spy_ma200, 2) if spy_ma200 else None,
        "spy_above_50ma":  spy_above_50,
        "spy_above_200ma": spy_above_200,
        "note":            note,
    }


def regime_pick_multiplier(regime: str) -> float:
    """
    Return a multiplier (0.5–1.0) to scale down pick counts in risky regimes.
    Screener multiplies max_picks by this before selecting candidates.
    """
    return {
        "bull":     1.0,
        "neutral":  1.0,
        "volatile": 0.6,   # fewer picks, higher bar
        "bear":     0.5,   # defensive only
    }.get(regime, 1.0)


def regime_emoji(regime: str) -> str:
    return {"bull": "🐂", "bear": "🐻", "volatile": "⚡", "neutral": "➡️"}.get(regime, "")


if __name__ == "__main__":
    import pprint
    pprint.pprint(get_market_regime())
