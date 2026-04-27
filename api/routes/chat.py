"""POST /api/chat — streaming analysis via SSE."""
from __future__ import annotations

import json
import logging
import re
import traceback

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.models import ChatRequest
from api import session as sessions
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Chinese name → ticker alias map
_ALIASES = {
    "苹果": "AAPL",
    "英伟达": "NVDA",
    "特斯拉": "TSLA",
    "谷歌": "GOOGL",
    "微软": "MSFT",
    "亚马逊": "AMZN",
}

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b", re.ASCII)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


def _detect_language(text: str) -> str:
    return "Chinese" if _CJK_RE.search(text) else "English"


def _extract_ticker(text: str, ticker_list: list):
    for alias, ticker in _ALIASES.items():
        if alias in text and ticker in ticker_list:
            logger.debug("[chat] ticker via alias: %s -> %s", alias, ticker)
            return ticker
    for match in _TICKER_RE.finditer(text):
        candidate = match.group(1)
        if candidate in ticker_list:
            logger.debug("[chat] ticker via regex: %s", candidate)
            return candidate
    return None


def _extract_comparison_tickers(text: str, ticker_list: list) -> tuple[str, str] | None:
    """Return (ticker_a, ticker_b) if the message references two distinct tracked tickers."""
    found: list[str] = []
    for alias, ticker in _ALIASES.items():
        if alias in text and ticker in ticker_list and ticker not in found:
            found.append(ticker)
    for match in _TICKER_RE.finditer(text):
        t = match.group(1)
        if t in ticker_list and t not in found:
            found.append(t)
    if len(found) >= 2:
        logger.debug("[chat] comparison tickers: %s vs %s", found[0], found[1])
        return found[0], found[1]
    return None


@router.post("/api/chat")
async def chat(req: ChatRequest):
    ticker_list = settings.ticker_list
    logger.debug("[chat] message=%r  session_id=%r", req.message, req.session_id)

    session_id, entry = sessions.get_or_create(req.session_id)
    logger.debug("[chat] session=%s  last_ticker=%s", session_id, entry.last_ticker)

    async def event_stream():
        yield {"data": json.dumps({"type": "session", "content": "", "session_id": session_id})}

        lang = _detect_language(req.message)

        # ── Comparison path: two tickers detected ────────────────────────────
        comp = _extract_comparison_tickers(req.message, ticker_list)
        if comp:
            ticker_a, ticker_b = comp
            entry.messages.append({"role": "user", "content": req.message})
            sessions.trim_messages(entry)
            try:
                from agent.agent import run_comparison_stream
                full_response = ""
                async for event in run_comparison_stream(ticker_a, ticker_b, reply_language=lang):
                    logger.debug("[chat] comparison event type=%s", event["type"])
                    yield {"data": json.dumps(event)}
                    if event["type"] == "chunk":
                        full_response += event["content"]
                entry.messages.append({"role": "assistant", "content": full_response})
                entry.last_ticker = None  # no single active ticker after comparison
                sessions.save(session_id, entry)
            except Exception as exc:
                logger.error("[chat] comparison exception: %s\n%s", exc, traceback.format_exc())
                yield {"data": json.dumps({"type": "error", "content": f"Error: {exc}"})}
            return

        # ── Single ticker path ───────────────────────────────────────────────
        ticker = _extract_ticker(req.message, ticker_list)
        is_followup = False
        logger.debug("[chat] extracted ticker=%s", ticker)

        if ticker is None:
            if entry.last_ticker:
                ticker = entry.last_ticker
                is_followup = True
                logger.debug("[chat] fallback to session ticker=%s (follow-up)", ticker)
            else:
                tracked = ", ".join(ticker_list)
                logger.debug("[chat] no ticker found, returning error")
                yield {"data": json.dumps({"type": "error", "content": f"Which ticker? I track: {tracked}"})}
                return

        entry.messages.append({"role": "user", "content": req.message})
        sessions.trim_messages(entry)

        try:
            if is_followup and entry.messages:
                logger.debug("[chat] follow-up path, building lightweight prompt")
                prior_ctx = "\n".join(
                    f"{m['role'].capitalize()}: {m['content']}"
                    for m in entry.messages[:-1]
                )
                prompt = f"Prior analysis context:\n{prior_ctx}\n\nQuestion: {req.message}"
                yield {"data": json.dumps({"type": "status", "content": "Thinking..."})}

                from agent.agent import _build_llm_client
                logger.debug("[chat] building llm client")
                llm = _build_llm_client()
                full_response = ""
                logger.debug("[chat] starting stream_complete (follow-up)")
                async for chunk in llm.stream_complete(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="You are a rigorous stock trend analyst.",
                ):
                    logger.debug("[chat] follow-up chunk len=%d", len(chunk))
                    full_response += chunk
                    yield {"data": json.dumps({"type": "chunk", "content": chunk})}

                entry.messages.append({"role": "assistant", "content": full_response})

            else:
                logger.debug("[chat] full pipeline path for ticker=%s", ticker)
                from agent.agent import run_query_stream
                logger.debug("[chat] reply_language=%s", lang)
                full_response = ""
                async for event in run_query_stream(ticker, reply_language=lang):
                    logger.debug("[chat] pipeline event type=%s len=%d",
                                 event["type"], len(event.get("content", "")))
                    yield {"data": json.dumps(event)}
                    if event["type"] == "chunk":
                        full_response += event["content"]

                entry.messages.append({"role": "assistant", "content": full_response})

            entry.last_ticker = ticker
            sessions.save(session_id, entry)
            logger.debug("[chat] done, saved session")

        except Exception as exc:
            logger.error("[chat] exception: %s\n%s", exc, traceback.format_exc())
            yield {"data": json.dumps({"type": "error", "content": f"Error: {exc}"})}
            return

        yield {"data": json.dumps({"type": "done", "content": ""})}

    return EventSourceResponse(event_stream())
