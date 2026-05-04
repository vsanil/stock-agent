"""
options_flow.py — Detect unusual options activity using yfinance (free).

Signals:
  - Volume/OI ratio > 2.0  → unusual activity (someone is betting big)
  - Put/call ratio < 0.7   → bullish flow (more calls than puts)
  - Put/call ratio > 1.5   → bearish flow (puts dominating)

yfinance options data is free but covers only US-listed stocks with options.
Crypto and some small-caps will return "no options data".
"""

import yfinance as yf


def get_options_signal(ticker: str) -> dict:
    """
    Analyze the nearest-expiry options chain for unusual activity.

    Returns:
        {
            "unusual":         bool,
            "put_call_ratio":  float | None,
            "vol_oi_ratio":    float | None,
            "call_volume":     int,
            "put_volume":      int,
            "bullish_flow":    bool,
            "bearish_flow":    bool,
            "signal_score":    int,    # -5 to +5
            "note":            str,
        }
    """
    base = {
        "unusual": False, "put_call_ratio": None, "vol_oi_ratio": None,
        "call_volume": 0, "put_volume": 0,
        "bullish_flow": False, "bearish_flow": False,
        "signal_score": 0, "note": "no options data",
    }

    try:
        tk   = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            return base

        # Use the nearest expiration for maximum liquidity signal
        chain = tk.option_chain(exps[0])
        calls = chain.calls
        puts  = chain.puts

        if calls.empty and puts.empty:
            return {**base, "note": "empty chain"}

        call_vol = int(calls["volume"].fillna(0).sum())
        put_vol  = int(puts["volume"].fillna(0).sum())
        call_oi  = int(calls["openInterest"].fillna(0).sum())
        put_oi   = int(puts["openInterest"].fillna(0).sum())

        total_vol = call_vol + put_vol
        total_oi  = call_oi + put_oi

        put_call_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else None
        vol_oi_ratio   = round(total_vol / total_oi, 2) if total_oi > 0 else None

        # Unusual: volume is > 2x open interest (abnormal betting activity)
        unusual = bool(vol_oi_ratio and vol_oi_ratio > 2.0)

        # Flow direction
        bullish_flow = bool(put_call_ratio is not None and put_call_ratio < 0.7)
        bearish_flow = bool(put_call_ratio is not None and put_call_ratio > 1.5)

        # Signal score: unusual + direction combined
        score = 0
        notes = []
        if unusual:
            score += 2
            notes.append(f"unusual vol/OI={vol_oi_ratio}")
        if bullish_flow:
            score += 3
            notes.append(f"bullish flow P/C={put_call_ratio}")
        if bearish_flow:
            score -= 3
            notes.append(f"bearish flow P/C={put_call_ratio}")

        note = ", ".join(notes) if notes else f"P/C={put_call_ratio}, vol/OI={vol_oi_ratio}"

        return {
            "unusual":        unusual,
            "put_call_ratio": put_call_ratio,
            "vol_oi_ratio":   vol_oi_ratio,
            "call_volume":    call_vol,
            "put_volume":     put_vol,
            "bullish_flow":   bullish_flow,
            "bearish_flow":   bearish_flow,
            "signal_score":   max(-5, min(5, score)),
            "note":           note,
        }

    except Exception as exc:
        return {**base, "note": f"error: {exc}"}


def batch_options_signals(tickers: list[str]) -> dict[str, dict]:
    """Fetch options signals for multiple tickers. Returns {ticker: signal_dict}."""
    return {t: get_options_signal(t) for t in tickers}


if __name__ == "__main__":
    import pprint
    for ticker in ["NVDA", "AAPL", "SPY"]:
        print(f"\n=== {ticker} ===")
        pprint.pprint(get_options_signal(ticker))
