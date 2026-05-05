"""
One-shot script to wipe a user's trade log clean.
Run from the stock-agent folder with your env vars:

  GIST_ID=xxx GH_GIST_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python clear_trade_log.py

Pass --all to wipe every user's log, or set CHAT_ID env var for a specific user.
"""
import os
import sys
from config_manager import save_user_trade_log, _load_gist_file, _write_gist_file, USER_TRADES_FILE

if "--all" in sys.argv:
    _write_gist_file(USER_TRADES_FILE, {})
    print("✅ All users' trade logs cleared.")
else:
    chat_id = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        print("⚠️  Set TELEGRAM_CHAT_ID or CHAT_ID env var, or pass --all")
        sys.exit(1)
    save_user_trade_log(chat_id, {"open": [], "closed": []})
    print(f"✅ Trade log cleared for {chat_id} — open: [], closed: []")
