from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .pipeline import PipelineError, WebGALPipeline
from .storage import JobStore


app = FastAPI(title="WebGAL Function-Call Backend", version="1.0.0")
store = JobStore()
pipeline = WebGALPipeline(store)
frontend_dir = settings.workspace_root / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


class CreateJobRequest(BaseModel):
    source_material: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class RunJobRequest(BaseModel):
    background: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    path = frontend_dir / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(path)


@app.post("/jobs")
def create_job(request: CreateJobRequest) -> dict[str, Any]:
    return store.create(request.source_material, request.options)


@app.get("/jobs")
def list_jobs() -> dict[str, Any]:
    jobs = []
    for path in sorted(store.jobs_dir.glob("*/job.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            jobs.append(store.get(path.parent.name))
        except FileNotFoundError:
            continue
    return {"jobs": jobs}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return store.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_job(job_id: str, request: RunJobRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if request.background:
        background_tasks.add_task(run_pipeline_background, job_id)
        job = store.get(job_id)
        job["status"] = "QUEUED"
        store.save(job)
        return job
    try:
        return pipeline.run_all(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/phases/{phase}")
def run_phase(job_id: str, phase: str) -> dict[str, Any]:
    try:
        return pipeline.run_phase(job_id, phase)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str) -> dict[str, Any]:
    try:
        return {"job_id": job_id, "artifacts": store.list_artifacts(job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str) -> FileResponse:
    try:
        path = store.artifact_path(job_id, artifact_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_path}")
    return FileResponse(path)


def run_pipeline_background(job_id: str) -> None:
    try:
        pipeline.run_all(job_id)
    except Exception:
        # pipeline.run_all records the failure on the job. Swallow here so
        # Starlette does not emit a full traceback after the HTTP response.
        return
