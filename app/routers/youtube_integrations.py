from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, inspect
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import date, datetime, timezone
import traceback
import os

from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(prefix="/integrations/youtube", tags=["integrations"], dependencies=[Depends(require_api_key)])

def _pick(model, *names):
    for n in names:
        if hasattr(model, n):
            return getattr(model, n)
    return None

def _attr_name(attr):
    return getattr(attr, "key", None) or getattr(attr, "name", None) or str(attr).split(".")[-1]

def ensure_kpi(db: Session, kpi_id: str, name: str, channel: str, unit: str, aggregation: str = "last"):
    kpi = db.query(models.KPI).filter(models.KPI.id == kpi_id).first()
    if not kpi:
        kpi = models.KPI(id=kpi_id, name=name, channel=channel, unit=unit, aggregation=aggregation)
        db.add(kpi)
        db.commit()

@router.get("/status")
def status(workspace_id: str, db: Session = Depends(get_db)):
    integ = (
        db.query(models.Integration)
        .filter(models.Integration.provider == "youtube")
        .filter(models.Integration.workspace_id == workspace_id)
        .first()
    )
    connected = bool(integ)

    M = models.Metric
    m_ws = _pick(M, "workspace_id", "workspace", "workspaceId", "ws_id")
    m_src = _pick(M, "source")
    m_date = _pick(M, "date", "dt", "day")

    last_metric_date = None
    if m_date is not None:
        q = db.query(func.max(m_date))
        if m_src is not None:
            q = q.filter(m_src.like("youtube:%"))
        if m_ws is not None:
            q = q.filter(m_ws == workspace_id)
        last_metric_date = q.scalar()

    return {
        "connected": connected,
        "external_account_id": getattr(integ, "external_account_id", None) if integ else None,
        "last_metric_date": last_metric_date,
    }

@router.post("/sync_channel")
def sync_channel(workspace_id: str, db: Session = Depends(get_db)):
    try:
        # Get OAuth connection
        integ = (
            db.query(models.Integration)
            .filter(models.Integration.provider == "youtube")
            .filter(models.Integration.workspace_id == workspace_id)
            .first()
        )
        if not integ:
            raise HTTPException(400, "YouTube is not connected for this workspace")

        # Build YouTube API client with stored credentials
        creds = Credentials(
            token=integ.access_token,
            refresh_token=integ.refresh_token,
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
        )
        
        # Check if token needs refresh
        if creds.expired:
            creds.refresh(Request())
            # Update stored tokens
            integ.access_token = creds.token
            if creds.refresh_token:
                integ.refresh_token = creds.refresh_token
            integ.expiry = datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else None
            db.commit()

        # Fetch real YouTube data
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        
        # Get channel statistics
        response = yt.channels().list(
            part="statistics",
            id=integ.external_account_id
        ).execute()
        
        if not response.get("items"):
            raise HTTPException(400, "Channel not found or no access")
            
        stats = response["items"][0]["statistics"]
        
        # Extract real values
        subs_value = float(stats.get("subscriberCount", 0))
        views_value = float(stats.get("viewCount", 0))
        video_count = float(stats.get("videoCount", 0))

        # Ensure KPIs exist
        ensure_kpi(db, "k_yt_subs", "Subscribers", "YouTube", "count", aggregation="last")
        ensure_kpi(db, "k_yt_views", "Total Views", "YouTube", "count", aggregation="last") 
        ensure_kpi(db, "k_yt_videos", "Video Count", "YouTube", "count", aggregation="last")

        # Clear old metrics for today (force fresh data)
        M = models.Metric
        dcol = _pick(M, "date", "dt", "day")
        wscol = _pick(M, "workspace_id", "workspace", "workspaceId", "ws_id")
        today = date.today()

        # Delete existing metrics for these KPIs today
        delete_q = db.query(M).filter(M.kpi_id.in_(["k_yt_subs", "k_yt_views", "k_yt_videos"]))
        if dcol is not None:
            delete_q = delete_q.filter(dcol == today)
        if wscol is not None:
            delete_q = delete_q.filter(wscol == workspace_id)
        delete_q.delete()

        # Insert fresh metrics
        def insert_metric(kpi_id: str, value: float):
            m = M(kpi_id=kpi_id, value=value, source="youtube:channels.statistics")
            if dcol is not None:
                setattr(m, _attr_name(dcol), today)
            if wscol is not None:
                setattr(m, _attr_name(wscol), workspace_id)
            db.add(m)

        insert_metric("k_yt_subs", subs_value)
        insert_metric("k_yt_views", views_value)
        insert_metric("k_yt_videos", video_count)
        
        db.commit()

        print(f"Stored channel ID: {integ.external_account_id}")
        print(f"Fresh metrics written: subs={subs_value}, views={views_value}, videos={video_count}")
        
        return {
            "ok": True, 
            "date": today.isoformat(), 
            "updated": ["k_yt_subs", "k_yt_views", "k_yt_videos"],
            "values": {
                "subscribers": int(subs_value),
                "views": int(views_value), 
                "videos": int(video_count)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "trace": traceback.format_exc().splitlines()[-10:],
            },
        )