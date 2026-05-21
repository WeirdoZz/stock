# Stock Analysis Agent — 技术栈参考

> 本文档说明项目各层使用的技术选型及选择原因，供开发者快速了解依赖关系。

---

## 总览

| 层级 | 技术 | 版本要求 |
|---|---|---|
| 语言 | Python | 3.11+ |
| Web 框架 | FastAPI | ≥ 0.111 |
| ASGI 服务器 | Uvicorn | ≥ 0.30 |
| 关系数据库 | SQLite + SQLAlchemy | ≥ 2.0 |
| 向量数据库 | ChromaDB | ≥ 0.5 |
| 嵌入模型 | sentence-transformers | ≥ 3.0 |
| LLM 接入 | Zoom AI / Anthropic / Aliyun DashScope | — |
| 数据采集 | yfinance, Alpha Vantage API, Finnhub API | — |
| 前端 | Vue 3 + Vite + TypeScript + Tailwind | Pinia 状态 + Vue Router 4（hash 模式） |
| 图表 | Chart.js 4 | npm 安装，按需注册 |
| 定时任务 | APScheduler | ≥ 3.10 |

---

## 后端框架

### FastAPI
- **用途：** HTTP API 层，挂载所有路由和静态文件
- **SSE 流式输出：** 依赖 `sse-starlette`（`EventSourceResponse`），用于将 LLM token 实时推送到浏览器
- **为什么不用 Flask/Django：** FastAPI 原生支持 `async`，可与 async LLM 客户端直接集成而不阻塞事件循环

### Uvicorn
- **用途：** ASGI 服务器，生产环境用 `exec uvicorn` 直接替换 shell 进程
- **Workers：** 默认 1（`WORKERS` 环境变量可调），多 worker 时 `_sync_status` in-memory 状态不共享（已知限制）

---

## 数据存储

### SQLite + SQLAlchemy ORM
- **用途：** 存储结构化数据（价格、新闻、相关性快照、基本面、ticker 注册、聊天会话）
- **文件路径：** `data/stock.db`（`DB_PATH` 可配置）
- **表：** `news_articles`、`price_bars`、`correlation_snapshots`、`fundamental_snapshots`、`registered_tickers`、`chat_sessions`、`chat_messages`
- **连接池：** `pool_size=5, max_overflow=10, pool_pre_ping=True`
- **WAL 模式：** 启动时通过 `@event.listens_for(engine, "connect")` 执行 `PRAGMA journal_mode=WAL`，允许读写并发；`PRAGMA synchronous=NORMAL` 兼顾性能和持久性；`PRAGMA cache_size=-32000` 分配 32MB 页缓存
- **为什么 SQLite：** 单机部署，无需独立数据库服务，文件直接 SFTP 备份

### ChromaDB
- **用途：** 向量数据库，存储新闻 headline 的嵌入向量，支持语义相似度搜索
- **目录：** `data/chroma`（`CHROMA_PATH` 可配置）
- **集合名：** `stock_news`，文档 ID 与 SQLite `news_articles.id` 对齐
- **为什么 ChromaDB：** 本地运行，无服务进程，Python 包直接调用

---

## 嵌入模型

### sentence-transformers / all-MiniLM-L6-v2
- **用途：** 将新闻 headline 转为 384 维向量，存入 ChromaDB
- **加载位置：** FastAPI 启动时 `_get_embedder()` 预热，缓存为模块级单例
- **模型缓存：** `~/.cache/huggingface/`（首次启动需联网下载）
- **为什么 MiniLM-L6-v2：** 轻量（80MB），推理快，语义质量对新闻标题场景足够

---

## LLM 接入

### 多后端适配器（`agent/agent.py`）

所有适配器实现统一接口：
```python
async def complete(messages, system_prompt, tools) -> LLMResponse
async def stream_complete(messages, system_prompt, tools)  # async generator → str chunks
```

| 后端 | 类 | 协议 | 备注 |
|---|---|---|---|
| Zoom AI Agent | `ZoomLLMClient` | SSE over HTTPS | `verify=False`（企业内网证书） |
| Anthropic Claude | `_AnthropicAdapter` | Anthropic SDK | `stream_complete` 降级为单次调用 |
| Aliyun DashScope | `_AliyunAdapter` | OpenAI-compatible REST | 模型固定为 `qwen-plus`；`verify=False` |

通过 `.env` 的 `LLM_BACKEND` 变量切换，无需改代码。

---

## 数据采集

### yfinance
- **用途（价格）：** 拉取 OHLCV 历史价格数据（日线 `1d` / 小时线 `1h`）
- **用途（期权结构）：** `Ticker.option_chain(expiry)` 获取期权链（strike / OI / gamma），计算 Max Pain 和 GEX（无需额外 API Key）
- **用途（ticker 校验）：** `validate_ticker()` 用 5 天历史数据探测，~1s/次，决定未知 ticker 是否注册到监控列表
- **去重：** 数据库 unique constraint `(ticker, timestamp, interval)` 防止重复写入

