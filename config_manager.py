"""
config_manager.py — Read/write agent config from a GitHub Gist (JSON store).
Falls back to hardcoded defaults if the Gist is unreachable.
"""

import os
import json
import requests

# ── Default config ────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    # Budgets — null means unset (no allocation shown in picks)
    "stock_budget":  None,   # total daily $ for stocks, split equally across all stock picks
    "crypto_budget": None,   # total daily $ for crypto, split equally across all crypto picks
    "max_short_picks": 2,
    "max_long_picks": 3,
    "stop_loss_pct": 5,
    "target_gain_pct": 8,
    "enabled": True,
    "timezone": "America/New_York",
    # Crypto settings
    "crypto_enabled": True,
    "max_crypto_short_picks": 2,
    "max_crypto_long_picks": 2,
    # AI intelligence settings
    "risk_profile": "moderate",       # conservative | moderate | aggressive
    "excluded_sectors": [],            # e.g. ["Energy", "Utilities"]
    "watchlist": [],                   # e.g. ["NVDA", "TSLA", "BRK-B"] — always evaluated
    # Pick mode: which sections appear in daily message
    "pick_mode": "both",              # "st" | "lt" | "both"
    # Multi-user pilot: list of chat_id strings allowed to receive messages
    # Empty list = owner-only mode (just TELEGRAM_CHAT_ID env var).
    "allowed_users": [],
}

GIST_FILENAME          = "config.json"
PICKS_FILENAME         = "picks.json"           # Stores morning picks for 10:30 AM confirmation
WEEKLY_PICKS_FILENAME  = "weekly_picks.json"    # Accumulates Mon–Fri picks for Saturday recap
TRADE_LOG_FILENAME     = "trade_log.json"       # Persistent trade log for performance tracking
PENDING_STATE_FILENAME = "pending_state.json"   # Conversation state for multi-step commands
PAPER_PORTFOLIO_FILE   = "paper_portfolio.json" # Paper trading portfolio (simulated trades)
PRICE_ALERTS_FILE      = "price_alerts.json"    # User price alerts
SIGNAL_CACHE_FILE      = "signal_cache.json"    # Cached sentiment + insider signals (5-day TTL)
SCREENER_CACHE_FILE    = "screener_cache.json"  # Pre-scored candidates from midnight run


