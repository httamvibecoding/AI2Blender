# AI2Blender

AI2Blender is a local-first AI-to-3D video MVP. A planner converts a text prompt into a validated Scene Spec; a repository-owned Blender worker builds a stylized procedural scene and renders it. The agent never sends executable Python to the worker.

## What works today

- Vietnamese/English prompt-to-Scene-Spec baseline (`POST /plan`). This is deterministic and does not call an external LLM.
- Project create/list/rename/delete, with SQLite persistence.
- Render job history persisted in SQLite, project association, retry for failed jobs, bounded concurrent Blender renders, timeout, worker log retrieval, MP4 preview/download, and ZIP artifact packaging.
- Web Scene Studio at `/`: prompt planning, JSON editing, project selection, job history, render status, preview, retry, and artifact download.
- Blender worker renders a simple procedural fictional Vietnamese king and palace with materials, lights, camera, a basic wave motion, and MP4 output.

This is a complete **local MVP**, not a production SaaS or a general text-to-3D model service. The current character is made from primitive geometry, the “rig” is a pair of arm pivots rather than a skeletal/weighted rig, and the planner is rules-based. It does not generate historically accurate assets, arbitrary character meshes, lip sync, motion capture, or multi-shot edits. Those require provider integrations and more capable assets/workers.

## Requirements and run

- Python 3.10+
- Blender on `PATH` or set `BLENDER_BIN` to the Blender executable
- Blender built with FFmpeg support

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export BLENDER_BIN=/path/to/blender # optional if Blender is already on PATH
uvicorn backend.app.main:app --reload
```

Open <http://127.0.0.1:8000/>. API docs are at `/docs`.

## API quickstart

Plan a Vietnamese prompt:

```bash
curl -X POST http://127.0.0.1:8000/plan \\
  -H 'Content-Type: application/json' \\
  -d '{"prompt":"Vua hoạt hình chào camera trong cung điện, 8 giây, camera tiến gần"}'
```

Create a project:

```bash
curl -X POST http://127.0.0.1:8000/projects \\
  -H 'Content-Type: application/json' -d '{"name":"Minh họa nhà vua"}'
```

Submit the included spec (optionally attach `?project_id=<uuid>`):

```bash
curl -X POST http://127.0.0.1:8000/jobs \\
  -H 'Content-Type: application/json' --data @examples/king_scene.json
```

Poll `GET /jobs/{id}`. Download the MP4 at `/jobs/{id}/output`, logs at `/jobs/{id}/log`, or the complete artifact ZIP at `/jobs/{id}/package`. Retry a failed job with `POST /jobs/{id}/retry`.

## Configuration

- `BLENDER_BIN`: Blender executable path.
- `AI2BLENDER_DATA_DIR`: artifact and default database directory (default `data/`).
- `AI2BLENDER_DB_PATH`: optional SQLite file path override.
- `AI2BLENDER_JOB_TIMEOUT`: render timeout in seconds (default 1200).
- `AI2BLENDER_MAX_RENDERS`: concurrent Blender process limit (default 1).

The job API currently runs Blender subprocesses from FastAPI background tasks. Keep it on a trusted local machine for this MVP. For deployment, use an external durable queue and isolated resource-limited workers, authentication, authorization, quotas, monitoring, and artifact retention. Do not execute agent-generated code or import untrusted Blender files in the API process.
