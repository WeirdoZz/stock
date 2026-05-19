"""Tests for the /api/overview aggregation (PR 3)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import (
    Base, FundamentalSnapshot, NewsArticle, PriceBar, RegisteredTicker,
)


@pytest.fixture()
def tmp_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def patch_session(tmp_session):
    @contextmanager
    def _fake():
        yield tmp_session
        tmp_session.commit()
    with patch("storage.repository.get_session", _fake):
        yield tmp_session


@pytest.fixture()
def client(patch_session):
    from api.routes.overview import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_ticker(session, ticker: str):
    session.add(RegisteredTicker(ticker=ticker, source="env"))


def _seed_prices(session, ticker: str, closes: list[float]):
    """Most recent first ordering of close prices: closes[0] = today, [-1] = oldest."""
    today = datetime.utcnow()
    for i, c in enumerate(closes):
        ts = today - timedelta(days=i)
        session.add(PriceBar(
            ticker=ticker, timestamp=ts, interval="1d",
            open=c, high=c, low=c, close=c, volume=1000, source="yfinance",
        ))


def _seed_news(session, ticker: str, scores: list[float]):
    base = datetime.utcnow() - timedelta(hours=1)
    for i, score in enumerate(scores):
        session.add(NewsArticle(
            id=f"{ticker}_{i}", ticker=ticker,
            headline=f"news {i}", summary="", source="alpha_vantage",
            url=f"http://example.com/{ticker}/{i}",
            published_at=base - timedelta(hours=i),
            sentiment_score=score, sentiment_label="Neutral",
        ))


def _seed_fundamentals(session, ticker: str, **fields):
    snap = FundamentalSnapshot(
        ticker=ticker,
        fetched_at=datetime.utcnow(),
        **fields,
    )
    session.add(snap)


class TestBuildOverviewCard:
    def test_returns_nulls_when_no_data(self, patch_session):
        from storage.repository import build_overview_card
        card = build_overview_card("AAPL")
        assert card["ticker"] == "AAPL"
        assert card["current_price"] is None
        assert card["change_5d_pct"] is None
        assert card["news_count_7d"] == 0
        assert card["pending_plans"] == 0

    def test_price_and_5d_change(self, patch_session, tmp_session):
        from storage.repository import build_overview_card
        # 6 bars: today=110, ..., 5 days ago=100
        _seed_prices(tmp_session, "AAPL", [110, 108, 106, 104, 102, 100])
        tmp_session.commit()

        card = build_overview_card("AAPL")
        assert card["current_price"] == 110
        assert card["change_5d_pct"] == 10.0  # (110 - 100) / 100 * 100

    def test_5d_change_null_when_too_few_bars(self, patch_session, tmp_session):
        from storage.repository import build_overview_card
        _seed_prices(tmp_session, "AAPL", [110, 108, 106])  # only 3 bars
        tmp_session.commit()

        card = build_overview_card("AAPL")
        assert card["current_price"] == 110
        assert card["change_5d_pct"] is None

    def test_news_rollup(self, patch_session, tmp_session):
        from storage.repository import build_overview_card
        _seed_news(tmp_session, "AAPL", [0.4, 0.6, -0.2])
        tmp_session.commit()
        card = build_overview_card("AAPL")
        assert card["news_count_7d"] == 3
        # avg(0.4, 0.6, -0.2) = 0.267
        assert card["avg_sentiment_7d"] == pytest.approx(0.267, abs=0.01)

    def test_fundamentals_pulled(self, patch_session, tmp_session):
        from storage.repository import build_overview_card
        _seed_fundamentals(
            tmp_session, "AAPL",
            pe_ttm=28.5, week_52_high=200, week_52_low=140, analyst_target_mean=210,
        )
        tmp_session.commit()

        card = build_overview_card("AAPL")
        assert card["pe_ttm"] == 28.5
        assert card["week_52_high"] == 200
        assert card["week_52_low"] == 140
        assert card["analyst_target_mean"] == 210

    def test_pending_plans_count_passed_through(self, patch_session):
        from storage.repository import build_overview_card
        card = build_overview_card("AAPL", pending_plans=3)
        assert card["pending_plans"] == 3


class TestBuildOverview:
    def test_returns_card_per_registered_ticker(self, patch_session, tmp_session):
        from storage.repository import build_overview
        _seed_ticker(tmp_session, "AAPL")
        _seed_ticker(tmp_session, "NVDA")
        tmp_session.commit()

        cards = build_overview()
        assert {c["ticker"] for c in cards} == {"AAPL", "NVDA"}

    def test_endpoint_round_trip(self, client, patch_session, tmp_session):
        _seed_ticker(tmp_session, "AAPL")
        _seed_prices(tmp_session, "AAPL", [110, 108, 106, 104, 102, 100])
        _seed_fundamentals(tmp_session, "AAPL", pe_ttm=25.0)
        tmp_session.commit()

        r = client.get("/api/overview")
        assert r.status_code == 200
        cards = r.json()
        assert len(cards) == 1
        assert cards[0]["ticker"] == "AAPL"
        assert cards[0]["current_price"] == 110
        assert cards[0]["change_5d_pct"] == 10.0
        assert cards[0]["pe_ttm"] == 25.0
