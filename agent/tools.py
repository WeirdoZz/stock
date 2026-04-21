"""Claude tool schemas for the stock analysis agent."""

TOOLS = [
    {
        "name": "fetch_current_news",
        "description": (
            "Retrieve recent news articles for a stock ticker from the local database. "
            "Returns headlines, summaries, sentiment scores, and publication timestamps. "
            "Use this first to understand what news is currently driving the stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol (e.g. AAPL, NVDA, TSLA).",
                },
                "hours_back": {
                    "type": "integer",
                    "description": "How many hours back to look for news (default 48).",
                    "default": 48,
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_price_history",
        "description": (
            "Retrieve historical OHLCV price bars for a ticker. "
            "Use this to assess current momentum, recent trend, and volatility."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol.",
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of calendar days to look back (default 14).",
                    "default": 14,
                },
                "interval": {
                    "type": "string",
                    "description": "Bar interval: '1d' for daily or '1h' for hourly.",
                    "enum": ["1d", "1h"],
                    "default": "1d",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_correlation_stats",
        "description": (
            "Get aggregate historical statistics about how news correlated with price moves "
            "for this ticker. Returns counts of bullish/bearish news events and their average "
            "next-day price changes. Use this to ground your confidence estimate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "search_similar_historical_events",
        "description": (
            "Semantically search past news articles similar to the provided headlines and "
            "return what the stock price did afterward. Use this to find historical precedents "
            "for the current news cycle and estimate the probability of an up/down move."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol.",
                },
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of current news headlines to find historical analogues for.",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Max number of similar past events to return (default 8).",
                    "default": 8,
                },
            },
            "required": ["ticker", "headlines"],
        },
    },
]
