"""
agent.py — Main daily runner. Called by GitHub Actions cron job.
Set DRY_RUN=true to print the Telegram message without sending it.
Set DRY_RUN=true + MOCK_DATA=true to skip screeners entirely (fastest test).
Runs stock screener + crypto screener, analyzes with Claude, sends Telegram message.
"""

import os
import sys
from datetime import datetime

import pytz

from config_manager import get_config
from screener import run_screener
from crypto_screener import run_crypto_screener
from ai_analyzer import analyze_with_claude
from telegram_notifier import format_daily_message, send_message

ET = pytz.timezone("America/New_York")
DRY_RUN   = os.environ.get("DRY_RUN",   "false").lower() == "true"
MOCK_DATA = os.environ.get("MOCK_DATA", "false").lower() == "true"


# ── Mock data for fast dry-run testing ───────────────────────────────────────

MOCK_STOCK_CANDIDATES = {
    "short_term": [
        {"ticker": "AAPL", "company": "Apple Inc", "sector": "Technology",
         "current_price": 182.50, "score": 85, "rsi": 48.2,
         "macd_crossover": True, "volume_ratio": 1.8},
        {"ticker": "NVDA", "company": "NVIDIA Corp", "sector": "Technology",
         "current_price": 875.00, "score": 75, "rsi": 52.1,
         "macd_crossover": False, "volume_ratio": 2.1},
    ],
    "long_term": [
        {"ticker": "MSFT", "company": "Microsoft Corp", "sector": "Technology",
         "current_price": 415.00, "score": 90, "pe_ratio": 32,
         "revenue_growth": 0.17, "debt_to_equity": 0.45, "market_cap": 3_000_000_000_000},
        {"ticker": "JNJ", "company": "Johnson & Johnson", "sector": "Health Care",
         "current_price": 155.00, "score": 80, "pe_ratio": 14,
         "revenue_growth": 0.06, "debt_to_equity": 0.5, "market_cap": 400_000_000_000},
    ],
}

MOCK_CRYPTO_CANDIDATES = {
    "short_term": [
        {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin",
         "current_price": 65000, "score": 80, "rsi": 55.0,
         "volume_ratio": 1.7, "price_change_24h_pct": 3.2, "price_change_7d_pct": 8.1},
        {"id": "solana", "symbol": "SOL", "name": "Solana",
         "current_price": 145.00, "score": 72, "rsi": 58.0,
         "volume_ratio": 2.1, "price_change_24h_pct": 4.5, "price_change_7d_pct": 12.3},
    ],
    "long_term": [
        {"id": "ethereum", "symbol": "ETH", "name": "Ethereum",
         "current_price": 3200, "score": 85, "market_cap": 385_000_000_000,
         "price_change_30d_pct": 12.5, "pct_below_ath": 34.0, "ma30": 2950.0},
        {"id": "chainlink", "symbol": "LINK", "name": "Chainlink",
         "current_price": 14.50, "score": 70, "market_cap": 8_500_000_000,
         "price_change_30d_pct": 18.2, "pct_below_ath": 55.0, "ma30": 13.20},
    ],
}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    mode = "DRY RUN (mock data)" if (DRY_RUN and MOCK_DATA) else "DRY RUN" if DRY_RUN else "LIVE"
    print(f"[agent] Starting [{mode}] at {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")

    config = get_config()

    if not config.get("enabled", True):
        print("[agent] Agent is paused (enabled=false in config). Skipping.")
        return

    now_et     = datetime.now(ET)
    is_weekend = now_et.weekday() >= 5

    if is_weekend and not config.get("crypto_enabled", True):
        print("[agent] Weekend + crypto disabled. Nothing to run.")
        return

    # ── Screeners (or mock data) ──────────────────────────────────────────────
    if MOCK_DATA:
        print("[agent] Using mock data (MOCK_DATA=true) — skipping live screeners.")
        stock_candidates  = MOCK_STOCK_CANDIDATES
        crypto_candidates = MOCK_CRYPTO_CANDIDATES
    else:
        stock_candidates = {"short_term": [], "long_term": []}
        if not is_weekend:
            print("[agent] Running stock screener...")
            try:
                stock_candidates = run_screener()
            except Exception as exc:
                print(f"[agent] Stock screener failed: {exc}")
                _alert(f"⚠ Stock screener error: {exc}")
        else:
            print(f"[agent] {now_et.strftime('%A')} — skipping stocks (market closed).")

        crypto_candidates = {"short_term": [], "long_term": []}
        if config.get("crypto_enabled", True):
            print("[agent] Running crypto screener...")
            try:
                crypto_candidates = run_crypto_screener()
            except Exception as exc:
                print(f"[agent] Crypto screener failed: {exc}")
                _alert(f"⚠ Crypto screener error: {exc}")

    has_stocks = bool(stock_candidates["short_term"] or stock_candidates["long_term"])
    has_crypto = bool(crypto_candidates["short_term"] or crypto_candidates["long_term"])

    if not has_stocks and not has_crypto:
        _alert("⚠ Both screeners returned no candidates today. No picks sent.")
        return

    # ── Claude analysis ───────────────────────────────────────────────────────
    print("[agent] Running Claude analysis...")
    try:
        picks = analyze_with_claude(
            stock_candidates,
            config,
            crypto_results=crypto_candidates if has_crypto else None,
        )
    except Exception as exc:
        print(f"[agent] Claude analysis failed: {exc}")
        _alert("⚠ Agent error today. Claude analysis unavailable. Picks not sent.")
        return

    # ── Format + send ─────────────────────────────────────────────────────────
    message = format_daily_message(picks, config)

    if DRY_RUN:
        print("\n" + "=" * 60)
        print("DRY RUN — Telegram message (not sent):")
        print("=" * 60)
        print(message)
        print(f"\nMessage length: {len(message)} chars")
        print("=" * 60)
    else:
        print("[agent] Sending Telegram message...")
        success = send_message(message)
        if not success:
            print("[agent] WARNING: Message failed to send.")
            sys.exit(1)

    print(f"[agent] Done. Picks processed for {now_et.strftime('%Y-%m-%d')}.")


def _alert(text: str):
    print(f"[agent] ALERT: {text}")
    if not DRY_RUN:
        send_message(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print(f"⚠ Unhandled agent error: {exc}\n{traceback.format_exc()}")
        if not DRY_RUN:
            send_message(f"⚠ Agent crashed: {exc}. Check GitHub Actions logs.")
        sys.exit(1)
