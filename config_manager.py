"""
config_manager.py — Read/write agent config from a GitHub Gist (JSON store).
Falls back to hardcoded defaults if the Gist is unreachable.
"""

import os
import json
import requests

# ── Default config ────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "short_term_budget": 25,
    "long_term_budget": 50,
    "max_short_picks": 2,
    "max_long_picks": 3,
    "stop_loss_pct": 5,
    "target_gain_pct": 8,
    "enabled": True,
    "timezone": "America/New_York",
    # Crypto settings
    "crypto_enabled": True,
    "crypto_short_budget": 20,
    "crypto_long_budget": 30,
    "max_crypto_short_picks": 2,
    "max_crypto_long_picks": 2,
}

GIST_FILENAME         = "config.json"
PICKS_FILENAME        = "picks.json"          # Stores morning picks for 10:30 AM confirmation
WEEKLY_PICKS_FILENAME = "weekly_picks.json"   # Accumulates Mon–Fri picks for Saturday recap
TRADE_LOG_FILENAME    = "trade_log.json"      # Persistent trade log for performance tracking


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
    Compute pick counts based on budget so larger budgets get more diversification.
    Maintains a minimum allocation per pick to keep positions meaningful.

    Thresholds:
      Stock ST  — min $12/pick, max 5 picks
      Stock LT  — min $15/pick, max 6 picks
      Crypto ST — min $10/pick, max 4 picks
      Crypto LT — min $10/pick, max 4 picks

    Examples:
      ST $25  → 2 picks ($12.50 each)
      ST $50  → 4 picks ($12.50 each)
      ST $100 → 5 picks (capped)
      LT $50  → 3 picks ($16.67 each)
      LT $100 → 6 picks (capped)
    """
    def _count(budget: float, min_per_pick: float, max_picks: int) -> int:
        return max(2, min(max_picks, int(budget / min_per_pick)))

    return {
        "max_short_picks":        _count(config.get("short_term_budget",  25), 12.0, 5),
        "max_long_picks":         _count(config.get("long_term_budget",   50), 15.0, 6),
        "max_crypto_short_picks": _count(config.get("crypto_short_budget", 20), 10.0, 4),
        "max_crypto_long_picks":  _count(config.get("crypto_long_budget",  30), 10.0, 4),
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


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    print("Current config:")
    pprint.pprint(get_config())
