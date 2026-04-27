from __future__ import annotations
import logging
from datetime import datetime
from ingestion.news import alpha_vantage_news, financial_juice, finnhub_news

logger = logging.getLogger(__name__)


def _safe_fetch(name: str, fn, *args, **kwargs) -> int:
    try:
        return fn(*args, **kwargs) or 0
    except Exception as exc:
        logger.warning("[aggregator] %s failed, skipping: %s", name, exc)
        return 0


def ingest_all_news(ticker: str, days_back: int = 90,
                    from_date: datetime | None = None) -> dict:
    """Fetch from all configured news sources.

    If from_date is provided, only fetches news after that date (incremental).
    Otherwise fetches the last days_back days (full mode).
    Each source is isolated — one failure does not abort the others.
    """
    av_count = _safe_fetch("alpha_vantage", alpha_vantage_news.fetch_and_store, ticker, limit=200)
    fj_count = _safe_fetch("financial_juice", financial_juice.fetch_and_store, ticker, hours_back=48)
    fh_count = _safe_fetch("finnhub", finnhub_news.fetch_and_store, ticker, days_back=days_back, from_date=from_date)
    return {
        "alpha_vantage": av_count,
        "financial_juice": fj_count,
        "finnhub": fh_count,
        "total": av_count + fj_count + fh_count,
    }
