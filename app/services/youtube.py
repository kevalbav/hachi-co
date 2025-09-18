import os
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from .. import models

def sync_channel_snapshot(db: Session, workspace_id: str) -> dict:
    integ = (
        db.query(models.Integration)
        .filter(models.Integration.workspace_id == workspace_id, models.Integration.provider == "youtube")
        .first()
    )
    if not integ:
        return {"ok": False, "reason": "not_connected"}

    creds = Credentials(
        token=integ.access_token,
        refresh_token=integ.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        scopes=(integ.scope.split() if integ.scope else []),
    )

    # will auto-refresh if refresh_token is present
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    me = yt.channels().list(part="statistics", mine=True).execute()
    items = me.get("items", [])
    if not items:
        return {"ok": False, "reason": "no_channel"}

    stats = items[0]["statistics"]
    subscribers = float(stats.get("subscriberCount", 0))
    views = float(stats.get("viewCount", 0))

    today = datetime.now().strftime("%Y-%m-%d")

    # upsert style: we’ll just insert daily snapshot rows
    for kid, val in (("k_yt_subs", subscribers), ("k_yt_views", views)):
        m = models.Metric(
            workspace_id=workspace_id if hasattr(models.Metric, "workspace_id") else None,
            kpi_id=kid, date=today, value=val, source="youtube:channels.statistics"
        )
        db.add(m)

    db.commit()
    return {"ok": True, "date": today, "subs": subscribers, "views": views}
