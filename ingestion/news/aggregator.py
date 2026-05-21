from __future__ import annotations
import logging
from datetime import datetime
from ingestion.news import alpha_vantage_news, financial_juice, finnhub_news
from ingestion.sentiment import stocktwits_client

logger = logging.getLogger(__name__)


def _safe_fetch(name: str, fn, *args, **kwargs) -> int:
    try:
        return fn(*args, **kwargs) or 0
    except Exception as exc:
        logger.warning("[aggregator] %s failed, skipping: %s", name, exc)
        return 0


def ingest_all_news(ticker: str, days_back: int = 90,
                    from_date: datetime | None = None) -> dict:
    """Fetch from all configured news + retail-sentiment sources.

    If from_date is provided, only fetches news after that date (incremental).
    Otherwise fetches the last days_back days (full mode).
    Each source is isolated — one failure does not abort the others.

    StockTwits is always pulled with its own short window (the API only exposes
    the most recent ~30 messages per symbol; there's no historical backfill).
    """
    av_count = _safe_fetch("alpha_vantage", alpha_vantage_news.fetch_and_store, ticker, limit=200)
    fj_count = _safe_fetch("financial_juice", financial_juice.fetch_and_store, ticker, hours_back=48)
    fh_count = _safe_fetch("finnhub", finnhub_news.fetch_and_store, ticker, days_back=days_back, from_date=from_date)
    st_count = _safe_fetch("stocktwits", stocktwits_client.fetch_and_store, ticker, max_messages=30)
    return {
        "alpha_vantage": av_count,
        "financial_juice": fj_count,
        "finnhub": fh_count,
        "stocktwits": st_count,
        "total": av_count + fj_count + fh_count + st_count,
    }
