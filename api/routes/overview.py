"""Overview aggregation endpoint (PR 3)."""
from __future__ import annotations

from fastapi import APIRouter

from storage.repository import build_overview

router = APIRouter()


@router.get("/api/overview")
def overview() -> list[dict]:
    """Returns one card per registered ticker with price / news / fundamentals
    rollup plus a count of pending plans."""
    return build_overview()
