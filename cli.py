#!/usr/bin/env python3
"""
Stock Analysis Agent CLI

Commands:
  python cli.py query AAPL          # AI trend analysis
  python cli.py sync AAPL           # Smart incremental update (run daily)
  python cli.py ingest AAPL         # Force full 90-day re-fetch
  python cli.py status AAPL         # Show what's in the DB for a ticker
"""
import click
from storage.database import init_db


@click.group()
def cli():
    """Stock trend analysis powered by AI."""
    init_db()


# ── query ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("ticker")
@click.option("--verbose", "-v", is_flag=True, help="Show data collection trace.")
def query(ticker: str, verbose: bool):
    """Run AI trend analysis for TICKER."""
    from agent.agent import run_query
    click.echo(f"\nAnalyzing {ticker.upper()}...\n")
    result = run_query(ticker, verbose=verbose)
    click.echo(result)


# ── sync (smart incremental) ──────────────────────────────────────────────────

@cli.command()
@click.argument("tickers", nargs=-1, required=False)
@click.option("--full", is_flag=True, help="Force full 90-day re-fetch even if data exists.")
def sync(tickers, full: bool):
    """Smart sync: full fetch on first run, incremental updates thereafter.

    If no tickers specified, uses WATCHED_TICKERS from .env.

    \b
    Examples:
      python cli.py sync                # sync all watched tickers
      python cli.py sync AAPL NVDA      # sync specific tickers
      python cli.py sync --full         # force re-fetch all watched tickers
    """
    from config.settings import settings
    if not tickers:
        tickers = settings.ticker_list
        click.echo(f"Using configured tickers: {tickers}")
    from datetime import datetime, timedelta
    from storage.repository import get_latest_price_date, get_latest_news_date
    from ingestion.prices.yfinance_client import fetch_and_store as fetch_prices
    from ingestion.news.aggregator import ingest_all_news
    from analysis.correlator import compute_correlations
    from analysis.embedder import embed_pending

    FULL_DAYS = 90

    for ticker in [t.upper() for t in tickers]:
        click.echo(f"\n{'='*50}")
        click.echo(f"Syncing {ticker}...")

        # ── Detect mode ───────────────────────────────────────────────────────
        last_price = get_latest_price_date(ticker)
        last_news = get_latest_news_date(ticker)
        is_first_run = (last_price is None) or full

        if is_first_run:
            click.echo(f"  Mode: FULL (90 days)" if not full else "  Mode: FULL (forced)")
            price_from = None
            news_from = None
            days_back = FULL_DAYS
        else:
            # Incremental: from last known date (with 1-day overlap to catch late data)
            price_from = last_price - timedelta(days=1)
            news_from = last_news - timedelta(days=1) if last_news else None
            days_since = (datetime.utcnow() - last_price).days
            click.echo(f"  Mode: INCREMENTAL (last price: {last_price.date()}, {days_since}d ago)")
            days_back = max(days_since + 2, 3)  # at least 3 days window

        # ── Prices ────────────────────────────────────────────────────────────
        click.echo(f"  [prices] Fetching...")
        n = fetch_prices(ticker, days_back=days_back, interval="1d", from_date=price_from)
        click.echo(f"  [prices] +{n} new bars")

        # ── News ──────────────────────────────────────────────────────────────
        click.echo(f"  [news] Fetching...")
        counts = ingest_all_news(ticker, days_back=days_back, from_date=news_from)
        click.echo(f"  [news] +{counts['total']} new articles "
                   f"(av={counts['alpha_vantage']}, finnhub={counts['finnhub']})")

        # ── Correlations ──────────────────────────────────────────────────────
        click.echo(f"  [correlate] Computing news→price correlations...")
        n = compute_correlations(ticker)
        click.echo(f"  [correlate] +{n} new snapshots")

        # ── Embeddings ────────────────────────────────────────────────────────
        click.echo(f"  [embed] Embedding new articles...")
        n = embed_pending(ticker=ticker)
        click.echo(f"  [embed] +{n} articles embedded")

        click.echo(f"  Done. Run: python cli.py query {ticker}")


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("ticker")
def status(ticker: str):
    """Show data summary for TICKER in the local DB."""
    from storage.repository import (
        get_latest_price_date, get_latest_news_date,
        get_correlation_stats, get_price_history, get_recent_news
    )
    from storage.database import get_session
    from storage.models import NewsArticle, PriceBar, CorrelationSnapshot
    from sqlalchemy import func

    ticker = ticker.upper()

    with get_session() as s:
        news_count = s.query(NewsArticle).filter(NewsArticle.ticker == ticker).count()
        price_count = s.query(PriceBar).filter(PriceBar.ticker == ticker, PriceBar.interval == "1d").count()
        corr_count = s.query(CorrelationSnapshot).filter(CorrelationSnapshot.ticker == ticker).count()
        embedded = s.query(NewsArticle).filter(
            NewsArticle.ticker == ticker, NewsArticle.embedded == 1
        ).count()
        oldest_news = s.query(func.min(NewsArticle.published_at)).filter(
            NewsArticle.ticker == ticker
        ).scalar()
        oldest_price = s.query(func.min(PriceBar.timestamp)).filter(
            PriceBar.ticker == ticker, PriceBar.interval == "1d"
        ).scalar()

    last_price = get_latest_price_date(ticker)
    last_news = get_latest_news_date(ticker)

    click.echo(f"\n{ticker} Data Status")
    click.echo("=" * 40)
    click.echo(f"News articles : {news_count:>6}  ({embedded} embedded in ChromaDB)")
    if oldest_news and last_news:
        click.echo(f"  Date range  : {oldest_news.date()} → {last_news.date()}")
    click.echo(f"Price bars    : {price_count:>6}  (daily)")
    if oldest_price and last_price:
        click.echo(f"  Date range  : {oldest_price.date()} → {last_price.date()}")
    click.echo(f"Correlations  : {corr_count:>6}  news→price snapshots")

    if last_price:
        from datetime import datetime
        days_stale = (datetime.utcnow() - last_price).days
        if days_stale == 0:
            click.echo(f"\n✓ Data is up to date")
        else:
            click.echo(f"\n⚠ Last price is {days_stale} day(s) old — run: python cli.py sync {ticker}")
    else:
        click.echo(f"\n✗ No data found — run: python cli.py sync {ticker}")


