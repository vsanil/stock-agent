# Graph Report - stock-agent  (2026-05-01)

## Corpus Check
- 11 files · ~18,482 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 223 nodes · 307 edges · 58 communities detected
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.8)
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
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]

## God Nodes (most connected - your core abstractions)
1. `_parse_and_execute()` - 22 edges
2. `load_trade_log()` - 16 edges
3. `run_morning()` - 16 edges
4. `handle_callback_query()` - 13 edges
5. `main()` - 12 edges
6. `run_confirmation()` - 11 edges
7. `get_config()` - 9 edges
8. `load_picks()` - 9 edges
9. `save_trade_log()` - 9 edges
10. `run_screener()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `open_trades()` --calls--> `save_trade_log()`  [INFERRED]
  trade_logger.py → config_manager.py
- `check_and_close_trades()` --calls--> `save_trade_log()`  [INFERRED]
  trade_logger.py → config_manager.py
- `get_performance_stats()` --calls--> `load_trade_log()`  [INFERRED]
  trade_logger.py → config_manager.py
- `_parse_and_execute()` --calls--> `get_performance_stats()`  [INFERRED]
  telegram_notifier.py → trade_logger.py
- `manual_open_trade()` --calls--> `load_trade_log()`  [INFERRED]
  trade_logger.py → config_manager.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (35): answer_callback_query(), _bot_token(), _chat_id(), _esc(), _explain_pick(), _fetch_live_price(), format_confirmation_message(), format_weekly_recap_message() (+27 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (31): _alert(), detect_run_mode(), is_market_holiday(), main(), agent.py — Main daily runner. Called by GitHub Actions cron job. Set DRY_RUN=tru, Auto-detect run mode by ET hour/weekday. Override with RUN_MODE env var., Run crypto screener with up to 5 attempts and increasing delays.     Sends a Tel, Full screener + Claude analysis + save picks + send morning message. (+23 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (29): get_config(), get_dynamic_pick_counts(), _gist_headers(), _gist_id(), _load_gist_file(), load_picks(), load_weekly_picks(), config_manager.py — Read/write agent config from a GitHub Gist (JSON store). Fal (+21 more)

### Community 3 - "Community 3"
Cohesion: 0.15
Nodes (15): handle_callback_query(), Handle inline keyboard button taps.     callback_data format:       buy|TICKER|p, cancel_trade(), get_performance_stats(), get_weekly_closed_trades(), manual_close_trade(), manual_open_trade(), trade_logger.py — Persistent trade tracking for short-term picks.  Lifecycle: (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.16
Nodes (14): get_upcoming_earnings(), earnings_checker.py — Fetch upcoming earnings dates for S&P 500 candidates.  One, Returns {ticker: "Thu May 1"} for stocks in `tickers` that report earnings     w, _get_finnhub_metrics(), get_sp500_tickers(), _long_term_score(), screener.py — S&P 500 stock screener using yfinance + pandas-ta. Returns top 5 s, Fetch S&P 500 tickers. Tries datahub.io CSV first (reliable from CI),     then W (+6 more)

### Community 5 - "Community 5"
Cohesion: 0.19
Nodes (14): analyze_with_claude(), _build_crypto_candidates(), _build_risk_profile_block(), _build_stock_candidates(), _build_user_prompt(), _call_claude(), _get_news_headlines(), ai_analyzer.py — Claude API integration for stock analysis. Accepts screener can (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.27
Nodes (11): _get_price_history(), _get_top_coins(), _long_term_score(), crypto_screener.py — Crypto screener using CoinGecko free API (no key needed). R, Two-phase crypto screening:       Phase 1 — Bulk call: filter + basic score → pi, Bulk fetch top coins by market cap. Requests sparkline but doesn't require it., Fetch hourly price history for a single coin via /coins/{id}/market_chart.     R, run_crypto_screener() (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (9): handle_incoming_command(), Parse and execute a Telegram command. Sends reply and returns reply text., health(), webhook.py — Flask app to receive inbound WhatsApp commands via CallMeBot webhoo, Receive Telegram update (message from user to bot)., Health check — returns current config., Call this once after deploying to Render to register the Telegram webhook.     e, register() (+1 more)

### Community 8 - "Community 8"
Cohesion: 0.5
Nodes (3): build_weekly_recap(), performance_tracker.py — Saturday weekly P&L recap.  Loads this week's picks fro, Returns a recap dict, or None if there are no picks this week.      Shape:     {

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Patch a single key in config.json on the Gist. Returns updated config.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): Patch multiple keys at once. Returns updated config.

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Write config dict to the Gist as config.json.

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): whatsapp.py — CallMeBot send/receive helpers + WhatsApp command parser.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Build the formatted daily WhatsApp message from Claude picks (stocks + crypto).

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Parse and execute a WhatsApp command string.     Sends a confirmation message ba

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Parse command and return reply string.

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): Health check — returns current config.

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Call this once after deploying to Render to register the Telegram webhook.     e

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Pull S&P 500 tickers from Wikipedia.

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Score a ticker for short-term trading (out of 100). Returns (score, metrics).

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Score a ticker for long-term investing (out of 100). Returns (score, metrics).

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Screen S&P 500 stocks and return top candidates.     Returns:         {

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Fetch top recent news headlines for a ticker from Finnhub free tier.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Combine short + long candidates, enrich with Finnhub news.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Format crypto screener results for the Claude prompt.

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Call Claude API and parse JSON response. Raises on failure.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Main entry point. Accepts stock screener output + optional crypto screener outpu

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Fetch top coins by market cap from CoinGecko /coins/markets.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Fetch historical OHLC-style price data for RSI/MA calculation.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Compute RSI from a list of daily closing prices.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Simple moving average over last `period` prices.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Score a coin for short-term trading (out of 100).

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Score a coin for long-term holding (out of 100).

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Screen top 100 crypto coins and return top candidates.     Returns:         {

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Send an error alert via WhatsApp (unless DRY_RUN).

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Send a Telegram message. Splits messages > 4096 chars automatically.     Retries

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Register a Telegram webhook URL (call once after deploying to Render).

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Build the formatted daily Telegram message from Claude picks (stocks + crypto).

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Parse and execute a Telegram command. Sends reply and returns reply text.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Parse command string and return reply.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Check WEBHOOK_SECRET in header or query param.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Receive inbound WhatsApp command from CallMeBot.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Health check — returns current config.

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Patch a single key in config.json on the Gist. Returns updated config.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Patch multiple keys at once. Returns updated config.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Write config dict to the Gist as config.json.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Build the formatted daily WhatsApp message from Claude picks.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Parse and execute a WhatsApp command string.     Sends a confirmation message ba

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Parse command and return reply string.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Call Claude API and parse JSON response. Raises on failure.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Main entry point.     Accepts screener output, enriches with news, calls Claude,

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Send an error alert via WhatsApp (unless DRY_RUN).

## Knowledge Gaps
- **129 isolated node(s):** `trade_logger.py — Persistent trade tracking for short-term picks.  Lifecycle:`, `Add today's short-term picks (stocks + crypto) to the open trades list.     Skip`, `Compare open trades against current prices.     Closes trades where target hit,`, `Compute all-time stats from closed trades.     Pass asset_type="stock" or "crypt`, `Log a trade the user actually placed.     If target/stop not provided, defaults` (+124 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 9`** (1 nodes): `Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `Patch a single key in config.json on the Gist. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (1 nodes): `Patch multiple keys at once. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (1 nodes): `Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `Write config dict to the Gist as config.json.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `whatsapp.py — CallMeBot send/receive helpers + WhatsApp command parser.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Build the formatted daily WhatsApp message from Claude picks (stocks + crypto).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `Parse and execute a WhatsApp command string.     Sends a confirmation message ba`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `Parse command and return reply string.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): `Health check — returns current config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `Call this once after deploying to Render to register the Telegram webhook.     e`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `Pull S&P 500 tickers from Wikipedia.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Score a ticker for short-term trading (out of 100). Returns (score, metrics).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Score a ticker for long-term investing (out of 100). Returns (score, metrics).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Screen S&P 500 stocks and return top candidates.     Returns:         {`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Fetch top recent news headlines for a ticker from Finnhub free tier.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Combine short + long candidates, enrich with Finnhub news.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `Format crypto screener results for the Claude prompt.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Call Claude API and parse JSON response. Raises on failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Main entry point. Accepts stock screener output + optional crypto screener outpu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Fetch top coins by market cap from CoinGecko /coins/markets.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Fetch historical OHLC-style price data for RSI/MA calculation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Compute RSI from a list of daily closing prices.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Simple moving average over last `period` prices.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Score a coin for short-term trading (out of 100).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Score a coin for long-term holding (out of 100).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Screen top 100 crypto coins and return top candidates.     Returns:         {`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Send an error alert via WhatsApp (unless DRY_RUN).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Send a Telegram message. Splits messages > 4096 chars automatically.     Retries`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Register a Telegram webhook URL (call once after deploying to Render).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Build the formatted daily Telegram message from Claude picks (stocks + crypto).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Parse and execute a Telegram command. Sends reply and returns reply text.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Parse command string and return reply.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Check WEBHOOK_SECRET in header or query param.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Receive inbound WhatsApp command from CallMeBot.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Health check — returns current config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Fetch config.json from GitHub Gist. Falls back to DEFAULT_CONFIG on error.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Patch a single key in config.json on the Gist. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Patch multiple keys at once. Returns updated config.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Restore config.json on the Gist to DEFAULT_CONFIG. Returns defaults.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Write config dict to the Gist as config.json.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Send a WhatsApp message via CallMeBot.     Truncates to 1500 chars. Retries up t`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Build the formatted daily WhatsApp message from Claude picks.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Parse and execute a WhatsApp command string.     Sends a confirmation message ba`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Parse command and return reply string.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Call Claude API and parse JSON response. Raises on failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Main entry point.     Accepts screener output, enriches with news, calls Claude,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Send an error alert via WhatsApp (unless DRY_RUN).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Community 1` to `Community 2`, `Community 4`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.170) - this node is a cross-community bridge._
- **Why does `run_morning()` connect `Community 1` to `Community 2`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `_parse_and_execute()` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 7`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `_parse_and_execute()` (e.g. with `load_picks()` and `get_config()`) actually correct?**
  _`_parse_and_execute()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `load_trade_log()` (e.g. with `open_trades()` and `check_and_close_trades()`) actually correct?**
  _`load_trade_log()` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `run_morning()` (e.g. with `run_screener()` and `get_dynamic_pick_counts()`) actually correct?**
  _`run_morning()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `handle_callback_query()` (e.g. with `webhook()` and `load_picks()`) actually correct?**
  _`handle_callback_query()` has 7 INFERRED edges - model-reasoned connections that need verification._