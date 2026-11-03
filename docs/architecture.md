# Architecture and next steps

## Current MVP

- **Scene contract:** `backend/app/schemas.py` uses strict Pydantic models and allow-listed options. Unsupported keys/actions are rejected rather than translated into executable code.
- **API/orchestration:** `backend/app/main.py` validates requests, creates a job directory, launches Blender as a subprocess, and exposes status/output endpoints.
- **Blender worker:** `blender/worker.py` creates a procedural cartoon king, a simple palace backdrop, materials, lights, camera, waving arm pivots, and an MP4 render.
- **Example:** `examples/king_scene.json` is a ready-to-submit request.

## Deliberate MVP limits

The procedural character is a visual placeholder, not a generated or historically verified 3D asset. Its arm pivots are not a full skeleton/skin-weight rig. The API keeps job status in process memory and executes one render per job; it has no durable queue, user authentication, multi-tenant isolation, or retry policy.

## Next implementation milestones

1. Add a persistent database and queue (for example Postgres plus Redis) and separate API and Blender worker processes.
2. Define versioned asset manifests and a secure asset-import step. Never let a language model submit arbitrary Python for execution.
3. Add a model provider adapter and validate imported mesh, texture paths, scale, and licensing metadata.
4. Add a rigging adapter for supported humanoid assets, with an explicit human-review fallback when automatic rigging fails.
5. Add animation adapters (curated clips or motion-capture retargeting) and scene validation before final rendering.
6. Store preview frames, logs, `.blend` files, and final video as job artifacts; provide progress events and cancellation.
7. Add tests for API validation and a Blender smoke test in CI using a pinned Blender version.

## Security and operations

The worker invokes only repository-controlled Python and receives a validated JSON file. Keep this boundary: do not replace it with `exec()` or direct execution of model-generated code. For production, run Blender in a disposable, resource-limited worker with restricted filesystem/network access, timeouts, and per-job storage permissions.