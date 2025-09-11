from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Date, Integer, Float, ForeignKey, PrimaryKeyConstraint


Base = declarative_base()

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
    unit = Column(String, default="count")          # "count" | "seconds" | "%"

class Goal(Base):
    __tablename__ = "goals"
    id = Column(String, primary_key=True)           # e.g., "g_2025_09_k_ig_reach"
    kpi_id = Column(String, ForeignKey("kpis.id"), nullable=False)
    period = Column(String, nullable=False)         # "YYYY-MM"
    target_value = Column(Float, nullable=False)

class Metric(Base):
    __tablename__ = "metrics"
    id = Column(String, primary_key=True)           # uuid
    kpi_id = Column(String, ForeignKey("kpis.id"), nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    source = Column(String, default="manual")       # "manual" | "csv" | "api"




class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True)          # e.g., "w_001"
    name = Column(String, nullable=False)          # brand or project name

class WorkspaceKPI(Base):
    __tablename__ = "workspace_kpis"
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    kpi_id = Column(String, ForeignKey("kpis.id"), nullable=False)
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "kpi_id"),)