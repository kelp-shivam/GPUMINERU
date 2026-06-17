import os
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict

import aiofiles
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse

from app.auth import verify_api_key
from app.config import settings
from app.logging_config import log
from app.models import SubmitResponse, TaskResponse, TaskStatus, TaskMetadata
from app.parser import parse_document, executor, _load_model

app = FastAPI(
    title="MinerU GPU API",
    version="3.3.0",
    description="MinerU 3.3 — backend=hybrid, effort=high, OCR=on. Model loaded once at startup.",
)

# job store: task_id → {status, metadata, zip_path, error, created_at, benchmark}
_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()

MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """Pre-load model at startup so first job doesn't pay cold-start cost."""
    import asyncio
    log.info("API starting", extra={"backend": settings.MINERU_BACKEND, "workers": settings.PARALLEL_WORKERS, "device": settings.MINERU_DEVICE})
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _load_model)


def _run_parse(task_id: str, input_path: str) -> None:
    with _jobs_lock:
        _jobs[task_id]["status"] = TaskStatus.processing

    try:
        result = parse_document(task_id, input_path)
        with _jobs_lock:
            _jobs[task_id].update({
                "status": TaskStatus.completed,
                "metadata": result,
                "zip_path": result["zip_path"],
                "benchmark": result["benchmark"],
            })
    except Exception as exc:
        with _jobs_lock:
            _jobs[task_id].update({
                "status": TaskStatus.failed,
                "error": str(exc),
            })
    finally:
        try:
            os.remove(input_path)
        except OSError:
            pass


@app.post(
    "/api/v1/tasks/submit",
    response_model=SubmitResponse,
    summary="Submit document for extraction",
)
async def submit_task(
    file: UploadFile = File(...),
    _: str = Depends(verify_api_key),
):
    task_id = str(uuid.uuid4())
    upload_path = os.path.join(settings.UPLOAD_DIR, f"{task_id}_{file.filename}")
    total = 0

    async with aiofiles.open(upload_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                await f.close()
                os.remove(upload_path)
                raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB")
            await f.write(chunk)

    created_at = datetime.now(timezone.utc).isoformat()
    with _jobs_lock:
        _jobs[task_id] = {
            "status": TaskStatus.pending,
            "created_at": created_at,
            "filename": file.filename,
            "size_bytes": total,
            "metadata": None,
            "zip_path": None,
            "benchmark": None,
            "error": None,
        }

    log.info("Task submitted", extra={"task_id": task_id, "filename": file.filename, "size_bytes": total})
    # Submit to bounded thread pool (PARALLEL_WORKERS slots)
    executor.submit(_run_parse, task_id, upload_path)

    return SubmitResponse(task_id=task_id, status=TaskStatus.pending, created_at=created_at)


@app.get(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Poll task status",
)
async def get_task(task_id: str, _: str = Depends(verify_api_key)):
    with _jobs_lock:
        job = _jobs.get(task_id)
    if not job:
        raise HTTPException(404, f"Task {task_id} not found")

    meta = None
    if job["metadata"]:
        m = job["metadata"]
        meta = TaskMetadata(
            pages=m.get("pages"),
            tables=m.get("tables"),
            images=m.get("images"),
            processing_time_ms=m.get("benchmark", {}).get("total_ms"),
        )

    download_url = f"/api/v1/tasks/{task_id}/download" if job["status"] == TaskStatus.completed else None

    return TaskResponse(
        task_id=task_id,
        status=job["status"],
        progress=50 if job["status"] == TaskStatus.processing else None,
        metadata=meta,
        download_url=download_url,
        error=job.get("error"),
    )


@app.get(
    "/api/v1/tasks/{task_id}/benchmark",
    summary="Per-phase timing breakdown for a completed task",
)
async def get_benchmark(task_id: str, _: str = Depends(verify_api_key)):
    with _jobs_lock:
        job = _jobs.get(task_id)
    if not job:
        raise HTTPException(404, f"Task {task_id} not found")
    if job["status"] not in (TaskStatus.completed, TaskStatus.failed):
        raise HTTPException(400, f"Task still {job['status']}")

    bench = job.get("benchmark") or {}
    meta = job.get("metadata") or {}
    return {
        "task_id": task_id,
        "status": job["status"],
        "filename": job.get("filename"),
        "size_bytes": job.get("size_bytes"),
        "pages": meta.get("pages"),
        "zip_size_mb": meta.get("zip_size_mb"),
        **bench,
    }


@app.get(
    "/api/v1/tasks/{task_id}/download",
    summary="Download ZIP (MD + JSON + images + tables)",
)
async def download_result(task_id: str, _: str = Depends(verify_api_key)):
    with _jobs_lock:
        job = _jobs.get(task_id)
    if not job:
        raise HTTPException(404, f"Task {task_id} not found")
    if job["status"] != TaskStatus.completed:
        raise HTTPException(400, f"Task status: {job['status']}")
    zip_path = job.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(404, "ZIP not found — may have expired")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{task_id}.zip")


@app.get("/api/v1/queue/stats", summary="Queue + GPU utilization stats")
async def queue_stats(_: str = Depends(verify_api_key)):
    with _jobs_lock:
        jobs = list(_jobs.values())

    statuses = [j["status"] for j in jobs]
    completed = [j for j in jobs if j["status"] == TaskStatus.completed and j.get("benchmark")]
    avg_ms = (
        int(sum(j["benchmark"]["total_ms"] for j in completed) / len(completed))
        if completed else None
    )
    avg_inference_ms = (
        int(sum(j["benchmark"]["inference_ms"] for j in completed) / len(completed))
        if completed else None
    )

    return {
        "pending": statuses.count(TaskStatus.pending),
        "processing": statuses.count(TaskStatus.processing),
        "completed": statuses.count(TaskStatus.completed),
        "failed": statuses.count(TaskStatus.failed),
        "total": len(statuses),
        "parallel_workers": settings.PARALLEL_WORKERS,
        "avg_total_ms": avg_ms,
        "avg_inference_ms": avg_inference_ms,
        "backend": settings.MINERU_BACKEND,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "workers": settings.PARALLEL_WORKERS, "device": settings.MINERU_DEVICE}
