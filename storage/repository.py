from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import func, case
from storage.database import get_session
from storage.models import (
    NewsArticle, PriceBar, CorrelationSnapshot, FundamentalSnapshot,
    RegisteredTicker, ChatSession, ChatMessage,
)


# ── Chat sessions ─────────────────────────────────────────────────────────────

def create_chat_session(session_id: str, title: str = "New chat") -> None:
    with get_session() as s:
        s.add(ChatSession(id=session_id, title=title))


def get_chat_session(session_id: str) -> dict | None:
    with get_session() as s:
        row = s.query(ChatSession).filter_by(id=session_id).first()
        if row is None:
            return None
        return {
            "id": row.id,
            "title": row.title,
            "archived": bool(row.archived),
            "last_ticker": row.last_ticker,
            "created_at": row.created_at.isoformat(),
            "last_active_at": row.last_active_at.isoformat(),
        }


def list_chat_sessions(include_archived: bool = False) -> list[dict]:
    with get_session() as s:
        q = s.query(ChatSession)
        if not include_archived:
            q = q.filter(ChatSession.archived == 0)
        rows = q.order_by(ChatSession.last_active_at.desc()).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "archived": bool(r.archived),
                "last_ticker": r.last_ticker,
                "created_at": r.created_at.isoformat(),
                "last_active_at": r.last_active_at.isoformat(),
            }
            for r in rows
        ]


def update_chat_session(
    session_id: str,
    *,
    title: str | None = None,
    archived: bool | None = None,
    last_ticker: str | None = None,
    bump_active: bool = False,
) -> bool:
    """Update one or more fields. Returns True if the row exists."""
    with get_session() as s:
        row = s.query(ChatSession).filter_by(id=session_id).first()
        if row is None:
            return False
        if title is not None:
            row.title = title
        if archived is not None:
            row.archived = 1 if archived else 0
        if last_ticker is not None:
            row.last_ticker = last_ticker
        if bump_active:
            row.last_active_at = datetime.utcnow()
        return True


def delete_chat_session(session_id: str) -> bool:
    """Delete a session and all its messages."""
    with get_session() as s:
        msg_deleted = s.query(ChatMessage).filter_by(session_id=session_id).delete()
        sess_deleted = s.query(ChatSession).filter_by(id=session_id).delete()
        return (sess_deleted + msg_deleted) > 0


def add_chat_message(session_id: str, role: str, content: str,
                     chart_json: str | None = None) -> int:
    """Append a message to a session. Returns the new row id."""
    with get_session() as s:
        m = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            chart_json=chart_json,
        )
        s.add(m)
        s.flush()
        return m.id


def list_chat_messages(session_id: str) -> list[dict]:
    with get_session() as s:
        rows = (
            s.query(ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "chart_json": r.chart_json,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


# ── Registered tickers ────────────────────────────────────────────────────────

def get_registered_tickers() -> list[str]:
    with get_session() as session:
        rows = session.query(RegisteredTicker.ticker).order_by(RegisteredTicker.ticker).all()
        return [r[0] for r in rows]


def is_ticker_registered(ticker: str) -> bool:
    with get_session() as session:
        return session.query(RegisteredTicker).filter_by(ticker=ticker.upper()).first() is not None


def register_ticker(ticker: str, source: str = "user") -> bool:
    """Insert if not exists. Returns True if newly inserted, False if already present."""
    ticker = ticker.upper()
    with get_session() as session:
        existing = session.query(RegisteredTicker).filter_by(ticker=ticker).first()
        if existing:
            return False
        session.add(RegisteredTicker(ticker=ticker, source=source))
        return True


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
                "summary": r.summary,
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


def get_latest_fundamentals(ticker: str) -> dict | None:
    """Return the most recent FundamentalSnapshot for ticker, or None."""
    with get_session() as session:
        row = (
            session.query(FundamentalSnapshot)
            .filter(FundamentalSnapshot.ticker == ticker.upper())
            .order_by(FundamentalSnapshot.fetched_at.desc())
            .first()
        )
        if not row:
            return None
        return {
            "ticker": row.ticker,
            "fetched_at": row.fetched_at.isoformat(),
            "valuation": {
                "pe_ttm":         row.pe_ttm,
                "pb_quarterly":   row.pb_quarterly,
                "ps_ttm":         row.ps_ttm,
                "ev_ebitda_ttm":  row.ev_ebitda_ttm,
                "dividend_yield": row.dividend_yield,
            },
            "profitability": {
                "roe_ttm":             row.roe_ttm,
                "roa_ttm":             row.roa_ttm,
                "gross_margin_ttm":    row.gross_margin_ttm,
                "operating_margin_ttm": row.operating_margin_ttm,
                "net_margin_ttm":      row.net_margin_ttm,
            },
            "growth": {
                "revenue_growth_yoy": row.revenue_growth_yoy,
                "eps_growth_yoy":     row.eps_growth_yoy,
                "revenue_growth_3y":  row.revenue_growth_3y,
                "eps_growth_3y":      row.eps_growth_3y,
            },
            "financial_health": {
                "current_ratio":    row.current_ratio,
                "debt_to_equity":   row.debt_to_equity,
                "free_cash_flow_ttm": row.free_cash_flow_ttm,
            },
            "market": {
                "week_52_high": row.week_52_high,
                "week_52_low":  row.week_52_low,
                "beta":         row.beta,
                "market_cap":   row.market_cap,
            },
            "analyst_consensus": {
                "strong_buy":   row.analyst_strong_buy,
                "buy":          row.analyst_buy,
                "hold":         row.analyst_hold,
                "sell":         row.analyst_sell,
                "strong_sell":  row.analyst_strong_sell,
                "target_mean":  row.analyst_target_mean,
                "target_high":  row.analyst_target_high,
                "target_low":   row.analyst_target_low,
            },
            "earnings": {
                "eps_actual":        row.eps_actual,
                "eps_estimate":      row.eps_estimate,
                "eps_surprise_pct":  row.eps_surprise_pct,
                "next_earnings_date": row.next_earnings_date,
            },
        }


def get_daily_sentiment(ticker: str, days: int = 7) -> list[dict]:
    """Return daily aggregated sentiment scores for the past N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as session:
        rows = (
            session.query(NewsArticle)
            .filter(
                NewsArticle.ticker == ticker.upper(),
                NewsArticle.published_at >= cutoff,
                NewsArticle.sentiment_score.isnot(None),
            )
            .order_by(NewsArticle.published_at.asc())
            .all()
        )
    from collections import defaultdict
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.published_at.date().isoformat()].append(r.sentiment_score)
    return [
        {"date": d, "avg_score": round(sum(v) / len(v), 3), "count": len(v)}
        for d, v in sorted(by_day.items())
    ]


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
