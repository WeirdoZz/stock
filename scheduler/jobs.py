from __future__ import annotations
import sys
import time
import signal
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _sync_ticker(ticker: str) -> None:
    """Full sync pipeline for one ticker (incremental-aware)."""
    from datetime import datetime, timedelta
    from storage.repository import get_latest_price_date, get_latest_news_date
    from ingestion.prices.yfinance_client import fetch_and_store as fetch_prices
    from ingestion.news.aggregator import ingest_all_news
    from ingestion.macro.fred_client import fetch_and_store as fetch_macro
    from analysis.correlator import compute_correlations
    from analysis.embedder import embed_pending

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Syncing {ticker}...")

    last_price = get_latest_price_date(ticker)
    is_first_run = last_price is None

    if is_first_run:
        price_from = None
        news_from = None
        days_back = 90
    else:
        price_from = last_price - timedelta(days=1)
        last_news = get_latest_news_date(ticker)
        news_from = last_news - timedelta(days=1) if last_news else None
        days_back = max((datetime.utcnow() - last_price).days + 2, 3)

    # Macro is global; ticker-keyed loop is fine because fetch_macro() short-
    # circuits when data is already fresh (<12h since last fetch).
    fetch_macro()

    p = fetch_prices(ticker, days_back=days_back, interval="1d", from_date=price_from)
    counts = ingest_all_news(ticker, days_back=days_back, from_date=news_from)
    c = compute_correlations(ticker)
    e = embed_pending(ticker=ticker)

    from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store as fetch_fundamentals
    fetch_fundamentals(ticker)

    print(f"  {ticker}: +{p} bars, +{counts['total']} articles "
          f"(av={counts.get('alpha_vantage',0)}, fj={counts.get('financial_juice',0)}, "
          f"fh={counts.get('finnhub',0)}, st={counts.get('stocktwits',0)}), "
          f"+{c} correlations, +{e} embeddings")


def run_scheduler(tickers: list[str], cron_expr: str) -> None:
    """
    Start a blocking scheduler with the given cron expression.
    cron_expr format: "minute hour day month day_of_week"
    Examples:
      "0 18 * * 1-5"   → weekdays at 18:00
      "0 9 * * *"      → every day at 09:00
      "*/30 * * * *"   → every 30 minutes
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron expression: {cron_expr!r}\n"
            "Expected 5 fields: minute hour day month day_of_week\n"
            "Example: '0 18 * * 1-5' (weekdays at 18:00)"
        )
    minute, hour, day, month, day_of_week = parts

    scheduler = BlockingScheduler()

    for ticker in tickers:
        scheduler.add_job(
            _sync_ticker,
            trigger=CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            ),
            args=[ticker],
            id=f"sync_{ticker}",
            name=f"Sync {ticker}",
            misfire_grace_time=300,  # allow up to 5min late start
        )

    # Print schedule info
    print(f"Scheduler started for: {tickers}")
    print(f"Cron: {cron_expr}")
    print("Next runs:")
    for job in scheduler.get_jobs():
        print(f"  {job.name}: {job.next_run_time}")
    print("Press Ctrl+C to stop.\n")

    # Graceful shutdown on SIGTERM (for process managers)
    def _shutdown(signum, frame):
        scheduler.shutdown(wait=False)
        sys.exit(0)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        print("Scheduler stopped.")
