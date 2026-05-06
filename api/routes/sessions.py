"""Session history endpoints (PR 2).

Sessions are listed in the right-rail history panel; messages are loaded
on demand when the user clicks a session.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage.repository import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_messages,
    list_chat_sessions,
    update_chat_session,
)

router = APIRouter()


class SessionPatch(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None


class CreateSessionBody(BaseModel):
    title: Optional[str] = None


@router.get("/api/sessions")
def list_sessions(include_archived: bool = False) -> list[dict]:
    return list_chat_sessions(include_archived=include_archived)


@router.post("/api/sessions")
def create_session(body: CreateSessionBody) -> dict:
    new_id = str(uuid.uuid4())
    title = body.title or "New chat"
    create_chat_session(new_id, title=title)
    row = get_chat_session(new_id)
    if row is None:
        raise HTTPException(500, "Failed to create session")
    return row


@router.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    row = get_chat_session(session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    return row


@router.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, patch: SessionPatch) -> dict:
    ok = update_chat_session(
        session_id,
        title=patch.title,
        archived=patch.archived,
    )
    if not ok:
        raise HTTPException(404, "Session not found")
    row = get_chat_session(session_id)
    return row  # type: ignore[return-value]


@router.delete("/api/sessions/{session_id}")
def remove_session(session_id: str) -> dict:
    ok = delete_chat_session(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"deleted": session_id}


@router.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str) -> list[dict]:
    if get_chat_session(session_id) is None:
        raise HTTPException(404, "Session not found")
    return list_chat_messages(session_id)
