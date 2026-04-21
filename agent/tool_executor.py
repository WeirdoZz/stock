from __future__ import annotations
import json
from storage import repository
from storage.vector_store import search_similar
from storage.repository import get_news_article_by_ids


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the appropriate function and return JSON string result."""
    try:
        result = _dispatch(tool_name, tool_input)
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, default=str, indent=2)


def _dispatch(tool_name: str, tool_input: dict):
    if tool_name == "fetch_current_news":
        ticker = tool_input["ticker"]
        hours_back = tool_input.get("hours_back", 48)
        articles = repository.get_recent_news(ticker, hours_back=hours_back)
        return {
            "ticker": ticker.upper(),
            "hours_back": hours_back,
            "count": len(articles),
            "articles": articles,
        }

    elif tool_name == "get_price_history":
        ticker = tool_input["ticker"]
        days_back = tool_input.get("days_back", 14)
        interval = tool_input.get("interval", "1d")
        bars = repository.get_price_history(ticker, days_back=days_back, interval=interval)
        return {
            "ticker": ticker.upper(),
            "days_back": days_back,
            "interval": interval,
            "count": len(bars),
            "bars": bars,
        }

    elif tool_name == "get_correlation_stats":
        ticker = tool_input["ticker"]
        stats = repository.get_correlation_stats(ticker)
        return stats

    elif tool_name == "search_similar_historical_events":
        ticker = tool_input["ticker"]
        headlines = tool_input["headlines"]
        n_results = tool_input.get("n_results", 8)

        similar = search_similar(headlines, ticker=ticker, n_results=n_results)

        # Enrich with correlation data
        ids = [s["id"] for s in similar]
        article_data = {a["id"]: a for a in get_news_article_by_ids(ids)}
        corr_stats = repository.get_correlation_stats(ticker)

        enriched = []
        for s in similar:
            art = article_data.get(s["id"], {})
            enriched.append(
                {
                    "headline": s["headline"],
                    "published_at": s["published_at"],
                    "similarity_score": s["similarity"],
                    "sentiment_label": s["sentiment_label"],
                }
            )

        return {
            "ticker": ticker.upper(),
            "query_headlines": headlines,
            "similar_events_found": len(enriched),
            "similar_events": enriched,
            "aggregate_stats": corr_stats,
        }

    else:
        return {"error": f"Unknown tool: {tool_name}"}
