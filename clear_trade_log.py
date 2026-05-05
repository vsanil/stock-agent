"""
One-shot script to wipe the trade log clean.
Run from the stock-agent folder with your Render env vars:

  GIST_ID=xxx GH_GIST_TOKEN=xxx python clear_trade_log.py
"""
from config_manager import save_trade_log

save_trade_log({"open": [], "closed": []})
print("✅ Trade log cleared — open: [], closed: []")
