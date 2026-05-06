"""FastAPI application entry point."""
from __future__ import annotations

import logging
from config.settings import settings
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.chat import router as chat_router
from api.routes.data import router as data_router

app = FastAPI(title="Stock Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(data_router)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Module-global so chat.py can register new tickers on the live scheduler.
_scheduler = None
_cron_expr: str | None = None


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


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
