import os
import importlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy as sa

from .deps import engine
from . import models

app = FastAPI(title="Hachi-co API", version="0.3.0")

# CORS (dev-friendly; tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.get("/health")
def health():
    return {"ok": True}

def _ensure_kpi_aggregation_column() -> None:
    """
    If table 'kpis' exists and column 'aggregation' is missing, add it.
    Skip if table doesn't exist (fresh DB) — create_all() will create it correctly.
    """
    insp = sa.inspect(engine)
    if not insp.has_table("kpis"):
        return
    cols = [c["name"] for c in insp.get_columns("kpis")]
    if "aggregation" not in cols:
        with engine.begin() as conn:
            conn.exec_driver_sql('ALTER TABLE kpis ADD COLUMN aggregation VARCHAR NOT NULL DEFAULT "sum";')
        print("[migrate] Added kpis.aggregation (DEFAULT 'sum')")

def _include_routers() -> None:
    # Try to mount any router modules that exist
    for modname in [
        "wins",
        "kpis",
        "goals",
        "metrics",
        "workspaces",
        "reports",
        "tasks",
        "oauth_youtube",
        "youtube_integrations",  
        "references", 
        "dayplan",
        "instagram_integrations",
        "oauth_instagram"
    ]:
        try:
            mod = importlib.import_module(f"{__package__}.routers.{modname}")
            app.include_router(mod.router)
            print(f"[routers] mounted {modname}")
        except Exception as e:
            print(f"[routers] skip {modname}: {e}")

@app.on_event("startup")
def _on_startup():
    # 1) create tables for all models
    models.Base.metadata.create_all(bind=engine)
    # 2) run idempotent migrations
    _ensure_kpi_aggregation_column()

# Include routers immediately (not in startup event)
_include_routers()