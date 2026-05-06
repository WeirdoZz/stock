"""
Tests for:
  - ingestion/fundamentals/finnhub_fundamentals.py  (fetch_and_store)
  - storage/repository.py                           (get_latest_fundamentals)

All Finnhub HTTP calls are mocked — no network or API key required.
DB tests use an isolated temporary SQLite file.

Patching rules:
  - `storage.repository.get_session`             — used by repository functions
  - `ingestion.fundamentals.finnhub_fundamentals.get_session` — used by fetch_and_store
  Both modules bind get_session at import time via `from storage.database import get_session`,
  so we must patch the name in each module's namespace, not in storage.database.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base, FundamentalSnapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_session(tmp_path):
    """SQLAlchemy session backed by an isolated temp SQLite file."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def patch_session(tmp_session):
    """
    Patch get_session in both modules that import it directly.
    Yields the underlying tmp_session for direct DB assertions.
    """
    @contextmanager
    def _fake():
        yield tmp_session
        tmp_session.commit()

    with (
        patch("storage.repository.get_session", _fake),
        patch("ingestion.fundamentals.finnhub_fundamentals.get_session", _fake),
    ):
        yield tmp_session


# ── Finnhub mock response factory ─────────────────────────────────────────────

def _mock_responses(pe=25.0, roe=0.35, eps_actual=2.5, eps_estimate=2.2,
                    next_date="2025-09-01"):
    """side_effect list covering all 5 Finnhub endpoint calls."""
    def resp(data):
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.json.return_value = data
        return r

    return [
        resp({"metric": {
            "peTTM": pe, "pbQuarterly": 8.0, "psTTM": 7.5,
            "evToEbitdaTTM": 20.0, "dividendYieldIndicatedAnnual": 0.005,
            "roeTTM": roe, "roaTTM": 0.18,
            "grossMarginTTM": 0.44, "operatingMarginTTM": 0.30,
            "netProfitMarginTTM": 0.25,
            "revenueGrowthTTMYoy": 0.06, "epsGrowthTTMYoy": 0.12,
            "revenueGrowth3Y": 0.09, "epsGrowth3Y": 0.15,
            "currentRatioQuarterly": 1.4,
            "totalDebt/totalEquityQuarterly": 1.8,
            "freeCashFlowTTM": 100_000_000_000,
            "52WeekHigh": 200.0, "52WeekLow": 140.0,
            "beta": 1.2, "marketCapitalization": 3_000_000_000_000,
        }}),
        resp([{"strongBuy": 20, "buy": 15, "hold": 8, "sell": 2, "strongSell": 0}]),
        resp({"targetMean": 210.0, "targetHigh": 250.0, "targetLow": 170.0}),
        resp([{"actual": eps_actual, "estimate": eps_estimate, "period": "2025-03-31"}]),
        resp({"earningsCalendar": [{"date": next_date, "symbol": "AAPL"}]}),
    ]


# ── fetch_and_store ────────────────────────────────────────────────────────────

