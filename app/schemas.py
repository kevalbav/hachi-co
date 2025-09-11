from pydantic import BaseModel, Field
from datetime import date

class WinCreate(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    date: date
    title: str = Field(..., min_length=1)
    description: str | None = None
    tags: str | None = None
    effort_mins: int = 0

class WinOut(BaseModel):
    id: str
    workspace_id: str
    date: date
    title: str
    tags: str | None = None
    effort_mins: int


from uuid import uuid4
from datetime import date
from pydantic import BaseModel, Field

class KPICreate(BaseModel):
    id: str = Field(..., min_length=3)
    name: str
    channel: str
    unit: str = "count"

class GoalCreate(BaseModel):
    id: str
    kpi_id: str
    period: str            # "YYYY-MM"
    target_value: float

class MetricCreate(BaseModel):
    kpi_id: str
    date: date
    value: float
    source: str = "manual"

# helper to mint ids client-side if you want
def new_id() -> str:
    return str(uuid4())


class TaskCreate(BaseModel):
    workspace_id: str
    date: date
    title: str = Field(..., min_length=1)
    effort_mins: int = 0

class TaskStatusUpdate(BaseModel):
    status: str  # "open" or "done"

