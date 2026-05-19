"""Tests for plans repo + REST endpoints (PR 3)."""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base


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


@pytest.fixture()
def client(patch_session):
    from api.routes.plans import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── Repository ────────────────────────────────────────────────────────────────

class TestPlanRepository:
    def test_create_and_list(self, patch_session):
        from storage.repository import create_plan, list_plans
        p = create_plan("aapl", "buy", target_price=180.0, quantity=10)
        assert p["ticker"] == "AAPL"   # uppercased
        assert p["action"] == "buy"
        assert p["target_price"] == 180.0
        assert p["status"] == "pending"

        rows = list_plans()
        assert len(rows) == 1
        assert rows[0]["id"] == p["id"]

    def test_invalid_action_rejected(self, patch_session):
        from storage.repository import create_plan
        with pytest.raises(ValueError):
            create_plan("AAPL", "yolo")

    def test_invalid_status_rejected(self, patch_session):
        from storage.repository import create_plan
        with pytest.raises(ValueError):
            create_plan("AAPL", "buy", status="halfway")

    def test_list_filters_by_ticker_and_status(self, patch_session):
        from storage.repository import create_plan, list_plans
        create_plan("AAPL", "buy")
        create_plan("AAPL", "sell", status="completed")
        create_plan("NVDA", "watch")

        assert len(list_plans(ticker="AAPL")) == 2
        assert len(list_plans(status="pending")) == 2
        assert len(list_plans(ticker="aapl", status="completed")) == 1

    def test_update_changes_fields_and_bumps_updated_at(self, patch_session):
        from storage.repository import create_plan, update_plan, get_plan
        p = create_plan("AAPL", "buy")
        original_updated = p["updated_at"]

        out = update_plan(p["id"], status="completed", note="filled at $179")
        assert out is not None
        assert out["status"] == "completed"
        assert out["note"] == "filled at $179"
        assert out["updated_at"] >= original_updated

    def test_update_rejects_invalid_action(self, patch_session):
        from storage.repository import create_plan, update_plan
        p = create_plan("AAPL", "buy")
        with pytest.raises(ValueError):
            update_plan(p["id"], action="????")

    def test_update_returns_none_for_missing(self, patch_session):
        from storage.repository import update_plan
        assert update_plan(9999, status="completed") is None

    def test_delete_removes_row(self, patch_session):
        from storage.repository import create_plan, delete_plan, get_plan
        p = create_plan("AAPL", "buy")
        assert delete_plan(p["id"]) is True
        assert get_plan(p["id"]) is None

    def test_delete_missing_returns_false(self, patch_session):
        from storage.repository import delete_plan
        assert delete_plan(9999) is False

    def test_count_pending_groups_by_ticker(self, patch_session):
        from storage.repository import create_plan, count_pending_plans_by_ticker
        create_plan("AAPL", "buy")
        create_plan("AAPL", "watch")
        create_plan("AAPL", "sell", status="completed")  # not counted
        create_plan("NVDA", "buy")
        counts = count_pending_plans_by_ticker()
        assert counts == {"AAPL": 2, "NVDA": 1}


# ── REST endpoints ────────────────────────────────────────────────────────────

class TestPlansEndpoints:
    def test_create_then_list(self, client):
        r = client.post("/api/plans", json={
            "ticker": "AAPL", "action": "buy", "target_price": 180,
        })
        assert r.status_code == 200
        pid = r.json()["id"]

        rows = client.get("/api/plans").json()
        assert any(p["id"] == pid for p in rows)

    def test_create_rejects_bad_action(self, client):
        r = client.post("/api/plans", json={"ticker": "AAPL", "action": "yolo"})
        assert r.status_code == 400

    def test_get_404_for_missing(self, client):
        assert client.get("/api/plans/9999").status_code == 404

    def test_patch_updates_fields(self, client):
        pid = client.post("/api/plans", json={"ticker": "AAPL", "action": "buy"}).json()["id"]
        r = client.patch(f"/api/plans/{pid}", json={"status": "completed", "note": "done"})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
        assert r.json()["note"] == "done"

    def test_patch_uppercases_ticker(self, client):
        pid = client.post("/api/plans", json={"ticker": "AAPL", "action": "buy"}).json()["id"]
        r = client.patch(f"/api/plans/{pid}", json={"ticker": "tsla"})
        assert r.json()["ticker"] == "TSLA"

    def test_delete_removes(self, client):
        pid = client.post("/api/plans", json={"ticker": "AAPL", "action": "buy"}).json()["id"]
        assert client.delete(f"/api/plans/{pid}").status_code == 200
        assert client.get(f"/api/plans/{pid}").status_code == 404

    def test_filter_by_ticker_and_status(self, client):
        client.post("/api/plans", json={"ticker": "AAPL", "action": "buy"})
        client.post("/api/plans", json={"ticker": "NVDA", "action": "watch"})
        client.post("/api/plans", json={"ticker": "AAPL", "action": "sell", "status": "completed"})

        rows = client.get("/api/plans", params={"ticker": "AAPL"}).json()
        assert {p["ticker"] for p in rows} == {"AAPL"}

        pending = client.get("/api/plans", params={"status": "pending"}).json()
        assert all(p["status"] == "pending" for p in pending)
        assert len(pending) == 2
