from __future__ import annotations
import logging
import yfinance as yf
from datetime import datetime, timedelta
from storage.database import get_session
from storage.models import PriceBar
from sqlalchemy.dialects.sqlite import insert

logger = logging.getLogger(__name__)


def validate_ticker(ticker: str) -> bool:
    """Quick check: does this ticker actually exist on yfinance?
    Returns True if 5d history yields any rows. Used to gate auto-registration."""
    try:
        df = yf.Ticker(ticker.upper()).history(period="5d", interval="1d")
        return not df.empty
    except Exception as exc:
        logger.warning("[validate_ticker] %s: %s", ticker, exc)
        return False


def fetch_and_store(ticker: str, days_back: int = 90, interval: str = "1d",
                    from_date: datetime | None = None) -> int:
    """Fetch OHLCV from yfinance and upsert into DB. Returns rows stored.

    If from_date is provided, fetches from that date to today (incremental mode).
    Otherwise fetches the last days_back days (full mode).
    """
    yf_interval_map = {"1d": "1d", "1h": "1h"}
    yf_interval = yf_interval_map.get(interval, "1d")

    end = datetime.utcnow()
    start = from_date if from_date else end - timedelta(days=days_back)

    tk = yf.Ticker(ticker.upper())
    df = tk.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval=yf_interval)

    if df.empty:
        return 0

    df = df.reset_index()
    # Column names differ by interval
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"

    rows = []
    for _, row in df.iterrows():
        ts = row[ts_col]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        rows.append(
            {
                "ticker": ticker.upper(),
                "timestamp": ts,
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": float(row.get("Volume", 0)),
                "interval": interval,
                "source": "yfinance",
            }
        )

    if not rows:
        return 0

    with get_session() as session:
        stmt = insert(PriceBar).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "timestamp", "interval"])
        session.execute(stmt)

    return len(rows)
