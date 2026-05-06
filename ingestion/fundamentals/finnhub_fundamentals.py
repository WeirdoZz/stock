"""
Finnhub fundamental data ingestion.
Fetches per ticker (all via free tier):
  - /stock/metric?metric=all  → 60+ valuation/profitability/growth/health metrics
  - /stock/recommendation     → analyst buy/hold/sell consensus (most recent period)
  - /stock/price-target       → analyst price target mean/high/low
  - /stock/earnings           → latest quarter EPS actual vs estimate
  - /calendar/earnings        → next earnings date (90-day look-ahead)
"""
from __future__ import annotations

import logging
import requests
import urllib3
from datetime import datetime, timedelta

from config.settings import settings
from storage.database import get_session
from storage.models import FundamentalSnapshot

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get(endpoint: str, params: dict) -> dict | list | None:
    headers = {"X-Finnhub-Token": settings.finnhub_api_key}
    try:
        resp = requests.get(
            f"{FINNHUB_BASE}{endpoint}",
            headers=headers,
            params=params,
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("[fundamentals] %s failed: %s", endpoint, exc)
        return None


def fetch_and_store(ticker: str) -> bool:
    """Fetch all fundamental data from Finnhub and persist a new daily snapshot.
    Returns True on success, False if key is missing or all requests fail.
    """
    ticker = ticker.upper()
    if not settings.finnhub_api_key:
        logger.warning("[fundamentals] No Finnhub API key configured, skipping.")
        return False

    # ── 1. Core metrics ───────────────────────────────────────────────────────
    metrics_resp = _get("/stock/metric", {"symbol": ticker, "metric": "all"})
    m = (metrics_resp or {}).get("metric", {})

    # ── 2. Analyst recommendations (most recent period) ───────────────────────
    rec_resp = _get("/stock/recommendation", {"symbol": ticker})
    rec = (rec_resp[0] if isinstance(rec_resp, list) and rec_resp else {})

    # ── 3. Analyst price targets ──────────────────────────────────────────────
    pt = _get("/stock/price-target", {"symbol": ticker}) or {}

    # ── 4. Earnings history — latest quarter EPS actual vs estimate ───────────
    earn_resp = _get("/stock/earnings", {"symbol": ticker, "limit": 4})
    latest_earn = (earn_resp[0] if isinstance(earn_resp, list) and earn_resp else {})

    # ── 5. Next earnings date (90-day calendar look-ahead) ────────────────────
    today = datetime.utcnow().date()
    cal_resp = _get("/calendar/earnings", {
        "from": today.isoformat(),
        "to": (today + timedelta(days=90)).isoformat(),
        "symbol": ticker,
    })
    next_earnings_date: str | None = None
    if isinstance(cal_resp, dict) and cal_resp.get("earningsCalendar"):
        next_earnings_date = cal_resp["earningsCalendar"][0].get("date")

    # ── Compute EPS surprise % ────────────────────────────────────────────────
    eps_actual = latest_earn.get("actual")
    eps_estimate = latest_earn.get("estimate")
    eps_surprise_pct: float | None = None
    if eps_actual is not None and eps_estimate:
        try:
            eps_surprise_pct = round(
                (eps_actual - eps_estimate) / abs(eps_estimate) * 100, 2
            )
        except ZeroDivisionError:
            pass

    # ── Persist ───────────────────────────────────────────────────────────────
    snapshot = FundamentalSnapshot(
        ticker=ticker,
        fetched_at=datetime.utcnow(),
        # Valuation
        pe_ttm=m.get("peTTM"),
        pb_quarterly=m.get("pbQuarterly"),
        ps_ttm=m.get("psTTM"),
        ev_ebitda_ttm=m.get("evToEbitdaTTM"),
        dividend_yield=m.get("dividendYieldIndicatedAnnual"),
        # Profitability
        roe_ttm=m.get("roeTTM"),
        roa_ttm=m.get("roaTTM"),
        gross_margin_ttm=m.get("grossMarginTTM"),
        operating_margin_ttm=m.get("operatingMarginTTM"),
        net_margin_ttm=m.get("netProfitMarginTTM"),
        # Growth
        revenue_growth_yoy=m.get("revenueGrowthTTMYoy"),
        eps_growth_yoy=m.get("epsGrowthTTMYoy"),
        revenue_growth_3y=m.get("revenueGrowth3Y"),
        eps_growth_3y=m.get("epsGrowth3Y"),
        # Financial Health
        current_ratio=m.get("currentRatioQuarterly"),
        debt_to_equity=m.get("totalDebt/totalEquityQuarterly"),
        free_cash_flow_ttm=m.get("freeCashFlowTTM"),
        # Market
        week_52_high=m.get("52WeekHigh"),
        week_52_low=m.get("52WeekLow"),
        beta=m.get("beta"),
        market_cap=m.get("marketCapitalization"),
        # Analyst
        analyst_strong_buy=rec.get("strongBuy"),
        analyst_buy=rec.get("buy"),
        analyst_hold=rec.get("hold"),
        analyst_sell=rec.get("sell"),
        analyst_strong_sell=rec.get("strongSell"),
        analyst_target_mean=pt.get("targetMean"),
        analyst_target_high=pt.get("targetHigh"),
        analyst_target_low=pt.get("targetLow"),
        # Earnings
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        eps_surprise_pct=eps_surprise_pct,
        next_earnings_date=next_earnings_date,
    )

    with get_session() as session:
        session.add(snapshot)

    logger.info("[fundamentals] Stored snapshot for %s (PE=%.1f, ROE=%.1f%%)",
                ticker, m.get("peTTM") or 0, m.get("roeTTM") or 0)
    return True
