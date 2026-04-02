import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db, check_db
from models import UsageRecord, UsagePostResponse

app = FastAPI(title="Claude Usage API", description="Local log-based usage collection (no Anthropic API).")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)
API_KEY = os.getenv("API_KEY", "")

_TOTAL_TOKENS_SQL = "SELECT COALESCE(SUM(total_tokens), 0) FROM claude_usage WHERE {condition}"


def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> None:
    if not API_KEY:
        return
    if not credentials or credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not check_db():
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ready"}


@app.post("/usage", response_model=UsagePostResponse)
def post_usage(
    payload: UsageRecord | list[UsageRecord],
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    records = [payload] if isinstance(payload, UsageRecord) else payload
    saved_ids = []
    for r in records:
        total = r.input_tokens + r.output_tokens
        created = r.created_at or datetime.now(timezone.utc)
        row = {
            "user_name": r.user_name,
            "machine": r.machine,
            "project": r.project,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": total,
            "session_id": r.session_id or "",
            "message_uuid": r.message_uuid or "",
            "created_at": created,
        }
        result = db.execute(
            text("""
            INSERT INTO claude_usage
            (user_name, machine, project, model, input_tokens, output_tokens, total_tokens, session_id, message_uuid, created_at)
            VALUES (:user_name, :machine, :project, :model, :input_tokens, :output_tokens, :total_tokens, :session_id, :message_uuid, :created_at)
            ON CONFLICT (user_name, machine, session_id, message_uuid) DO UPDATE SET
              input_tokens = EXCLUDED.input_tokens,
              output_tokens = EXCLUDED.output_tokens,
              total_tokens = EXCLUDED.total_tokens,
              created_at = EXCLUDED.created_at
            RETURNING id
            """),
            row,
        )
        row_id = result.scalar()
        if row_id:
            saved_ids.append(row_id)
    return UsagePostResponse(ok=True, saved_count=len(saved_ids), saved_ids=saved_ids)


def _sum_tokens(db: Session, condition: str, params: dict = None) -> dict:
    r = db.execute(text(_TOTAL_TOKENS_SQL.format(condition=condition)), params or {}).scalar()
    return {"total_tokens": r or 0}


@app.get("/usage/today")
def get_today(
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    cond = "(created_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date"
    params = {}
    if user:
        cond += " AND user_name = :target_user"
        params["target_user"] = user
    return _sum_tokens(db, cond, params)


@app.get("/usage/yesterday")
def get_yesterday(
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    cond = "(created_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date - 1"
    params = {}
    if user:
        cond += " AND user_name = :target_user"
        params["target_user"] = user
    return _sum_tokens(db, cond, params)


@app.get("/usage/week")
def get_week(
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    cond = "date_trunc('week', created_at AT TIME ZONE 'Asia/Seoul') = date_trunc('week', NOW() AT TIME ZONE 'Asia/Seoul')"
    params = {}
    if user:
        cond += " AND user_name = :target_user"
        params["target_user"] = user
    return _sum_tokens(db, cond, params)


@app.get("/usage/month")
def get_month(
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    cond = "date_trunc('month', created_at AT TIME ZONE 'Asia/Seoul') = date_trunc('month', NOW() AT TIME ZONE 'Asia/Seoul')"
    params = {}
    if user:
        cond += " AND user_name = :target_user"
        params["target_user"] = user
    return _sum_tokens(db, cond, params)


@app.get("/usage/users")
def get_users(db: Session = Depends(get_db)):
    r = db.execute(text("SELECT DISTINCT user_name FROM claude_usage ORDER BY user_name"))
    return {"users": [x[0] for x in r]}


def _build_filter(date: Optional[str], user: Optional[str],
                   date_from: Optional[str] = None, date_to: Optional[str] = None) -> tuple[str, dict]:
    """Build WHERE conditions and params for date/user filters.
    Supports single date or date range (date_from ~ date_to)."""
    conds = []
    params = {}
    if date_from and date_to:
        conds.append("(created_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN :date_from AND :date_to")
        params["date_from"] = date_from
        params["date_to"] = date_to
    elif date:
        conds.append("(created_at AT TIME ZONE 'Asia/Seoul')::date = :target_date")
        params["target_date"] = date
    else:
        conds.append("(created_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date")
    if user:
        conds.append("user_name = :target_user")
        params["target_user"] = user
    return " AND ".join(conds), params


@app.get("/usage/sessions")
def get_sessions(
    limit: int = Query(100, le=500),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD (KST)"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD (KST)"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD (KST)"),
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    where, params = _build_filter(date, user, date_from, date_to)
    params["limit"] = limit
    r = db.execute(
        text(f"""
        SELECT user_name, machine, project, model, input_tokens, output_tokens, total_tokens, created_at
        FROM claude_usage WHERE {where}
        ORDER BY created_at DESC LIMIT :limit
        """),
        params,
    )
    rows = r.mappings().all()
    return {
        "rows": [
            {
                "user_name": x["user_name"],
                "machine": x["machine"],
                "project": x["project"],
                "model": x["model"],
                "input_tokens": x["input_tokens"],
                "output_tokens": x["output_tokens"],
                "total_tokens": x["total_tokens"],
                "created_at": x["created_at"].isoformat() if x["created_at"] else None,
            }
            for x in rows
        ]
    }


@app.get("/usage/by-user")
def get_by_user(
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD (KST)"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD (KST)"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD (KST)"),
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    where, params = _build_filter(date, user, date_from, date_to)
    r = db.execute(text(f"""
        SELECT user_name,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(total_tokens) AS total_tokens,
               COUNT(*) AS turn_count
        FROM claude_usage WHERE {where}
        GROUP BY user_name ORDER BY total_tokens DESC
    """), params)
    return {"rows": [dict(x._mapping) for x in r]}


@app.get("/usage/by-project")
def get_by_project(
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD (KST)"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD (KST)"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD (KST)"),
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    where, params = _build_filter(date, user, date_from, date_to)
    r = db.execute(text(f"""
        SELECT COALESCE(project, '(none)') AS project,
               SUM(total_tokens) AS total_tokens,
               COUNT(*) AS turn_count,
               COUNT(DISTINCT user_name) AS unique_users
        FROM claude_usage WHERE {where}
        GROUP BY project ORDER BY total_tokens DESC
    """), params)
    return {"rows": [dict(x._mapping) for x in r]}


@app.get("/usage/by-model")
def get_by_model(
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD (KST)"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD (KST)"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD (KST)"),
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    where, params = _build_filter(date, user, date_from, date_to)
    r = db.execute(text(f"""
        SELECT COALESCE(model, '(unknown)') AS model,
               SUM(total_tokens) AS total_tokens,
               COUNT(*) AS turn_count
        FROM claude_usage WHERE {where}
        GROUP BY model ORDER BY total_tokens DESC
    """), params)
    return {"rows": [dict(x._mapping) for x in r]}


@app.get("/usage/hourly")
def get_hourly(
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD (KST)"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD (KST)"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD (KST)"),
    user: Optional[str] = Query(None, description="User name filter"),
    db: Session = Depends(get_db),
):
    where, params = _build_filter(date, user, date_from, date_to)
    r = db.execute(text(f"""
        SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Seoul') AS hour,
               user_name,
               SUM(total_tokens) AS total_tokens,
               COUNT(*) AS turn_count
        FROM claude_usage WHERE {where}
        GROUP BY hour, user_name ORDER BY hour
    """), params)
    return {"rows": [dict(x._mapping) for x in r]}


@app.get("/usage/daily")
def get_daily(days: int = Query(30, le=90), db: Session = Depends(get_db)):
    r = db.execute(text("""
        SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
               user_name,
               SUM(total_tokens) AS total_tokens,
               COUNT(*) AS turn_count
        FROM claude_usage
        WHERE created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - :days
        GROUP BY day, user_name ORDER BY day
    """), {"days": days})
    return {"rows": [{**dict(x._mapping), "day": str(x._mapping["day"])} for x in r]}


# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(FRONTEND_DIR):
    @app.get("/dashboard")
    def serve_dashboard():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
