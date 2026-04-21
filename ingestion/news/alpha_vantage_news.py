from __future__ import annotations
import hashlib
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
from config.settings import settings
from storage.database import get_session
from storage.models import NewsArticle
from sqlalchemy.dialects.sqlite import insert

AV_NEWS_URL = "https://www.alphavantage.co/query"


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:64]


def _parse_av_datetime(s: str) -> datetime:
    # Format: 20231011T120000
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%S")
    except ValueError:
        return datetime.utcnow()


def fetch_and_store(ticker: str, limit: int = 200) -> int:
    """Fetch news from Alpha Vantage NEWS_SENTIMENT and store in DB."""
    if not settings.alpha_vantage_api_key:
        print("[alpha_vantage_news] No API key configured, skipping.")
        return 0

    # Fetch news from the past 90 days so we have historical data for correlation
    from datetime import datetime, timedelta
    time_from = (datetime.utcnow() - timedelta(days=90)).strftime("%Y%m%dT0000")
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper(),
        "limit": min(limit, 1000),
        "time_from": time_from,
        "apikey": settings.alpha_vantage_api_key,
    }

    try:
        resp = requests.get(AV_NEWS_URL, params=params, timeout=30, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[alpha_vantage_news] Request failed: {e}")
        return 0

    feed = data.get("feed", [])
    if not feed:
        print(f"[alpha_vantage_news] No articles returned for {ticker}.")
        return 0

    rows = []
    for item in feed:
        url = item.get("url", "")
        art_id = _article_id(url or item.get("title", ""))

        # Extract ticker-specific sentiment
        ticker_sentiment = next(
            (
                ts
                for ts in item.get("ticker_sentiment", [])
                if ts.get("ticker", "").upper() == ticker.upper()
            ),
            {},
        )
        sentiment_score = float(ticker_sentiment.get("ticker_sentiment_score", 0) or 0)
        sentiment_label = ticker_sentiment.get("ticker_sentiment_label", "Neutral")

        rows.append(
            {
                "id": art_id,
                "ticker": ticker.upper(),
                "headline": item.get("title", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": url,
                "published_at": _parse_av_datetime(item.get("time_published", "")),
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "embedded": 0,
            }
        )

    if not rows:
        return 0

    with get_session() as session:
        stmt = insert(NewsArticle).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)

    return len(rows)
