"""
Tests for the chat session/message persistence layer (PR 2):
  - storage.repository: create/get/list/update/delete chat_sessions + messages
  - api.routes.sessions: REST endpoints

DB tests use an isolated temporary SQLite file. Endpoint tests build a fresh
FastAPI app with the sessions router so they don't trigger the real startup
hook (which loads embeddings + scheduler).
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base


# ── DB fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def patch_session(tmp_session):
    @contextmanager
    def _fake():
        yield tmp_session
        tmp_session.commit()

    with patch("storage.repository.get_session", _fake):
        yield tmp_session


# ── Repository tests ──────────────────────────────────────────────────────────

class TestSessionRepository:
    def test_create_and_get(self, patch_session):
        from storage.repository import create_chat_session, get_chat_session
        create_chat_session("abc", "My Chat")
        row = get_chat_session("abc")
        assert row is not None
        assert row["id"] == "abc"
        assert row["title"] == "My Chat"
        assert row["archived"] is False

    def test_get_returns_none_for_missing(self, patch_session):
        from storage.repository import get_chat_session
        assert get_chat_session("nonexistent") is None

    def test_list_excludes_archived_by_default(self, patch_session):
        from storage.repository import (
            create_chat_session, update_chat_session, list_chat_sessions,
        )
        create_chat_session("a", "Active")
        create_chat_session("b", "Archived")
        update_chat_session("b", archived=True)

        active_only = list_chat_sessions()
        assert {s["id"] for s in active_only} == {"a"}

        with_archived = list_chat_sessions(include_archived=True)
        assert {s["id"] for s in with_archived} == {"a", "b"}

    def test_update_title_archived_last_ticker(self, patch_session):
        from storage.repository import (
            create_chat_session, update_chat_session, get_chat_session,
        )
        create_chat_session("x")
        ok = update_chat_session("x", title="Renamed", archived=True, last_ticker="AAPL")
        assert ok is True
        row = get_chat_session("x")
        assert row["title"] == "Renamed"
        assert row["archived"] is True
        assert row["last_ticker"] == "AAPL"

    def test_update_returns_false_for_missing(self, patch_session):
        from storage.repository import update_chat_session
        assert update_chat_session("nope", title="x") is False

    def test_delete_session_cascades_messages(self, patch_session, tmp_session):
        from storage.repository import (
            create_chat_session, add_chat_message,
            delete_chat_session, list_chat_messages,
        )
        from storage.models import ChatMessage, ChatSession
        create_chat_session("s1")
        add_chat_message("s1", "user", "hi")
        add_chat_message("s1", "assistant", "hello")

        ok = delete_chat_session("s1")
        assert ok is True
        assert list_chat_messages("s1") == []
        assert tmp_session.query(ChatSession).filter_by(id="s1").first() is None
        assert tmp_session.query(ChatMessage).filter_by(session_id="s1").count() == 0


class TestMessageRepository:
    def test_add_and_list(self, patch_session):
        from storage.repository import (
            create_chat_session, add_chat_message, list_chat_messages,
        )
        create_chat_session("s")
        add_chat_message("s", "user", "first")
        add_chat_message("s", "assistant", "reply", chart_json='{"mode":"single"}')

        msgs = list_chat_messages("s")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "first"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["chart_json"] == '{"mode":"single"}'

    def test_empty_session_returns_empty_list(self, patch_session):
        from storage.repository import create_chat_session, list_chat_messages
        create_chat_session("s")
        assert list_chat_messages("s") == []


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture()
def client(patch_session):
    from api.routes.sessions import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestSessionsAPI:
    def test_create_then_list(self, client):
        r = client.post("/api/sessions", json={"title": "First"})
        assert r.status_code == 200
        sid = r.json()["id"]

        r = client.get("/api/sessions")
        assert r.status_code == 200
        sessions_list = r.json()
        assert any(s["id"] == sid for s in sessions_list)
        assert any(s["title"] == "First" for s in sessions_list)

    def test_get_404_for_missing(self, client):
        r = client.get("/api/sessions/no-such-id")
        assert r.status_code == 404

    def test_patch_title(self, client):
        sid = client.post("/api/sessions", json={}).json()["id"]
        r = client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
        assert r.status_code == 200
        assert r.json()["title"] == "Renamed"

    def test_patch_archive_hides_from_default_list(self, client):
        sid = client.post("/api/sessions", json={"title": "to archive"}).json()["id"]
        client.patch(f"/api/sessions/{sid}", json={"archived": True})

        active = client.get("/api/sessions").json()
        assert all(s["id"] != sid for s in active)

        full = client.get("/api/sessions?include_archived=true").json()
        assert any(s["id"] == sid for s in full)

    def test_delete_removes_session_and_messages(self, client):
        from storage.repository import add_chat_message, list_chat_messages

        sid = client.post("/api/sessions", json={"title": "doomed"}).json()["id"]
        add_chat_message(sid, "user", "hi")

        r = client.delete(f"/api/sessions/{sid}")
        assert r.status_code == 200
        assert client.get(f"/api/sessions/{sid}").status_code == 404
        assert list_chat_messages(sid) == []

    def test_messages_404_for_missing_session(self, client):
        r = client.get("/api/sessions/missing/messages")
        assert r.status_code == 404
