"""
Stock analysis agent.
Architecture: Python runs all 4 tools, sends one consolidated prompt to Zoom/Anthropic for final analysis.
This avoids multi-turn context accumulation issues with stateless LLM backends.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from agent.zoom_client import ZoomLLMClient, TextBlock
from agent.tool_executor import execute_tool
from agent.prompts import ANALYSIS_PROMPT
from config.settings import settings


# ── LLM client factory ────────────────────────────────────────────────────────

def _build_llm_client():
    backend = os.environ.get("LLM_BACKEND", "zoom").lower()

    if backend == "zoom":
        zoom_token = os.environ.get("ZOOM_TOKEN", "")
        zoom_agent_id = os.environ.get("ZOOM_AGENT_ID", "")
        zoom_base_url = os.environ.get("ZOOM_BASE_URL", "https://eng.corp.zoom.com")
        if not zoom_token or not zoom_agent_id:
            raise RuntimeError("LLM_BACKEND=zoom but ZOOM_TOKEN or ZOOM_AGENT_ID is missing in .env")
        print(f"[agent] Backend: Zoom AI  (agent_id={zoom_agent_id[:8]}...)")
        return ZoomLLMClient(token=zoom_token, agent_id=zoom_agent_id, base_url=zoom_base_url)

    elif backend == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_BACKEND=anthropic but ANTHROPIC_API_KEY is not set in .env")
        print(f"[agent] Backend: Anthropic  (model={settings.claude_model})")
        return _AnthropicAdapter(settings.anthropic_api_key, settings.claude_model)

    elif backend == "aliyun":
        aliyun_key = os.environ.get("ALIYUN_API_KEY", "")
        if not aliyun_key:
            raise RuntimeError("LLM_BACKEND=aliyun but ALIYUN_API_KEY is not set in .env")
        print(f"[agent] Backend: Aliyun DashScope  (model=qwen-plus)")
        return _AliyunAdapter(aliyun_key)

    raise RuntimeError(f"Unknown LLM_BACKEND={backend!r}. Use 'zoom', 'anthropic', or 'aliyun'.")


class _AnthropicAdapter:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def complete(self, messages, system_prompt, tools):
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
        content = [TextBlock(text=b.text) for b in resp.content if b.type == "text"]
        from agent.zoom_client import LLMResponse
        return LLMResponse(stop_reason="end_turn", content=content)

    async def stream_complete(self, messages, system_prompt="", tools=None):
        """Fallback: call complete() and yield the full text as one chunk."""
        response = await self.complete(messages, system_prompt, tools or [])
        for block in response.content:
            if isinstance(block, TextBlock):
                yield block.text


class _AliyunAdapter:
    """DashScope (Aliyun) adapter — OpenAI-compatible endpoint, qwen-plus model."""
    _BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    _MODEL = "qwen-plus"

    def __init__(self, api_key: str):
        import httpx
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._BASE_URL,
            http_client=httpx.AsyncClient(verify=False),
        )

    def _build_messages(self, messages: list[dict], system_prompt: str) -> list[dict]:
        full: list[dict] = []
        if system_prompt:
            full.append({"role": "system", "content": system_prompt})
        full.extend(messages)
        return full

    async def complete(self, messages, system_prompt="", tools=None):
        resp = await self._client.chat.completions.create(
            model=self._MODEL,
            messages=self._build_messages(messages, system_prompt),
            max_tokens=4096,
        )
        text = resp.choices[0].message.content or ""
        from agent.zoom_client import LLMResponse
        return LLMResponse(stop_reason="end_turn", content=[TextBlock(text=text)])

    async def stream_complete(self, messages, system_prompt="", tools=None):
        stream = await self._client.chat.completions.create(
            model=self._MODEL,
            messages=self._build_messages(messages, system_prompt),
            max_tokens=4096,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Tool runner (Python-side, no LLM involvement) ─────────────────────────────

def _run_all_tools(ticker: str, verbose: bool) -> dict:
    """Run all 4 tools in Python and return their results."""
    results = {}

    if verbose:
        print(f"[tools] fetch_current_news({ticker}, 72h)")
    raw = execute_tool("fetch_current_news", {"ticker": ticker, "hours_back": 72})
    data = json.loads(raw)
    articles = data.get("articles", [])
    results["news"] = {
        "count": data.get("count", 0),
        "articles": [
            {
                "headline": a["headline"],
                "published_at": a["published_at"],
                "sentiment_label": a.get("sentiment_label"),
                "sentiment_score": a.get("sentiment_score"),
                "source": a.get("source"),
            }
            for a in articles[:20]  # top 20
        ],
    }

    top_headlines = [a["headline"] for a in articles[:8]]

    if verbose:
        print(f"[tools] search_similar_historical_events({ticker})")
    raw = execute_tool("search_similar_historical_events", {
        "ticker": ticker,
        "headlines": top_headlines,
        "n_results": 8,
    })
    data = json.loads(raw)
    results["similar"] = {
        "similar_events_found": data.get("similar_events_found", 0),
        "similar_events": data.get("similar_events", []),
        "aggregate_stats": data.get("aggregate_stats", {}),
    }

    if verbose:
        print(f"[tools] get_price_history({ticker}, 14d)")
    raw = execute_tool("get_price_history", {"ticker": ticker, "days_back": 14, "interval": "1d"})
    data = json.loads(raw)
    bars = data.get("bars", [])
    results["prices"] = {
        "count": data.get("count", 0),
        "interval": data.get("interval"),
        "bars": [
            {"timestamp": b["timestamp"], "close": b["close"], "volume": b["volume"]}
            for b in bars
        ],
    }

    if verbose:
        print(f"[tools] get_correlation_stats({ticker})")
    raw = execute_tool("get_correlation_stats", {"ticker": ticker})
    results["correlation_stats"] = json.loads(raw)

    if verbose:
        print(f"[tools] get_put_call_ratio({ticker})")
    from ingestion.prices.options_sentiment import get_put_call_ratio
    results["put_call_ratio"] = get_put_call_ratio(ticker)

    if verbose:
        print(f"[tools] get_insider_transactions({ticker})")
    from ingestion.news.finnhub_news import get_insider_transactions
    results["insider_transactions"] = get_insider_transactions(ticker)

    return results


# ── Main entry point ──────────────────────────────────────────────────────────

async def _run_query_async(ticker: str, verbose: bool = False, reply_language: str = "English") -> str:
    ticker = ticker.upper()

    # Step 1: Run all tools in Python
    tool_data = _run_all_tools(ticker, verbose)

    # Step 2: Build a single consolidated prompt with all data
    prompt = ANALYSIS_PROMPT.format(
        ticker=ticker,
        reply_language=reply_language,
        news_json=json.dumps(tool_data["news"], indent=2),
        similar_json=json.dumps(tool_data["similar"], indent=2),
        prices_json=json.dumps(tool_data["prices"], indent=2),
        corr_json=json.dumps(tool_data["correlation_stats"], indent=2),
        pcr_json=json.dumps(tool_data["put_call_ratio"], indent=2),
        insider_json=json.dumps(tool_data["insider_transactions"], indent=2),
    )

    # Step 3: Ask LLM for one-shot analysis
    llm = _build_llm_client()
    if verbose:
        print(f"[agent] Sending analysis request to LLM...")

    response = await llm.complete(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are a rigorous stock trend analyst. Write a structured analysis based solely on the data provided. Never fabricate data.",
        tools=[],
    )

    text_blocks = [b for b in response.content if isinstance(b, TextBlock)]
    return "\n".join(b.text for b in text_blocks)


def run_query(ticker: str, verbose: bool = False) -> str:
    return asyncio.run(_run_query_async(ticker, verbose))


async def run_query_stream(ticker: str, verbose: bool = False, reply_language: str = "English"):
    """Async generator yielding status updates and LLM chunks for streaming."""
    ticker = ticker.upper()
    yield {"type": "status", "content": "Collecting market data..."}
    loop = asyncio.get_event_loop()
    tool_data = await loop.run_in_executor(None, _run_all_tools, ticker, verbose)
    yield {"type": "status", "content": "Analyzing with AI..."}
    prompt = ANALYSIS_PROMPT.format(
        ticker=ticker,
        reply_language=reply_language,
        news_json=json.dumps(tool_data["news"], indent=2),
        similar_json=json.dumps(tool_data["similar"], indent=2),
        prices_json=json.dumps(tool_data["prices"], indent=2),
        corr_json=json.dumps(tool_data["correlation_stats"], indent=2),
        pcr_json=json.dumps(tool_data["put_call_ratio"], indent=2),
        insider_json=json.dumps(tool_data["insider_transactions"], indent=2),
    )
    llm = _build_llm_client()
    async for chunk in llm.stream_complete(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are a rigorous stock trend analyst. Write a structured analysis based solely on the data provided. Never fabricate data.",
    ):
        yield {"type": "chunk", "content": chunk}
    yield {"type": "done", "content": ""}
