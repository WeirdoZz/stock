"""GET /api/tickers, GET /api/status/{ticker}, POST /api/sync/{ticker}, GET /api/sync/status/{ticker}"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import TickerStatus

router = APIRouter()

# In-memory sync status per ticker: {ticker: {status, started_at, finished_at, error}}
_sync_status: dict[str, dict] = {}


@router.get("/api/tickers")
def list_tickers() -> list[str]:
    from storage.repository import get_registered_tickers
    return get_registered_tickers()


@router.get("/api/status/{ticker}", response_model=TickerStatus)
def ticker_status(ticker: str) -> TickerStatus:
    from storage.repository import is_ticker_registered
    ticker = ticker.upper()
    if not is_ticker_registered(ticker):
        raise HTTPException(status_code=404, detail=f"{ticker} is not registered")

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
    import logging
    from datetime import timedelta
    from storage.repository import get_latest_price_date, get_latest_news_date
    from ingestion.prices.yfinance_client import fetch_and_store as fetch_prices
    from ingestion.news.aggregator import ingest_all_news
    from analysis.correlator import compute_correlations
    from analysis.embedder import embed_pending

    log = logging.getLogger(__name__)

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

    log.info("[sync] %s starting (first_run=%s, days_back=%s)", ticker, is_first_run, days_back)

    p = fetch_prices(ticker, days_back=days_back, interval="1d", from_date=price_from)
    counts = ingest_all_news(ticker, days_back=days_back, from_date=news_from)
    c = compute_correlations(ticker)
    e = embed_pending(ticker=ticker)

    from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store as fetch_fundamentals
    fetch_fundamentals(ticker)

    log.info("[sync] %s done: +%s bars, +%s articles (av=%s, fj=%s, fh=%s), "
             "+%s correlations, +%s embeddings",
             ticker, p, counts.get("total", 0),
             counts.get("alpha_vantage", 0), counts.get("financial_juice", 0),
             counts.get("finnhub", 0), c, e)


def _run_sync_tracked(ticker: str) -> None:
    _sync_status[ticker] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "error": None,
    }
    try:
        _run_sync(ticker)
        _sync_status[ticker].update({"status": "done", "finished_at": datetime.utcnow().isoformat()})
        # Bust the in-memory tools cache so next analysis sees fresh data
        from agent.agent import invalidate_tools_cache
        invalidate_tools_cache(ticker)
    except Exception as exc:
        _sync_status[ticker].update({
            "status": "error",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(exc),
        })


@router.get("/api/sync/status/{ticker}")
def sync_status(ticker: str):
    from storage.repository import is_ticker_registered
    ticker = ticker.upper()
    if not is_ticker_registered(ticker):
        raise HTTPException(status_code=404, detail=f"{ticker} is not registered")
    state = _sync_status.get(ticker, {"status": "idle"})
    return {"ticker": ticker, **state}


@router.post("/api/sync/{ticker}")
def sync_ticker(ticker: str, background_tasks: BackgroundTasks):
    from storage.repository import is_ticker_registered
    ticker = ticker.upper()
    if not is_ticker_registered(ticker):
        raise HTTPException(status_code=404, detail=f"{ticker} is not registered")
    if _sync_status.get(ticker, {}).get("status") == "running":
        return {"status": "already_running", "ticker": ticker}
    background_tasks.add_task(_run_sync_tracked, ticker)
    return {"status": "queued", "ticker": ticker}
