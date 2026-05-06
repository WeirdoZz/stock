from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, Index, UniqueConstraint, BigInteger
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
