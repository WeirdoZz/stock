"""
Tests for ingestion/prices/options_structure.py

All yfinance calls are mocked — no network required.
Note: yfinance is imported lazily inside get_options_structure(), so we mock
yfinance.Ticker directly (not ingestion.prices.options_structure.yf).
"""
import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ingestion.prices.options_structure import (
    _gex,
    _max_pain,
    get_options_structure,
)


# ── Helper factories ───────────────────────────────────────────────────────────

def _make_calls(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _make_puts(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _build_mock_ticker(spot=150.0, expirations=("2025-06-20", "2025-07-18")):
    chain = MagicMock()
    chain.calls = _make_calls([
        {"strike": 145.0, "openInterest": 500, "gamma": 0.04},
        {"strike": 150.0, "openInterest": 800, "gamma": 0.06},
        {"strike": 155.0, "openInterest": 300, "gamma": 0.03},
    ])
    chain.puts = _make_puts([
        {"strike": 145.0, "openInterest": 600, "gamma": 0.04},
        {"strike": 150.0, "openInterest": 400, "gamma": 0.05},
        {"strike": 155.0, "openInterest": 200, "gamma": 0.02},
    ])
    ticker_mock = MagicMock()
    ticker_mock.info = {"currentPrice": spot}
    ticker_mock.options = expirations
    ticker_mock.option_chain.return_value = chain
    return ticker_mock


# ── _max_pain ──────────────────────────────────────────────────────────────────

class TestMaxPain:
    def test_simple_case(self):
        calls = _make_calls([
            {"strike": 100.0, "openInterest": 1000},
            {"strike": 110.0, "openInterest": 0},
        ])
        puts = _make_puts([
            {"strike": 100.0, "openInterest": 0},
            {"strike": 110.0, "openInterest": 0},
        ])
        assert _max_pain(calls, puts) == 100.0

    def test_put_heavy(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 10}])
        puts = _make_puts([{"strike": 90.0, "openInterest": 5000}])
        assert _max_pain(calls, puts) == 90.0

    def test_zero_oi_both_sides(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 0}])
        puts = _make_puts([{"strike": 100.0, "openInterest": 0}])
        assert _max_pain(calls, puts) == 100.0

    def test_symmetric_oi_returns_a_valid_strike(self):
        strikes = [95.0, 100.0, 105.0]
        calls = _make_calls([{"strike": s, "openInterest": 100} for s in strikes])
        puts = _make_puts([{"strike": s, "openInterest": 100} for s in strikes])
        assert _max_pain(calls, puts) in strikes


# ── _gex ──────────────────────────────────────────────────────────────────────

class TestGex:
    def test_positive_gex_stabilizing(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 1000, "gamma": 0.05}])
        puts = _make_puts([{"strike": 100.0, "openInterest": 100, "gamma": 0.05}])
        result = _gex(calls, puts, spot=100.0)
        assert result["gex_available"] is True
        assert result["net_gex_millions"] > 0
        assert result["gex_signal"] == "STABILIZING"

    def test_negative_gex_amplifying(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 100, "gamma": 0.05}])
        puts = _make_puts([{"strike": 100.0, "openInterest": 1000, "gamma": 0.05}])
        result = _gex(calls, puts, spot=100.0)
        assert result["gex_available"] is True
        assert result["net_gex_millions"] < 0
        assert result["gex_signal"] == "AMPLIFYING"

    def test_no_gamma_column(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 500}])
        puts = _make_puts([{"strike": 100.0, "openInterest": 500}])
        assert _gex(calls, puts, spot=100.0)["gex_available"] is False

    def test_all_gamma_nan(self):
        calls = _make_calls([{"strike": 100.0, "openInterest": 500, "gamma": float("nan")}])
        puts = _make_puts([{"strike": 100.0, "openInterest": 500, "gamma": float("nan")}])
        assert _gex(calls, puts, spot=100.0)["gex_available"] is False

    def test_top3_strikes_present(self):
        rows = [{"strike": float(s), "openInterest": 100, "gamma": 0.01 * i}
                for i, s in enumerate([95, 100, 105, 110], start=1)]
        result = _gex(_make_calls(rows), _make_puts(rows), spot=100.0)
        assert len(result["top_call_gamma_strikes"]) <= 3
        assert len(result["top_put_gamma_strikes"]) <= 3
        for entry in result["top_call_gamma_strikes"]:
            assert "strike" in entry and "gex_M" in entry


# ── get_options_structure (yfinance mocked at package level) ──────────────────

class TestGetOptionsStructure:
    def setup_method(self):
        from ingestion.prices import options_structure as mod
        mod._options_cache.clear()

    @patch("yfinance.Ticker")
    def test_returns_expected_keys(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _build_mock_ticker()
        result = get_options_structure("AAPL")
        assert result["ticker"] == "AAPL"
        assert result["spot_price"] == 150.0
        assert result["nearest_expiration"] is not None
        assert "max_pain" in result["nearest_expiration"]
        assert "gex_signal" in result["nearest_expiration"]
        assert "summary" in result

    @patch("yfinance.Ticker")
    def test_two_expirations_populated(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _build_mock_ticker()
        result = get_options_structure("AAPL")
        assert result["second_expiration"] is not None

    @patch("yfinance.Ticker")
    def test_result_is_cached(self, mock_ticker_cls):
        mock_ticker_cls.return_value = _build_mock_ticker()
        get_options_structure("MSFT")
        get_options_structure("MSFT")
        assert mock_ticker_cls.call_count == 1

    @patch("yfinance.Ticker")
    def test_no_options_returns_error(self, mock_ticker_cls):
        t = MagicMock()
        t.info = {"currentPrice": 150.0}
        t.options = []
        mock_ticker_cls.return_value = t
        assert "error" in get_options_structure("EMPTY")

    @patch("yfinance.Ticker")
    def test_yfinance_exception_returns_error(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = RuntimeError("network error")
        assert "error" in get_options_structure("BAD")

    @patch("yfinance.Ticker")
    def test_cache_expires(self, mock_ticker_cls):
        from ingestion.prices import options_structure as mod
        mock_ticker_cls.return_value = _build_mock_ticker()
        mod._options_cache["TSLA"] = ({"ticker": "TSLA"}, time.time() - 1)
        get_options_structure("TSLA")
        assert mock_ticker_cls.call_count == 1
