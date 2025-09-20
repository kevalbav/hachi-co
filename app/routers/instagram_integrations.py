# hachico/app/routers/instagram_integrations.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timezone
import requests
import traceback

from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(prefix="/integrations/instagram", tags=["integrations"], dependencies=[Depends(require_api_key)])

def _pick(model, *names):
    """Helper to find column name across different model schemas (from YouTube integration)"""
    for n in names:
        if hasattr(model, n):
            return getattr(model, n)
    return None

def _attr_name(attr):
    """Get attribute name for dynamic column setting (from YouTube integration)"""
    return getattr(attr, "key", None) or getattr(attr, "name", None) or str(attr).split(".")[-1]

def ensure_kpi(db: Session, kpi_id: str, name: str, channel: str, unit: str, aggregation: str = "last"):
    """Create KPI if it doesn't exist (following YouTube pattern)"""
    kpi = db.query(models.KPI).filter(models.KPI.id == kpi_id).first()
    if not kpi:
        kpi = models.KPI(id=kpi_id, name=name, channel=channel, unit=unit, aggregation=aggregation)
        db.add(kpi)
        db.commit()

@router.get("/status")
def status(workspace_id: str, db: Session = Depends(get_db)):
    """Get Instagram integration status for a workspace (following YouTube pattern)"""
    
    integ = (
        db.query(models.Integration)
        .filter(models.Integration.provider == "instagram")
        .filter(models.Integration.workspace_id == workspace_id)
        .first()
    )
    connected = bool(integ)

    # Check last sync date using the same pattern as YouTube
    M = models.Metric
    m_ws = _pick(M, "workspace_id", "workspace", "workspaceId", "ws_id")
    m_src = _pick(M, "source")
    m_date = _pick(M, "date", "dt", "day")

    last_metric_date = None
    if m_date is not None:
        q = db.query(func.max(m_date))
        if m_src is not None:
            q = q.filter(m_src.like("instagram:%"))
        if m_ws is not None:
            q = q.filter(m_ws == workspace_id)
        last_metric_date = q.scalar()

    # Get Instagram username if connected
    instagram_username = None
    if integ and integ.access_token:
        try:
            # Quick API call to get username
            response = requests.get(
                f"https://graph.instagram.com/v18.0/{integ.external_account_id}",
                params={
                    "fields": "username",
                    "access_token": integ.access_token
                },
                timeout=5
            )
            if response.ok:
                instagram_username = response.json().get("username")
        except:
            pass  # Don't fail status check if username fetch fails

    return {
        "connected": connected,
        "external_account_id": getattr(integ, "external_account_id", None) if integ else None,
        "username": instagram_username,
        "last_metric_date": last_metric_date,
    }

