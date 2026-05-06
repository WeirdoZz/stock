"""
Options market structure signals derived entirely from yfinance (no extra API key).

Calculates for the nearest 1-2 expirations:
  - Max Pain  : strike where option-buyer collective intrinsic value is minimised
                (theory: spot gravitates here into expiry as MMs delta-hedge)
  - GEX       : net Gamma Exposure in USD millions
                Positive GEX → MMs long gamma → they BUY dips, SELL rips → dampens moves
                Negative GEX → MMs short gamma → they amplify directional moves
  - Key levels: top call gamma strikes (overhead resistance) and put gamma strikes (support)

Results cached 1 hour — options chain downloads are slow (~1-2s per expiry).
"""
from __future__ import annotations

import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)

_options_cache: dict[str, tuple[dict, float]] = {}
_OPTIONS_TTL = 3600  # 1 hour


# ── Calculations ──────────────────────────────────────────────────────────────

def _max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    """Strike minimising total intrinsic value for all option buyers."""
    strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
    if not strikes:
        return None
    call_oi = dict(zip(calls["strike"], calls["openInterest"].fillna(0)))
    put_oi  = dict(zip(puts["strike"],  puts["openInterest"].fillna(0)))

    pain = {}
    for K in strikes:
        # Calls with strike < K are ITM; puts with strike > K are ITM
        pain[K] = (
            sum(max(K - s, 0) * call_oi.get(s, 0) for s in strikes)
            + sum(max(s - K, 0) * put_oi.get(s, 0) for s in strikes)
        ) * 100  # each contract = 100 shares
    return min(pain, key=pain.get)


def _gex(calls: pd.DataFrame, puts: pd.DataFrame, spot: float) -> dict:
    """Net gamma exposure. Returns gex_available=False when gamma is absent."""
    if "gamma" not in calls.columns or calls["gamma"].isna().all():
        return {"gex_available": False}

    c, p = calls.copy(), puts.copy()
    c["gex"] = c["gamma"].fillna(0) * c["openInterest"].fillna(0) * 100 * spot
    p["gex"] = p["gamma"].fillna(0) * p["openInterest"].fillna(0) * 100 * spot

    net = c["gex"].sum() - p["gex"].sum()

    def top3(df):
        return [
            {"strike": row["strike"], "gex_M": round(row["gex"] / 1e6, 2)}
            for _, row in df.nlargest(3, "gex").iterrows()
        ]

    return {
        "gex_available": True,
        "net_gex_millions": round(net / 1e6, 2),
        "gex_signal": "STABILIZING" if net > 0 else "AMPLIFYING",
        "top_call_gamma_strikes": top3(c),   # overhead resistance
        "top_put_gamma_strikes":  top3(p),   # downside support
    }


def _interpret(exp: dict, spot: float) -> str:
    parts: list[str] = []
    mp = exp.get("max_pain")
    if mp:
        dist = round((mp - spot) / spot * 100, 2)
        parts.append(
            f"Max Pain ${mp:.1f} ({abs(dist):.1f}% "
            f"{'above' if dist > 0 else 'below'} spot)"
        )
    sig = exp.get("gex_signal")
    val = exp.get("net_gex_millions")
    if sig and val is not None:
        verb = "dampening" if sig == "STABILIZING" else "amplifying"
        parts.append(f"GEX {sig} (net {val:+.1f}M → MMs {verb} moves)")
    return "; ".join(parts) if parts else "Insufficient data"


# ── Public API ────────────────────────────────────────────────────────────────

def get_options_structure(ticker: str) -> dict:
    """Return Max Pain + GEX for nearest 2 expirations. Cached 1 hour."""
    ticker = ticker.upper()
    now = time.time()
    cached = _options_cache.get(ticker)
    if cached and now < cached[1]:
        return cached[0]

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        spot = info.get("currentPrice") or info.get("regularMarketPrice")

        expirations = t.options
        if not expirations or not spot:
            result: dict = {"error": "No options data or spot price unavailable"}
            _options_cache[ticker] = (result, now + _OPTIONS_TTL)
            return result

        per_exp = []
        for exp_date in expirations[:2]:
            chain = t.option_chain(exp_date)
            mp  = _max_pain(chain.calls, chain.puts)
            gex = _gex(chain.calls, chain.puts, spot)
            per_exp.append({
                "expiration": exp_date,
                "max_pain": mp,
                "max_pain_distance_pct": (
                    round((mp - spot) / spot * 100, 2) if mp else None
                ),
                **gex,
            })

        result = {
            "ticker": ticker,
            "spot_price": spot,
            "nearest_expiration":  per_exp[0] if per_exp else None,
            "second_expiration":   per_exp[1] if len(per_exp) > 1 else None,
            "summary": _interpret(per_exp[0], spot) if per_exp else "No data",
        }

    except Exception as exc:
        logger.warning("[options_structure] %s: %s", ticker, exc)
        result = {"error": str(exc)}

    _options_cache[ticker] = (result, now + _OPTIONS_TTL)
    return result
