from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Date, Text, Index, UniqueConstraint, BigInteger
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(String(64), primary_key=True)  # sha256 of url
    ticker = Column(String(10), nullable=False)
    headline = Column(Text, nullable=False)
    summary = Column(Text)
    source = Column(String(100))
    url = Column(Text)
    published_at = Column(DateTime, nullable=False)
    sentiment_score = Column(Float)   # -1.0 to 1.0
    sentiment_label = Column(String(20))  # Bearish/Neutral/Bullish
    embedded = Column(Integer, default=0)  # 0/1 flag for ChromaDB
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_news_ticker_published", "ticker", "published_at"),
    )


class PriceBar(Base):
    __tablename__ = "price_bars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    interval = Column(String(5), nullable=False)  # '1d' or '1h'
    source = Column(String(50), default="yfinance")

    __table_args__ = (
        UniqueConstraint("ticker", "timestamp", "interval", name="uq_price_bar"),
        Index("ix_price_ticker_ts", "ticker", "timestamp"),
    )


class CorrelationSnapshot(Base):
    __tablename__ = "correlation_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    news_id = Column(String(64), nullable=False)
    price_change_1h = Column(Float)   # % change 1h after article
    price_change_4h = Column(Float)
    price_change_1d = Column(Float)
    direction = Column(String(10))    # 'up' / 'down' / 'flat'
    magnitude = Column(Float)         # abs(price_change_1d)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "news_id", name="uq_correlation"),
        Index("ix_corr_ticker", "ticker"),
    )


class Plan(Base):
    """A user-recorded holding plan: 'I want to buy AAPL at $180 by 2026-06-15'.
    Independent of registered_tickers — a plan can reference any ticker the
    user typed in, even one not currently being synced."""
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)            # 'buy' | 'sell' | 'hold' | 'watch'
    target_price = Column(Float)                           # optional target
    quantity = Column(Integer)                             # optional shares
    target_date = Column(String(20))                       # YYYY-MM-DD, optional
    status = Column(String(20), nullable=False, default="pending")  # 'pending' | 'completed' | 'cancelled'
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_plans_ticker_status", "ticker", "status"),
    )


class ChatSession(Base):
    """Persistent chat conversation. One row per user-visible session in the
    history sidebar. `archived = 1` hides it from the default list without
    deleting the messages."""
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True)             # uuid4
    title = Column(String(200), nullable=False, default="New chat")
    archived = Column(Integer, nullable=False, default=0) # 0 or 1
    last_ticker = Column(String(10))                      # carried across follow-ups
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_active_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_chat_sessions_active", "archived", "last_active_at"),
    )


class ChatMessage(Base):
    """One user or assistant message inside a ChatSession."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), nullable=False)
    role = Column(String(10), nullable=False)             # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    chart_json = Column(Text)                             # optional serialized chart payload
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_chat_messages_session", "session_id", "created_at"),
    )


class RegisteredTicker(Base):
    """Tickers under active sync. Bootstrapped from .env on startup, augmented
    by user queries about new tickers via the chat interface."""
    __tablename__ = "registered_tickers"

    ticker = Column(String(10), primary_key=True)
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source = Column(String(20), nullable=False, default="user")  # "env" or "user"


class FundamentalSnapshot(Base):
    """Daily snapshot of fundamental metrics for a ticker (from Finnhub)."""
    __tablename__ = "fundamental_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ── Valuation ────────────────────────────────────────────────────────────
    pe_ttm              = Column(Float)   # P/E trailing 12 months
    pb_quarterly        = Column(Float)   # P/Book (quarterly)
    ps_ttm              = Column(Float)   # P/Sales TTM
    ev_ebitda_ttm       = Column(Float)   # EV/EBITDA TTM
    dividend_yield      = Column(Float)   # indicated annual yield %

    # ── Profitability ────────────────────────────────────────────────────────
    roe_ttm             = Column(Float)   # Return on Equity %
    roa_ttm             = Column(Float)   # Return on Assets %
    gross_margin_ttm    = Column(Float)   # Gross margin %
    operating_margin_ttm = Column(Float)  # Operating margin %
    net_margin_ttm      = Column(Float)   # Net profit margin %

    # ── Growth ───────────────────────────────────────────────────────────────
    revenue_growth_yoy  = Column(Float)   # Revenue YoY growth %
    eps_growth_yoy      = Column(Float)   # EPS YoY growth %
    revenue_growth_3y   = Column(Float)   # 3-year revenue CAGR %
    eps_growth_3y       = Column(Float)   # 3-year EPS CAGR %

    # ── Financial Health ─────────────────────────────────────────────────────
    current_ratio       = Column(Float)   # current assets / current liabilities
    debt_to_equity      = Column(Float)   # total debt / equity
    free_cash_flow_ttm  = Column(Float)   # FCF TTM (raw, USD)

    # ── Market Data ──────────────────────────────────────────────────────────
    week_52_high        = Column(Float)
    week_52_low         = Column(Float)
    beta                = Column(Float)   # vs S&P 500
    market_cap          = Column(Float)   # USD

    # ── Analyst Consensus ────────────────────────────────────────────────────
    analyst_strong_buy  = Column(Integer)
    analyst_buy         = Column(Integer)
    analyst_hold        = Column(Integer)
    analyst_sell        = Column(Integer)
    analyst_strong_sell = Column(Integer)
    analyst_target_mean = Column(Float)
    analyst_target_high = Column(Float)
    analyst_target_low  = Column(Float)

    # ── Earnings ─────────────────────────────────────────────────────────────
    eps_actual          = Column(Float)   # last reported EPS
    eps_estimate        = Column(Float)   # analyst estimate for last quarter
    eps_surprise_pct    = Column(Float)   # (actual - estimate) / |estimate| * 100
    next_earnings_date  = Column(String(20))  # YYYY-MM-DD

    __table_args__ = (
        Index("ix_fundamental_ticker_date", "ticker", "fetched_at"),
    )


class MacroSnapshot(Base):
    """Daily macro time-series from FRED. One row per (series_id, observation_date).
    Series are global (not per-ticker). `_sync_macro()` upserts the latest
    observations once per day; analysis reads the most recent value per series
    via `get_macro_latest()`."""
    __tablename__ = "macro_snapshots"

    series_id = Column(String(20), primary_key=True)   # e.g. "DFF", "DGS10", "CPIAUCSL"
    date = Column(Date, primary_key=True)              # observation date
    value = Column(Float, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_macro_series_date", "series_id", "date"),
    )