### Alpha Vantage API
- **用途：** 新闻文章 + 情感分数（`sentiment_score`、`sentiment_label`）
- **Key：** `ALPHA_VANTAGE_API_KEY`
- **失败处理：** `_safe_fetch()` 包装 — 异常时记 warning 日志，返回 0，不阻断其他数据源

### Finnhub API
- **用途（新闻）：** 新闻文章 + 内部人交易数据（`get_insider_transactions()`）
- **用途（基本面）：** 5 个端点批量获取 `FundamentalSnapshot`：估值（PE/PB/PS/EV-EBITDA）、盈利能力（ROE/利润率）、成长性（营收/EPS 同比/3年CAGR）、财务健康（流动比率/负债率/FCF）、市场数据（52周高低/Beta/市值）、分析师共识（买卖评级/目标价）、最近一季 EPS 及下次财报日期
- **Key：** `FINNHUB_API_KEY`
- **调用时机：** 每次 `_run_sync()` 最后阶段（API sync / CLI sync 均触发）
- **失败处理：** 同上，独立隔离

### Financial Juice
- **用途：** 补充新闻源（最近 48 小时）
- **失败处理：** 同上，独立隔离

### FRED（Federal Reserve Economic Data）
- **用途：** 拉宏观时序进 `macro_snapshots` 表，给每次分析提供 Macro Context 段（利率/收益率曲线/CPI/失业率/VIX）
- **Series：** `DFF`、`DGS10`、`DGS2`、`CPIAUCSL`、`UNRATE`、`VIXCLS`
- **Key：** `FRED_API_KEY`（免费，秒注册：https://fred.stlouisfed.org/docs/api/api_key.html）。未配置时静默跳过，prompt 里 macro_json 为空，LLM 会在 Caveats 里点出
- **节流：** 12h TTL —— `fred_client.is_macro_stale()` 检查 `MAX(fetched_at)`，每次 ticker sync 均预调用但实际命中 API 的频率上限是 2 次/天
- **派生字段：** `get_macro_latest()` 计算 `yield_curve_10y_2y_bps`（10Y−2Y 利差，单位 bp）和 `cpi_yoy_pct`（12 个月 CPI 同比）

### StockTwits（散户情感）
- **用途：** 拉公开消息流（最近 30 条），按 24h 窗口聚合 bullish/bearish 占比，用作 Retail Sentiment 段的低权重参考信号
- **端点：** `api.stocktwits.com/api/2/streams/symbol/{TICKER}.json`，**无需 auth**
- **存储位置：** 复用 `news_articles` 表，`source='stocktwits'` 作为分流 marker
- **Sentiment 映射：** `entities.sentiment.basic = "Bullish"→+0.5 / "Bearish"→−0.5 / null→None`（数值取 0.5 而非 1.0，避免散户置信压过专业新闻）
- **Embedding：** 写入时 `embedded=1`，跳过向量化（短文本噪音大，污染 historical-analogue 检索）
- **隔离查询：** `get_daily_sentiment` / `get_recent_news` / `build_overview_card` 的新闻聚合统一加 `source != 'stocktwits'` 过滤；`get_retail_sentiment_summary()` 反向只查 stocktwits

### 期权市场结构（`ingestion/prices/options_structure.py`）

无需额外 API Key，基于 yfinance `option_chain()` 计算两个核心指标：

| 指标 | 计算方式 | 交易含义 |
|---|---|---|
| **Max Pain** | 遍历所有行权价 K，使期权买方总内在价值 `Σmax(K-s,0)·callOI + Σmax(s-K,0)·putOI` 最小化 | 理论上到期日前股价向 Max Pain 靠拢（做市商对冲压力） |
| **GEX（Gamma Exposure）** | `Σ(gamma·OI·100·spot)` calls 减 puts | 正 GEX → 做市商 long gamma → 买跌卖涨 → 压制波动（STABILIZING）；负 GEX → 放大趋势（AMPLIFYING） |
| **关键 Gamma 水平** | Call gamma 最大的 Top-3 行权价（阻力）；Put gamma 最大的 Top-3 行权价（支撑） | 识别期权市场隐含的价格磁力区 |

覆盖最近 2 个到期日；gamma 列缺失时 `gex_available: false`。

---

## 内存缓存（无依赖）

项目使用简单的 `dict + time.time()` 实现 TTL 缓存，无需 Redis 或 cachetools：

