from __future__ import annotations
from datetime import timedelta
from storage.database import get_session
from storage.models import NewsArticle, PriceBar, CorrelationSnapshot
from sqlalchemy.dialects.sqlite import insert


def _find_price_at(session, ticker: str, target_dt, interval: str = "1d"):
    """Find the closest price bar at or after target_dt."""
    bar = (
        session.query(PriceBar)
        .filter(
            PriceBar.ticker == ticker,
            PriceBar.timestamp >= target_dt,
            PriceBar.interval == interval,
        )
        .order_by(PriceBar.timestamp.asc())
        .first()
    )
    return bar


def _direction(pct: float | None) -> str:
    if pct is None:
        return "flat"
    if pct > 0.5:
        return "up"
    if pct < -0.5:
        return "down"
    return "flat"


def compute_correlations(ticker: str) -> int:
    """
    For each news article, find the price at publication time and at +1h/+4h/+1d,
    compute pct changes, and upsert CorrelationSnapshots.
    Returns number of snapshots written.
    """
    ticker = ticker.upper()
    written = 0

    with get_session() as session:
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.ticker == ticker)
            .all()
        )

        rows = []
        for article in articles:
            pub = article.published_at

            # Find base price (closest bar at or before pub time)
            base_bar = (
                session.query(PriceBar)
                .filter(
                    PriceBar.ticker == ticker,
                    PriceBar.timestamp <= pub,
                    PriceBar.interval == "1d",
                )
                .order_by(PriceBar.timestamp.desc())
                .first()
            )
            if not base_bar or not base_bar.close:
                continue

            base_price = base_bar.close

            def pct_change(offset_hours):
                bar = _find_price_at(session, ticker, pub + timedelta(hours=offset_hours), "1d")
                if bar and bar.close:
                    return round((bar.close - base_price) / base_price * 100, 4)
                return None

            ch_1d = pct_change(24)
            # Skip articles where future price bar doesn't exist yet (too recent)
            if ch_1d is None:
                continue
            ch_4h = pct_change(4)
            ch_1h = pct_change(1)

            direction = _direction(ch_1d)
            magnitude = round(abs(ch_1d), 4) if ch_1d is not None else None

            rows.append(
                {
                    "ticker": ticker,
                    "news_id": article.id,
                    "price_change_1h": ch_1h,
                    "price_change_4h": ch_4h,
                    "price_change_1d": ch_1d,
                    "direction": direction,
                    "magnitude": magnitude,
                }
            )

        if rows:
            stmt = insert(CorrelationSnapshot).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "news_id"])
            result = session.execute(stmt)
            written = result.rowcount if result.rowcount > 0 else len(rows)

    return written
