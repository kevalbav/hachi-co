from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models, schemas

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
