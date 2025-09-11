from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime
from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(prefix="/reports", tags=["reports"])

def _month_bounds(period: str):
    # period: "YYYY-MM"
    year, month = map(int, period.split("-"))
    start = date(year, month, 1)
    end = date(year + (month // 12), 1 if month == 12 else month + 1, 1)
    return start, end

@router.post("/preview", dependencies=[Depends(require_api_key)])
def report_preview(payload: dict, db: Session = Depends(get_db)):
    """
    payload: {"workspace_id": "w_001", "period": "2025-09", "limit_kpis": 5, "limit_wins": 5}
    """
    workspace_id = payload.get("workspace_id")
    period = payload.get("period")
    if not workspace_id or not period:
        raise HTTPException(422, "workspace_id and period are required (YYYY-MM)")

    ws = db.get(models.Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")

    month_start, month_end = _month_bounds(period)

    # which KPIs are attached to this workspace?
    links = db.query(models.WorkspaceKPI).filter_by(workspace_id=workspace_id).all()
    kpi_ids = [ln.kpi_id for ln in links]
    kpi_rows = db.query(models.KPI).filter(models.KPI.id.in_(kpi_ids)).all()
    kpi_index = {k.id: k for k in kpi_rows}

    # build KPI cards (actual/target/pct)
    cards = []
    for kpi_id in kpi_ids:
        actual = db.query(func.coalesce(func.sum(models.Metric.value), 0.0))\
            .filter(models.Metric.kpi_id == kpi_id,
                    models.Metric.date >= month_start,
                    models.Metric.date < month_end)\
            .scalar()
        goal = db.query(models.Goal).filter_by(kpi_id=kpi_id, period=period).first()
        target = goal.target_value if goal else 0.0
        pct = (actual / target * 100.0) if target > 0 else None
        k = kpi_index.get(kpi_id)
        cards.append({
            "kpi_id": kpi_id,
            "name": k.name if k else kpi_id,
            "channel": k.channel if k else None,
            "unit": k.unit if k else None,
            "actual": actual,
            "target": target,
            "pct_of_target": pct,
        })

    # recent wins in this month (top 5 by default)
    limit_wins = int(payload.get("limit_wins", 5))
    wins = db.query(models.Win)\
        .filter(models.Win.workspace_id == workspace_id,
                models.Win.date >= month_start,
                models.Win.date < month_end)\
        .order_by(models.Win.date.desc())\
        .limit(limit_wins)\
        .all()
    wins_out = [{
        "date": w.date.isoformat(),
        "title": w.title,
        "tags": w.tags
    } for w in wins]

    # assemble summary
    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "workspace": {"id": ws.id, "name": ws.name},
        "period": period,
        "kpi_summary": cards[: int(payload.get("limit_kpis", 5))],
        "highlights": wins_out,
        "notes": ""  # you can fill from UI later
    }
    return {"ok": True, "report": summary}
