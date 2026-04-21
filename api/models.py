from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatChunk(BaseModel):
    type: str  # "session" | "status" | "chunk" | "done" | "error"
    content: str
    session_id: Optional[str] = None


class TickerStatus(BaseModel):
    ticker: str
    news_count: int
    price_count: int
    correlation_count: int
    embedded_count: int
    last_price_date: Optional[str]
    last_news_date: Optional[str]
    days_stale: Optional[int]
