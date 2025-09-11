from fastapi import FastAPI
from .models import Base
from .deps import engine
from .routers import wins
from fastapi import FastAPI
from .models import Base
from .deps import engine
from .routers import wins, kpis, goals, metrics, workspaces, reports, tasks


app = FastAPI(title="Hachi-co API", version="0.1.0")

# Phase 1: create tables dynamically (we'll move to Alembic later)
Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"ok": True}


app.include_router(wins.router)
app.include_router(kpis.router)
app.include_router(goals.router)
app.include_router(metrics.router)
app.include_router(workspaces.router)
app.include_router(reports.router)
app.include_router(tasks.router)