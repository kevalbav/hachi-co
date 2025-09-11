from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

@router.post("", dependencies=[Depends(require_api_key)])
def create_workspace(payload: dict, db: Session = Depends(get_db)):
    # payload: {"id": "w_001", "name": "My Brand"}
    if db.get(models.Workspace, payload["id"]):
        raise HTTPException(409, "Workspace already exists")
    w = models.Workspace(id=payload["id"], name=payload["name"])
    db.add(w); db.commit()
    return {"ok": True, "workspace_id": w.id}

@router.post("/{workspace_id}/attach_kpi", dependencies=[Depends(require_api_key)])
def attach_kpi(workspace_id: str, payload: dict, db: Session = Depends(get_db)):
    # payload: {"kpi_id": "k_ig_reach"}
    if not db.get(models.Workspace, workspace_id):
        raise HTTPException(404, "Workspace not found")
    if not db.get(models.KPI, payload["kpi_id"]):
        raise HTTPException(404, "KPI not found")
    link = models.WorkspaceKPI(workspace_id=workspace_id, kpi_id=payload["kpi_id"])
    # upsert-ish: try add; on duplicate primary key, it's fine to ignore via merge
    db.merge(link)
    db.commit()
    return {"ok": True}
