"""StockTwits retail sentiment ingestion.

Public stream endpoint, no auth required. Each message carries an optional
`entities.sentiment.basic ∈ {Bullish, Bearish}`; we map to a numeric score
so it can live alongside news rows. The retail signal is intentionally
labeled `source="stocktwits"` so analysis queries can separate it from
professional news (see `storage.repository.RETAIL_SOURCE`).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import requests
import urllib3
from sqlalchemy.dialects.sqlite import insert

from storage.database import get_session
from storage.models import NewsArticle
from storage.repository import RETAIL_SOURCE

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

STOCKTWITS_BASE = "https://api.stocktwits.com/api/2"

# Map StockTwits' coarse Bullish/Bearish labels onto the [-1, 1] range we use
# elsewhere. 0.5 (not 1.0) so retail confidence doesn't visually dominate
# professional news sentiment if they ever get aggregated together.
_SENTIMENT_MAP = {
    "Bullish": (0.5,  "Bullish"),
    "Bearish": (-0.5, "Bearish"),
}


def _message_id(ticker: str, msg_id: int) -> str:
    return hashlib.sha256(f"stocktwits:{ticker}:{msg_id}".encode()).hexdigest()[:64]


def fetch_and_store(ticker: str, max_messages: int = 30) -> int:
    """Pull the latest StockTwits messages for `ticker` and upsert into
    `news_articles` with `source='stocktwits'`. Returns rows written.

    Idempotent: re-running against the same window is a no-op (deduped by
    deterministic id). Each new row is marked `embedded=1` so the vector
    embedder skips retail chatter — we don't want noisy 280-char takes
    polluting the historical-analogue search."""
    try:
        resp = requests.get(
            f"{STOCKTWITS_BASE}/streams/symbol/{ticker.upper()}.json",
            params={"limit": max_messages},
            timeout=15,
            headers={"User-Agent": "stock-analysis/1.0"},
            verify=False,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("[stocktwits] %s failed: %s", ticker, exc)
        return 0

    messages = payload.get("messages", [])
    if not messages:
        return 0

    rows = []
    for m in messages:
        body = (m.get("body") or "").strip()
        if not body:
            continue
        msg_id = m.get("id")
        if msg_id is None:
            continue

        created = m.get("created_at")  # ISO 8601 UTC, e.g. "2025-04-21T10:15:00Z"
        try:
            published = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ") if created \
                        else datetime.utcnow()
        except ValueError:
            published = datetime.utcnow()

        entities = m.get("entities") or {}
        sentiment = (entities.get("sentiment") or {}).get("basic")
        score, label = _SENTIMENT_MAP.get(sentiment, (None, None))

        user = m.get("user") or {}
        username = user.get("username") or "anonymous"
        msg_url = f"https://stocktwits.com/{username}/message/{msg_id}"

        rows.append({
            "id": _message_id(ticker, msg_id),
            "ticker": ticker.upper(),
            "headline": body[:500],   # column is TEXT but cap for sanity
            "summary": None,
            "source": RETAIL_SOURCE,
            "url": msg_url,
            "published_at": published,
            "sentiment_score": score,
            "sentiment_label": label,
            "embedded": 1,            # skip vector embedding for retail chatter
        })

    if not rows:
        return 0

    with get_session() as session:
        stmt = insert(NewsArticle).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)

    return len(rows)
