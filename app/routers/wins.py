from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import uuid4
from ..deps import get_db, require_api_key
from .. import models, schemas

router = APIRouter(prefix="/wins", tags=["wins"])

@router.post("", dependencies=[Depends(require_api_key)])
def create_win(payload: schemas.WinCreate, db: Session = Depends(get_db)):
    win = models.Win(
        id=str(uuid4()),
        workspace_id=payload.workspace_id,
        date=payload.date,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        effort_mins=payload.effort_mins,
    )
    db.add(win)
    db.commit()
    return {"ok": True, "win_id": win.id}

@router.get("", dependencies=[Depends(require_api_key)])
def list_wins(
    workspace_id: str = Query(..., description="Filter by workspace"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.Win)
        .filter(models.Win.workspace_id == workspace_id)
        .order_by(models.Win.date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "workspace_id": r.workspace_id,
            "date": r.date.isoformat(),
            "title": r.title,
            "tags": r.tags,
            "effort_mins": r.effort_mins,
        }
        for r in rows
    ]
