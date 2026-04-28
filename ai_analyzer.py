"""
ai_analyzer.py — Claude API integration for stock + crypto analysis.
Accepts screener candidates, enriches stocks with Finnhub news, returns structured picks.
"""

import os
import json
import time
import requests
import anthropic

FINNHUB_BASE = "https://finnhub.io/api/v1"
MAX_TOKENS = 2000   # Increased to accommodate crypto section


# ── Finnhub news (stocks only) ────────────────────────────────────────────────

def _get_news_headlines(ticker: str, max_headlines: int = 3) -> list[str]:
    """Fetch top recent news headlines for a stock ticker from Finnhub free tier."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    try:
        from datetime import date, timedelta
        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        url = (
            f"{FINNHUB_BASE}/company-news"
            f"?symbol={ticker}&from={week_ago}&to={today}&token={api_key}"
        )
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        articles = resp.json()
        headlines = [a["headline"] for a in articles[:max_headlines] if "headline" in a]
        return headlines
    except Exception as exc:
        print(f"[ai_analyzer] Finnhub news error for {ticker}: {exc}")
        return []


# ── Build stock candidate payload ─────────────────────────────────────────────

def _build_stock_candidates(screener_results: dict) -> list[dict]:
    """Combine short + long stock candidates and enrich with Finnhub news."""
    candidates = []
    seen = set()

    all_picks = (
        [("short_term", s) for s in screener_results.get("short_term", [])] +
        [("long_term",  s) for s in screener_results.get("long_term",  [])]
    )

    for category, stock in all_picks:
        ticker = stock["ticker"]
        entry = {
            "asset_type": "stock",
            "category": category,
            "ticker": ticker,
            "company_name": stock.get("company", ticker),
            "sector": stock.get("sector", "Unknown"),
            "current_price": stock.get("current_price"),
            "score": stock.get("score"),
            "rsi": stock.get("rsi"),
            "macd_crossover": stock.get("macd_crossover"),
            "volume_ratio": stock.get("volume_ratio"),
            "pe_ratio": stock.get("pe_ratio"),
            "revenue_growth": stock.get("revenue_growth"),
            "debt_to_equity": stock.get("debt_to_equity"),
            "market_cap": stock.get("market_cap"),
            "news_headlines": [],
        }

        if ticker not in seen:
            entry["news_headlines"] = _get_news_headlines(ticker)
            seen.add(ticker)
            time.sleep(0.2)

        candidates.append(entry)

    return candidates


# ── Build crypto candidate payload ────────────────────────────────────────────

def _build_crypto_candidates(crypto_results: dict) -> list[dict]:
    """Format crypto screener results for the Claude prompt."""
    candidates = []

    all_picks = (
        [("short_term", c) for c in crypto_results.get("short_term", [])] +
        [("long_term",  c) for c in crypto_results.get("long_term",  [])]
    )

    for category, coin in all_picks:
        entry = {
            "asset_type": "crypto",
            "category": category,
            "ticker": coin.get("symbol", coin.get("id", "")).upper(),
            "name": coin.get("name"),
            "current_price": coin.get("current_price"),
            "market_cap_usd": coin.get("market_cap"),
            "score": coin.get("score"),
            "rsi": coin.get("rsi"),
            "volume_ratio": coin.get("volume_ratio"),
            "price_change_24h_pct": coin.get("price_change_24h_pct"),
            "price_change_7d_pct": coin.get("price_change_7d_pct"),
            "price_change_30d_pct": coin.get("price_change_30d_pct"),
            "pct_below_ath": coin.get("pct_below_ath"),
            "ma7": coin.get("ma7"),
            "ma30": coin.get("ma30"),
        }
        candidates.append(entry)

    return candidates


# ── Claude prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a financial analysis assistant for stocks and cryptocurrencies. "
    "Analyze the provided candidates and return ONLY valid JSON. "
    "Respond with no preamble, no markdown, no explanation. Just the raw JSON object."
)

STRICT_RETRY_SYSTEM = (
    "You are a JSON generator. Output ONLY a valid JSON object. "
    "No text before or after. No markdown. No code blocks. Start with { and end with }."
)


def _build_user_prompt(
    stock_candidates: list[dict],
    crypto_candidates: list[dict],
    config: dict,
) -> str:
    return f"""Analyze these stock AND crypto candidates for a personal investor with the following budgets:

STOCKS:
  Short-term budget: ${config.get('short_term_budget', 25)} (target gains within 1-4 weeks)
  Long-term budget:  ${config.get('long_term_budget', 50)} (dollar-cost average over 1-5 years)
  Keep best {config.get('max_short_picks', 2)} short-term stocks and best {config.get('max_long_picks', 3)} long-term stocks.

CRYPTO:
  Short-term crypto budget: ${config.get('crypto_short_budget', 20)} (target gains within 1-2 weeks, high risk)
  Long-term crypto budget:  ${config.get('crypto_long_budget', 30)} (hold 6-24 months)
  Keep best {config.get('max_crypto_short_picks', 2)} short-term crypto and best {config.get('max_crypto_long_picks', 2)} long-term crypto.

