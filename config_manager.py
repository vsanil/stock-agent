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

GIST_FILENAME = "config.json"


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


# ── Internal helpers ──────────────────────────────────────────────────────────

def _write_config(config: dict) -> None:
    """Write config dict to the Gist as config.json."""
    url = f"https://api.github.com/gists/{_gist_id()}"
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(config, indent=2)
            }
        }
    }
    resp = requests.patch(url, headers=_gist_headers(), json=payload, timeout=10)
    resp.raise_for_status()
    print(f"[config_manager] Config updated: {config}")


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    print("Current config:")
    pprint.pprint(get_config())
