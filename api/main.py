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


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.on_event("startup")
def startup():
    import os
    from storage.database import init_db
    from storage.vector_store import _get_embedder
    from config.settings import settings

    init_db()

    # Pre-warm the embedding model so it loads once at startup, not on first request
    _get_embedder()
    print("[startup] Embedding model loaded.")

    # Start background scheduler for all watched tickers
    _start_scheduler(settings.ticker_list, settings.sync_cron)


def _start_scheduler(tickers: list, cron_expr: str) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.jobs import _sync_ticker

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        print(f"[scheduler] Invalid SYNC_CRON={cron_expr!r}, skipping. Expected 5 fields.")
        return

    minute, hour, day, month, day_of_week = parts
    scheduler = BackgroundScheduler()

    for ticker in tickers:
        scheduler.add_job(
            _sync_ticker,
            trigger=CronTrigger(
                minute=minute, hour=hour, day=day,
                month=month, day_of_week=day_of_week,
            ),
            args=[ticker],
            id=f"sync_{ticker}",
            name=f"Sync {ticker}",
            misfire_grace_time=300,
        )

    scheduler.start()
    next_runs = {job.name: str(job.next_run_time) for job in scheduler.get_jobs()}
    print(f"[scheduler] Started. Cron={cron_expr!r}  Tickers={tickers}")
    print(f"[scheduler] Next runs: {next_runs}")
