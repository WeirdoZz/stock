from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, Index, UniqueConstraint
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
