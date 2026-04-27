"""
Finnhub news ingestion.
Free tier: 60 req/min, up to 1 year of historical company news.
This solves the historical news gap that Alpha Vantage free tier has.
"""
from __future__ import annotations
import hashlib
import time
import requests
import urllib3
from datetime import datetime, timedelta
from config.settings import settings
from storage.database import get_session
from storage.models import NewsArticle
from sqlalchemy.dialects.sqlite import insert

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# In-memory cache for insider transactions (changes at most daily)
_insider_cache: dict[str, tuple[list, float]] = {}
_INSIDER_TTL = 6 * 3600  # 6 hours


def _article_id(url: str, headline: str) -> str:
    return hashlib.sha256(f"{url}{headline}".encode()).hexdigest()[:64]


def fetch_and_store(ticker: str, days_back: int = 90,
                    from_date: datetime | None = None) -> int:
    """Fetch historical news from Finnhub and store in DB. Returns new rows stored.

    If from_date is provided, fetches from that date to today (incremental mode).
    Otherwise fetches the last days_back days (full mode).
    """
    if not settings.finnhub_api_key:
        print("[finnhub_news] No API key configured, skipping.")
        return 0

    end_dt = datetime.utcnow()
    start_dt = from_date if from_date else end_dt - timedelta(days=days_back)
    headers = {"X-Finnhub-Token": settings.finnhub_api_key}

    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/company-news",
            headers=headers,
            params={
                "symbol": ticker.upper(),
                "from": start_dt.strftime("%Y-%m-%d"),
                "to": end_dt.strftime("%Y-%m-%d"),
            },
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        articles = resp.json()
    except Exception as e:
        print(f"[finnhub_news] Request failed: {e}")
        return 0

    if not isinstance(articles, list) or not articles:
        print(f"[finnhub_news] No articles returned for {ticker}.")
        return 0

    rows = []
    for item in articles:
        headline = item.get("headline", "")
        url = item.get("url", "")
        if not headline:
            continue

        art_id = _article_id(url, headline)
        ts = item.get("datetime", 0)
        published_at = datetime.utcfromtimestamp(ts) if ts else datetime.utcnow()

        rows.append({
            "id": art_id,
            "ticker": ticker.upper(),
            "headline": headline,
            "summary": item.get("summary", ""),
            "source": item.get("source", "finnhub"),
            "url": url,
            "published_at": published_at,
            "sentiment_score": None,   # Finnhub free doesn't include sentiment
            "sentiment_label": None,
            "embedded": 0,
        })

    if not rows:
        return 0

    with get_session() as session:
        stmt = insert(NewsArticle).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)

    return len(rows)


def get_insider_transactions(ticker: str) -> list[dict]:
    """Fetch recent insider transactions (buy/sell) for a ticker.
    Results are cached for 6 hours.
    """
    cache_key = ticker.upper()
    now = time.time()
    cached = _insider_cache.get(cache_key)
    if cached and now < cached[1]:
        return cached[0]

    if not settings.finnhub_api_key:
        return []

    headers = {"X-Finnhub-Token": settings.finnhub_api_key}
    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/stock/insider-transactions",
            headers=headers,
            params={"symbol": ticker.upper()},
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[finnhub_news] Insider transactions failed: {e}")
        return []

    txns = data.get("data", [])
    # Filter to actual buy/sell (code P = purchase, S = sale)
    relevant = [
        {
            "name": t.get("name"),
            "transaction_date": t.get("transactionDate"),
            "transaction_type": "BUY" if t.get("transactionCode") == "P" else "SELL",
            "shares": t.get("change"),
            "price": t.get("transactionPrice"),
        }
        for t in txns
        if t.get("transactionCode") in ("P", "S") and not t.get("isDerivative")
    ]
    result = relevant[:20]
    _insider_cache[cache_key] = (result, now + _INSIDER_TTL)
    return result
