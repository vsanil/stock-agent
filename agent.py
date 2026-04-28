"""
agent.py — Main daily runner. Called by GitHub Actions cron job.
Set DRY_RUN=true to print the WhatsApp message without sending it.
Runs stock screener + crypto screener, analyzes with Claude, sends WhatsApp.
"""

import os
import sys
from datetime import datetime

import pytz

from config_manager import get_config
from screener import run_screener
from crypto_screener import run_crypto_screener
from ai_analyzer import analyze_with_claude
from whatsapp import format_daily_message, send_message

ET = pytz.timezone("America/New_York")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def main():
    print(f"[agent] Starting {'(DRY RUN) ' if DRY_RUN else ''}at {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")

    # ── Load config ────────────────────────────────────────────────────────────
    config = get_config()

    if not config.get("enabled", True):
        print("[agent] Agent is paused (enabled=false in config). Skipping.")
        return

    # ── Weekday check (stocks only trade Mon-Fri; crypto runs every day) ───────
    now_et = datetime.now(ET)
    is_weekend = now_et.weekday() >= 5

    if is_weekend and not config.get("crypto_enabled", True):
        print(f"[agent] Weekend + crypto disabled. Nothing to run.")
        return

    # ── Run stock screener (weekdays only) ────────────────────────────────────
    stock_candidates = {"short_term": [], "long_term": []}
    if not is_weekend:
        print("[agent] Running stock screener...")
        try:
            stock_candidates = run_screener()
        except Exception as exc:
            print(f"[agent] Stock screener failed: {exc}")
            _alert(f"⚠ Stock screener error: {exc}")
    else:
        print(f"[agent] {now_et.strftime('%A')} — skipping stock screener (markets closed).")

    # ── Run crypto screener (every day) ──────────────────────────────────────
    crypto_candidates = {"short_term": [], "long_term": []}
    if config.get("crypto_enabled", True):
        print("[agent] Running crypto screener...")
        try:
            crypto_candidates = run_crypto_screener()
        except Exception as exc:
            print(f"[agent] Crypto screener failed: {exc}")
            _alert(f"⚠ Crypto screener error: {exc}")

    # ── Check we have something to send ───────────────────────────────────────
    has_stocks = bool(stock_candidates["short_term"] or stock_candidates["long_term"])
    has_crypto = bool(crypto_candidates["short_term"] or crypto_candidates["long_term"])

    if not has_stocks and not has_crypto:
        _alert("⚠ Both screeners returned no candidates today. No picks sent.")
        return

    # ── Claude analysis ────────────────────────────────────────────────────────
    print("[agent] Running Claude analysis (stocks + crypto)...")
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

    # ── Format message ─────────────────────────────────────────────────────────
    message = format_daily_message(picks, config)

    # ── Send or print ──────────────────────────────────────────────────────────
    if DRY_RUN:
        print("\n" + "=" * 60)
        print("DRY RUN — WhatsApp message (not sent):")
        print("=" * 60)
        print(message)
        print(f"\nMessage length: {len(message)} chars")
        print("=" * 60)
    else:
        print("[agent] Sending WhatsApp message...")
        success = send_message(message)
        if not success:
            print("[agent] WARNING: Message failed to send.")
            sys.exit(1)

    print(f"[agent] Done. Picks processed for {now_et.strftime('%Y-%m-%d')}.")


def _alert(text: str):
    """Send an error alert via WhatsApp (unless DRY_RUN)."""
    print(f"[agent] ALERT: {text}")
    if not DRY_RUN:
        send_message(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        err = f"⚠ Unhandled agent error: {exc}\n{traceback.format_exc()}"
        print(err)
        if not DRY_RUN:
            send_message(f"⚠ Agent crashed: {exc}. Check GitHub Actions logs.")
        sys.exit(1)
