import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "app.db"
DATA_DIR = DB_PATH.parent


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                spec_json TEXT NOT NULL,
                output TEXT,
                error TEXT,
                job_dir TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


init_db()


def create_project(name: str) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (project_id, name, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": project_id, "name": name, "created_at": now, "updated_at": now}


def create_job(spec: dict[str, Any], project_id: str | None = None) -> str:
    import uuid
    from datetime import datetime, timezone

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    job_dir = (ROOT / "data" / "jobs" / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jobs (id, project_id, status, created_at, started_at, finished_at, spec_json, output, error, job_dir)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                project_id,
                "queued",
                now,
                None,
                None,
                json.dumps(spec),
                None,
                None,
                str(job_dir),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "spec": json.loads(row["spec_json"]),
            "output": row["output"],
            "error": row["error"],
            "job_dir": row["job_dir"],
        }
    finally:
        conn.close()


def list_jobs(project_id: str | None = None, include_projects: bool = False) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if project_id is not None:
            query += " WHERE project_id = ?"
            params.append(project_id)
        rows = conn.execute(f"{query} ORDER BY created_at DESC").fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "id": row["id"],
                "project_id": row["project_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "spec": json.loads(row["spec_json"]),
                "output": row["output"],
                "error": row["error"],
                "job_dir": row["job_dir"],
            }
            jobs.append(item)
        if include_projects:
            projects = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
            return [{"projects": [dict(p) for p in projects], "jobs": jobs}]
        return jobs
    finally:
        conn.close()


def update_job_status(job_id: str, fields: dict[str, Any]) -> None:
    conn = _connect()
    try:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()