Stock Candidates:
{json.dumps(stock_candidates, indent=2)}

Crypto Candidates:
{json.dumps(crypto_candidates, indent=2)}

Return this exact JSON structure:
{{
  "daily_summary": "one sentence overall market mood covering both stocks and crypto",
  "stocks": {{
    "short_term": [
      {{
        "ticker": "AAPL",
        "company": "Apple Inc",
        "action": "BUY",
        "entry_price": 182.50,
        "target_price": 197.10,
        "stop_loss": 173.38,
        "allocation": 12.50,
        "conviction": 4,
        "thesis": "one sentence why, max 15 words",
        "risk": "one sentence risk, max 10 words"
      }}
    ],
    "long_term": [
      {{
        "ticker": "MSFT",
        "company": "Microsoft Corp",
        "action": "BUY",
        "entry_price": 415.00,
        "target_price": 500.00,
        "allocation": 16.67,
        "conviction": 5,
        "thesis": "one sentence why, max 15 words",
        "horizon": "2-3 years"
      }}
    ]
  }},
  "crypto": {{
    "short_term": [
      {{
        "symbol": "BTC",
        "name": "Bitcoin",
        "action": "BUY",
        "entry_price": 65000,
        "target_price": 72000,
        "stop_loss": 61750,
        "allocation": 10.00,
        "conviction": 3,
        "thesis": "one sentence why, max 15 words",
        "risk": "one sentence risk, max 10 words"
      }}
    ],
    "long_term": [
      {{
        "symbol": "ETH",
        "name": "Ethereum",
        "action": "BUY",
        "entry_price": 3200,
        "target_price": 5000,
        "allocation": 15.00,
        "conviction": 4,
        "thesis": "one sentence why, max 15 words",
        "horizon": "12-18 months"
      }}
    ]
  }},
  "disclaimer": "For informational purposes only. Not financial advice. Crypto is highly volatile."
}}"""


# ── Claude call ───────────────────────────────────────────────────────────────

def _call_claude(system: str, user: str) -> dict:
    """Call Claude API and parse JSON response. Raises on failure."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = message.content[0].text.strip()
    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_with_claude(
    screener_results: dict,
    config: dict,
    crypto_results: dict | None = None,
) -> dict:
    """
    Main entry point. Accepts stock screener output + optional crypto screener output.
    Enriches stocks with Finnhub news, calls Claude once for both asset classes.
    Returns unified picks dict.
    """
    print("[ai_analyzer] Building stock candidates payload...")
    stock_candidates = _build_stock_candidates(screener_results)

    crypto_candidates = []
    if crypto_results:
        print("[ai_analyzer] Building crypto candidates payload...")
        crypto_candidates = _build_crypto_candidates(crypto_results)

    user_prompt = _build_user_prompt(stock_candidates, crypto_candidates, config)

    print("[ai_analyzer] Calling Claude API (stocks + crypto)...")
    try:
        picks = _call_claude(SYSTEM_PROMPT, user_prompt)
        print("[ai_analyzer] Claude response parsed successfully.")
        return picks
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        print(f"[ai_analyzer] Parse error on first attempt ({exc}). Retrying with strict prompt...")

    try:
        picks = _call_claude(STRICT_RETRY_SYSTEM, user_prompt)
        print("[ai_analyzer] Retry succeeded.")
        return picks
    except Exception as exc2:
        print(f"[ai_analyzer] Claude analysis failed after retry: {exc2}")
        raise RuntimeError(f"Claude analysis failed: {exc2}") from exc2


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint
    mock_stocks = {
        "short_term": [
            {"ticker": "AAPL", "company": "Apple Inc", "sector": "Technology",
             "current_price": 182.50, "score": 85, "rsi": 48.2,
             "macd_crossover": True, "volume_ratio": 1.8},
        ],
        "long_term": [
            {"ticker": "MSFT", "company": "Microsoft Corp", "sector": "Technology",
             "current_price": 415.00, "score": 90, "pe_ratio": 32,
             "revenue_growth": 0.17, "debt_to_equity": 0.45, "market_cap": 3_000_000_000_000},
        ],
    }
    mock_crypto = {
        "short_term": [
            {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin",
             "current_price": 65000, "score": 80, "rsi": 55.0,
             "volume_ratio": 1.7, "price_change_24h_pct": 3.2},
        ],
        "long_term": [
            {"id": "ethereum", "symbol": "ETH", "name": "Ethereum",
             "current_price": 3200, "score": 85, "market_cap": 385_000_000_000,
             "price_change_30d_pct": 12.5, "pct_below_ath": 34.0},
        ],
    }
    mock_config = {
        "short_term_budget": 25, "long_term_budget": 50,
        "max_short_picks": 2, "max_long_picks": 3,
        "crypto_short_budget": 20, "crypto_long_budget": 30,
        "max_crypto_short_picks": 2, "max_crypto_long_picks": 2,
    }
    picks = analyze_with_claude(mock_stocks, mock_config, mock_crypto)
    pprint.pprint(picks)
