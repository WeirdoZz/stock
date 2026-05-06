"""
Tests for runtime ticker registration:
  - storage.repository: register_ticker, is_ticker_registered, get_registered_tickers
  - ingestion.prices.yfinance_client: validate_ticker
  - api.routes.chat: _resolve_ticker

All external dependencies (yfinance) are mocked; no network or API keys needed.
DB tests use an isolated temp SQLite file.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base, RegisteredTicker


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def patch_session(tmp_session):
    """Patch get_session in storage.repository so register_ticker etc. write to tmp DB."""
    @contextmanager
    def _fake():
        yield tmp_session
        tmp_session.commit()

    with patch("storage.repository.get_session", _fake):
        yield tmp_session


# ── register_ticker / is_ticker_registered / get_registered_tickers ───────────

class TestRegisterTicker:
    def test_new_ticker_returns_true(self, patch_session):
        from storage.repository import register_ticker
        assert register_ticker("AAPL", "user") is True

    def test_persists_to_db(self, patch_session, tmp_session):
        from storage.repository import register_ticker
        register_ticker("NVDA", "user")
        row = tmp_session.query(RegisteredTicker).filter_by(ticker="NVDA").first()
        assert row is not None
        assert row.source == "user"
        assert row.registered_at is not None

    def test_uppercases_input(self, patch_session, tmp_session):
        from storage.repository import register_ticker
        register_ticker("tsla", "user")
        row = tmp_session.query(RegisteredTicker).filter_by(ticker="TSLA").first()
        assert row is not None

    def test_duplicate_returns_false(self, patch_session):
        from storage.repository import register_ticker
        assert register_ticker("AAPL", "user") is True
        assert register_ticker("AAPL", "user") is False

    def test_duplicate_does_not_overwrite_source(self, patch_session, tmp_session):
        """Re-registering an env-sourced ticker as 'user' should NOT change its source."""
        from storage.repository import register_ticker
        register_ticker("AAPL", "env")
        register_ticker("AAPL", "user")  # second call is a no-op
        row = tmp_session.query(RegisteredTicker).filter_by(ticker="AAPL").first()
        assert row.source == "env"


class TestIsTickerRegistered:
    def test_returns_true_for_registered(self, patch_session):
        from storage.repository import register_ticker, is_ticker_registered
        register_ticker("AAPL", "env")
        assert is_ticker_registered("AAPL") is True

    def test_returns_false_for_unregistered(self, patch_session):
        from storage.repository import is_ticker_registered
        assert is_ticker_registered("ZZZZ") is False

    def test_case_insensitive_lookup(self, patch_session):
        from storage.repository import register_ticker, is_ticker_registered
        register_ticker("AAPL", "env")
        assert is_ticker_registered("aapl") is True


class TestGetRegisteredTickers:
    def test_empty_db_returns_empty_list(self, patch_session):
        from storage.repository import get_registered_tickers
        assert get_registered_tickers() == []

    def test_returns_alphabetical_order(self, patch_session):
        from storage.repository import register_ticker, get_registered_tickers
        for t in ["TSLA", "AAPL", "NVDA"]:
            register_ticker(t, "env")
        assert get_registered_tickers() == ["AAPL", "NVDA", "TSLA"]


# ── validate_ticker (yfinance mocked) ─────────────────────────────────────────

class TestValidateTicker:
    @patch("yfinance.Ticker")
    def test_valid_ticker_returns_true(self, mock_ticker_cls):
        t = MagicMock()
        t.history.return_value = pd.DataFrame({"Close": [150.0, 151.0]})
        mock_ticker_cls.return_value = t

        from ingestion.prices.yfinance_client import validate_ticker
        assert validate_ticker("AAPL") is True

    @patch("yfinance.Ticker")
    def test_empty_history_returns_false(self, mock_ticker_cls):
        t = MagicMock()
        t.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = t

        from ingestion.prices.yfinance_client import validate_ticker
        assert validate_ticker("ZZZZZ") is False

    @patch("yfinance.Ticker")
    def test_yfinance_exception_returns_false(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = RuntimeError("network error")
        from ingestion.prices.yfinance_client import validate_ticker
        assert validate_ticker("BAD") is False


# ── _resolve_ticker (pure function, no mocking) ───────────────────────────────

class TestResolveTicker:
    def test_registered_alpha_match(self):
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("How is AAPL doing?", ["AAPL", "NVDA"]) == ("AAPL", True)

    def test_unregistered_single_candidate(self):
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("AMD trends?", ["AAPL", "NVDA"]) == ("AMD", False)

    def test_skips_single_letter_words(self):
        """'I think AAPL is good' should resolve to AAPL, not 'I'."""
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("I think AAPL is good", ["AAPL"]) == ("AAPL", True)

    def test_chinese_alias_for_registered(self):
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("苹果怎么样", ["AAPL"]) == ("AAPL", True)

    def test_chinese_alias_for_unregistered(self):
        """Alias resolves to its ticker even if that ticker isn't registered yet."""
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("英伟达怎么样", ["AAPL"]) == ("NVDA", False)

    def test_prefers_registered_over_unregistered(self):
        """When message contains both a registered and an unregistered ticker,
        prefer the registered one to keep the normal flow."""
        from api.routes.chat import _resolve_ticker
        # AAPL registered, AMD not
        result = _resolve_ticker("Compare AAPL with AMD", ["AAPL"])
        assert result == ("AAPL", True)

    def test_multiple_unregistered_returns_none(self):
        """Two unknown candidates → ambiguous → no resolution (avoid wrong auto-register)."""
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("AMD vs AMZN", []) == (None, False)

    def test_no_ticker_pattern(self):
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("hello world", ["AAPL"]) == (None, False)

    def test_lowercase_tickers_ignored(self):
        """Regex requires uppercase — 'aapl' shouldn't be picked up."""
        from api.routes.chat import _resolve_ticker
        assert _resolve_ticker("aapl in lowercase", ["AAPL"]) == (None, False)
