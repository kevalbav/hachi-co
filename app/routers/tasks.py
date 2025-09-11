from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import date as ddate
from ..deps import get_db, require_api_key
from .. import models, schemas

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", dependencies=[Depends(require_api_key)])
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    # ensure workspace exists (optional but nice)
    if not db.get(models.Workspace, payload.workspace_id):
        raise HTTPException(404, "Workspace not found")
    t = models.Task(
        id=str(uuid4()),
        workspace_id=payload.workspace_id,
        date=payload.date,
        title=payload.title,
        effort_mins=payload.effort_mins,
    )
    db.add(t); db.commit()
    return {"ok": True, "task_id": t.id}

@router.get("", dependencies=[Depends(require_api_key)])
def list_tasks(
    workspace_id: str = Query(...),
    date: str | None = Query(None, description="YYYY-MM-DD (optional)"),
    status: str | None = Query(None, description='"open" or "done"'),
    db: Session = Depends(get_db),
):
    q = db.query(models.Task).filter(models.Task.workspace_id == workspace_id)
    if date:
        try:
            day = ddate.fromisoformat(date)
        except ValueError:
            raise HTTPException(422, "Bad date format (YYYY-MM-DD)")
        q = q.filter(models.Task.date == day)
    if status:
        q = q.filter(models.Task.status == status)
    rows = q.order_by(models.Task.date.desc()).limit(100).all()
    return [
        {"id": r.id, "date": r.date.isoformat(), "title": r.title, "status": r.status, "effort_mins": r.effort_mins}
        for r in rows
    ]

@router.post("/{task_id}/status", dependencies=[Depends(require_api_key)])
def update_task_status(task_id: str, payload: schemas.TaskStatusUpdate, db: Session = Depends(get_db)):
    t = db.get(models.Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    if payload.status not in {"open", "done"}:
        raise HTTPException(422, 'status must be "open" or "done"')
    t.status = payload.status
    db.commit()
    return {"ok": True}

@router.delete("/{task_id}", dependencies=[Depends(require_api_key)])
def delete_task(task_id: str, db: Session = Depends(get_db)):
    t = db.get(models.Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    db.delete(t); db.commit()
    return {"ok": True}
