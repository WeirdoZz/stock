"""DB-backed chat session store.

Sessions and messages live in `chat_sessions` / `chat_messages` (see
`storage/models.py`). This module exposes the small surface that the chat
endpoint actually needs: load-or-create-session, append-message, etc.

`SessionEntry` mirrors the in-memory dataclass we used to have so chat.py
can keep its existing access patterns (entry.messages, entry.last_ticker).
The only difference: `save()` now writes to the DB.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from storage.repository import (
    create_chat_session,
    get_chat_session,
    list_chat_messages,
    add_chat_message,
    update_chat_session,
)

# How many messages to load back into the working context for follow-ups.
# Older messages stay in DB (for the history sidebar) but are dropped from
# the LLM prompt to keep token usage bounded.
PROMPT_CONTEXT_WINDOW = 20


@dataclass
class SessionEntry:
    id: str
    messages: list = field(default_factory=list)   # list[{"role", "content"}]
    last_ticker: Optional[str] = None


def get_or_create(session_id: Optional[str]) -> tuple[str, SessionEntry]:
    """Load an existing session from the DB (with its recent messages) or
    create a new one. Returns (session_id, entry)."""
    if session_id:
        row = get_chat_session(session_id)
        if row is not None:
            messages = [
                {"role": m["role"], "content": m["content"]}
                for m in list_chat_messages(session_id)
            ]
            entry = SessionEntry(
                id=session_id,
                messages=messages,
                last_ticker=row.get("last_ticker"),
            )
            return session_id, entry

    new_id = str(uuid.uuid4())
    create_chat_session(new_id)
    return new_id, SessionEntry(id=new_id)


def save(entry: SessionEntry) -> None:
    """Bump last_active_at + persist last_ticker. Messages are written
    directly via `append_message()` from chat.py as they happen."""
    update_chat_session(
        entry.id,
        last_ticker=entry.last_ticker,
        bump_active=True,
    )


def append_message(entry: SessionEntry, role: str, content: str,
                   chart_json: Optional[str] = None) -> None:
    """Append a message to the in-memory entry AND persist it to the DB."""
    entry.messages.append({"role": role, "content": content})
    add_chat_message(entry.id, role, content, chart_json=chart_json)


def trim_messages(entry: SessionEntry) -> None:
    """Cap the in-memory `messages` list (used for prompt context). DB rows
    are NOT deleted — the full history stays available for the sidebar."""
    while len(entry.messages) > PROMPT_CONTEXT_WINDOW:
        entry.messages.pop(0)
        if entry.messages:
            entry.messages.pop(0)


def update_title_from_first_message(entry: SessionEntry, content: str) -> None:
    """Auto-title a session based on the first user message (truncated).
    Idempotent: only fires when the title is still the default."""
    row = get_chat_session(entry.id)
    if row is None or row["title"] != "New chat":
        return
    title = content.strip().splitlines()[0][:60] if content.strip() else "New chat"
    update_chat_session(entry.id, title=title)
