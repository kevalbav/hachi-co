from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date
from calendar import monthrange

from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(
    prefix="/report",
    tags=["reports"],
    dependencies=[Depends(require_api_key)],
)

# ---------- helpers ----------

def month_bounds(period: str) -> tuple[str, str]:
    """Return (start_date, end_date) for 'YYYY-MM' as 'YYYY-MM-DD' strings."""
    try:
        y, m = map(int, period.split("-"))
        start = date(y, m, 1).strftime("%Y-%m-%d")
        end = date(y, m, monthrange(y, m)[1]).strftime("%Y-%m-%d")
        return start, end
    except Exception:
        raise HTTPException(400, "Invalid period, expected YYYY-MM")

def pick_optional_col(model, *names):
    """Return the first existing column attribute on model, or None if none found."""
    for n in names:
        if hasattr(model, n):
            return getattr(model, n)
    return None

def get_attached_kpi_ids(db: Session, workspace_id: str) -> list[str]:
    """
    Prefer explicitly attached KPIs (WorkspaceKPI). If that table doesn't exist
    or there are no rows, fall back to all KPIs.
    """
    try:
        if hasattr(models, "WorkspaceKPI"):
            wk_ws = pick_optional_col(models.WorkspaceKPI, "workspace_id", "workspace", "workspaceId", "ws_id")
            wk_kpi = pick_optional_col(models.WorkspaceKPI, "kpi_id", "kpi", "kpiId")
            if wk_ws is not None and wk_kpi is not None:
                ids = [row[0] for row in db.query(wk_kpi).filter(wk_ws == workspace_id).all()]
                if ids:
                    return ids
    except Exception:
        pass
    return [k.id for k in db.query(models.KPI).all()]

# ---------- routes ----------

@router.get("/workspace/{workspace_id}/month/{period}")
def workspace_month_report(workspace_id: str, period: str, db: Session = Depends(get_db)):
    """
    Monthly summary for a workspace:
      - Respects KPI.aggregation: "sum" (sum of values in month) vs "last" (latest value within month)
      - Uses attached KPI IDs to scope when Metric lacks workspace_id
      - Pulls Goal.target (if present) to compute pct_of_target
    """
    start, end = month_bounds(period)

    kpi_ids = get_attached_kpi_ids(db, workspace_id)
    if not kpi_ids:
        return {"workspace_id": workspace_id, "period": period, "kpis": []}

    # Load KPI definitions once
    kpis = {k.id: k for k in db.query(models.KPI).filter(models.KPI.id.in_(kpi_ids)).all()}

    # Resolve Metric columns (workspace optional)
    M = models.Metric
    m_ws   = pick_optional_col(M, "workspace_id", "workspace", "workspaceId", "ws_id")  # may be None
    m_kpi  = pick_optional_col(M, "kpi_id", "kpi", "kpiId")
    m_date = pick_optional_col(M, "date", "dt", "day")
    m_val  = pick_optional_col(M, "value", "val", "amount", "number")

    if m_kpi is None or m_date is None or m_val is None:
        raise HTTPException(500, "Metric model missing required columns (kpi_id/date/value)")

    # Resolve Goal columns (still workspace-scoped; if your Goal also lacks workspace, optionalize similarly)
    G = models.Goal
    g_ws     = pick_optional_col(G, "workspace_id", "workspace", "workspaceId", "ws_id")
    g_kpi    = pick_optional_col(G, "kpi_id", "kpi", "kpiId")
    g_period = pick_optional_col(G, "period", "month", "mm")
    g_target = pick_optional_col(G, "target", "goal", "target_value")

    rows = []
    for kpi_id, kpi in kpis.items():
        # Build metric filters; workspace is optional
        metric_filters = [
            m_kpi == kpi_id,
            m_date >= start,
            m_date <= end,
        ]
        if m_ws is not None:
            metric_filters.append(m_ws == workspace_id)

        agg = getattr(kpi, "aggregation", "sum")

        if agg == "last":
            actual = (
                db.query(m_val)
                .filter(and_(*metric_filters))
                .order_by(m_date.desc())
                .limit(1)
                .scalar()
                or 0.0
            )
        else:
            actual = (
                db.query(func.sum(m_val))
                .filter(and_(*metric_filters))
                .scalar()
                or 0.0
            )

        # Goal target lookup
        target = 0.0
        if g_kpi is not None and g_period is not None and g_target is not None:
            goal_filters = [g_kpi == kpi_id, g_period == period]
            if g_ws is not None:
                goal_filters.append(g_ws == workspace_id)
            target = db.query(g_target).filter(and_(*goal_filters)).scalar() or 0.0

        pct = (actual / target * 100.0) if target and target > 0 else None

        rows.append({
            "kpi_id": kpi_id,
            "name": kpi.name,
            "channel": kpi.channel,
            "unit": kpi.unit,
            "aggregation": agg,
            "actual": float(actual),
            "target": float(target),
            "pct_of_target": float(pct) if pct is not None else None,
        })

    # Sort so the most-behind show first (None at top)
    rows.sort(key=lambda r: (r["pct_of_target"] if r["pct_of_target"] is not None else -1.0))
    return {"workspace_id": workspace_id, "period": period, "kpis": rows}

@router.get("/workspace/{workspace_id}/month/{period}/kpi/{kpi_id}")
def workspace_month_kpi_detail(workspace_id: str, period: str, kpi_id: str, db: Session = Depends(get_db)):
    """
    Drilldown for a single KPI in a month: returns daily points (date, value).
    Workspace filter is applied only if Metric has a workspace column.
    """
    start, end = month_bounds(period)

    kpi = db.query(models.KPI).filter(models.KPI.id == kpi_id).first()
    if not kpi:
        raise HTTPException(404, "KPI not found")

    M = models.Metric
    m_ws   = pick_optional_col(M, "workspace_id", "workspace", "workspaceId", "ws_id")  # may be None
    m_kpi  = pick_optional_col(M, "kpi_id", "kpi", "kpiId")
    m_date = pick_optional_col(M, "date", "dt", "day")
    m_val  = pick_optional_col(M, "value", "val", "amount", "number")

    if m_kpi is None or m_date is None or m_val is None:
        raise HTTPException(500, "Metric model missing required columns (kpi_id/date/value)")

    filters = [m_kpi == kpi_id, m_date >= start, m_date <= end]
    if m_ws is not None:
        filters.append(m_ws == workspace_id)

    pts = (
        db.query(m_date, m_val)
        .filter(and_(*filters))
        .order_by(m_date.asc())
        .all()
    )
    series = [{"date": d, "value": float(v)} for (d, v) in pts]

    return {
        "workspace_id": workspace_id,
        "period": period,
        "kpi": {
            "kpi_id": kpi.id,
            "name": kpi.name,
            "channel": kpi.channel,
            "unit": kpi.unit,
            "aggregation": getattr(kpi, "aggregation", "sum"),
        },
        "series": series,
    }
