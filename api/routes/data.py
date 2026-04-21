"""GET /api/tickers, GET /api/status/{ticker}, POST /api/sync/{ticker}"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import TickerStatus
from config.settings import settings

router = APIRouter()


@router.get("/api/tickers")
def list_tickers() -> list[str]:
    return settings.ticker_list


@router.get("/api/status/{ticker}", response_model=TickerStatus)
def ticker_status(ticker: str) -> TickerStatus:
    ticker = ticker.upper()
    if ticker not in settings.ticker_list:
        raise HTTPException(status_code=404, detail=f"{ticker} is not in the watched list")

    from storage.database import get_session
    from storage.models import NewsArticle, PriceBar, CorrelationSnapshot
    from storage.repository import get_latest_price_date, get_latest_news_date
    from sqlalchemy import func

    with get_session() as s:
        news_count = s.query(NewsArticle).filter(NewsArticle.ticker == ticker).count()
        price_count = (
            s.query(PriceBar)
            .filter(PriceBar.ticker == ticker, PriceBar.interval == "1d")
            .count()
        )
        corr_count = (
            s.query(CorrelationSnapshot)
            .filter(CorrelationSnapshot.ticker == ticker)
            .count()
        )
        embedded_count = (
            s.query(NewsArticle)
            .filter(NewsArticle.ticker == ticker, NewsArticle.embedded == 1)
            .count()
        )

    last_price = get_latest_price_date(ticker)
    last_news = get_latest_news_date(ticker)

    days_stale = None
    if last_price:
        days_stale = (datetime.utcnow() - last_price).days

    return TickerStatus(
        ticker=ticker,
        news_count=news_count,
        price_count=price_count,
        correlation_count=corr_count,
        embedded_count=embedded_count,
        last_price_date=last_price.date().isoformat() if last_price else None,
        last_news_date=last_news.date().isoformat() if last_news else None,
        days_stale=days_stale,
    )


def _run_sync(ticker: str) -> None:
    from datetime import timedelta
    from storage.repository import get_latest_price_date, get_latest_news_date
    from ingestion.prices.yfinance_client import fetch_and_store as fetch_prices
    from ingestion.news.aggregator import ingest_all_news
    from analysis.correlator import compute_correlations
    from analysis.embedder import embed_pending

    last_price = get_latest_price_date(ticker)
    last_news = get_latest_news_date(ticker)
    is_first_run = last_price is None

    if is_first_run:
        days_back = 90
        price_from = None
        news_from = None
    else:
        days_since = (datetime.utcnow() - last_price).days
        days_back = max(days_since + 2, 3)
        price_from = last_price - timedelta(days=1)
        news_from = last_news - timedelta(days=1) if last_news else None

    fetch_prices(ticker, days_back=days_back, interval="1d", from_date=price_from)
    ingest_all_news(ticker, days_back=days_back, from_date=news_from)
    compute_correlations(ticker)
    embed_pending(ticker=ticker)


@router.post("/api/sync/{ticker}")
def sync_ticker(ticker: str, background_tasks: BackgroundTasks):
    ticker = ticker.upper()
    if ticker not in settings.ticker_list:
        raise HTTPException(status_code=404, detail=f"{ticker} is not in the watched list")
    background_tasks.add_task(_run_sync, ticker)
    return {"status": "queued", "ticker": ticker}
