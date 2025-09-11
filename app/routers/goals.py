from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models, schemas

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
