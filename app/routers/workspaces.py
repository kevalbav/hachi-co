from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models
from pydantic import BaseModel
from typing import Optional


router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class AttachPayload(BaseModel):
    kpi_id: str


@router.post("", dependencies=[Depends(require_api_key)])
def create_workspace(payload: dict, db: Session = Depends(get_db)):
    # payload: {"id": "w_001", "name": "My Brand"}
    if db.get(models.Workspace, payload["id"]):
        raise HTTPException(409, "Workspace already exists")
    w = models.Workspace(id=payload["id"], name=payload["name"])
    db.add(w)
    db.commit()
    return {"ok": True, "workspace_id": w.id}


# Support both query parameter (current UI) and JSON body
@router.post("/{workspace_id}/attach_kpi", dependencies=[Depends(require_api_key)])
def attach_kpi(
    workspace_id: str, 
    db: Session = Depends(get_db),
    kpi_id: Optional[str] = Query(None),  # Query parameter
    payload: Optional[AttachPayload] = None  # JSON body
):
    # Get kpi_id from either query param or JSON body
    target_kpi_id = kpi_id if kpi_id else (payload.kpi_id if payload else None)
    
    if not target_kpi_id:
        raise HTTPException(400, "kpi_id required either as query param or in request body")
    
    if not db.get(models.Workspace, workspace_id):
        raise HTTPException(404, "Workspace not found")
    if not db.get(models.KPI, target_kpi_id):
        raise HTTPException(404, "KPI not found")
    
    link = models.WorkspaceKPI(workspace_id=workspace_id, kpi_id=target_kpi_id)
    # upsert-ish: try add; on duplicate primary key, it's fine to ignore via merge
    db.merge(link)
    db.commit()
    return {"ok": True}


@router.post("/{workspace_id}/detach_kpi", dependencies=[Depends(require_api_key)])
def detach_kpi(
    workspace_id: str, 
    db: Session = Depends(get_db),
    kpi_id: Optional[str] = Query(None),  # Query parameter
    payload: Optional[AttachPayload] = None  # JSON body
):
    # Get kpi_id from either query param or JSON body
    target_kpi_id = kpi_id if kpi_id else (payload.kpi_id if payload else None)
    
    if not target_kpi_id:
        raise HTTPException(400, "kpi_id required either as query param or in request body")
    
    link = (
        db.query(models.WorkspaceKPI)
        .filter_by(workspace_id=workspace_id, kpi_id=target_kpi_id)
        .first()
    )
    if not link:
        raise HTTPException(404, "Attachment not found")
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.get("/{workspace_id}/kpis", dependencies=[Depends(require_api_key)])
def list_attached_kpis(workspace_id: str, db: Session = Depends(get_db)):
    w = db.get(models.Workspace, workspace_id)
    if not w:
        raise HTTPException(404, "Workspace not found")
    rows = (
        db.query(models.KPI)
        .join(models.WorkspaceKPI, models.WorkspaceKPI.kpi_id == models.KPI.id)
        .filter(models.WorkspaceKPI.workspace_id == workspace_id)
        .order_by(models.KPI.channel.asc(), models.KPI.name.asc())
        .all()
    )
    return [{"id": r.id, "name": r.name, "channel": r.channel, "unit": r.unit, "aggregation": r.aggregation} for r in rows]