@router.post("/sync_profile")
def sync_profile(workspace_id: str, db: Session = Depends(get_db)):
    """Sync Instagram profile metrics to KPIs (following YouTube pattern)"""
    
    try:
        # Get OAuth connection
        integ = (
            db.query(models.Integration)
            .filter(models.Integration.provider == "instagram")
            .filter(models.Integration.workspace_id == workspace_id)
            .first()
        )
        if not integ:
            raise HTTPException(400, "Instagram is not connected for this workspace")

        access_token = integ.access_token
        instagram_account_id = integ.external_account_id
        
        # Get Instagram profile data
        profile_response = requests.get(
            f"https://graph.instagram.com/v18.0/{instagram_account_id}",
            params={
                "fields": "followers_count,follows_count,media_count,username,account_type",
                "access_token": access_token
            }
        )
        profile_response.raise_for_status()
        profile_data = profile_response.json()
        
        # Get recent media for engagement calculation
        media_response = requests.get(
            f"https://graph.instagram.com/v18.0/{instagram_account_id}/media",
            params={
                "fields": "id,like_count,comments_count,timestamp",
                "limit": 12,  # Last 12 posts for engagement average
                "access_token": access_token
            }
        )
        media_response.raise_for_status()
        media_data = media_response.json()
        
        # Extract values
        followers_count = float(profile_data.get("followers_count", 0))
        following_count = float(profile_data.get("follows_count", 0))
        media_count = float(profile_data.get("media_count", 0))
        
        # Calculate average engagement from recent posts
        recent_posts = media_data.get("data", [])
        total_engagement = 0
        engagement_count = 0
        
        for post in recent_posts:
            likes = post.get("like_count", 0) or 0
            comments = post.get("comments_count", 0) or 0
            total_engagement += likes + comments
            engagement_count += 1
        
        avg_engagement = float(total_engagement / engagement_count) if engagement_count > 0 else 0.0
        engagement_rate = float((avg_engagement / followers_count) * 100) if followers_count > 0 else 0.0

        # Ensure KPIs exist (following YouTube pattern)
        ensure_kpi(db, "k_ig_followers", "Followers", "Instagram", "count", aggregation="last")
        ensure_kpi(db, "k_ig_following", "Following", "Instagram", "count", aggregation="last") 
        ensure_kpi(db, "k_ig_posts", "Posts", "Instagram", "count", aggregation="last")
        ensure_kpi(db, "k_ig_avg_engagement", "Avg Engagement", "Instagram", "count", aggregation="last")
        ensure_kpi(db, "k_ig_engagement_rate", "Engagement Rate", "Instagram", "percent", aggregation="last")

        # Clear old metrics for today (following YouTube pattern)
        M = models.Metric
        dcol = _pick(M, "date", "dt", "day")
        wscol = _pick(M, "workspace_id", "workspace", "workspaceId", "ws_id")
        today = date.today()

        # Delete existing metrics for these KPIs today
        kpi_ids = ["k_ig_followers", "k_ig_following", "k_ig_posts", "k_ig_avg_engagement", "k_ig_engagement_rate"]
        delete_q = db.query(M).filter(M.kpi_id.in_(kpi_ids))
        if dcol is not None:
            delete_q = delete_q.filter(dcol == today)
        if wscol is not None:
            delete_q = delete_q.filter(wscol == workspace_id)
        delete_q.delete()

        # Insert fresh metrics (following YouTube pattern)
        def insert_metric(kpi_id: str, value: float):
            m = M(kpi_id=kpi_id, value=value, source="instagram:profile")
            if dcol is not None:
                setattr(m, _attr_name(dcol), today)
            if wscol is not None:
                setattr(m, _attr_name(wscol), workspace_id)
            db.add(m)

        insert_metric("k_ig_followers", followers_count)
        insert_metric("k_ig_following", following_count)
        insert_metric("k_ig_posts", media_count)
        insert_metric("k_ig_avg_engagement", avg_engagement)
        insert_metric("k_ig_engagement_rate", engagement_rate)
        
        db.commit()

        print(f"Instagram sync completed for account: {profile_data.get('username')}")
        print(f"Fresh metrics: followers={followers_count}, following={following_count}, posts={media_count}")
        print(f"Engagement: avg={avg_engagement:.1f}, rate={engagement_rate:.2f}%")
        
        return {
            "ok": True, 
            "date": today.isoformat(), 
            "updated": ["k_ig_followers", "k_ig_following", "k_ig_posts", "k_ig_avg_engagement", "k_ig_engagement_rate"],
            "profile_data": {
                "username": profile_data.get("username"),
                "account_type": profile_data.get("account_type"),
                "followers": int(followers_count),
                "following": int(following_count),
                "posts": int(media_count),
                "avg_engagement": round(avg_engagement, 1),
                "engagement_rate": round(engagement_rate, 2)
            }
        }

    except HTTPException:
        raise
    except requests.RequestException as e:
        print(f"Instagram API error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch Instagram data: {str(e)}")
    except Exception as e:
        db.rollback()
        print(f"Instagram sync error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "trace": traceback.format_exc().splitlines()[-10:],
            },
        )

@router.delete("/disconnect")
def disconnect_instagram(workspace_id: str, db: Session = Depends(get_db)):
    """Disconnect Instagram integration from workspace"""
    
    integ = db.query(models.Integration).filter(
        models.Integration.provider == "instagram",
        models.Integration.workspace_id == workspace_id
    ).first()
    
    if integ:
        db.delete(integ)
        db.commit()
        return {"success": True, "message": "Instagram disconnected"}
    else:
        return {"success": True, "message": "Instagram was not connected"}