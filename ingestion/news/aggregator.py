from __future__ import annotations
from datetime import datetime
from ingestion.news import alpha_vantage_news, financial_juice, finnhub_news


def ingest_all_news(ticker: str, days_back: int = 90,
                    from_date: datetime | None = None) -> dict:
    """Fetch from all configured news sources.

    If from_date is provided, only fetches news after that date (incremental).
    Otherwise fetches the last days_back days (full mode).
    """
    av_count = alpha_vantage_news.fetch_and_store(ticker, limit=200)
    fj_count = financial_juice.fetch_and_store(ticker, hours_back=48)
    fh_count = finnhub_news.fetch_and_store(ticker, days_back=days_back, from_date=from_date)
    return {
        "alpha_vantage": av_count,
        "financial_juice": fj_count,
        "finnhub": fh_count,
        "total": av_count + fj_count + fh_count,
    }
