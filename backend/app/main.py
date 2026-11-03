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

from .schemas import ProjectCreateRequest, SceneSpec
from .storage import create_job, create_project, get_job, list_jobs

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "blender" / "worker.py"
WEB_INDEX = ROOT / "web" / "index.html"
BLENDER_BIN = os.environ.get("BLENDER_BIN") or shutil.which("blender")

app = FastAPI(title="AI2Blender", version="0.3.0", description="Validated scene specs rendered by a Blender worker.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_blender_job(job_id: str, spec: dict[str, Any]) -> None:
    from .storage import update_job_status

    job = get_job(job_id)
    if not job:
        return
    job_dir = Path(job["job_dir"])
    job_dir.mkdir(parents=True, exist_ok=True)
    spec_path = job_dir / "scene_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    update_job_status(job_id, {"status": "running", "started_at": utc_now()})
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
            update_job_status(job_id, {"status": "failed", "error": "Blender render failed. Inspect the job log for details.", "finished_at": utc_now()})
        else:
            update_job_status(job_id, {"status": "succeeded", "output": str(output_path), "finished_at": utc_now()})
    except Exception as exc:  # noqa: BLE001 - report worker launch failures to the client
        update_job_status(job_id, {"status": "failed", "error": f"Could not run Blender: {exc}", "finished_at": utc_now()})


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    if not WEB_INDEX.is_file():
        raise HTTPException(status_code=404, detail="Dashboard files are missing")
    return FileResponse(WEB_INDEX, media_type="text/html")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "blender_available": bool(BLENDER_BIN and Path(BLENDER_BIN).is_file())}


@app.post("/projects", status_code=201)
async def create_project_endpoint(payload: ProjectCreateRequest) -> dict[str, Any]:
    project = create_project(payload.name)
    return project


@app.get("/projects")
async def list_projects_endpoint() -> list[dict[str, Any]]:
    return list_jobs(project_id=None, include_projects=True)


@app.post("/jobs", status_code=202)
async def create_job_endpoint(spec: SceneSpec, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if not BLENDER_BIN:
        raise HTTPException(status_code=503, detail="Blender was not found. Set BLENDER_BIN or add blender to PATH.")

    spec_data = spec.model_dump()
    job_id = create_job(spec_data)
    background_tasks.add_task(run_blender_job, job_id, spec_data)
    return get_job(job_id)


@app.get("/jobs")
async def list_jobs_endpoint() -> list[dict[str, Any]]:
    return list_jobs(project_id=None)


@app.get("/jobs/{job_id}")
async def get_job_endpoint(job_id: str) -> dict[str, Any]:
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@app.get("/jobs/{job_id}/output")
async def get_output(job_id: str) -> FileResponse:
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record["status"] != "succeeded":
        raise HTTPException(status_code=409, detail="Render is not ready")
    output_path = Path(record["output"])
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Render file is missing")
    return FileResponse(output_path, media_type="video/mp4", filename=f"{job_id}.mp4")
