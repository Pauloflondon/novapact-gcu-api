import os
import sqlite3
from pathlib import Path

# DB lives inside repo, deterministic & portable
DB_PATH = Path("gcu_v1/state/gcu_state.db")

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))

def init_db():
    with get_conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS run_status (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            hitl_required INTEGER NOT NULL,
            approval_required INTEGER NOT NULL,
            approval_provided INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

from datetime import datetime

def load_run_state(run_id: str):
    with get_conn() as c:
        row = c.execute(
            "SELECT status, hitl_required, approval_required, approval_provided, updated_at "
            "FROM run_status WHERE run_id = ?",
            (run_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "run_id": run_id,
        "status": row[0],
        "hitl_required": bool(row[1]),
        "approval_required": bool(row[2]),
        "approval_provided": bool(row[3]),
        "updated_at": row[4],
    }

def persist_run_state(
    run_id: str,
    status: str,
    hitl_required: bool,
    approval_required: bool,
    approval_provided: bool
):
    with get_conn() as c:
        c.execute(
            "INSERT INTO run_status (run_id, status, hitl_required, approval_required, approval_provided, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "status=excluded.status, "
            "hitl_required=excluded.hitl_required, "
            "approval_required=excluded.approval_required, "
            "approval_provided=excluded.approval_provided, "
            "updated_at=excluded.updated_at",
            (
                run_id,
                status,
                int(hitl_required),
                int(approval_required),
                int(approval_provided),
                datetime.utcnow().isoformat()
            )
        )
