from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..deps import get_db, require_api_key
from .. import models

TZ = ZoneInfo("Asia/Kolkata")
router = APIRouter(prefix="/day", tags=["day"], dependencies=[Depends(require_api_key)])

# ---------- helpers ----------
def today_ist() -> str:
    now = datetime.now(TZ)
    return now.strftime("%Y-%m-%d")

def ymd_to_month(ymd: str) -> str:    # "2025-09-13" -> "2025-09"
    return ymd[:7]

def ensure_today_plan(db: Session, workspace_id: str) -> str:
    today = today_ist()

    # already initialized today? do nothing
    plan = db.query(models.DayPlan).filter(
        and_(models.DayPlan.workspace_id == workspace_id,
             models.DayPlan.date == today)
    ).first()
    if plan:
        return today

    # mark initialized first (so even if user deletes all tasks later, we won't re-carry)
    plan = models.DayPlan(workspace_id=workspace_id, date=today)
    db.add(plan)
    db.commit()

    # carry over incomplete from yesterday once
    y = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)
    yday = y.strftime("%Y-%m-%d")

    prev_open = db.query(models.DayTask).filter(
        and_(models.DayTask.workspace_id == workspace_id,
             models.DayTask.date == yday,
             models.DayTask.done == False)
    ).all()

    for t in prev_open:
        db.add(models.DayTask(
            workspace_id=workspace_id, date=today,
            text=t.text, done=False, carried_from=t.date
        ))
    db.commit()
    return today

# ---------- payloads ----------
class TaskCreate(BaseModel):
    text: str

class TaskToggle(BaseModel):
    done: bool

# ---------- endpoints ----------
@router.get("/today/{workspace_id}")
def get_today(workspace_id: str, db: Session = Depends(get_db)):
    date = ensure_today_plan(db, workspace_id)
    tasks = db.query(models.DayTask).filter(
        and_(models.DayTask.workspace_id == workspace_id, models.DayTask.date == date)
    ).order_by(models.DayTask.created_at.asc()).all()
    return {
        "workspace_id": workspace_id,
        "date": date,
        "tasks": [
            {"id": t.id, "text": t.text, "done": t.done, "carried_from": t.carried_from}
            for t in tasks
        ]
    }

@router.get("/{workspace_id}/{date}/tasks")
def list_day(workspace_id: str, date: str, db: Session = Depends(get_db)):
    tasks = db.query(models.DayTask).filter(
        and_(models.DayTask.workspace_id == workspace_id, models.DayTask.date == date)
    ).order_by(models.DayTask.created_at.asc()).all()
    return [{"id": t.id, "text": t.text, "done": t.done, "carried_from": t.carried_from} for t in tasks]

@router.post("/{workspace_id}/{date}/add")
def add_task(workspace_id: str, date: str, payload: TaskCreate, db: Session = Depends(get_db)):
    t = models.DayTask(workspace_id=workspace_id, date=date, text=payload.text.strip(), done=False)
    db.add(t); db.commit(); db.refresh(t)
    return {"ok": True, "id": t.id}

@router.post("/{workspace_id}/{date}/{task_id}/toggle")
def toggle_task(workspace_id: str, date: str, task_id: str, payload: TaskToggle, db: Session = Depends(get_db)):
    t = db.query(models.DayTask).filter(
        and_(models.DayTask.id == task_id, models.DayTask.workspace_id == workspace_id, models.DayTask.date == date)
    ).first()
    if not t: raise HTTPException(404, "Task not found")
    t.done = bool(payload.done); db.commit()
    return {"ok": True}

@router.delete("/{workspace_id}/{date}/{task_id}")
def delete_task(workspace_id: str, date: str, task_id: str, db: Session = Depends(get_db)):
    n = db.query(models.DayTask).filter(
        and_(
            models.DayTask.id == task_id,
            models.DayTask.workspace_id == workspace_id,
            models.DayTask.date == date,
        )
    ).delete(synchronize_session=False)
    db.commit()
    if n == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}

@router.get("/{workspace_id}/month/{period}")
def month_group(workspace_id: str, period: str, db: Session = Depends(get_db)):
    # period: "YYYY-MM"; return days for that month grouped newest-first
    like = f"{period}-%"
    rows = db.query(models.DayTask).filter(
        and_(models.DayTask.workspace_id == workspace_id,
             models.DayTask.date.like(like))
    ).order_by(models.DayTask.date.desc(), models.DayTask.created_at.asc()).all()

    grouped = {}
    for t in rows:
        grouped.setdefault(t.date, []).append({"id": t.id, "text": t.text, "done": t.done, "carried_from": t.carried_from})

    days = [{"date": d, "tasks": grouped[d]} for d in sorted(grouped.keys(), reverse=True)]
    return {"workspace_id": workspace_id, "period": period, "days": days}

@router.post("/{workspace_id}/{date}/clear_done")
def clear_done(workspace_id: str, date: str, db: Session = Depends(get_db)):
    q = db.query(models.DayTask).filter(
        and_(models.DayTask.workspace_id == workspace_id,
             models.DayTask.date == date,
             models.DayTask.done == True)
    )
    # If you prefer to just mark them undone instead of deleting:
    # count = q.update({models.DayTask.done: False}, synchronize_session=False)
    count = q.delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "cleared": int(count)}

class TaskUpdate(BaseModel):
    text: str

@router.patch("/{workspace_id}/{date}/{task_id}")
def update_task(workspace_id: str, date: str, task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    t = db.query(models.DayTask).filter(
        and_(models.DayTask.id == task_id,
             models.DayTask.workspace_id == workspace_id,
             models.DayTask.date == date)
    ).first()
    if not t:
        raise HTTPException(404, "Task not found")
    t.text = payload.text.strip()
    db.commit()
    return {"ok": True}


