from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime, Text, UniqueConstraint, String, Index, Boolean,  Date, Integer, Float, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.sql import func
from uuid import uuid4
from datetime import datetime
import sqlalchemy as sa
Base = declarative_base()
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Boolean

class Win(Base):
    __tablename__ = "wins"
    id = Column(String, primary_key=True)                    # uuid str
    workspace_id = Column(String, nullable=False)            # keep phase 1 simple
    date = Column(Date, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    tags = Column(String, nullable=True)                     # comma-separated
    effort_mins = Column(Integer, default=0)


    from sqlalchemy import Column, String, Float, Date, ForeignKey

class KPI(Base):
    __tablename__ = "kpis"
    id = Column(String, primary_key=True)           # e.g., "k_ig_reach"
    name = Column(String, nullable=False)           # "Reach"
    channel = Column(String, nullable=False)        # "Instagram"
    unit = Column(String, default="count")
    aggregation = Column(String, nullable=False, default="sum")          # "count" | "seconds" | "%"

class Goal(Base):
    __tablename__ = "goals"
    id = Column(String, primary_key=True)           # e.g., "g_2025_09_k_ig_reach"
    kpi_id = Column(String, ForeignKey("kpis.id"), nullable=False)
    period = Column(String, nullable=False)         # "YYYY-MM"
    target_value = Column(Float, nullable=False)

class Metric(Base):
    __tablename__ = "metrics"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True, nullable=False)

    kpi_id = sa.Column(sa.String, sa.ForeignKey("kpis.id"), nullable=False, index=True)
    date   = sa.Column(sa.Date,   nullable=False, index=True)
    value  = sa.Column(sa.Float,  nullable=False)
    source = sa.Column(sa.String, nullable=True)

    # optional / workspace-scoping; keep nullable=True for painless migration
    workspace_id = sa.Column(sa.String, nullable=True, index=True)

    kpi = relationship("KPI", backref="metrics")

    __table_args__ = (
        # prevent duplicate daily points per scope; workspace_id can be NULL
        sa.UniqueConstraint("kpi_id", "date", "workspace_id", name="uq_metric_scope"),
    )       # "manual" | "csv" | "api"




class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True)          # e.g., "w_001"
    name = Column(String, nullable=False)  
    references = relationship("Reference", back_populates="workspace")
        # brand or project name

class WorkspaceKPI(Base):
    __tablename__ = "workspace_kpis"
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    kpi_id = Column(String, ForeignKey("kpis.id"), nullable=False)
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "kpi_id"),)
   

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)                  # uuid
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    date = Column(Date, nullable=False)                    # day the task belongs to
    title = Column(String, nullable=False)
    status = Column(String, default="open")                # "open" | "done"
    effort_mins = Column(Integer, default=0)


class DayTask(Base):
    __tablename__ = "day_tasks"  # <— new table name, avoids collision
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, nullable=False)         # e.g. "w_001"
    date = Column(String, nullable=False)                  # "YYYY-MM-DD"
    text = Column(String, nullable=False)
    done = Column(Boolean, default=False, nullable=False)
    carried_from = Column(String, nullable=True)           # "YYYY-MM-DD" if carried forward
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_day_tasks_ws_date", "workspace_id", "date"),
    )


class DayPlan(Base):
    __tablename__ = "day_plans"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, nullable=False)   # e.g. "w_001"
    date = Column(String, nullable=False)           # "YYYY-MM-DD"
    initialized_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "date", name="uq_day_plans_ws_date"),
        Index("ix_day_plans_ws_date", "workspace_id", "date"),
    )


class Integration(Base):
    __tablename__ = "integrations"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)  # 'youtube' | 'instagram' | 'linkedin'
    external_account_id = Column(String, nullable=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_integrations_ws_provider"),
        Index("ix_integrations_ws_provider", "workspace_id", "provider"),
    )

class Reference(Base):
    __tablename__ = "references"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    
    url = Column(Text, nullable=False)
    note = Column(Text)
    title = Column(Text)
    description = Column(Text)
    thumbnail = Column(Text)
    platform = Column(String, index=True)
    tags = Column(JSON, default=list)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    workspace = relationship("Workspace", back_populates="references")
    