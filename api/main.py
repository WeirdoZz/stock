"""FastAPI application entry point."""
from __future__ import annotations

import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.chat import router as chat_router
from api.routes.data import router as data_router

app = FastAPI(title="Stock Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(data_router)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.on_event("startup")
def startup():
    from storage.database import init_db
    init_db()
    # Pre-warm the embedding model so it loads once at startup, not on first request
    from storage.vector_store import _get_embedder
    _get_embedder()
    print("[startup] Embedding model loaded.")
