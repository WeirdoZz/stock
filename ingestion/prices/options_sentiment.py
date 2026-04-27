"""
Fetch options market sentiment signals from Alpha Vantage.
- Put-Call Ratio (HISTORICAL_PUT_CALL_RATIO)
- Volume/OI Ratio (HISTORICAL_VOLUME_OPEN_INTEREST_RATIO)
Both work on free key; Vol/OI is subject to 25 req/day limit.
"""
from __future__ import annotations
import time
import requests
import urllib3
from config.settings import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AV_BASE = "https://www.alphavantage.co/query"

# In-memory cache: key → (result, expires_at)
_pcr_cache: dict[str, tuple[dict, float]] = {}
_PCR_TTL = 6 * 3600  # 6 hours — PCR doesn't change intraday


def get_put_call_ratio(ticker: str, date: str | None = None) -> dict:
    """
    Returns put-call ratio for the given ticker.
    date: 'YYYY-MM-DD' or None for latest session.
    Results are cached for 6 hours (PCR doesn't change intraday).

    Interpretation:
      PCR <= 0.6  → Bullish (more calls than puts)
      PCR ~0.7-1.0 → Neutral
      PCR >= 1.0  → Bearish (more puts than calls)
    Note: Extreme readings can be contrarian signals.
    """
    cache_key = f"{ticker.upper()}:{date or 'latest'}"
    now = time.time()
    cached = _pcr_cache.get(cache_key)
    if cached and now < cached[1]:
        return cached[0]

    if not settings.alpha_vantage_api_key:
        return {"error": "No Alpha Vantage API key configured"}

    params = {
        "function": "HISTORICAL_PUT_CALL_RATIO",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_api_key,
    }
    if date:
        params["date"] = date

    try:
        resp = requests.get(AV_BASE, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    if "Information" in data or "Note" in data:
        return {"error": data.get("Information") or data.get("Note")}

    pcr_value = float(data.get("put_call_ratio_full_chain", 0) or 0)

    # Interpret the signal
    if pcr_value <= 0.6:
        signal = "BULLISH"
        interpretation = f"Low PCR ({pcr_value:.2f}) — significantly more calls than puts, options market is bullish"
    elif pcr_value >= 1.0:
        signal = "BEARISH"
        interpretation = f"High PCR ({pcr_value:.2f}) — more puts than calls, options market is bearish"
    else:
        signal = "NEUTRAL"
        interpretation = f"Neutral PCR ({pcr_value:.2f}) — balanced options market sentiment"

    # Nearest expirations (next 4)
    by_expiry = data.get("put_call_ratio_by_expiration", [])[:4]

    result = {
        "ticker": ticker.upper(),
        "date": data.get("date", "latest"),
        "put_call_ratio": pcr_value,
        "signal": signal,
        "interpretation": interpretation,
        "by_expiration": by_expiry,
    }
    _pcr_cache[cache_key] = (result, now + _PCR_TTL)
    return result


def get_volume_oi_ratio(ticker: str, date: str | None = None) -> dict:
    """
    Returns volume-to-open-interest ratio.
    High ratio = heavy speculation / possible trend change.
    Low ratio  = stable positions, lower volatility.
    """
    if not settings.alpha_vantage_api_key:
        return {"error": "No Alpha Vantage API key configured"}

    params = {
        "function": "HISTORICAL_VOLUME_OPEN_INTEREST_RATIO",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_api_key,
    }
    if date:
        params["date"] = date

    try:
        resp = requests.get(AV_BASE, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    if "Information" in data or "Note" in data:
        return {"error": data.get("Information") or data.get("Note")}

    return data
