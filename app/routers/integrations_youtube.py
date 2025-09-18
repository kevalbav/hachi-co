from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..deps import get_db, require_api_key
from .. import models
from ..services.youtube import sync_channel_snapshot

router = APIRouter(
    prefix="/integrations/youtube",
    tags=["integrations"],
    dependencies=[Depends(require_api_key)],
)

def _pick(model, *names):
    for n in names:
        if hasattr(model, n):
            return getattr(model, n)
    return None

@router.get("/status")
def yt_status(workspace_id: str, db: Session = Depends(get_db)):
    integ = (
        db.query(models.Integration)
        .filter(models.Integration.provider == "youtube")
        .filter(models.Integration.workspace_id == workspace_id if hasattr(models.Integration, "workspace_id") else True)
        .first()
    )
    connected = bool(integ)

    # last metric date (workspace filter only if column exists)
    M = models.Metric
    m_ws   = _pick(M, "workspace_id", "workspace", "workspaceId", "ws_id")
    m_src  = _pick(M, "source")
    m_date = _pick(M, "date", "dt", "day")

    q = db.query(func.max(m_date)) if m_date is not None else None
    if q is not None:
        if m_src is not None:
            q = q.filter(m_src.like("youtube:%"))
        if m_ws is not None:
            q = q.filter(m_ws == workspace_id)
        last_metric_date = q.scalar()
    else:
        last_metric_date = None

    return {
        "connected": connected,
        "external_account_id": getattr(integ, "external_account_id", None) if integ else None,
        "last_metric_date": last_metric_date
    }

@router.post("/sync_channel")
def yt_sync_channel(workspace_id: str, db: Session = Depends(get_db)):
    # delegates to shared service (handles token refresh and metric writes)
    try:
        return sync_channel_snapshot(db, workspace_id)
    except Exception as e:
        raise HTTPException(500, f"sync failed: {e}")
