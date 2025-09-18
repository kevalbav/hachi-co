from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models, schemas
from pydantic import BaseModel 

router = APIRouter(prefix="/goals", tags=["goals"])

@router.post("", dependencies=[Depends(require_api_key)])
def create_goal(payload: schemas.GoalCreate, db: Session = Depends(get_db)):
    g = models.Goal(**payload.model_dump())
    db.add(g); db.commit()
    return {"ok": True, "goal_id": g.id}

@router.get("/{kpi_id}/{period}", dependencies=[Depends(require_api_key)])
def get_goal(kpi_id: str, period: str, db: Session = Depends(get_db)):
    g = db.query(models.Goal).filter_by(kpi_id=kpi_id, period=period).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    return {"kpi_id": kpi_id, "period": period, "target_value": g.target_value}


class GoalSetPayload(BaseModel):
    kpi_id: str           # e.g. "k_ig_reach"
    period: str           # "YYYY-MM"
    target_value: float

@router.post("/set", dependencies=[Depends(require_api_key)])
def set_goal(payload: GoalSetPayload, db: Session = Depends(get_db)):
    """
    Create or update a goal for (kpi_id, period). Id convention: g_{period}_{kpi_id}
    """
    workspace_id = "w_001"
    goal_id = f"g_{workspace_id}_{payload.kpi_id}_{payload.period}"

    g = db.get(models.Goal, goal_id)
    if g:
        g.target_value = float(payload.target_value)
        db.commit()
        db.refresh(g)
        return {"ok": True, "goal_id": g.id, "mode": "updated"}

    # create new
    g = models.Goal(
        id=goal_id,
        kpi_id=payload.kpi_id,
        period=payload.period,
        target_value=float(payload.target_value),
    )
    db.add(g)
    db.commit()
    return {"ok": True, "goal_id": g.id, "mode": "created"}