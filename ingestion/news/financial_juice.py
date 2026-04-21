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

FJ_BASE_URL = "https://api.financialjuice.com/feed"


def _article_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:64]


def fetch_and_store(ticker: str, hours_back: int = 48) -> int:
    """Fetch recent headlines from Financial Juice and store in DB."""
    if not settings.financial_juice_api_key:
        print("[financial_juice] No API key configured, skipping.")
        return 0

    headers = {"Authorization": f"Bearer {settings.financial_juice_api_key}"}
    params = {"search": ticker.upper(), "hours": hours_back}

    try:
        resp = requests.get(FJ_BASE_URL, headers=headers, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[financial_juice] Request failed: {e}")
        return 0

    items = data if isinstance(data, list) else data.get("items", data.get("data", []))
    rows = []
    for item in items:
        headline = item.get("title") or item.get("headline") or item.get("text", "")
        if not headline:
            continue

        art_id = _article_id(headline + str(item.get("publishedDate", "")))
        published_raw = item.get("publishedDate") or item.get("date") or item.get("created_at")
        try:
            published_at = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            published_at = datetime.utcnow()

        rows.append(
            {
                "id": art_id,
                "ticker": ticker.upper(),
                "headline": headline,
                "summary": item.get("summary") or item.get("body", ""),
                "source": "financialjuice",
                "url": item.get("url", ""),
                "published_at": published_at,
                "sentiment_score": None,
                "sentiment_label": None,
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
