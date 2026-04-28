# Graph Report - stock-agent  (2026-04-28)

## Corpus Check
- 7 files · ~5,788 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 90 nodes · 113 edges · 18 communities detected
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `get_config()` - 9 edges
2. `main()` - 8 edges
3. `_write_config()` - 7 edges
4. `_parse_and_execute()` - 7 edges
5. `analyze_with_claude()` - 7 edges
6. `run_crypto_screener()` - 7 edges
7. `run_screener()` - 6 edges
8. `update_config()` - 5 edges
9. `update_config_multi()` - 5 edges
10. `send_message()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `get_config()` --calls--> `health()`  [INFERRED]
  config_manager.py → webhook.py
- `get_config()` --calls--> `main()`  [INFERRED]
  config_manager.py → agent.py
- `handle_incoming_command()` --calls--> `webhook()`  [INFERRED]
  whatsapp.py → webhook.py
- `run_screener()` --calls--> `main()`  [INFERRED]
  screener.py → agent.py
- `analyze_with_claude()` --calls--> `main()`  [INFERRED]
  ai_analyzer.py → agent.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.23
Nodes (15): get_config(), _gist_headers(), _gist_id(), config_manager.py — Read/write agent config from a GitHub Gist (JSON store). Fal, Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error., Patch a single key in config.json on the Gist. Returns updated config., Patch multiple keys at once. Returns updated config., Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults. (+7 more)

### Community 1 - "Community 1"
Cohesion: 0.18
Nodes (15): _get_market_chart(), _get_top_coins(), _long_term_score(), crypto_screener.py — Crypto screener using CoinGecko free API (no key needed). R, Score a coin for long-term holding (out of 100)., Screen top 100 crypto coins and return top candidates.     Returns:         {, Fetch top coins by market cap from CoinGecko /coins/markets., Fetch historical OHLC-style price data for RSI/MA calculation. (+7 more)

### Community 2 - "Community 2"
Cohesion: 0.2
Nodes (12): _alert(), main(), agent.py — Main daily runner. Called by GitHub Actions cron job. Set DRY_RUN=tru, Send an error alert via WhatsApp (unless DRY_RUN)., _conviction_bar(), format_daily_message(), handle_incoming_command(), whatsapp.py — CallMeBot send/receive helpers + WhatsApp command parser. (+4 more)

### Community 3 - "Community 3"
Cohesion: 0.22
Nodes (12): analyze_with_claude(), _build_crypto_candidates(), _build_stock_candidates(), _build_user_prompt(), _call_claude(), _get_news_headlines(), ai_analyzer.py — Claude API integration for stock analysis. Accepts screener can, Fetch top recent news headlines for a ticker from Finnhub free tier. (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.27
Nodes (9): get_sp500_tickers(), _long_term_score(), screener.py — S&P 500 stock screener using yfinance + pandas-ta. Returns top 5 s, Score a ticker for long-term investing (out of 100). Returns (score, metrics)., Screen S&P 500 stocks and return top candidates.     Returns:         {, Pull S&P 500 tickers from Wikipedia., Score a ticker for short-term trading (out of 100). Returns (score, metrics)., run_screener() (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.25
Nodes (7): health(), webhook.py — Flask app to receive inbound WhatsApp commands via CallMeBot webhoo, Check WEBHOOK_SECRET in header or query param., Receive inbound WhatsApp command from CallMeBot., Health check — returns current config., _verify_secret(), webhook()

### Community 6 - "Community 6"
Cohesion: 1.0
Nodes (1): Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.

### Community 7 - "Community 7"
Cohesion: 1.0
Nodes (1): Patch a single key in config.json on the Gist. Returns updated config.

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (1): Patch multiple keys at once. Returns updated config.

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Write config dict to the Gist as config.json.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): Build the formatted daily WhatsApp message from Claude picks.

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Parse and execute a WhatsApp command string.     Sends a confirmation message ba

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Parse command and return reply string.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Call Claude API and parse JSON response. Raises on failure.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Main entry point.     Accepts screener output, enriches with news, calls Claude,

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Send an error alert via WhatsApp (unless DRY_RUN).

## Knowledge Gaps
- **48 isolated node(s):** `config_manager.py — Read/write agent config from a GitHub Gist (JSON store). Fal`, `Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.`, `Patch a single key in config.json on the Gist. Returns updated config.`, `Patch multiple keys at once. Returns updated config.`, `Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.` (+43 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 6`** (1 nodes): `Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 7`** (1 nodes): `Patch a single key in config.json on the Gist. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 8`** (1 nodes): `Patch multiple keys at once. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (1 nodes): `Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `Write config dict to the Gist as config.json.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (1 nodes): `Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (1 nodes): `Build the formatted daily WhatsApp message from Claude picks.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `Parse and execute a WhatsApp command string.     Sends a confirmation message ba`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `Parse command and return reply string.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `Call Claude API and parse JSON response. Raises on failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Main entry point.     Accepts screener output, enriches with news, calls Claude,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `Send an error alert via WhatsApp (unless DRY_RUN).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.544) - this node is a cross-community bridge._
- **Why does `get_config()` connect `Community 0` to `Community 2`, `Community 5`?**
  _High betweenness centrality (0.281) - this node is a cross-community bridge._
- **Why does `run_crypto_screener()` connect `Community 1` to `Community 2`?**
  _High betweenness centrality (0.244) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `get_config()` (e.g. with `_parse_and_execute()` and `health()`) actually correct?**
  _`get_config()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `main()` (e.g. with `get_config()` and `run_screener()`) actually correct?**
  _`main()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_parse_and_execute()` (e.g. with `update_config()` and `reset_config()`) actually correct?**
  _`_parse_and_execute()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `config_manager.py — Read/write agent config from a GitHub Gist (JSON store). Fal`, `Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.`, `Patch a single key in config.json on the Gist. Returns updated config.` to the rest of the system?**
  _48 weakly-connected nodes found - possible documentation gaps or missing edges._