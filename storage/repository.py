from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import func, case
from storage.database import get_session
from storage.models import NewsArticle, PriceBar, CorrelationSnapshot


# ── News ──────────────────────────────────────────────────────────────────────

def get_recent_news(ticker: str, hours_back: int = 48) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    with get_session() as session:
        rows = (
            session.query(NewsArticle)
            .filter(
                NewsArticle.ticker == ticker.upper(),
                NewsArticle.published_at >= cutoff,
            )
            .order_by(NewsArticle.published_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": r.id,
                "headline": r.headline,
                "summary": r.summary,
                "source": r.source,
                "published_at": r.published_at.isoformat(),
                "sentiment_score": r.sentiment_score,
                "sentiment_label": r.sentiment_label,
            }
            for r in rows
        ]


def get_unembedded_articles(ticker: str | None = None) -> list[dict]:
    with get_session() as session:
        q = session.query(NewsArticle).filter(NewsArticle.embedded == 0)
        if ticker:
            q = q.filter(NewsArticle.ticker == ticker.upper())
        rows = q.all()
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "headline": r.headline,
                "published_at": r.published_at,
                "sentiment_label": r.sentiment_label,
                "sentiment_score": r.sentiment_score,
            }
            for r in rows
        ]


def mark_articles_embedded(ids: list[str]) -> None:
    with get_session() as session:
        session.query(NewsArticle).filter(NewsArticle.id.in_(ids)).update(
            {"embedded": 1}, synchronize_session=False
        )


# ── Prices ────────────────────────────────────────────────────────────────────

def get_price_history(ticker: str, days_back: int = 30, interval: str = "1d") -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    with get_session() as session:
        rows = (
            session.query(PriceBar)
            .filter(
                PriceBar.ticker == ticker.upper(),
                PriceBar.timestamp >= cutoff,
                PriceBar.interval == interval,
            )
            .order_by(PriceBar.timestamp.asc())
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]


# ── Correlations ──────────────────────────────────────────────────────────────

def get_correlation_stats(ticker: str) -> dict:
    with get_session() as session:
        rows = (
            session.query(CorrelationSnapshot)
            .filter(CorrelationSnapshot.ticker == ticker.upper())
            .all()
        )
        if not rows:
            return {"ticker": ticker, "sample_count": 0}

        up = [r for r in rows if r.direction == "up"]
        down = [r for r in rows if r.direction == "down"]
        flat = [r for r in rows if r.direction == "flat"]

        def avg(vals):
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        changes_1d = [r.price_change_1d for r in rows if r.price_change_1d is not None]

        return {
            "ticker": ticker.upper(),
            "sample_count": len(rows),
            "up_count": len(up),
            "down_count": len(down),
            "flat_count": len(flat),
            "up_pct": round(len(up) / len(rows) * 100, 1),
            "down_pct": round(len(down) / len(rows) * 100, 1),
            "avg_1d_change_pct": avg(changes_1d),
            "avg_up_magnitude": avg([r.magnitude for r in up if r.magnitude]),
            "avg_down_magnitude": avg([r.magnitude for r in down if r.magnitude]),
        }


# ── Sync state helpers ────────────────────────────────────────────────────────

def get_latest_price_date(ticker: str) -> datetime | None:
    """Return the most recent price bar timestamp for ticker, or None if no data."""
    with get_session() as session:
        result = (
            session.query(func.max(PriceBar.timestamp))
            .filter(PriceBar.ticker == ticker.upper(), PriceBar.interval == "1d")
            .scalar()
        )
        return result


def get_latest_news_date(ticker: str) -> datetime | None:
    """Return the most recent news article timestamp for ticker, or None if no data."""
    with get_session() as session:
        result = (
            session.query(func.max(NewsArticle.published_at))
            .filter(NewsArticle.ticker == ticker.upper())
            .scalar()
        )
        return result


def get_news_article_by_ids(ids: list[str]) -> list[dict]:
    with get_session() as session:
        rows = session.query(NewsArticle).filter(NewsArticle.id.in_(ids)).all()
        return [
            {
                "id": r.id,
                "headline": r.headline,
                "published_at": r.published_at.isoformat(),
                "sentiment_label": r.sentiment_label,
            }
            for r in rows
        ]
