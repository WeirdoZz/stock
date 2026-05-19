"""Holding plan CRUD endpoints (PR 3)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage.repository import (
    create_plan,
    delete_plan,
    get_plan,
    list_plans,
    update_plan,
    VALID_ACTIONS,
    VALID_STATUSES,
)

router = APIRouter()


class CreatePlanBody(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    action: str
    target_price: Optional[float] = None
    quantity: Optional[int] = Field(None, ge=0)
    target_date: Optional[str] = None    # YYYY-MM-DD
    status: str = "pending"
    note: Optional[str] = None


class UpdatePlanBody(BaseModel):
    ticker: Optional[str] = None
    action: Optional[str] = None
    target_price: Optional[float] = None
    quantity: Optional[int] = None
    target_date: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


@router.get("/api/plans")
def list_all(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    return list_plans(ticker=ticker, status=status)


@router.post("/api/plans")
def create(body: CreatePlanBody) -> dict:
    if body.action not in VALID_ACTIONS:
        raise HTTPException(400, f"action must be one of {sorted(VALID_ACTIONS)}")
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    return create_plan(
        body.ticker,
        body.action,
        target_price=body.target_price,
        quantity=body.quantity,
        target_date=body.target_date,
        status=body.status,
        note=body.note,
    )


@router.patch("/api/plans/{plan_id}")
def patch(plan_id: int, body: UpdatePlanBody) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if "action" in fields and fields["action"] not in VALID_ACTIONS:
        raise HTTPException(400, f"action must be one of {sorted(VALID_ACTIONS)}")
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    if "ticker" in fields and fields["ticker"]:
        fields["ticker"] = fields["ticker"].upper()
    updated = update_plan(plan_id, **fields)
    if updated is None:
        raise HTTPException(404, "Plan not found")
    return updated


@router.delete("/api/plans/{plan_id}")
def remove(plan_id: int) -> dict:
    if not delete_plan(plan_id):
        raise HTTPException(404, "Plan not found")
    return {"deleted": plan_id}


@router.get("/api/plans/{plan_id}")
def get_one(plan_id: int) -> dict:
    p = get_plan(plan_id)
    if p is None:
        raise HTTPException(404, "Plan not found")
    return p
