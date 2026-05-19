"""FastAPI application entry point."""
from __future__ import annotations

import logging
from config.settings import settings
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(message)s")

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.chat import router as chat_router
from api.routes.data import router as data_router
from api.routes.sessions import router as sessions_router
from api.routes.plans import router as plans_router
from api.routes.overview import router as overview_router

app = FastAPI(title="Stock Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(data_router)
app.include_router(sessions_router)
app.include_router(plans_router)
app.include_router(overview_router)

# ── Frontend (Vite-built Vue 3 SPA) ─────────────────────────────────────────
# `frontend/dist` is produced by `npm run build` and contains the compiled
# index.html plus hashed asset bundles under `dist/assets/`.
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if (_FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

# Module-global so chat.py can register new tickers on the live scheduler.
_scheduler = None
_cron_expr: str | None = None


@app.get("/")
def index():
    index_path = _FRONTEND_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run `cd frontend && npm install && npm run build`.",
        )
    return FileResponse(str(index_path))


@app.on_event("startup")
def startup():
    from storage.database import init_db
    from storage.vector_store import _get_embedder
    from storage.repository import get_registered_tickers, register_ticker
    from config.settings import settings

    init_db()

    # Pre-warm the embedding model so it loads once at startup, not on first request
    _get_embedder()
    print("[startup] Embedding model loaded.")

    # Bootstrap tickers from .env into the registered_tickers table (insert-if-absent).
    # After this, the scheduler reads from DB only — .env is just a seed list.
    for t in settings.ticker_list:
        register_ticker(t, source="env")

    tickers = get_registered_tickers()
    _start_scheduler(tickers, settings.sync_cron)
    _kick_startup_freshness_syncs(tickers)


def _expected_latest_trading_date():
    """Most recent past US trading weekday (holidays ignored).

    yfinance returns no bars for weekends, so on Sat/Sun we expect data only
    through the prior Friday. Used to decide if a ticker's stored prices are
    behind the latest open session and need a startup sync.
    """
    from datetime import datetime, timezone, timedelta
    d = datetime.now(timezone.utc).date()
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def _kick_startup_freshness_syncs(tickers: list) -> None:
    """For every registered ticker, sync in the background if its latest
    price bar is older than the most recent US trading day, or missing entirely.
    Runs off-thread so app startup stays fast."""
    import threading
    from storage.repository import get_latest_price_date
    from api.routes.data import _run_sync_tracked

    expected = _expected_latest_trading_date()
    stale: list[str] = []
    for t in tickers:
        last = get_latest_price_date(t)
        if last is None or last.date() < expected:
            stale.append(t)

    if not stale:
        print(f"[startup] All {len(tickers)} tickers fresh through {expected}.")
        return

    print(f"[startup] {len(stale)}/{len(tickers)} tickers stale; "
          f"syncing in background (target={expected}): {stale}")

    def _runner():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(_run_sync_tracked, stale))
        print(f"[startup] Freshness sync complete: {stale}")

    threading.Thread(target=_runner, daemon=True, name="startup-freshness-sync").start()


def _start_scheduler(tickers: list, cron_expr: str) -> None:
    global _scheduler, _cron_expr
    from apscheduler.schedulers.background import BackgroundScheduler

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        print(f"[scheduler] Invalid SYNC_CRON={cron_expr!r}, skipping. Expected 5 fields.")
        return

    _cron_expr = cron_expr
    _scheduler = BackgroundScheduler()

    for ticker in tickers:
        _add_job(ticker)

    _scheduler.start()
    next_runs = {job.name: str(job.next_run_time) for job in _scheduler.get_jobs()}
    print(f"[scheduler] Started. Cron={cron_expr!r}  Tickers={tickers}")
    print(f"[scheduler] Next runs: {next_runs}")


def _add_job(ticker: str) -> None:
    """Register a single ticker's cron sync job on the live scheduler."""
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.jobs import _sync_ticker

    if _scheduler is None or _cron_expr is None:
        return
    minute, hour, day, month, day_of_week = _cron_expr.strip().split()
    _scheduler.add_job(
        _sync_ticker,
        trigger=CronTrigger(minute=minute, hour=hour, day=day,
                            month=month, day_of_week=day_of_week),
        args=[ticker],
        id=f"sync_{ticker}",
        name=f"Sync {ticker}",
        misfire_grace_time=300,
        replace_existing=True,
    )


def add_ticker_to_scheduler(ticker: str) -> None:
    """Public entry for adding a newly-registered ticker to the running scheduler."""
    _add_job(ticker.upper())
    if _scheduler is not None:
        job = _scheduler.get_job(f"sync_{ticker.upper()}")
        if job:
            print(f"[scheduler] Added {ticker.upper()}, next run: {job.next_run_time}")
