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
- **Collects** price data (yfinance), news (Alpha Vantage, Finnhub), options sentiment, and insider transactions
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
│       └── data.py           # GET /api/tickers, GET /api/status/{ticker}, POST /api/sync/{ticker}, GET /api/sync/status/{ticker}
│
├── ingestion/                # External data collection
│   ├── news/
│   │   ├── aggregator.py     # Orchestrates all news sources → ingest_all_news()
│   │   ├── alpha_vantage_news.py
│   │   ├── finnhub_news.py   # Also provides get_insider_transactions()
│   │   └── financial_juice.py
│   └── prices/
│       ├── yfinance_client.py    # OHLCV price bars → fetch_and_store()
│       └── options_sentiment.py  # get_put_call_ratio()
│
├── analysis/                 # Post-ingestion analytics
│   ├── correlator.py         # Links news articles to subsequent price moves
│   └── embedder.py           # Embeds news headlines into ChromaDB
│
├── storage/                  # Persistence layer
│   ├── database.py           # SQLAlchemy engine, init_db(), get_session()
│   ├── models.py             # ORM models: NewsArticle, PriceBar, CorrelationSnapshot
│   ├── repository.py         # All DB query functions
│   └── vector_store.py       # ChromaDB wrapper: embed_articles(), search_similar()
│
├── config/
│   └── settings.py           # Pydantic Settings — all config loaded from .env
│
├── scheduler/
│   └── jobs.py               # _sync_ticker() sync logic, run_scheduler() (CLI use only)
│
├── frontend/
│   └── index.html            # Single-file UI (no build step, vanilla JS + marked.js CDN)
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
  │     ├─ execute_tool("fetch_current_news")          → SQLite query
  │     ├─ execute_tool("search_similar_historical_events") → ChromaDB search
  │     ├─ execute_tool("get_price_history")           → SQLite query
  │     ├─ execute_tool("get_correlation_stats")       → SQLite query
  │     ├─ get_put_call_ratio(ticker)                  → yfinance options chain
  │     └─ get_insider_transactions(ticker)            → Finnhub API
  ├─ Yield {"type": "status", "content": "Analyzing with AI..."}
  ├─ Build ANALYSIS_PROMPT with all data + reply_language
  └─ LLM.stream_complete() → yield {"type": "chunk", "content": "..."} per token
       └─ yield {"type": "done"}
```

### Data Sync Pipeline
```
Trigger: scheduler (auto on startup) OR CLI sync OR POST /api/sync/{ticker}
  │
  ▼  (status tracked in api/routes/data.py:_sync_status dict)
ingestion/prices/yfinance_client.py → fetch_and_store()     → PriceBar table
ingestion/news/aggregator.py → ingest_all_news()            → NewsArticle table
  ├─ alpha_vantage_news.py  (isolated — failure logs warning, continues)
  ├─ financial_juice.py     (isolated — failure logs warning, continues)
  └─ finnhub_news.py        (isolated — failure logs warning, continues)
analysis/correlator.py → compute_correlations()             → CorrelationSnapshot table
analysis/embedder.py → embed_pending()                      → ChromaDB
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
| `_run_all_tools` | `(ticker, verbose) → dict` | Sync. Runs all 6 data tools, returns dict with keys: `news`, `similar`, `prices`, `correlation_stats`, `put_call_ratio`, `insider_transactions`. |
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

Contains `ANALYSIS_PROMPT` — the single template injected with all tool data before sending to LLM.

**Template variables:** `{ticker}`, `{reply_language}`, `{news_json}`, `{similar_json}`, `{prices_json}`, `{corr_json}`, `{pcr_json}`, `{insider_json}`

**Language control:** `reply_language` is injected at the **end** of the prompt (after all data) as a `CRITICAL INSTRUCTION`. Placing it at the end improves compliance — LLMs tend to follow the last instruction most strongly.

---

### `api/session.py`

In-memory session store. **No persistence — clears on server restart.**

```python
get_or_create(session_id: str | None) → (session_id: str, SessionEntry)
save(session_id, entry)
trim_messages(entry)   # enforces MAX_MESSAGES=20, drops oldest user+assistant pairs
```

`SessionEntry` fields: `messages: list[dict]`, `last_ticker: str | None`, `last_accessed: float`

Sessions expire after 1 hour idle (`TTL_SECONDS = 3600`).

---

### `api/routes/chat.py`

**Ticker extraction (3-stage, comparison checked first):**
1. `_extract_comparison_tickers()`: scan for 2 distinct tracked tickers → if found, route to `run_comparison_stream()` immediately, skip single-ticker logic
2. Chinese alias map: `{"苹果": "AAPL", "英伟达": "NVDA", ...}`
3. Regex `\b([A-Z]{1,5})\b` with `re.ASCII` flag (critical — without `re.ASCII`, Chinese chars count as `\w` and break `\b` boundaries)
4. Session fallback: reuse `last_ticker` if no ticker found → marks as follow-up