| 缓存位置 | key | TTL | 作用 |
|---|---|---|---|
| `agent/agent.py:_tools_cache` | `ticker` | 20 分钟 | `_run_all_tools` 完整结果；sync 完成后主动失效 |
| `ingestion/prices/options_sentiment.py:_pcr_cache` | `ticker:date` | 6 小时 | PCR 不随日内变化 |
| `ingestion/news/finnhub_news.py:_insider_cache` | `ticker` | 6 小时 | Insider 交易数据日内稳定 |
| `ingestion/prices/options_structure.py:_options_cache` | `ticker` | 1 小时 | 期权链下载慢（每次 ~1–2s/到期日）；Max Pain + GEX 小时内基本不变 |

**并行工具采集：** `_collect_tools` 中，news 顺序先跑（subsequent tasks 依赖 headlines），其余 **9 个任务**（similar search、prices、corr stats、PCR、insider、fundamentals、options structure、macro、retail sentiment）通过 `ThreadPoolExecutor(max_workers=9)` 并行执行，节省 HTTP 等待时间约 1–2s。Macro 和 retail 都读 DB（不走 HTTP），sync pipeline 已把上游写入做掉了。

## 定时任务

### APScheduler — BackgroundScheduler
- **用途：** 在 FastAPI 进程内后台定时执行 sync 任务
- **触发器：** `CronTrigger`，cron 表达式来自 `SYNC_CRON`（默认工作日 18:00）
- **注意：** `BlockingScheduler`（`scheduler/jobs.py`）仅用于 CLI `watch` 命令，API 启动用 `BackgroundScheduler`

---

## 前端

### Vue 3 + Vite + TypeScript + Tailwind

- **入口：** `frontend/index.html`（仅挂 `<div id="app">`），真正的 UI 在 `frontend/src/`
- **构建：** Vite 6（`npm run build` 输出到 `frontend/dist/`，由 FastAPI mount `/assets` + 根路径返回 `index.html`）
- **开发服务器：** `npm run dev`（端口 5173，自动 proxy `/api` → `localhost:9999`）
- **状态管理：** Pinia 2，两个 store：
  - `stores/tickers.ts` — 侧边栏 ticker 列表 + sync 轮询定时器
  - `stores/chat.ts` — `session_id` + 消息日志 + streaming flag
- **SSE 流式接收：** `composables/useSSE.ts` 用 `fetch()` + `ReadableStream` 解析 `\r\n\r\n` 事件边界
- **样式：** Tailwind 3 utility 优先；markdown 渲染区域用 `.bubble-md` 自定义类保留 `<h1>/<table>` 等基础样式
- **TypeScript 严格模式：** `strict: true` + `noUnusedLocals/Parameters`，`vue-tsc -b` 在构建前做类型检查

### 主要 npm 依赖

| 包 | 用途 |
|---|---|
| `vue` 3.5+ | 组件框架 |
| `vue-router` 4+ | 路由（`/overview`、`/plans`，hash 模式） |
| `pinia` 2+ | 全局状态 |
| `chart.js` 4+ | 价格 / 情感图（按需 `register(...registerables)`） |
| `marked` 14+ | LLM 输出的 markdown 渲染 |
| `tailwindcss` 3+ | 样式 |
| `vite` 6+ + `@vitejs/plugin-vue` | 构建 + dev server |
| `vue-tsc` 2+ | Vue 文件类型检查 |

### Chart.js 使用模式
- `Charts.vue` 组件接收 `ChartPayload`，在 `onMounted` / `watch(props.chart)` 时销毁旧实例并重建
- **单 ticker：** 14 天收盘价折线图 + 7 天情感柱状图（正绿负红）
- **对比模式：** 归一化百分比折线对比图 + 双 ticker 情感柱状对比图

### 构建集成（start.sh）
启动时检查 `frontend/{package.json,src/}` md5 hash，仅当变更或 `dist/` 缺失才跑 `npm install + npm run build`。SFTP 流程：本地保存触发自动上传 → 远程 `start.sh` 检测变更并重建。

---

## 运行环境

### Python 虚拟环境
- **目录：** `.venv/`
- **创建：** `start.sh` 自动处理（支持 Ubuntu / macOS）
- **依赖变更检测：** 用 `pyproject.toml` 的 md5 hash 判断是否需要 `pip install`（存储在 `.venv/.deps_installed`）

### 环境变量
- **加载方式：** `python-dotenv` 从 `.env` 文件读取，`pydantic-settings` 做类型校验
- **配置类：** `config/settings.py` — `Settings` 类，字段详见 `ARCHITECTURE.md § 6`

---

## 关键依赖版本约束

| 包 | 最低版本 | 原因 |
|---|---|---|
| `sqlalchemy` | 2.0 | 2.x API（`select()` style），1.x 不兼容 |
| `chromadb` | 0.5 | 0.4→0.5 有 breaking API 变更 |
| `fastapi` | 0.111 | `lifespan` context 及新版 `BackgroundTasks` |
| `anthropic` | 0.40 | `messages.create()` streaming API |
| `openai` | 1.0 | v1 统一了同步/异步接口 |
| Python | 3.11 | `tomllib` 标准库、类型注解语法 |
