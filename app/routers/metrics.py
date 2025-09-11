from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import uuid4
from datetime import date
from ..deps import get_db, require_api_key
from .. import models, schemas
from fastapi import UploadFile, File, HTTPException
import csv, io
from datetime import datetime
from uuid import uuid4

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.post("", dependencies=[Depends(require_api_key)])
def add_metric(payload: schemas.MetricCreate, db: Session = Depends(get_db)):
    m = models.Metric(id=str(uuid4()), **payload.model_dump())
    db.add(m); db.commit()
    return {"ok": True, "metric_id": m.id}

@router.get("/progress/{kpi_id}/{period}", dependencies=[Depends(require_api_key)])
def progress(kpi_id: str, period: str, db: Session = Depends(get_db)):
    # period "YYYY-MM"
    year, month = map(int, period.split("-"))
    month_start = date(year, month, 1)
    month_end = date(year + (month // 12), 1 if month == 12 else month + 1, 1)

    actual = db.query(func.coalesce(func.sum(models.Metric.value), 0.0))\
        .filter(models.Metric.kpi_id == kpi_id,
                models.Metric.date >= month_start,
                models.Metric.date < month_end)\
        .scalar()
    goal = db.query(models.Goal).filter_by(kpi_id=kpi_id, period=period).first()
    target = goal.target_value if goal else 0.0
    pct = (actual / target * 100.0) if target > 0 else None
    return {"kpi_id": kpi_id, "period": period, "actual": actual, "target": target, "pct_of_target": pct}


@router.get("/progress/workspace/{workspace_id}/{period}", dependencies=[Depends(require_api_key)])
def progress_workspace(workspace_id: str, period: str, db: Session = Depends(get_db)):
    # Gather all KPI ids attached to this workspace
    kpi_links = db.query(models.WorkspaceKPI).filter_by(workspace_id=workspace_id).all()
    kpi_ids = [ln.kpi_id for ln in kpi_links]
    if not kpi_ids:
        return {"workspace_id": workspace_id, "period": period, "cards": []}

    # Period boundaries
    from datetime import date
    from sqlalchemy import func
    year, month = map(int, period.split("-"))
    month_start = date(year, month, 1)
    month_end = date(year + (month // 12), 1 if month == 12 else month + 1, 1)

    # Query all KPIs metadata
    kpi_rows = db.query(models.KPI).filter(models.KPI.id.in_(kpi_ids)).all()
    kpi_index = {k.id: k for k in kpi_rows}

    # For each KPI, compute actual, target
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

    return {"workspace_id": workspace_id, "period": period, "cards": cards}


@router.post("/import", dependencies=[Depends(require_api_key)])
async def import_metrics(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1) basic checks
    if not (file.filename.lower().endswith(".csv")):
        raise HTTPException(400, "Please upload a .csv file")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    required = {"kpi_id", "date", "value"}
    if not reader.fieldnames or not required.issubset(set(h.strip() for h in reader.fieldnames)):
        raise HTTPException(400, f"CSV must include headers: {sorted(required)}")

    inserted = updated = skipped = 0
    errors: list[str] = []

    # 2) upsert by (kpi_id, date)
    for i, row in enumerate(reader, start=2):  # header is line 1
        try:
            kpi_id = (row.get("kpi_id") or "").strip()
            if not kpi_id:
                skipped += 1
                continue
            d = datetime.strptime((row.get("date") or "").strip(), "%Y-%m-%d").date()
            v = float(row.get("value"))
            src = (row.get("source") or "csv").strip() or "csv"
        except Exception as e:
            errors.append(f"row {i}: {e}")
            skipped += 1
            continue

        m = db.query(models.Metric).filter_by(kpi_id=kpi_id, date=d).first()
        if m:
            m.value = v
            m.source = src
            updated += 1
        else:
            db.add(models.Metric(
                id=str(uuid4()),
                kpi_id=kpi_id,
                date=d,
                value=v,
                source=src
            ))
            inserted += 1

    db.commit()
    return {"ok": True, "inserted": inserted, "updated": updated, "skipped": skipped, "errors_preview": errors[:5]}