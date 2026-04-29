"""
agent.py — Main daily runner. Called by GitHub Actions cron job.

Three run modes (auto-detected by ET time, or forced via RUN_MODE env var):
  morning      → 8:00 AM ET  — full screener + Claude analysis + save picks
  confirmation → 10:30 AM ET — fetch live prices, compare to morning picks
  weekly       → Saturday 8 AM — runs crypto morning picks THEN weekly recap

Env vars:
  DRY_RUN=true    → print message, don't send
  MOCK_DATA=true  → skip live screeners (fast test)
  RUN_MODE=morning|confirmation|weekly → override auto-detection
"""

import os
import sys
import time
from datetime import datetime

import pytz

from config_manager import get_config, save_picks, load_picks, save_weekly_pick, get_dynamic_pick_counts
from trade_logger import open_trades, check_and_close_trades
from screener import run_screener
from crypto_screener import run_crypto_screener
from ai_analyzer import analyze_with_claude
from price_checker import get_current_prices
from telegram_notifier import (
    format_daily_message, format_confirmation_message,
    format_weekly_recap_message, send_message,
)

ET        = pytz.timezone("America/New_York")
DRY_RUN   = os.environ.get("DRY_RUN",   "false").lower() == "true"
MOCK_DATA = os.environ.get("MOCK_DATA", "false").lower() == "true"

CRYPTO_RETRY_DELAYS = [15, 30, 60, 120]   # seconds between retries (4 attempts after first)


# ── Mock data for fast testing ────────────────────────────────────────────────

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


# ── Mode detection ────────────────────────────────────────────────────────────

def detect_run_mode(now_et: datetime) -> str:
    """Auto-detect run mode by ET hour/weekday. Override with RUN_MODE env var."""
    forced = os.environ.get("RUN_MODE", "").lower()
    if forced in ("morning", "confirmation", "weekly", "close_check"):
        return forced
    if now_et.weekday() == 5 and now_et.hour < 10:   # Saturday morning
        return "weekly"
    if now_et.hour < 10:
        return "morning"
    if now_et.hour >= 15:
        return "close_check"   # 3:30 PM ET — silent unless a trade closed
    return "confirmation"


# ── Crypto screener with retry ────────────────────────────────────────────────

def _run_crypto_with_retry() -> dict:
    """
    Run crypto screener with up to 5 attempts and increasing delays.
    Sends a Telegram alert on first failure, recovery alert if it succeeds late,
    and a final failure alert if all attempts are exhausted.
    """
    empty = {"short_term": [], "long_term": []}

    for attempt, delay in enumerate([0] + CRYPTO_RETRY_DELAYS, start=1):
        if delay:
            print(f"[agent] Crypto retry {attempt}/5 — waiting {delay}s...")
            time.sleep(delay)
        try:
            result = run_crypto_screener()
            if result.get("short_term") or result.get("long_term"):
                if attempt > 1:
                    _alert(f"✅ Crypto screener recovered on attempt {attempt}/5.")
                return result
            raise ValueError("Screener returned empty results")
        except Exception as exc:
            print(f"[agent] Crypto screener attempt {attempt}/5 failed: {exc}")
            if attempt == 3:
                _alert(f"⚠️ Crypto screener still failing after 3 attempts — retrying ({exc}).")
            elif attempt == len(CRYPTO_RETRY_DELAYS) + 1:
                _alert("❌ Crypto screener failed after 5 attempts. Skipping crypto today.")

    return empty


# ── Morning run ───────────────────────────────────────────────────────────────

def run_morning(config: dict, now_et: datetime):
    """Full screener + Claude analysis + save picks + send morning message."""
    is_weekend = now_et.weekday() >= 5

    if is_weekend and not config.get("crypto_enabled", True):
        print("[agent] Weekend + crypto disabled. Nothing to run.")
        return

    if MOCK_DATA:
        print("[agent] Using mock data — skipping live screeners.")
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

        crypto_candidates = {"short_term": [], "long_term": []}
        if config.get("crypto_enabled", True):
            print("[agent] Running crypto screener (with retry)...")
            crypto_candidates = _run_crypto_with_retry()

    has_stocks = bool(stock_candidates["short_term"] or stock_candidates["long_term"])
    has_crypto = bool(crypto_candidates["short_term"] or crypto_candidates["long_term"])

    if not has_stocks and not has_crypto:
        _alert("⚠ Both screeners returned no candidates today. No picks sent.")
        return

    # Apply dynamic pick counts based on current budget
    dynamic_counts = get_dynamic_pick_counts(config)
    config = {**config, **dynamic_counts}
    print(f"[agent] Dynamic pick counts: {dynamic_counts}")

    print("[agent] Running Claude analysis...")
    try:
        picks = analyze_with_claude(
            stock_candidates, config,
            crypto_results=crypto_candidates if has_crypto else None,
        )
    except Exception as exc:
        print(f"[agent] Claude analysis failed: {exc}")
        _alert("⚠ Agent error today. Claude analysis unavailable.")
        return

    # Save picks to Gist for 10:30 AM confirmation run + weekly recap
    save_picks(picks)
    if not now_et.weekday() >= 5:   # Don't count weekend crypto-only as a "week day"
        try:
            save_weekly_pick(picks)
        except Exception as exc:
            print(f"[agent] Weekly picks save failed (non-critical): {exc}")

    # Open new trades in the trade log
    try:
        open_trades(picks)
    except Exception as exc:
        print(f"[agent] Trade log open failed (non-critical): {exc}")

    message = format_daily_message(picks, config)
    _send_or_print(message, label="8:00 AM Morning Briefing")


