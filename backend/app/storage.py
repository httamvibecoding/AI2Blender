import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AI2BLENDER_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("AI2BLENDER_DB_PATH", DATA_DIR / "app.db")).resolve()
JOBS_DIR = DATA_DIR / "jobs"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                spec_json TEXT NOT NULL,
                output TEXT,
                error TEXT,
                job_dir TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jobs_project_created ON jobs(project_id, created_at DESC);
            """
        )


def _project(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


def _job(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "project_id": row["project_id"], "status": row["status"],
        "created_at": row["created_at"], "started_at": row["started_at"],
        "finished_at": row["finished_at"], "attempt": row["attempt"],
        "spec": json.loads(row["spec_json"]), "output": row["output"],
        "error": row["error"], "job_dir": row["job_dir"],
    }


def create_project(name: str) -> dict[str, Any]:
    record = {"id": str(uuid.uuid4()), "name": name, "created_at": _now(), "updated_at": _now()}
    with _connect() as conn:
        conn.execute("INSERT INTO projects (id,name,created_at,updated_at) VALUES (?,?,?,?)", tuple(record.values()))
    return record


def get_project(project_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _project(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with _connect() as conn:
        return [_project(row) for row in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")]


def update_project(project_id: str, name: str) -> dict[str, Any] | None:
    with _connect() as conn:
        conn.execute("UPDATE projects SET name=?, updated_at=? WHERE id=?", (name, _now(), project_id))
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _project(row) if row else None


def delete_project(project_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        return True


def create_job(spec: dict[str, Any], project_id: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    job_dir = (JOBS_DIR / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id,project_id,status,created_at,attempt,spec_json,job_dir) VALUES (?,?,?,?,?,?,?)",
            (job_id, project_id, "queued", _now(), 1, json.dumps(spec), str(job_dir)),
        )
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job(row) if row else None


def list_jobs(project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        if project_id:
            rows = conn.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id, limit))
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_job(row) for row in rows]


def update_job_status(job_id: str, fields: dict[str, Any]) -> None:
    allowed = {"status", "started_at", "finished_at", "output", "error", "attempt"}
    if not fields or set(fields) - allowed:
        raise ValueError("Unsupported job update fields")
    assignments = ", ".join(f"{key}=?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id=?", (*fields.values(), job_id))


def retry_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "failed":
            raise ValueError("Only failed jobs can be retried")
        conn.execute(
            "UPDATE jobs SET status='queued', started_at=NULL, finished_at=NULL, output=NULL, error=NULL, attempt=attempt+1 WHERE id=?",
            (job_id,),
        )
        updated = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job(updated)


def recover_interrupted_jobs() -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE jobs SET status='failed', error='API restarted while this render was active; retry the job.', finished_at=? WHERE status IN ('queued','running')",
            (_now(),),
        )
        return cursor.rowcount


init_db()
