from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    watched_tickers: str = "AAPL"   # comma-separated, e.g. "AAPL,NVDA,TSLA"
    anthropic_api_key: str = ""
    alpha_vantage_api_key: str = ""
    financial_juice_api_key: str = ""
    finnhub_api_key: str = ""
    fred_api_key: str = ""           # Federal Reserve Economic Data (free, instant signup)

    @property
    def ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.watched_tickers.split(",") if t.strip()]

    db_path: str = str(DATA_DIR / "stock.db")
    chroma_path: str = str(DATA_DIR / "chroma")

    claude_model: str = "claude-sonnet-4-6"
    embedding_model: str = "all-MiniLM-L6-v2"
    log_level: str = "INFO"
    sync_cron: str = "0 18 * * 1-5"

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
