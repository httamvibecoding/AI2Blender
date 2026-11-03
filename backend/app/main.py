import asyncio
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from .agent import plan_scene
from .schemas import ProjectCreateRequest, ProjectUpdateRequest, PromptRequest, SceneSpec
from .storage import (
    create_job, create_project, delete_project, get_job, get_project, list_jobs,
    list_projects, recover_interrupted_jobs, retry_job, update_job_status, update_project,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "blender" / "worker.py"
WEB_INDEX = ROOT / "web" / "index.html"
BLENDER_BIN = os.environ.get("BLENDER_BIN") or shutil.which("blender")
JOB_TIMEOUT_SECONDS = int(os.environ.get("AI2BLENDER_JOB_TIMEOUT", "1200"))
MAX_CONCURRENT_RENDERS = max(1, int(os.environ.get("AI2BLENDER_MAX_RENDERS", "1")))
RENDER_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)

app = FastAPI(title="AI2Blender", version="0.4.0", description="AI-planned scene specs rendered by a validated Blender worker.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
async def recover_jobs() -> None:
    recover_interrupted_jobs()


async def run_blender_job(job_id: str) -> None:
    async with RENDER_SEMAPHORE:
        job = get_job(job_id)
        if not job:
            return
        job_dir = Path(job["job_dir"]).resolve()
        expected_parent = Path(os.environ.get("AI2BLENDER_DATA_DIR", ROOT / "data")).resolve() / "jobs"
        if not job_dir.is_relative_to(expected_parent.resolve()):
            update_job_status(job_id, {"status": "failed", "error": "Invalid job artifact path.", "finished_at": utc_now()})
            return
        job_dir.mkdir(parents=True, exist_ok=True)
        spec_path = job_dir / "scene_spec.json"
        output_path = job_dir / "render.mp4"
        spec_path.write_text(json.dumps(job["spec"], indent=2), encoding="utf-8")
        log_path = job_dir / "blender.log"
        update_job_status(job_id, {"status": "running", "started_at": utc_now()})
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                process = await asyncio.create_subprocess_exec(
                    BLENDER_BIN, "--background", "--python", str(WORKER), "--",
                    "--spec", str(spec_path), "--output", str(output_path),
                    stdout=log_file, stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    return_code = await asyncio.wait_for(process.wait(), timeout=JOB_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise RuntimeError(f"Render exceeded {JOB_TIMEOUT_SECONDS} seconds and was stopped")
            if return_code != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
                update_job_status(job_id, {"status": "failed", "error": "Blender render failed. Inspect the job log and retry.", "finished_at": utc_now()})
            else:
                update_job_status(job_id, {"status": "succeeded", "output": str(output_path), "error": None, "finished_at": utc_now()})
        except Exception as exc:  # noqa: BLE001 - store worker failure for the dashboard
            update_job_status(job_id, {"status": "failed", "error": str(exc)[:1000], "finished_at": utc_now()})


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    if not WEB_INDEX.is_file():
        raise HTTPException(status_code=404, detail="Dashboard files are missing")
    return FileResponse(WEB_INDEX, media_type="text/html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "blender_available": bool(BLENDER_BIN and Path(BLENDER_BIN).is_file()), "planner": "deterministic", "max_concurrent_renders": MAX_CONCURRENT_RENDERS}


@app.post("/plan")
async def create_plan(payload: PromptRequest) -> dict[str, Any]:
    return plan_scene(payload.prompt)


@app.post("/projects", status_code=201)
async def create_project_endpoint(payload: ProjectCreateRequest) -> dict[str, Any]:
    return create_project(payload.name)


@app.get("/projects")
async def list_projects_endpoint() -> list[dict[str, Any]]:
    return list_projects()


@app.get("/projects/{project_id}")
async def get_project_endpoint(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["jobs"] = list_jobs(project_id=project_id)
    return project


@app.patch("/projects/{project_id}")
async def rename_project_endpoint(project_id: str, payload: ProjectUpdateRequest) -> dict[str, Any]:
    project = update_project(project_id, payload.name)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project_endpoint(project_id: str) -> None:
    project_jobs = list_jobs(project_id=project_id, limit=1000)
    if any(job["status"] in {"queued", "running"} for job in project_jobs):
        raise HTTPException(status_code=409, detail="Cannot delete a project while render jobs are active")
    if not delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


async def submit_job(spec: SceneSpec, project_id: str | None, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if not BLENDER_BIN:
        raise HTTPException(status_code=503, detail="Blender was not found. Set BLENDER_BIN or add it to PATH.")
    if project_id and not get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    job_id = create_job(spec.model_dump(), project_id)
    background_tasks.add_task(run_blender_job, job_id)
    return get_job(job_id)


@app.post("/jobs", status_code=202)
async def create_job_endpoint(spec: SceneSpec, background_tasks: BackgroundTasks, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    return await submit_job(spec, project_id, background_tasks)


@app.post("/projects/{project_id}/jobs", status_code=202)
async def create_project_job_endpoint(project_id: str, spec: SceneSpec, background_tasks: BackgroundTasks) -> dict[str, Any]:
    return await submit_job(spec, project_id, background_tasks)


@app.get("/jobs")
async def list_jobs_endpoint(project_id: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return list_jobs(project_id=project_id, limit=limit)


@app.get("/jobs/{job_id}")
async def get_job_endpoint(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job_endpoint(job_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if not BLENDER_BIN:
        raise HTTPException(status_code=503, detail="Blender was not found. Set BLENDER_BIN or add it to PATH.")
    try:
        job = retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    background_tasks.add_task(run_blender_job, job_id)
    return job


@app.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
async def get_job_log(job_id: str) -> str:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    log_path = Path(job["job_dir"]) / "blender.log"
    if not log_path.is_file():
        return "No Blender log is available yet."
    return log_path.read_text(encoding="utf-8", errors="replace")[-50_000:]


@app.get("/jobs/{job_id}/output")
async def get_output(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "succeeded" or not job["output"]:
        raise HTTPException(status_code=409, detail="Render is not ready")
    output_path = Path(job["output"]).resolve()
    if not output_path.is_relative_to(Path(job["job_dir"]).resolve()) or not output_path.is_file():
        raise HTTPException(status_code=404, detail="Render file is missing")
    return FileResponse(output_path, media_type="video/mp4", filename=f"{job_id}.mp4")


@app.get("/jobs/{job_id}/package")
async def package_job(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "succeeded":
        raise HTTPException(status_code=409, detail="Only completed renders can be packaged")
    job_dir = Path(job["job_dir"]).resolve()
    archive_path = job_dir / "ai2blender-package.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("render.mp4", "scene_spec.json", "blender.log"):
            path = job_dir / name
            if path.is_file():
                archive.write(path, arcname=name)
        archive.writestr("manifest.json", json.dumps({"job_id": job_id, "project_id": job["project_id"], "attempt": job["attempt"], "created_at": job["created_at"]}, indent=2))
    return FileResponse(archive_path, media_type="application/zip", filename=f"{job_id}-artifacts.zip")
