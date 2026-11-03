# AI2Blender

A starter for an AI-agent-driven 3D video workflow. The agent submits a validated scene description; a fixed Blender Python worker builds a stylized scene and renders it. Blender is the execution engine, not a GUI that the agent has to operate.

## MVP scope

This starter renders a simple, stylized fictional Vietnamese king greeting the camera. It demonstrates scene setup, materials, camera, lighting, a basic procedural character, a waving animation, and MP4 rendering. It is **not** a historically accurate character generator, production-grade rigging system, or general-purpose text-to-3D model generator.

## Requirements

- Python 3.10+
- Blender installed and available as `blender` on `PATH` (or set `BLENDER_BIN`)
- Blender built with FFmpeg support for MP4 output

## Run

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export BLENDER_BIN=/path/to/blender # optional if Blender is already on PATH
uvicorn backend.app.main:app --reload
```

Submit the included example:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H 'Content-Type: application/json' \
  --data @examples/king_scene.json
```

Poll the returned `id` at `GET /jobs/{id}`. When status is `succeeded`, download the render from `GET /jobs/{id}/output`.

API docs are available at `http://127.0.0.1:8000/docs`.

## Workflow

1. An agent turns a user prompt into the JSON contract in `backend/app/schemas.py`.
2. The API validates the request and saves it as a job input.
3. The API invokes the repository-owned Blender worker with the validated JSON. It does **not** execute model-generated Python.
4. The worker creates the scene and animation, then renders an MP4.
5. The client polls job status and retrieves the result.

The initial API stores job state in memory and artifacts under `data/jobs/`; this is suitable for local development only. Before deployment, add persistent job storage, a queue, authentication, quotas, worker isolation, and artifact retention controls. Treat any future model/asset imports as untrusted input and run Blender in a restricted worker/container.

See `docs/architecture.md` for the planned extension points.