# ── ingest (force full re-fetch) ──────────────────────────────────────────────

@cli.command()
@click.argument("ticker")
@click.option("--days", default=90, help="Days of history to fetch.")
def ingest(ticker: str, days: int):
    """Force full historical data fetch for TICKER (same as sync --full)."""
    from ingestion.prices.yfinance_client import fetch_and_store as fetch_prices
    from ingestion.news.aggregator import ingest_all_news
    from analysis.correlator import compute_correlations
    from analysis.embedder import embed_pending

    ticker = ticker.upper()
    click.echo(f"Full ingest for {ticker} ({days} days)...")

    n = fetch_prices(ticker, days_back=days, interval="1d")
    click.echo(f"[prices] Stored {n} bars.")

    counts = ingest_all_news(ticker, days_back=days)
    click.echo(f"[news] Stored: {counts}")

    n = compute_correlations(ticker)
    click.echo(f"[correlate] Wrote {n} snapshots.")

    n = embed_pending(ticker=ticker)
    click.echo(f"[embed] Embedded {n} articles.")

    click.echo(f"\nDone. Run: python cli.py query {ticker}")


# ── watch (background scheduler) ─────────────────────────────────────────────

@cli.command()
@click.argument("tickers", nargs=-1, required=False)
@click.option(
    "--cron",
    default="0 18 * * 1-5",
    show_default=True,
    help=(
        'Cron expression (5 fields). Examples:\n\n'
        '"0 18 * * 1-5"  weekdays at 18:00\n'
        '"0 9 * * *"     every day at 09:00\n'
        '"*/30 * * * *"  every 30 minutes'
    ),
)
def watch(tickers, cron: str):
    """Start scheduler to auto-sync TICKERS on a cron schedule.

    \b
    Examples:
      python cli.py watch                            # all watched tickers, default cron
      python cli.py watch AAPL NVDA                  # specific tickers
      python cli.py watch --cron "0 9 * * *"         # all tickers, 9am daily
      python cli.py watch AAPL NVDA --cron "0 18 * * 1-5"
    """
    from config.settings import settings
    from scheduler.jobs import run_scheduler
    resolved = list(tickers) if tickers else settings.ticker_list
    if not tickers:
        click.echo(f"Using configured tickers: {resolved}")
    run_scheduler(resolved, cron)


if __name__ == "__main__":
    cli()