class TestFetchAndStore:
    @patch("ingestion.fundamentals.finnhub_fundamentals.requests.get")
    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_returns_true_on_success(self, mock_settings, mock_get, patch_session):
        mock_settings.finnhub_api_key = "test-key"
        mock_get.side_effect = _mock_responses()
        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        assert fetch_and_store("AAPL") is True

    @patch("ingestion.fundamentals.finnhub_fundamentals.requests.get")
    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_snapshot_persisted_to_db(self, mock_settings, mock_get,
                                      patch_session, tmp_session):
        mock_settings.finnhub_api_key = "test-key"
        mock_get.side_effect = _mock_responses(pe=28.5, roe=0.40)
        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        fetch_and_store("AAPL")

        row = tmp_session.query(FundamentalSnapshot).filter_by(ticker="AAPL").first()
        assert row is not None
        assert row.pe_ttm == pytest.approx(28.5)
        assert row.roe_ttm == pytest.approx(0.40)
        assert row.analyst_strong_buy == 20
        assert row.analyst_target_mean == pytest.approx(210.0)
        assert row.next_earnings_date == "2025-09-01"

    @patch("ingestion.fundamentals.finnhub_fundamentals.requests.get")
    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_eps_surprise_beat(self, mock_settings, mock_get,
                               patch_session, tmp_session):
        # actual=2.5, estimate=2.0 → +25.0%
        mock_settings.finnhub_api_key = "test-key"
        mock_get.side_effect = _mock_responses(eps_actual=2.5, eps_estimate=2.0)
        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        fetch_and_store("AAPL")
        row = tmp_session.query(FundamentalSnapshot).filter_by(ticker="AAPL").first()
        assert row.eps_surprise_pct == pytest.approx(25.0)

    @patch("ingestion.fundamentals.finnhub_fundamentals.requests.get")
    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_eps_surprise_miss(self, mock_settings, mock_get,
                               patch_session, tmp_session):
        # actual=1.8, estimate=2.0 → -10.0%
        mock_settings.finnhub_api_key = "test-key"
        mock_get.side_effect = _mock_responses(eps_actual=1.8, eps_estimate=2.0)
        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        fetch_and_store("TSLA")
        row = tmp_session.query(FundamentalSnapshot).filter_by(ticker="TSLA").first()
        assert row.eps_surprise_pct == pytest.approx(-10.0)

    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_returns_false_when_no_api_key(self, mock_settings, patch_session):
        mock_settings.finnhub_api_key = ""
        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        assert fetch_and_store("AAPL") is False

    @patch("ingestion.fundamentals.finnhub_fundamentals.requests.get")
    @patch("ingestion.fundamentals.finnhub_fundamentals.settings")
    def test_partial_failure_still_stores_row(self, mock_settings, mock_get,
                                              patch_session, tmp_session):
        """Endpoints 2-5 fail; row still written with whatever data metric returned."""
        mock_settings.finnhub_api_key = "test-key"
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        ok.json.return_value = {"metric": {"peTTM": 30.0}}
        fail = MagicMock()
        fail.raise_for_status.side_effect = Exception("timeout")
        mock_get.side_effect = [ok, fail, fail, fail, fail]

        from ingestion.fundamentals.finnhub_fundamentals import fetch_and_store
        fetch_and_store("NVDA")

        row = tmp_session.query(FundamentalSnapshot).filter_by(ticker="NVDA").first()
        assert row is not None
        assert row.pe_ttm == pytest.approx(30.0)
        assert row.analyst_strong_buy is None


# ── get_latest_fundamentals ────────────────────────────────────────────────────

class TestGetLatestFundamentals:
    def _insert(self, session, ticker="AAPL", pe=25.0, offset_secs=0):
        snap = FundamentalSnapshot(
            ticker=ticker,
            fetched_at=datetime.utcnow() - timedelta(seconds=offset_secs),
            pe_ttm=pe,
            pb_quarterly=8.0,
            analyst_strong_buy=20,
            analyst_buy=15,
            analyst_hold=8,
            analyst_sell=2,
            analyst_strong_sell=0,
            analyst_target_mean=210.0,
            eps_actual=2.5,
            eps_estimate=2.2,
            eps_surprise_pct=13.64,
            next_earnings_date="2025-09-01",
        )
        session.add(snap)
        session.commit()

    def test_returns_none_when_no_data(self, patch_session):
        from storage.repository import get_latest_fundamentals
        assert get_latest_fundamentals("AAPL") is None

    def test_returns_dict_with_expected_structure(self, patch_session, tmp_session):
        self._insert(tmp_session)
        from storage.repository import get_latest_fundamentals
        result = get_latest_fundamentals("AAPL")
        assert result is not None
        assert set(result.keys()) == {
            "ticker", "fetched_at", "valuation", "profitability",
            "growth", "financial_health", "market", "analyst_consensus", "earnings",
        }
        assert result["valuation"]["pe_ttm"] == pytest.approx(25.0)
        assert result["analyst_consensus"]["strong_buy"] == 20
        assert result["earnings"]["eps_surprise_pct"] == pytest.approx(13.64)
        assert result["earnings"]["next_earnings_date"] == "2025-09-01"

    def test_returns_most_recent_snapshot(self, patch_session, tmp_session):
        self._insert(tmp_session, pe=20.0, offset_secs=3600)  # older
        self._insert(tmp_session, pe=99.0, offset_secs=0)     # newer
        from storage.repository import get_latest_fundamentals
        assert get_latest_fundamentals("AAPL")["valuation"]["pe_ttm"] == pytest.approx(99.0)

    def test_ticker_isolation(self, patch_session, tmp_session):
        self._insert(tmp_session, ticker="AAPL", pe=25.0)
        self._insert(tmp_session, ticker="NVDA", pe=50.0)
        from storage.repository import get_latest_fundamentals
        assert get_latest_fundamentals("AAPL")["valuation"]["pe_ttm"] == pytest.approx(25.0)
        assert get_latest_fundamentals("NVDA")["valuation"]["pe_ttm"] == pytest.approx(50.0)
        assert get_latest_fundamentals("TSLA") is None
