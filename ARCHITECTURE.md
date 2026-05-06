# Stock Analysis Agent — Architecture & Developer Reference

> This document is the single source of truth for developers (human or AI) continuing development of this project. Read this before touching any code.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Data Flow](#3-data-flow)
4. [Module Reference](#4-module-reference)
5. [API Reference](#5-api-reference)
6. [Configuration Reference](#6-configuration-reference)
7. [Database Schema](#7-database-schema)
8. [LLM Backends](#8-llm-backends)
9. [Frontend](#9-frontend)
10. [CLI Reference](#10-cli-reference)
11. [Deployment](#11-deployment)
12. [Known Quirks & Gotchas](#12-known-quirks--gotchas)

---

## 1. Project Overview

A stock trend analysis system that:
- **Collects** price data (yfinance), news (Alpha Vantage, Finnhub), options sentiment, insider transactions, fundamental data (Finnhub), and options market structure (Max Pain + GEX via yfinance)
- **Stores** everything in SQLite + ChromaDB (vector search)
- **Analyzes** via a single-turn LLM call with all data pre-collected (no multi-turn agentic loop)
- **Serves** analysis through a FastAPI backend with SSE streaming
- **Displays** results in a single-file ChatGPT-style web UI

**Key architectural principle:** Python collects all data first, then sends one consolidated prompt to the LLM. This avoids multi-turn context accumulation issues with stateless LLM backends (Zoom AI, Qwen).

---

## 2. Directory Structure

```
stock/
├── agent/                    # LLM orchestration layer
│   ├── agent.py              # Main entry: _run_all_tools(), run_query(), run_query_stream()
│   ├── zoom_client.py        # Zoom AI Agent SSE client (also defines TextBlock, LLMResponse)
│   ├── tool_executor.py      # Tool dispatcher: execute_tool(name, input) → JSON string
│   ├── tools.py              # Tool schemas (for LLM tool-calling, not currently used in API path)
│   └── prompts.py            # ANALYSIS_PROMPT template
│
├── api/                      # FastAPI web backend
│   ├── main.py               # App factory, CORS, startup hooks, scheduler init
│   ├── models.py             # Pydantic models: ChatRequest, ChatChunk, TickerStatus
│   ├── session.py            # In-memory session store (TTL 1h, max 20 msgs)
│   └── routes/
│       ├── chat.py           # POST /api/chat → SSE stream
│       ├── data.py           # GET /api/tickers, GET /api/status/{ticker}, POST /api/sync/{ticker}, GET /api/sync/status/{ticker}
│       └── sessions.py       # GET/POST/PATCH/DELETE /api/sessions[/{id}], GET /api/sessions/{id}/messages
│
├── ingestion/                # External data collection
│   ├── news/
│   │   ├── aggregator.py     # Orchestrates all news sources → ingest_all_news()
│   │   ├── alpha_vantage_news.py
│   │   ├── finnhub_news.py   # Also provides get_insider_transactions()
│   │   └── financial_juice.py
│   ├── prices/
│   │   ├── yfinance_client.py    # OHLCV price bars → fetch_and_store()
│   │   ├── options_sentiment.py  # get_put_call_ratio() (6h cache)
│   │   └── options_structure.py  # get_options_structure() → Max Pain + GEX (1h cache)
│   └── fundamentals/
│       ├── __init__.py
│       └── finnhub_fundamentals.py  # fetch_and_store() → FundamentalSnapshot
│
├── analysis/                 # Post-ingestion analytics
│   ├── correlator.py         # Links news articles to subsequent price moves
│   └── embedder.py           # Embeds news headlines into ChromaDB
│
├── storage/                  # Persistence layer
│   ├── database.py           # SQLAlchemy engine, init_db(), get_session()
│   ├── models.py             # ORM models: NewsArticle, PriceBar, CorrelationSnapshot, FundamentalSnapshot
│   ├── repository.py         # All DB query functions
│   └── vector_store.py       # ChromaDB wrapper: embed_articles(), search_similar()
│
├── config/
│   └── settings.py           # Pydantic Settings — all config loaded from .env
│
├── scheduler/
│   └── jobs.py               # _sync_ticker() sync logic, run_scheduler() (CLI use only)
│
├── frontend/                 # Vite + Vue 3 + TypeScript + Tailwind SPA
│   ├── package.json
│   ├── vite.config.ts        # Dev server proxies /api → :9999
│   ├── index.html            # Vite entry (mounts <div id="app"/>)
│   ├── src/
│   │   ├── main.ts           # createApp + Pinia
│   │   ├── App.vue           # Sidebar + ChatPanel layout
│   │   ├── style.css         # Tailwind directives + markdown styles
│   │   ├── api/client.ts     # REST wrapper (tickers, status, sync)
│   │   ├── stores/           # Pinia: tickers.ts, chat.ts
│   │   ├── composables/      # useSSE.ts (POST + ReadableStream parser)
│   │   ├── components/       # Sidebar, ChatPanel, MessageBubble, Charts, InputBox
│   │   └── types/index.ts    # SSEEvent, ChatMessage, ChartPayload, etc.
│   └── dist/                 # Build output (gitignored, served by FastAPI)
│
├── cli.py                    # Click CLI: query / sync / ingest / status / watch
├── start.sh                  # Ubuntu one-shot startup script
└── pyproject.toml            # Dependencies
```

---

## 3. Data Flow

### Analysis Request (API path)
```
Browser POST /api/chat  {"message": "AAPL趋势怎么样", "session_id": null}
  │
  ▼
api/routes/chat.py
  ├─ Extract ticker from message (alias map → regex → session fallback)
  ├─ Detect reply language (Chinese/English) from message
  ├─ Yield SSE: {"type": "session", "session_id": "..."}
  │
  ▼
agent/agent.py: run_query_stream(ticker, reply_language)
  ├─ Yield {"type": "status", "content": "Collecting market data..."}
  ├─ run_in_executor → _run_all_tools(ticker)          ← sync, runs in thread pool
  │     ├─ [serial] execute_tool("fetch_current_news")          → SQLite query
  │     └─ [parallel, 7 workers via ThreadPoolExecutor]
  │           ├─ execute_tool("search_similar_historical_events") → ChromaDB
  │           ├─ execute_tool("get_price_history")               → SQLite
  │           ├─ execute_tool("get_correlation_stats")           → SQLite
  │           ├─ get_put_call_ratio(ticker)                      → yfinance options chain
  │           ├─ get_insider_transactions(ticker)                → Finnhub API
  │           ├─ get_latest_fundamentals(ticker)                 → SQLite (FundamentalSnapshot)
  │           └─ get_options_structure(ticker)                   → yfinance option_chain (Max Pain + GEX)
  ├─ Yield {"type": "status", "content": "Analyzing with AI..."}
  ├─ Build ANALYSIS_PROMPT with all data + reply_language
  └─ LLM.stream_complete() → yield {"type": "chunk", "content": "..."} per token
       └─ yield {"type": "done"}
```

### Data Sync Pipeline
```
Trigger: scheduler (auto on startup) OR CLI sync OR POST /api/sync/{ticker}
  │
  ▼  (status tracked in api/routes/data.py:_sync_status dict when via API)
ingestion/prices/yfinance_client.py → fetch_and_store()     → PriceBar table
ingestion/news/aggregator.py → ingest_all_news()            → NewsArticle table
  ├─ alpha_vantage_news.py  (isolated — failure logs warning, continues)
  ├─ financial_juice.py     (isolated — failure logs warning, continues)
  └─ finnhub_news.py        (isolated — failure logs warning, continues)
analysis/correlator.py → compute_correlations()             → CorrelationSnapshot table
analysis/embedder.py → embed_pending()                      → ChromaDB
ingestion/fundamentals/finnhub_fundamentals.py → fetch_and_store() → FundamentalSnapshot table
  ├─ /stock/metric?metric=all    → valuation, profitability, growth, health, market metrics
  ├─ /stock/recommendation       → analyst buy/hold/sell counts
  ├─ /stock/price-target         → mean/high/low price targets
  ├─ /stock/earnings             → EPS actual/estimate/surprise (most recent quarter)
  └─ /calendar/earnings          → next earnings date (next 90 days)
```

---

## 4. Module Reference

### `agent/agent.py`

**Public functions:**

| Function | Signature | Description |
|---|---|---|
| `run_query` | `(ticker: str, verbose: bool) → str` | Sync wrapper for CLI use. Calls `asyncio.run()`. Do NOT call from async context. |
| `run_query_stream` | `async gen (ticker, verbose, reply_language)` | Single-ticker async generator. Yields `status` → `chunks` → `chart` → `done`. Guards against missing data: yields `error` and returns if no price data exists. |
| `run_comparison_stream` | `async gen (ticker_a, ticker_b, verbose, reply_language)` | Two-ticker comparison. Collects both tickers' data in parallel via `asyncio.gather`, then streams `COMPARISON_PROMPT` to LLM. Yields same event types as `run_query_stream`. |
| `_run_all_tools` | `(ticker, verbose) → dict` | Cache wrapper (20-min TTL, key = ticker). Returns cached result on hit; calls `_collect_tools` on miss and stores result. |
| `_collect_tools` | `(ticker, verbose) → dict` | Actual data collection: news fetched first (serial), then 7 tasks run in parallel via `ThreadPoolExecutor(max_workers=7)`: similar search, prices, corr stats, PCR, insider, fundamentals, options structure. |
| `invalidate_tools_cache` | `(ticker) → None` | Removes ticker's entry from `_tools_cache`. Called by `data.py` when sync completes so the next analysis sees fresh data. |
| `_build_chart_data` | `(ticker, tool_data) → dict` | Builds single-ticker chart payload: `{mode: "single", tickers, prices: {ticker: [{date, close}]}, sentiment: {ticker: [{date, avg_score, count}]}}`. Calls `get_daily_sentiment()` for 7-day sentiment. |
| `_build_comparison_chart_data` | `(ticker_a, ticker_b, data_a, data_b) → dict` | Builds comparison chart payload: `{mode: "comparison", tickers, prices: {...}, sentiment: {...}}`. Frontend normalizes prices to % change from day 1. |
| `_build_llm_client` | `() → adapter` | Factory. Reads `LLM_BACKEND` env var, returns `ZoomLLMClient`, `_AnthropicAdapter`, or `_AliyunAdapter`. |

**LLM Adapters (private):**

| Class | Backend | Notes |
|---|---|---|
| `ZoomLLMClient` | Zoom AI Agent | Defined in `zoom_client.py`. Uses SSE streaming. `verify=False` (corporate SSL). |
| `_AnthropicAdapter` | Anthropic Claude | `stream_complete()` is a fallback — calls `complete()` and yields full text as one chunk. |
| `_AliyunAdapter` | DashScope / qwen-plus | OpenAI-compatible. Uses `httpx.AsyncClient(verify=False)` for SSL issues. Model hardcoded as `qwen-plus`. |

All adapters must implement:
- `async complete(messages, system_prompt, tools) → LLMResponse`
- `async stream_complete(messages, system_prompt, tools)` → async generator yielding `str` chunks

---

### `agent/zoom_client.py`

Standalone Zoom AI Agent client. Also defines shared response types used project-wide:

```python
@dataclass class TextBlock:    type="text",  text: str
@dataclass class ToolUseBlock: type="tool_use", id, name, input
@dataclass class LLMResponse:  stop_reason: str, content: list[TextBlock|ToolUseBlock]
```

`_build_question()` — converts OpenAI-style messages list to a single Zoom question string.

---

### `agent/prompts.py`

Contains `ANALYSIS_PROMPT` and `COMPARISON_PROMPT` — templates injected with all tool data before sending to LLM.

**`ANALYSIS_PROMPT` template variables:** `{ticker}`, `{reply_language}`, `{news_json}`, `{similar_json}`, `{prices_json}`, `{corr_json}`, `{fundamentals_json}`, `{pcr_json}`, `{options_structure_json}`, `{insider_json}`

**Analysis output sections (in order):** Fundamental Snapshot → Current News Summary → Options Market Signal (PCR + Max Pain + GEX) → Insider Activity → Historical Analogues → Price Momentum → Trend Inference → Caveats

**`COMPARISON_PROMPT` template variables:** `{ticker_a}`, `{ticker_b}`, `{reply_language}`, `{news_a/b_json}`, `{prices_a/b_json}`, `{corr_a/b_json}`, `{pcr_a/b_json}`, `{insider_a/b_json}`

**Language control:** `reply_language` is injected at the **end** of the prompt (after all data) as a `CRITICAL INSTRUCTION`. Placing it at the end improves compliance — LLMs tend to follow the last instruction most strongly.

---

### `api/session.py`

DB-backed session store (PR 2). Backed by `chat_sessions` + `chat_messages`.

```python
get_or_create(session_id: str | None) → (session_id: str, SessionEntry)
save(entry)                                 # bumps last_active_at + persists last_ticker
append_message(entry, role, content, ...)   # writes to DB AND mutates entry.messages
trim_messages(entry)                        # caps PROMPT_CONTEXT_WINDOW=20 in-memory
update_title_from_first_message(entry, msg) # auto-titles new sessions on first user msg
```

`SessionEntry` fields: `id: str`, `messages: list[dict]`, `last_ticker: str | None`.

Sessions never expire — they live in the DB indefinitely until the user
archives or deletes them via the history rail. The in-memory `messages` list
is only the working window for the LLM prompt; the DB always has the full
log via `list_chat_messages(session_id)`.

---

### `api/routes/chat.py`

**Ticker extraction (3-stage, comparison checked first):**
1. `_extract_comparison_tickers()`: scan for 2 distinct tracked tickers → if found, route to `run_comparison_stream()` immediately, skip single-ticker logic
2. Chinese alias map: `{"苹果": "AAPL", "英伟达": "NVDA", ...}`
3. Regex `\b([A-Z]{1,5})\b` with `re.ASCII` flag (critical — without `re.ASCII`, Chinese chars count as `\w` and break `\b` boundaries)
4. Session fallback: reuse `last_ticker` if no ticker found → marks as follow-up

**Routing logic (in priority order):**
- 2 registered tickers detected → `run_comparison_stream()`; `entry.last_ticker = None`
- Single unregistered candidate → validate via `validate_ticker()`; if valid, register + schedule + fire-and-forget sync, return "采集中" message; if invalid, return error
- Same session + same registered ticker reused → lightweight context prompt (no tool re-collection)
- New registered ticker → full `run_query_stream()` pipeline

**Dynamic ticker registration:** unknown tickers detected in chat go through `validate_ticker()` (yfinance 5-day history check, ~1s). Valid ones are inserted into `registered_tickers` and added to the live scheduler via `api.main.add_ticker_to_scheduler()`. Comparison flow only triggers on already-registered tickers — first-time registration is single-ticker only.

**Language detection:** `_detect_language()` checks for CJK characters (`\u4e00-\u9fff`) in message.

---

### `storage/vector_store.py`

Module-level singletons (`_client`, `_collection`, `_embedder`) — lazy-initialized, cached for the process lifetime.

Model: `sentence-transformers/all-MiniLM-L6-v2` (loaded from HuggingFace cache at `~/.cache/huggingface`). Pre-warmed at FastAPI startup to avoid first-request delay.

---

### `ingestion/fundamentals/finnhub_fundamentals.py`

`fetch_and_store(ticker: str) → bool` — fetches comprehensive fundamental data from 5 Finnhub endpoints and upserts a `FundamentalSnapshot` row.

| Endpoint | Data |
|---|---|
| `/stock/metric?metric=all` | Valuation, profitability, growth, health, market metrics (via `metrics["metric"]` dict) |
| `/stock/recommendation` | Analyst buy/hold/sell/strong_buy/strong_sell counts (most recent period) |
| `/stock/price-target` | Mean/high/low analyst price targets |
| `/stock/earnings?limit=4` | EPS actual/estimate for most recent quarter; computes `eps_surprise_pct` |
| `/calendar/earnings?from=today&to=today+90d` | Next earnings release date |

Called automatically at the end of every `_run_sync()` (API and CLI sync).

---

### `ingestion/prices/options_structure.py`

`get_options_structure(ticker: str) → dict` — calculates Max Pain and Gamma Exposure for the nearest 2 option expirations using yfinance `option_chain()`. Results cached 1 hour (`_options_cache`, TTL = 3600s).

**Calculations:**
- **Max Pain:** For each candidate strike K, compute `Σ max(K-s,0)·callOI(s) + Σ max(s-K,0)·putOI(s)` across all strikes. Min K = Max Pain.
- **GEX (Gamma Exposure):** `Σ(gamma·OI·100·spot)` for calls minus puts. `net_gex > 0` → MMs are long gamma → STABILIZING (dampens moves). `net_gex < 0` → MMs short gamma → AMPLIFYING (accelerates moves).
- **Key levels:** Top-3 call gamma strikes (overhead resistance) and top-3 put gamma strikes (downside support).

Returns: `{ticker, spot_price, nearest_expiration: {expiration, max_pain, max_pain_distance_pct, gex_available, net_gex_millions, gex_signal, top_call_gamma_strikes, top_put_gamma_strikes}, second_expiration: {...}, summary: str}`

---

### `scheduler/jobs.py`

`_sync_ticker(ticker)` — incremental-aware sync: detects first run (no price data) vs incremental (overlap by 1 day). Runs: prices → news → correlations → embeddings → fundamentals. Same pipeline as `api/routes/data._run_sync()`.

**Important:** `run_scheduler()` uses `BlockingScheduler` — only for CLI `watch` command. The API uses `BackgroundScheduler` (non-blocking), initialized directly in `api/main.py:_start_scheduler()`.

---

## 5. API Reference

Base URL: `http://host:9999`

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves `frontend/index.html` |
| `POST` | `/api/chat` | Streaming analysis. Body: `ChatRequest`. Response: SSE stream. |
| `GET` | `/api/tickers` | Returns `list[str]` of registered tickers from the `registered_tickers` table (DB-backed, not from `.env`). |
| `GET` | `/api/status/{ticker}` | Returns `TickerStatus` JSON. 404 if ticker is not registered. |
| `POST` | `/api/sync/{ticker}` | Queues background sync. 404 if not registered. If already running, returns `{"status": "already_running"}`. |
| `GET` | `/api/sync/status/{ticker}` | Returns current sync state. 404 if not registered. State is in-memory — resets on server restart. |
| `GET` | `/api/sessions` | List chat sessions ordered by `last_active_at desc`. `?include_archived=true` to include archived. |
| `POST` | `/api/sessions` | Create a new session. Body: `{title?: string}`. Returns the created row. |
| `GET` | `/api/sessions/{id}` | Single session metadata. 404 if not found. |
| `PATCH` | `/api/sessions/{id}` | Body: `{title?, archived?}`. Updates the session and returns it. 404 if not found. |
| `DELETE` | `/api/sessions/{id}` | Hard-delete the session and all its messages. |
| `GET` | `/api/sessions/{id}/messages` | Returns the persisted message log (oldest first). 404 if session missing. |

### SSE Event Types (`POST /api/chat`)

All events are JSON-encoded in `data:` field:

| `type` | Timing | `content` |
|---|---|---|
| `session` | First event always | `""` — `session_id` field carries the ID |
| `status` | During pipeline | Human-readable progress string |
| `chunk` | During LLM streaming | Partial text to append to bubble |
| `chart` | After last chunk, before `done` | JSON string — chart payload `{mode, tickers, prices, sentiment}`; frontend calls `renderCharts()` |
| `ticker_registered` | When a new ticker is auto-registered via chat (before `chunk`) | The ticker symbol — frontend appends a sidebar row and starts polling sync status |
| `done` | Final event | `""` — triggers final markdown re-render |
| `error` | On any failure | Error message string |

### `ChatRequest` body
```json
{"message": "AAPL趋势怎么样", "session_id": null}
```
Pass `session_id` from previous `session` event to maintain conversation context.

---

## 6. Configuration Reference

All config via `.env` file (loaded by Pydantic Settings):

| Variable | Default | Description |
|---|---|---|
| `WATCHED_TICKERS` | `"AAPL"` | Comma-separated tickers, e.g. `"AAPL,NVDA,TSLA"` |
| `LLM_BACKEND` | `"zoom"` | `"zoom"` / `"anthropic"` / `"aliyun"` |
| `ALIYUN_API_KEY` | `""` | DashScope API key (when `LLM_BACKEND=aliyun`) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (when `LLM_BACKEND=anthropic`) |
| `ZOOM_TOKEN` | `""` | Zoom personal access token |
| `ZOOM_AGENT_ID` | `""` | Zoom AI Agent ID |
| `ZOOM_BASE_URL` | `"https://eng.corp.zoom.com"` | Zoom API base URL |
| `ALPHA_VANTAGE_API_KEY` | `""` | Alpha Vantage news API key |
| `FINNHUB_API_KEY` | `""` | Finnhub news + insider data API key |
| `LOG_LEVEL` | `"INFO"` | `DEBUG` / `INFO` / `WARNING` |
| `SYNC_CRON` | `"0 18 * * 1-5"` | Cron for auto-sync (weekdays 18:00) |
| `DB_PATH` | `data/stock.db` | SQLite file path |
| `CHROMA_PATH` | `data/chroma` | ChromaDB directory path |

---

## 7. Database Schema

SQLite at `data/stock.db`. Managed by SQLAlchemy.

### `news_articles`
| Column | Type | Notes |
|---|---|---|
| `id` | String PK | SHA256 of URL (dedup key) |
| `ticker` | String | Uppercase |
| `headline` | String | |
| `summary` | Text | |
| `source` | String | `"alpha_vantage"` / `"finnhub"` |
| `url` | String | |
| `published_at` | DateTime | UTC |
| `sentiment_score` | Float | −1.0 to +1.0 |
| `sentiment_label` | String | `"Bullish"` / `"Bearish"` / `"Neutral"` |
| `embedded` | Integer | 0 = not in ChromaDB, 1 = embedded |

Index: `(ticker, published_at)`

### `price_bars`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `ticker` | String | |
| `timestamp` | DateTime | UTC |
| `open/high/low/close` | Float | |
| `volume` | BigInteger | |
| `interval` | String | `"1d"` or `"1h"` |
| `source` | String | `"yfinance"` |

Unique constraint: `(ticker, timestamp, interval)`

### `correlation_snapshots`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `ticker` | String | |
| `news_id` | String | FK → `news_articles.id` |
| `price_change_1h/4h/1d` | Float | % change after article published |
| `direction` | String | `"up"` / `"down"` / `"flat"` |
| `magnitude` | Float | Absolute % change |

Unique constraint: `(ticker, news_id)`

### `chat_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | String(36) PK | UUID4 |
| `title` | String(200) | Auto-set from first user message; user-renamable |
| `archived` | Integer | 0 or 1; archived rows hidden from default list |
| `last_ticker` | String(10) | Carried across follow-ups (replaces in-memory state) |
| `created_at` | DateTime | UTC |
| `last_active_at` | DateTime | Bumped on every save; drives sort order |

Index: `(archived, last_active_at)` for the default-list query.

### `chat_messages`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `session_id` | String(36) | FK → `chat_sessions.id` (no ON DELETE; we cascade in repo) |
| `role` | String(10) | `'user'` or `'assistant'` |
| `content` | Text | Plain text or markdown |
| `chart_json` | Text | Optional serialized `ChartPayload` (for assistant messages) |
| `created_at` | DateTime | UTC |

Index: `(session_id, created_at)` for in-order replay.

### `registered_tickers`

| Column | Type | Notes |
|---|---|---|
| `ticker` | String(10) PK | Uppercase |
| `registered_at` | DateTime | UTC |
| `source` | String(20) | `"env"` (bootstrapped from `WATCHED_TICKERS`) or `"user"` (added via chat) |

Drives `GET /api/tickers`, `_start_scheduler()`, and the comparison/registration logic in `chat.py`. `.env` is treated as a seed list — at startup, every ticker in `settings.ticker_list` is `INSERT OR IGNORE`-ed into this table; thereafter the table is the source of truth.

### `fundamental_snapshots`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `ticker` | String | Uppercase |
| `fetched_at` | DateTime | UTC, time of Finnhub fetch |
| `pe_ttm` | Float | Trailing P/E ratio |
| `pb_quarterly` | Float | Price-to-book (quarterly) |
| `ps_ttm` | Float | Price-to-sales (TTM) |
| `ev_ebitda_ttm` | Float | EV/EBITDA (TTM) |
| `dividend_yield` | Float | Annual dividend yield |
| `roe_ttm` | Float | Return on equity (TTM) |
| `roa_ttm` | Float | Return on assets (TTM) |
| `gross_margin_ttm` | Float | Gross profit margin (TTM) |
| `operating_margin_ttm` | Float | Operating margin (TTM) |
| `net_margin_ttm` | Float | Net profit margin (TTM) |
| `revenue_growth_yoy` | Float | Revenue growth YoY % |
| `eps_growth_yoy` | Float | EPS growth YoY % |
| `revenue_growth_3y` | Float | Revenue CAGR 3-year |
| `eps_growth_3y` | Float | EPS CAGR 3-year |
| `current_ratio` | Float | Liquidity ratio |
| `debt_to_equity` | Float | Leverage ratio |
| `free_cash_flow_ttm` | Float | FCF trailing 12 months (USD) |
| `week_52_high/low` | Float | 52-week price range |
| `beta` | Float | Market beta |
| `market_cap` | Float | Market cap (USD) |
| `analyst_strong_buy/buy/hold/sell/strong_sell` | Integer | Analyst recommendation counts |
| `analyst_target_mean/high/low` | Float | Analyst price targets |
| `eps_actual/estimate` | Float | Most recent quarterly EPS |
| `eps_surprise_pct` | Float | `(actual - estimate) / abs(estimate) * 100` |
| `next_earnings_date` | String(20) | ISO date of next earnings release |

Index: `(ticker, fetched_at)`

---

## 8. LLM Backends

### Adding a New Backend

1. Create a new adapter class in `agent/agent.py` following this interface:
```python
class _MyAdapter:
    async def complete(self, messages: list[dict], system_prompt: str, tools: list) -> LLMResponse:
        ...
    async def stream_complete(self, messages: list[dict], system_prompt: str = "", tools=None):
        # async generator — yield str chunks
        yield chunk
```

2. Add a branch in `_build_llm_client()`:
```python
elif backend == "mybackend":
    return _MyAdapter(...)
```

3. Add the required env var(s) to `config/settings.py` and `.env.example`.

### SSL Notes
Both Zoom and Aliyun backends use `verify=False` in their HTTP clients due to corporate/internal SSL certificate issues. Do not remove this.

---

## 9. Frontend

Vite + Vue 3 + TypeScript + Tailwind SPA under `frontend/`. Built artefacts in `frontend/dist/` are served by FastAPI; the dev server (`npm run dev`) proxies `/api` to the FastAPI backend on port 9999.

**Layout:** three columns — left ticker sidebar, center chat panel, right
session history rail (PR 2). The history rail lists past conversations, lets
the user create new / archive / delete / rename sessions; clicking a row
hydrates the chat panel from `/api/sessions/{id}/messages`.

**State:** Pinia. Three stores:
- `stores/tickers.ts` — sidebar state (one row per registered ticker, sync polling timers, register-on-the-fly via SSE).
- `stores/chat.ts` — active `session_id`, in-memory message log, streaming flag, hydrate-from-DB.
- `stores/sessions.ts` — history rail list, `activeId` (persisted in `localStorage`), archive/delete/rename actions.

**SSE parsing (`composables/useSSE.ts`):**
Uses `fetch()` + `ReadableStream` (not `EventSource`) because SSE over POST isn't supported by the native EventSource API.

**Critical:** `sse-starlette` sends `\r\n\r\n` as event boundaries. The composable normalises `\r\n` → `\n` before splitting on `\n\n`. Do not remove this normalisation.

Event handling matches the API's SSE event types one-for-one (`session`, `status`, `chunk`, `chart`, `ticker_registered`, `done`, `error`); each updates the active assistant message or the tickers store.

**Sidebar (`components/Sidebar.vue`):**
Each ticker row shows `[ticker] [last sync date / "同步中"] [⟳ sync button]`.
- Date pulled from `GET /api/status/{ticker}` on first load; red if `days_stale >= 1`, "未同步" (red) if never synced.
- Clicking ⟳ calls `POST /api/sync/{ticker}`, then polls `GET /api/sync/status/{ticker}` every 2 s until `status != "running"`, then re-fetches `/api/status/{ticker}` to refresh the date.
- Spin animation (`@keyframes spin`) while running.

**Chart rendering (`components/Charts.vue`):**
Renders inline below an assistant bubble whenever the message has a `chart` payload. Two `<canvas>`es (price + sentiment); destroyed/recreated on prop change.
- `mode: "single"` → 14-day close price (filled line) + 7-day sentiment (bars; green if positive, red if negative).
- `mode: "comparison"` → normalised % change from day 1 (multi-line) + side-by-side sentiment bars.
- Uses `chart.js` from npm (no CDN).

**Markdown:** `marked` (npm) — `MessageBubble.vue` calls `marked.parse(rawText)` and renders into a `.bubble-md` container. Status placeholders (the italic "Collecting market data…" line) live in the bubble's wrapper, not inside the markdown body, so re-renders don't clobber them.

---

## 10. CLI Reference

```bash
# Run AI analysis (sync, blocks until complete)
python cli.py query AAPL
python cli.py query AAPL --verbose

# Smart incremental sync (detects first run vs incremental automatically)
python cli.py sync
python cli.py sync AAPL NVDA
python cli.py sync --full          # force 90-day re-fetch

# Force full historical re-fetch
python cli.py ingest AAPL --days 90

# Show DB stats for a ticker
python cli.py status AAPL

# Start blocking background scheduler (CLI-only, use API scheduler for web)
python cli.py watch
python cli.py watch AAPL NVDA --cron "0 9 * * *"
```

---

## 11. Deployment

### Start (Ubuntu)
```bash
bash start.sh            # auto-creates venv, installs deps, starts uvicorn on port 9999
PORT=8080 bash start.sh  # custom port
```

`start.sh` skips `pip install` if `pyproject.toml` md5 hash hasn't changed since last run (stored in `.venv/.deps_installed`).

### Manual start
```bash
.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 9999
```

### What happens on startup
1. `init_db()` — creates SQLite tables if they don't exist
2. `_get_embedder()` — pre-loads sentence-transformers model into RAM
3. `_start_scheduler()` — starts `BackgroundScheduler` with cron from `SYNC_CRON`

---

## 12. Known Quirks & Gotchas

| Issue | Root Cause | Fix Applied |
|---|---|---|
| Ticker regex fails on `AAPL趋势` | Python `re` treats Chinese chars as `\w` by default, breaking `\b` | Use `re.ASCII` flag |
| SSE events not parsed by frontend | `sse-starlette` uses `\r\n\r\n`, frontend split on `\n\n` | Normalize `\r\n→\n` before split |
| LLM replies in English despite Chinese question | Language instruction in system prompt overridden by English template content | Inject `reply_language` at END of user prompt as `CRITICAL INSTRUCTION` |
| SSL errors to DashScope/Zoom | Corporate network intercepts TLS | `verify=False` on all HTTP clients |
| `run_query()` cannot be called from async context | Uses `asyncio.run()` internally | Only call from CLI. Use `run_query_stream()` from API routes |
| `_run_all_tools()` blocks event loop | All tool functions are synchronous SQLite/HTTP calls | Always wrap in `loop.run_in_executor(None, ...)` |
| Embedding model reloads on every request | Lazy init — first request triggers load | Pre-warm via `_get_embedder()` in FastAPI startup |
| `start.sh` exits silently with no error | `set -e` + `[ -z "$val" ] && cmd` returns 1 when val is set | Use `if [ -z ]; then fi` in bash functions |
| SFTP file transfers reset mtime | PyCharm SFTP doesn't preserve timestamps | Use md5 hash comparison instead of mtime for dep check |
| LLM hallucinates data for unsynced tickers | `_run_all_tools()` returns empty arrays; LLM fills gaps with invented data | `run_query_stream()` now checks `get_latest_price_date()` first and yields `type=error` if None |
| Tools cache serves stale data after sync | 20-min TTL survives sync completion | `invalidate_tools_cache(ticker)` called in `_run_sync_tracked` immediately after sync finishes |
| Sync fails silently when one news source is down | Any exception in `ingest_all_news()` propagated upward | Each source wrapped in `_safe_fetch()` — failure logs a warning and returns 0, others continue |
| Sync status lost after server restart | `_sync_status` is in-memory only | Expected behavior; use `GET /api/status/{ticker}` (DB-backed) for persistent data freshness info |
| Asking about an unregistered ticker used to error out | `_extract_ticker` filtered by `settings.ticker_list` | Replaced with `_resolve_ticker()` returning `(ticker, is_registered)`; unregistered candidates go through `validate_ticker()` (yfinance) and are auto-registered if valid |
| New ticker added at runtime not picked up by scheduler | Scheduler iterated tickers once at startup | Scheduler instance now module-global in `api/main.py`; `add_ticker_to_scheduler()` exposed for runtime job registration |
