import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .schemas import SceneSpec

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "blender" / "worker.py"
DATA_DIR = Path(os.environ.get("AI2BLENDER_DATA_DIR", ROOT / "data" / "jobs")).resolve()
BLENDER_BIN = os.environ.get("BLENDER_BIN") or shutil.which("blender")

app = FastAPI(title="AI2Blender", version="0.1.0", description="Validated scene specs rendered by a Blender worker.")
# In-memory MVP state: replace with a persistent database/queue for deployment.
JOBS: dict[str, dict[str, Any]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_blender_job(job_id: str, job_dir: Path, spec_path: Path) -> None:
    record = JOBS[job_id]
    record["status"] = "running"
    record["started_at"] = utc_now()
    log_path = job_dir / "blender.log"
    output_path = job_dir / "render.mp4"
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            process = await asyncio.create_subprocess_exec(
                BLENDER_BIN,
                "--background",
                "--python",
                str(WORKER),
                "--",
                "--spec",
                str(spec_path),
                "--output",
                str(output_path),
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
            )
            return_code = await process.wait()
        if return_code != 0 or not output_path.is_file():
            record["status"] = "failed"
            record["error"] = "Blender render failed. Inspect the job log for details."
        else:
            record["status"] = "succeeded"
            record["output"] = str(output_path)
    except Exception as exc:  # noqa: BLE001 - report worker launch failures to the client
        record["status"] = "failed"
        record["error"] = f"Could not run Blender: {exc}"
    finally:
        record["finished_at"] = utc_now()


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "blender_available": bool(BLENDER_BIN and Path(BLENDER_BIN).is_file())}


@app.post("/jobs", status_code=202)
async def create_job(spec: SceneSpec, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if not BLENDER_BIN:
        raise HTTPException(status_code=503, detail="Blender was not found. Set BLENDER_BIN or add blender to PATH.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    job_dir = DATA_DIR / job_id
    job_dir.mkdir()
    spec_path = job_dir / "scene_spec.json"
    spec_path.write_text(json.dumps(spec.model_dump(), indent=2), encoding="utf-8")
    JOBS[job_id] = {"id": job_id, "status": "queued", "created_at": utc_now(), "spec": spec.model_dump()}
    background_tasks.add_task(run_blender_job, job_id, job_dir, spec_path)
    return JOBS[job_id]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    record = JOBS.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@app.get("/jobs/{job_id}/output")
async def get_output(job_id: str) -> FileResponse:
    record = JOBS.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record["status"] != "succeeded":
        raise HTTPException(status_code=409, detail="Render is not ready")
    output_path = Path(record["output"])
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Render file is missing")
    return FileResponse(output_path, media_type="video/mp4", filename=f"{job_id}.mp4")