**Routing logic (in priority order):**
- 2 tickers detected → `run_comparison_stream()`; `entry.last_ticker` set to `None`
- Same session + same ticker reused → lightweight context prompt (no tool re-collection)
- New single ticker → full `run_query_stream()` pipeline

**Language detection:** `_detect_language()` checks for CJK characters (`\u4e00-\u9fff`) in message.

---

### `storage/vector_store.py`

Module-level singletons (`_client`, `_collection`, `_embedder`) — lazy-initialized, cached for the process lifetime.

Model: `sentence-transformers/all-MiniLM-L6-v2` (loaded from HuggingFace cache at `~/.cache/huggingface`). Pre-warmed at FastAPI startup to avoid first-request delay.

---

### `scheduler/jobs.py`

`_sync_ticker(ticker)` — incremental-aware sync: detects first run (no price data) vs incremental (overlap by 1 day).

**Important:** `run_scheduler()` uses `BlockingScheduler` — only for CLI `watch` command. The API uses `BackgroundScheduler` (non-blocking), initialized directly in `api/main.py:_start_scheduler()`.

---

## 5. API Reference

Base URL: `http://host:9999`

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves `frontend/index.html` |
| `POST` | `/api/chat` | Streaming analysis. Body: `ChatRequest`. Response: SSE stream. |
| `GET` | `/api/tickers` | Returns `list[str]` of watched tickers from settings. |
| `GET` | `/api/status/{ticker}` | Returns `TickerStatus` JSON with DB record counts and staleness. |
| `POST` | `/api/sync/{ticker}` | Queues background sync. Returns `{"status": "queued"}` immediately. If already running, returns `{"status": "already_running"}` without queuing again. |
| `GET` | `/api/sync/status/{ticker}` | Returns current sync state: `{"ticker", "status": "idle\|running\|done\|error", "started_at", "finished_at", "error"}`. State is in-memory — resets on server restart. |

### SSE Event Types (`POST /api/chat`)

All events are JSON-encoded in `data:` field:

| `type` | Timing | `content` |
|---|---|---|
| `session` | First event always | `""` — `session_id` field carries the ID |
| `status` | During pipeline | Human-readable progress string |
| `chunk` | During LLM streaming | Partial text to append to bubble |
| `chart` | After last chunk, before `done` | JSON string — chart payload `{mode, tickers, prices, sentiment}`; frontend calls `renderCharts()` |
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

`frontend/index.html` — single file, no build step, no npm.

**Dependencies (CDN):**
- `marked.js` — markdown rendering of LLM analysis output

**SSE Parsing:**
Uses `fetch()` + `ReadableStream` (not `EventSource`) because SSE over POST is not supported by the native `EventSource` API.

**Critical:** `sse-starlette` sends `\r\n\r\n` as event boundaries. The frontend normalizes `\r\n` → `\n` before splitting on `\n\n`. Do not remove this normalization step.

**Session management:** `session_id` received in the first `type=session` event is stored in a JS variable and sent back with every subsequent request.

**Sidebar (ticker list):**
Each ticker row shows: `[ticker name] [last sync date] [⟳ sync button]`.
- Date is fetched from `GET /api/status/{ticker}` on page load; red if `days_stale >= 1`, "未同步" (red) if never synced.
- Clicking ⟳ calls `POST /api/sync/{ticker}`, then polls `GET /api/sync/status/{ticker}` every 2s until `status != "running"`, then refreshes the date display.
- Sync button shows a CSS spin animation while running.

**Chart rendering (`renderCharts(msgEl, chartData)`):**
Called when a `type: "chart"` SSE event arrives. Appends a `.chart-wrap` div as a sibling to the text bubble (so `done`'s markdown re-render doesn't overwrite charts).
- `mode: "single"` → two Chart.js canvases: 14-day close price (line, filled) + 7-day sentiment (bar, green/red by sign)
- `mode: "comparison"` → two Chart.js canvases: normalized % change from day 1 (two lines) + side-by-side daily sentiment bars
- Uses Chart.js 4 from CDN (`chart.umd.min.js`). No build step.

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
| Sync fails silently when one news source is down | Any exception in `ingest_all_news()` propagated upward | Each source wrapped in `_safe_fetch()` — failure logs a warning and returns 0, others continue |
| Sync status lost after server restart | `_sync_status` is in-memory only | Expected behavior; use `GET /api/status/{ticker}` (DB-backed) for persistent data freshness info |
