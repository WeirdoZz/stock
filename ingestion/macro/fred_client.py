"""FRED (Federal Reserve Economic Data) ingestion.

Free API: https://fred.stlouisfed.org/docs/api/api_key.html (instant signup).
Rate limit is generous; we only pull 6 series and skip the call entirely when
recent data is on hand. Stores into `macro_snapshots` keyed by (series_id, date).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date as _date

import requests
import urllib3

from config.settings import settings
from storage.repository import (
    get_macro_fetched_at, upsert_macro_observations,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

# Series → human label. CPI pulls 18 months so YoY can be computed even
# when the latest observation is right at month boundary; everything else
# only needs a recent window.
SERIES = {
    "DFF":      {"label": "Fed Funds Rate (effective)",    "lookback_days": 30},
    "DGS10":    {"label": "10-Year Treasury Yield",        "lookback_days": 30},
    "DGS2":     {"label": "2-Year Treasury Yield",         "lookback_days": 30},
    "CPIAUCSL": {"label": "CPI All Urban Consumers",       "lookback_days": 540},
    "UNRATE":   {"label": "Unemployment Rate",             "lookback_days": 90},
    "VIXCLS":   {"label": "CBOE VIX",                       "lookback_days": 30},
}

# How fresh is "fresh enough" — skip the refresh if the most recent fetch was
# within this window. Macro series update slowly (daily at fastest).
DEFAULT_TTL = timedelta(hours=12)


def is_macro_stale(ttl: timedelta = DEFAULT_TTL) -> bool:
    last = get_macro_fetched_at()
    if last is None:
        return True
    return datetime.utcnow() - last > ttl


def _fetch_series(series_id: str, lookback_days: int) -> list[dict]:
    """Hit the FRED observations endpoint for one series. Returns a list of
    `{"date": date, "value": float}` (NaN entries filtered out)."""
    start = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    resp = requests.get(
        f"{FRED_BASE}/series/observations",
        params={
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "observation_start": start,
        },
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()
    payload = resp.json()
    out: list[dict] = []
    for o in payload.get("observations", []):
        raw = o.get("value")
        if raw is None or raw == "." or raw == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        try:
            d = _date.fromisoformat(o["date"])
        except (KeyError, ValueError):
            continue
        out.append({"date": d, "value": v})
    return out


def fetch_and_store(force: bool = False) -> dict:
    """Refresh every tracked FRED series unless we already pulled recently
    (or `force=True`). Returns `{series_id: rows_written}`; an empty dict
    means we skipped or no API key is configured."""
    if not settings.fred_api_key:
        logger.warning("[fred] FRED_API_KEY not set — skipping macro refresh")
        return {}
    if not force and not is_macro_stale():
        logger.info("[fred] macro data already fresh, skipping")
        return {}

    counts: dict[str, int] = {}
    for series_id, meta in SERIES.items():
        try:
            obs = _fetch_series(series_id, meta["lookback_days"])
            counts[series_id] = upsert_macro_observations(series_id, obs)
        except Exception as exc:  # one failed series doesn't kill the others
            logger.warning("[fred] %s failed: %s", series_id, exc)
            counts[series_id] = 0
    total = sum(counts.values())
    logger.info("[fred] refreshed %d series, %d total rows upserted", len(counts), total)
    return counts
