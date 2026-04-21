"""In-memory session store. TTL: 1 hour, max 20 messages per session."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

TTL_SECONDS = 3600
MAX_MESSAGES = 20

_sessions: dict = {}


@dataclass
class SessionEntry:
    messages: list = field(default_factory=list)
    last_ticker: Optional[str] = None
    last_accessed: float = field(default_factory=time.time)


def get_or_create(session_id: Optional[str]):
    """Return existing session or create a new one. Always evicts stale first."""
    _evict_stale()
    if session_id and session_id in _sessions:
        entry = _sessions[session_id]
        entry.last_accessed = time.time()
        return session_id, entry
    new_id = str(uuid.uuid4())
    entry = SessionEntry()
    _sessions[new_id] = entry
    return new_id, entry


def save(session_id: str, entry: SessionEntry) -> None:
    entry.last_accessed = time.time()
    _sessions[session_id] = entry


def trim_messages(entry: SessionEntry) -> None:
    """Enforce MAX_MESSAGES by dropping oldest user+assistant pairs."""
    while len(entry.messages) > MAX_MESSAGES:
        entry.messages.pop(0)
        if entry.messages:
            entry.messages.pop(0)


def _evict_stale() -> None:
    cutoff = time.time() - TTL_SECONDS
    stale = [k for k, v in _sessions.items() if v.last_accessed < cutoff]
    for k in stale:
        del _sessions[k]
