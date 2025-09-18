import os
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from .deps import SessionLocal  # if you expose this; otherwise create a SessionLocal in deps.py
from . import models
from .services.youtube import sync_channel_snapshot

_tz = pytz.timezone("Asia/Kolkata")
scheduler = BackgroundScheduler(timezone=_tz)

def _sync_all_youtube():
    # one DB session for the whole run
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(models.Integration.workspace_id)
            .filter(models.Integration.provider == "youtube")
            .distinct()
            .all()
        )
        for (wid,) in rows:
            try:
                sync_channel_snapshot(db, wid)
            except Exception as e:
                # log and continue; don't crash the job loop
                print(f"[jobs] youtube sync failed for {wid}: {e}")
    finally:
        db.close()

def start_scheduler():
    # Avoid duplicate jobs if reloader starts twice
    if not scheduler.get_jobs():
        scheduler.add_job(_sync_all_youtube, "cron", hour=3, minute=5)  # 03:05 IST daily
    scheduler.start()