# ── Confirmation run ──────────────────────────────────────────────────────────

def run_confirmation():
    """Load morning picks, fetch live prices, send comparison message."""
    print("[agent] Loading morning picks from Gist...")
    picks = load_picks()

    if not picks:
        print("[agent] No picks found for today — skipping confirmation.")
        return

    print("[agent] Fetching current prices...")
    try:
        current_prices = get_current_prices(picks)
    except Exception as exc:
        print(f"[agent] Price fetch failed: {exc}")
        _alert("⚠ Could not fetch prices for 10:30 AM check.")
        return

    # Check and close trades that hit target or stop
    try:
        closed = check_and_close_trades(current_prices)
        for trade in closed:
            emoji = "✅" if trade["outcome"] == "target" else ("🔴" if trade["outcome"] == "stop" else "⏱")
            sign  = "+" if trade["return_pct"] >= 0 else ""
            _alert(f"{emoji} <b>{trade['ticker']}</b> {trade['outcome'].upper()} HIT "
                   f"@ <code>${trade['closed_price']}</code>  "
                   f"<b>{sign}{trade['return_pct']:.1f}%</b>  "
                   f"(${trade['gain_usd']:+.2f})")
    except Exception as exc:
        print(f"[agent] Trade close check failed (non-critical): {exc}")

    message = format_confirmation_message(picks, current_prices)
    _send_or_print(message, label="10:30 AM Confirmation")


# ── Close check (3:30 PM — silent unless a trade closed) ─────────────────────

def run_close_check():
    """3:30 PM run. Checks trades silently — only sends a message if target/stop hit."""
    print("[agent] Running 3:30 PM close check...")
    picks = load_picks()
    if not picks:
        print("[agent] No picks for today — nothing to check.")
        return

    try:
        current_prices = get_current_prices(picks)
    except Exception as exc:
        print(f"[agent] Price fetch failed: {exc}")
        return

    try:
        closed = check_and_close_trades(current_prices)
        if closed:
            for trade in closed:
                emoji = "✅" if trade["outcome"] == "target" else ("🔴" if trade["outcome"] == "stop" else "⏱")
                sign  = "+" if trade["return_pct"] >= 0 else ""
                _alert(f"{emoji} <b>{trade['ticker']}</b> {trade['outcome'].upper()} HIT "
                       f"@ <code>${trade['closed_price']}</code>  "
                       f"<b>{sign}{trade['return_pct']:.1f}%</b>  "
                       f"(${trade['gain_usd']:+.2f})")
        else:
            print("[agent] 3:30 PM close check: no trades hit. No message sent.")
    except Exception as exc:
        print(f"[agent] Trade close check failed (non-critical): {exc}")


# ── Weekly recap (Saturday morning) ──────────────────────────────────────────

def run_weekly_recap(config: dict, now_et: datetime):
    """Saturday: run crypto morning picks, then send a compact weekly recap."""
    # Step 1: Saturday crypto morning picks (markets closed, crypto runs 24/7)
    run_morning(config, now_et)

    # Step 2: Weekly performance recap
    print("[agent] Building weekly recap...")
    try:
        from performance_tracker import build_weekly_recap
        recap = build_weekly_recap()
        if recap:
            message = format_weekly_recap_message(recap)
            _send_or_print(message, label="Weekly Recap")
        else:
            print("[agent] No weekly picks data — skipping recap.")
    except Exception as exc:
        print(f"[agent] Weekly recap failed (non-critical): {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now_et = datetime.now(ET)
    mode   = detect_run_mode(now_et)

    print(f"[agent] Starting [{mode.upper()}{'  DRY RUN' if DRY_RUN else ''}] "
          f"at {now_et.strftime('%Y-%m-%d %H:%M ET')}")

    config = get_config()
    if not config.get("enabled", True):
        print("[agent] Agent is paused. Skipping.")
        return

    if mode == "morning":
        run_morning(config, now_et)
    elif mode == "weekly":
        run_weekly_recap(config, now_et)
    elif mode == "close_check":
        run_close_check()
    else:
        run_confirmation()

    print(f"[agent] Done ({mode}) for {now_et.strftime('%Y-%m-%d')}.")


def _send_or_print(message: str, label: str = ""):
    if DRY_RUN:
        print(f"\n{'=' * 60}")
        print(f"DRY RUN — {label} (not sent):")
        print("=" * 60)
        print(message)
        print(f"\nLength: {len(message)} chars")
        print("=" * 60)
    else:
        print(f"[agent] Sending {label} to Telegram...")
        success = send_message(message)
        if not success:
            print("[agent] WARNING: Message failed to send.")
            sys.exit(1)


def _alert(text: str):
    print(f"[agent] ALERT: {text}")
    if not DRY_RUN:
        send_message(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print(f"⚠ Unhandled error: {exc}\n{traceback.format_exc()}")
        if not DRY_RUN:
            send_message(f"⚠ Agent crashed: {exc}. Check GitHub Actions logs.")
        sys.exit(1)
