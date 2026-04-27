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
| 前端 | 纯 HTML + Vanilla JS | 无构建步骤 |
| 图表 | Chart.js 4 | CDN，无 npm |
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
- **用途：** 存储结构化数据（价格、新闻、相关性快照）
- **文件路径：** `data/stock.db`（`DB_PATH` 可配置）
- **表：** `news_articles`、`price_bars`、`correlation_snapshots`
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
- **用途：** 拉取 OHLCV 历史价格数据（日线 `1d` / 小时线 `1h`）
- **去重：** 数据库 unique constraint `(ticker, timestamp, interval)` 防止重复写入

### Alpha Vantage API
- **用途：** 新闻文章 + 情感分数（`sentiment_score`、`sentiment_label`）
- **Key：** `ALPHA_VANTAGE_API_KEY`
- **失败处理：** `_safe_fetch()` 包装 — 异常时记 warning 日志，返回 0，不阻断其他数据源

### Finnhub API
- **用途：** 新闻文章 + 内部人交易数据（`get_insider_transactions()`）
- **Key：** `FINNHUB_API_KEY`
- **失败处理：** 同上，独立隔离

### Financial Juice
- **用途：** 补充新闻源（最近 48 小时）
- **失败处理：** 同上，独立隔离

---

## 内存缓存（无依赖）

项目使用简单的 `dict + time.time()` 实现 TTL 缓存，无需 Redis 或 cachetools：

| 缓存位置 | key | TTL | 作用 |
|---|---|---|---|
| `agent/agent.py:_tools_cache` | `ticker` | 20 分钟 | `_run_all_tools` 结果；sync 完成后主动失效 |
| `ingestion/prices/options_sentiment.py:_pcr_cache` | `ticker:date` | 6 小时 | PCR 不随日内变化 |
| `ingestion/news/finnhub_news.py:_insider_cache` | `ticker` | 6 小时 | Insider 交易数据日内稳定 |

**并行工具采集：** `_collect_tools` 中，news 顺序先跑（subsequent tasks 依赖 headlines），其余 5 个任务（similar search、prices、corr stats、PCR、insider）通过 `ThreadPoolExecutor(max_workers=5)` 并行执行，节省 HTTP 等待时间约 500–1000ms。

## 定时任务

### APScheduler — BackgroundScheduler
- **用途：** 在 FastAPI 进程内后台定时执行 sync 任务
- **触发器：** `CronTrigger`，cron 表达式来自 `SYNC_CRON`（默认工作日 18:00）
- **注意：** `BlockingScheduler`（`scheduler/jobs.py`）仅用于 CLI `watch` 命令，API 启动用 `BackgroundScheduler`

---

## 前端

### 纯 HTML + Vanilla JS（无框架、无构建）
- **文件：** `frontend/index.html`（单文件）
- **Markdown 渲染：** `marked.js`（CDN）
- **图表渲染：** `Chart.js 4`（CDN，`chart.umd.min.js`）— 无需 npm/构建
- **流式接收：** `fetch()` + `ReadableStream`（非 `EventSource`，因为 SSE over POST 不受原生 API 支持）
- **侧边栏功能：**
  - 启动时并行请求 `/api/status/{ticker}` 和 `/api/sync/status/{ticker}`
  - 显示最后同步日期，超过 1 天标红
  - ⟳ 按钮触发 sync，轮询进度，完成后自动刷新日期

### Chart.js 使用模式
- 每次 `type: "chart"` SSE 事件到达时，调用 `renderCharts(msgEl, chartData)` 动态创建 `<canvas>` 并初始化 Chart 实例
- 图表容器挂在 `.msg` 元素上（而非 `.bubble`），避免被 `done` 事件的 `innerHTML` 重写覆盖
- **单 ticker：** 14 天收盘价折线图 + 7 天情感柱状图（正绿负红）
- **对比模式：** 归一化百分比折线对比图 + 双 ticker 情感柱状对比图

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