def _gist_headers() -> dict:
    token = os.environ.get("GH_GIST_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def _gist_id() -> str:
    gist_id = os.environ.get("GIST_ID", "")
    if not gist_id:
        raise EnvironmentError("GIST_ID environment variable is not set.")
    return gist_id


# ── Public API ────────────────────────────────────────────────────────────────

def get_config() -> dict:
    """Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error."""
    try:
        url = f"https://api.github.com/gists/{_gist_id()}"
        resp = requests.get(url, headers=_gist_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw = data["files"][GIST_FILENAME]["content"]
        config = json.loads(raw)
        # Merge with defaults so new keys are always present
        merged = {**DEFAULT_CONFIG, **config}
        return merged
    except Exception as exc:
        print(f"[config_manager] WARNING: Could not fetch Gist config ({exc}). Using defaults.")
        return dict(DEFAULT_CONFIG)


def update_config(key: str, value) -> dict:
    """Patch a single key in config.json on the Gist. Returns updated config."""
    config = get_config()
    config[key] = value
    _write_config(config)
    return config


def update_config_multi(updates: dict) -> dict:
    """Patch multiple keys at once. Returns updated config."""
    config = get_config()
    config.update(updates)
    _write_config(config)
    return config


def reset_config() -> dict:
    """Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults."""
    _write_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


# ── Multi-user allowlist helpers ─────────────────────────────────────────────

def get_allowed_users() -> list[str]:
    """Return list of allowed chat_ids. Always includes TELEGRAM_CHAT_ID (owner)."""
    import os
    config = get_config()
    users  = [str(u) for u in config.get("allowed_users", [])]
    owner  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if owner and owner not in users:
        users.insert(0, owner)
    return users


def add_allowed_user(chat_id: str) -> list[str]:
    """Add a chat_id to allowed_users. Returns updated list."""
    config = get_config()
    users  = [str(u) for u in config.get("allowed_users", [])]
    if str(chat_id) not in users:
        users.append(str(chat_id))
        update_config("allowed_users", users)
        print(f"[config_manager] Added user {chat_id} to allowlist.")
    return users


def remove_allowed_user(chat_id: str) -> list[str]:
    """Remove a chat_id from allowed_users. Returns updated list."""
    import os
    owner = os.environ.get("TELEGRAM_CHAT_ID", "")
    if str(chat_id) == str(owner):
        raise ValueError("Cannot remove the bot owner from the allowlist.")
    config = get_config()
    users  = [str(u) for u in config.get("allowed_users", []) if str(u) != str(chat_id)]
    update_config("allowed_users", users)
    print(f"[config_manager] Removed user {chat_id} from allowlist.")
    return users


# ── Picks storage (for 10:30 AM confirmation run) ────────────────────────────

def save_picks(picks: dict) -> None:
    """Save morning picks to Gist as picks.json for the confirmation run."""
    from datetime import date
    picks["_saved_date"] = date.today().isoformat()
    url = f"https://api.github.com/gists/{_gist_id()}"
    payload = {
        "files": {
            PICKS_FILENAME: {
                "content": json.dumps(picks, indent=2)
            }
        }
    }
    try:
        resp = requests.patch(url, headers=_gist_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        print("[config_manager] Morning picks saved to Gist.")
    except Exception as exc:
        print(f"[config_manager] WARNING: Could not save picks ({exc}).")


def load_picks() -> dict | None:
    """Load today's morning picks from Gist. Returns None if not found or stale."""
    from datetime import date
    try:
        url = f"https://api.github.com/gists/{_gist_id()}"
        resp = requests.get(url, headers=_gist_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", {})
        if PICKS_FILENAME not in files:
            return None
        raw   = files[PICKS_FILENAME]["content"]
        picks = json.loads(raw)
        # Only return picks saved today
        if picks.get("_saved_date") != date.today().isoformat():
            print("[config_manager] Picks are from a previous day — skipping confirmation.")
            return None
        return picks
    except Exception as exc:
        print(f"[config_manager] WARNING: Could not load picks ({exc}).")
        return None


# ── Weekly picks storage (for Saturday recap) ────────────────────────────────

def save_weekly_pick(picks: dict) -> None:
    """Append today's picks to weekly_picks.json in Gist. Clears stale weeks automatically."""
    from datetime import date, timedelta
    today = date.today().isoformat()

    # Load existing weekly data
    weekly = _load_gist_file(WEEKLY_PICKS_FILENAME) or {}

    # If the oldest entry is > 6 days old, it's a new week — start fresh
    if weekly:
        oldest = min(weekly.keys())
        try:
            if (date.today() - date.fromisoformat(oldest)).days > 6:
                weekly = {}
        except ValueError:
            weekly = {}

    weekly[today] = picks
    _write_gist_file(WEEKLY_PICKS_FILENAME, weekly)
    print(f"[config_manager] Weekly picks updated ({len(weekly)} days this week).")


def load_weekly_picks() -> dict:
    """Load this week's picks keyed by date string. Returns {} if empty or missing."""
    return _load_gist_file(WEEKLY_PICKS_FILENAME) or {}


# ── Dynamic pick counts ───────────────────────────────────────────────────────

def get_dynamic_pick_counts(config: dict) -> dict:
    """
    Compute pick counts from the two-bucket budgets.
    If budget is unset, fall back to the config's existing max_*_picks values.

    Stock budget split equally between ST and LT:
      $100 stock → 2 ST + 3 LT (defaults), $200 → up to 4 ST + 5 LT
    Crypto budget split equally between ST and LT.

    Min per pick: stocks $12, crypto $10. Max: 5 ST / 6 LT / 4 CST / 4 CLT.
    """
    def _count(budget: float | None, share: float, min_per_pick: float,
               max_picks: int, default: int) -> int:
        if not budget:
            return default
        allocated = budget * share   # rough half for ST, half for LT
        return max(2, min(max_picks, int(allocated / min_per_pick)))

    sb = config.get("stock_budget")
    cb = config.get("crypto_budget")

    return {
        "max_short_picks":        _count(sb, 0.4, 12.0, 5, config.get("max_short_picks", 2)),
        "max_long_picks":         _count(sb, 0.6, 15.0, 6, config.get("max_long_picks",  3)),
        "max_crypto_short_picks": _count(cb, 0.5, 10.0, 4, config.get("max_crypto_short_picks", 2)),
        "max_crypto_long_picks":  _count(cb, 0.5, 10.0, 4, config.get("max_crypto_long_picks",  2)),
    }


# ── Trade log (persistent P&L tracking) ──────────────────────────────────────

def load_trade_log() -> dict:
    """Load trade log from Gist. Returns {"open": [], "closed": []} if missing."""
    data = _load_gist_file(TRADE_LOG_FILENAME)
    if not data:
        return {"open": [], "closed": []}
    data.setdefault("open", [])
    data.setdefault("closed", [])
    return data


def save_trade_log(log: dict) -> None:
    """Save trade log to Gist."""
    _write_gist_file(TRADE_LOG_FILENAME, log)
    print(f"[config_manager] Trade log saved "
          f"({len(log['open'])} open, {len(log['closed'])} closed).")


# ── Signal cache (sentiment + insider, 5-day TTL) ────────────────────────────

SIGNAL_CACHE_TTL_DAYS = 5


def load_signal_cache() -> dict:
    """
    Load the signal cache from Gist.
    Cache structure: { ticker: { "sentiment": {...}, "insider": {...}, "cached_date": "YYYY-MM-DD" } }
    Returns {} if missing.
    """
    return _load_gist_file(SIGNAL_CACHE_FILE) or {}


def save_signal_cache(cache: dict) -> None:
    """Write signal cache to Gist."""
    _write_gist_file(SIGNAL_CACHE_FILE, cache)
    print(f"[config_manager] Signal cache saved ({len(cache)} ticker(s)).")


def get_cached_signal(cache: dict, ticker: str) -> dict | None:
    """
    Return cached signals for a ticker if still within TTL, else None.
    Caller is responsible for providing the loaded cache dict to avoid
    repeated Gist fetches.
    """
    from datetime import date
    entry = cache.get(ticker)
    if not entry:
        return None
    try:
        cached_date = date.fromisoformat(entry.get("cached_date", ""))
        age_days    = (date.today() - cached_date).days
        if age_days <= SIGNAL_CACHE_TTL_DAYS:
            return entry
    except Exception:
        pass
    return None


def set_cached_signal(cache: dict, ticker: str, sentiment: dict | None,
                      insider: dict | None) -> None:
    """
    Upsert a ticker's signals in the cache dict (in-place).
    Call save_signal_cache(cache) after processing all tickers.
    """
    from datetime import date
    cache[ticker] = {
        "sentiment":   sentiment,
        "insider":     insider,
        "cached_date": date.today().isoformat(),
    }


# ── Screener cache (midnight pre-score, consumed by 8 AM morning run) ────────

SCREENER_CACHE_MAX_AGE_HOURS = 10   # midnight ET → 8 AM ET = 8h; 10h gives buffer


def save_screener_cache(stock_results: dict, crypto_results: dict) -> None:
    """
    Save pre-scored screener candidates from the midnight run.
    Stored as screener_cache.json in the Gist.
    """
    from datetime import datetime
    payload = {
        "cached_at":  datetime.utcnow().isoformat(),
        "stocks":     stock_results,
        "crypto":     crypto_results,
    }
    _write_gist_file(SCREENER_CACHE_FILE, payload)
    print("[config_manager] Screener cache saved to Gist.")


def load_screener_cache() -> dict | None:
    """
    Load the midnight screener cache if it exists and is fresh (< 10h old).
    Returns the cache dict {cached_at, stocks, crypto} or None if stale/missing.
    """
    from datetime import datetime, timedelta
    data = _load_gist_file(SCREENER_CACHE_FILE)
    if not data:
        return None
    try:
        cached_at = datetime.fromisoformat(data["cached_at"])
        age = datetime.utcnow() - cached_at
        if age > timedelta(hours=SCREENER_CACHE_MAX_AGE_HOURS):
            print(f"[config_manager] Screener cache is {age} old — too stale, ignoring.")
            return None
        print(f"[config_manager] Screener cache hit — {age} old.")
        return data
    except Exception as exc:
        print(f"[config_manager] Screener cache invalid ({exc}).")
        return None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _write_config(config: dict) -> None:
    """Write config dict to the Gist as config.json."""
    _write_gist_file(GIST_FILENAME, config)
    print(f"[config_manager] Config updated: {config}")


def _load_gist_file(filename: str) -> dict | None:
    """Fetch and parse a JSON file from the Gist. Returns None on any error."""
    try:
        url  = f"https://api.github.com/gists/{_gist_id()}"
        resp = requests.get(url, headers=_gist_headers(), timeout=10)
        resp.raise_for_status()
        files = resp.json().get("files", {})
        if filename not in files:
            return None
        return json.loads(files[filename]["content"])
    except Exception as exc:
        print(f"[config_manager] WARNING: Could not load {filename} ({exc}).")
        return None


def _write_gist_file(filename: str, data: dict) -> None:
    """Write any dict as a JSON file to the Gist."""
    url     = f"https://api.github.com/gists/{_gist_id()}"
    payload = {"files": {filename: {"content": json.dumps(data, indent=2)}}}
    resp    = requests.patch(url, headers=_gist_headers(), json=payload, timeout=10)
    resp.raise_for_status()


# ── Pending conversation state (multi-step commands) ─────────────────────────

def load_pending_state(chat_id: str) -> dict | None:
    """
    Load pending conversation state for a chat_id.
    Returns None if not found or expired (60-second TTL).
    """
    from datetime import datetime
    data  = _load_gist_file(PENDING_STATE_FILENAME) or {}
    state = data.get(str(chat_id))
    if not state:
        return None
    try:
        if datetime.utcnow() > datetime.fromisoformat(state["expires_at"]):
            clear_pending_state(chat_id)
            return None
    except Exception:
        return None
    return state


def save_pending_state(chat_id: str, command: str,
                       step: int = 1, data: dict | None = None) -> None:
    """Save pending state for a chat_id with a 60-second expiry."""
    from datetime import datetime, timedelta
    all_states = _load_gist_file(PENDING_STATE_FILENAME) or {}
    all_states[str(chat_id)] = {
        "command":    command,
        "step":       step,
        "data":       data or {},
        "expires_at": (datetime.utcnow() + timedelta(seconds=60)).isoformat(),
    }
    _write_gist_file(PENDING_STATE_FILENAME, all_states)


def clear_pending_state(chat_id: str) -> None:
    """Remove pending state for a chat_id."""
    all_states = _load_gist_file(PENDING_STATE_FILENAME) or {}
    if str(chat_id) in all_states:
        del all_states[str(chat_id)]
        _write_gist_file(PENDING_STATE_FILENAME, all_states)


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    print("Current config:")
    pprint.pprint(get_config())
