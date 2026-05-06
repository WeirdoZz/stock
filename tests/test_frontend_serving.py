"""
Tests for FastAPI serving the Vite-built frontend.

We don't import api.main directly because its startup hook does heavy work
(loads the embedding model, starts the scheduler). Instead we mount just the
relevant routes onto a fresh FastAPI app and point it at temp dist directories.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient


def _build_app(dist_dir: Path) -> FastAPI:
    """Replicate api/main.py's frontend-serving routes against a temp dist."""
    app = FastAPI()

    if (dist_dir / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(dist_dir / "assets")),
            name="assets",
        )

    @app.get("/")
    def index():
        index_path = dist_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=503, detail="Frontend not built.")
        return FileResponse(str(index_path))

    return app


class TestIndexRoute:
    def test_returns_503_when_dist_missing(self, tmp_path: Path):
        client = TestClient(_build_app(tmp_path / "dist"))
        r = client.get("/")
        assert r.status_code == 503
        assert "not built" in r.json()["detail"].lower()

    def test_returns_index_html_when_built(self, tmp_path: Path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!DOCTYPE html><html><body>vue</body></html>")
        client = TestClient(_build_app(dist))
        r = client.get("/")
        assert r.status_code == 200
        assert "vue" in r.text


class TestAssetsMount:
    def test_assets_served_when_present(self, tmp_path: Path):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("ok")
        (dist / "assets" / "app.js").write_text("console.log('hi')")
        client = TestClient(_build_app(dist))
        r = client.get("/assets/app.js")
        assert r.status_code == 200
        assert "console.log" in r.text

    def test_assets_404_when_dist_missing(self, tmp_path: Path):
        # No dist/, so no assets mount and any /assets/* should 404
        client = TestClient(_build_app(tmp_path / "dist"))
        r = client.get("/assets/whatever.js")
        assert r.status_code == 404
