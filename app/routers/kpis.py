from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models, schemas
from fastapi import HTTPException
from sqlalchemy import func
router = APIRouter(prefix="/kpis", tags=["kpis"])

@router.post("", dependencies=[Depends(require_api_key)])
def create_kpi(payload: schemas.KPICreate, db: Session = Depends(get_db)):
    k = models.KPI(**payload.model_dump())
    db.add(k); db.commit()
    return {"ok": True, "kpi_id": k.id}

@router.get("", dependencies=[Depends(require_api_key)])
def list_kpis(db: Session = Depends(get_db)):
    rows = db.query(models.KPI).all()
    return [{"id": r.id, "name": r.name, "channel": r.channel, "unit": r.unit} for r in rows]



@router.post("", dependencies=[Depends(require_api_key)])
def create_kpi(payload: schemas.KPICreate, db: Session = Depends(get_db)):
    if db.get(models.KPI, payload.id):
        raise HTTPException(409, "KPI already exists")
    k = models.KPI(**payload.model_dump())
    db.add(k); db.commit()
    return {"ok": True, "kpi_id": k.id}


@router.delete("/{kpi_id}", dependencies=[Depends(require_api_key)])
def delete_kpi(
    kpi_id: str,
    force: bool = Query(False, description="Delete metrics/goals/attachments too"),
    db: Session = Depends(get_db),
):
    kpi = db.get(models.KPI, kpi_id)
    if not kpi:
        raise HTTPException(404, "KPI not found")

    # Count related rows
    m_count = db.query(func.count(models.Metric.kpi_id)).filter(models.Metric.kpi_id == kpi_id).scalar() or 0
    g_count = db.query(func.count(models.Goal.kpi_id)).filter(models.Goal.kpi_id == kpi_id).scalar() or 0
    a_count = db.query(func.count(models.WorkspaceKPI.kpi_id)).filter(models.WorkspaceKPI.kpi_id == kpi_id).scalar() or 0

    if (m_count or g_count or a_count) and not force:
        raise HTTPException(
            409,
            f"KPI has related data: metrics={m_count}, goals={g_count}, attachments={a_count}. "
            f"Re-try with ?force=true to delete all related data."
        )

    # Cascade delete (metrics, goals, attachments), then KPI itself
    if force:
        db.query(models.Metric).filter(models.Metric.kpi_id == kpi_id).delete(synchronize_session=False)
        db.query(models.Goal).filter(models.Goal.kpi_id == kpi_id).delete(synchronize_session=False)
        db.query(models.WorkspaceKPI).filter(models.WorkspaceKPI.kpi_id == kpi_id).delete(synchronize_session=False)

    db.delete(kpi)
    db.commit()
    return {"ok": True, "deleted": {"metrics": int(m_count), "goals": int(g_count), "attachments": int(a_count)}}