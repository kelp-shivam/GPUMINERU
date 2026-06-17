"""
MinerU 3.3 parse engine.

Model-singleton strategy: load VLM + layout models ONCE at process start,
then process all jobs through the loaded instance. On L4 (46GB):
  - VLM (bfloat16) ~20GB
  - Layout/table/formula/OCR models ~6-8GB
  - ~16GB headroom → PARALLEL_WORKERS=2 safe
"""

import os
import time
import zipfile
import shutil
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import settings
from app.logging_config import log

# ── GPU semaphore — caps concurrent inference on single GPU ──────────────────
_gpu_sem = threading.Semaphore(settings.PARALLEL_WORKERS)

# ── Thread pool sized to PARALLEL_WORKERS ────────────────────────────────────
executor = ThreadPoolExecutor(max_workers=settings.PARALLEL_WORKERS)

# ── Model singleton (Python API path) ────────────────────────────────────────
_model_lock = threading.Lock()
_mineru_instance = None   # set by _load_model() at startup


def _load_model():
    """
    Load MinerU model once into process memory.
    Called once at app startup — all parse jobs reuse this instance.
    Falls back to CLI subprocess mode if Python API unavailable.
    """
    global _mineru_instance
    with _model_lock:
        if _mineru_instance is not None:
            return _mineru_instance
        try:
            log.info("Loading MinerU model singleton", extra={"backend": settings.MINERU_BACKEND, "device": settings.MINERU_DEVICE})
            from mineru.cli.common import get_backend_instance
            _mineru_instance = get_backend_instance(
                backend=settings.MINERU_BACKEND,
                device=settings.MINERU_DEVICE,
            )
            log.info("Model loaded — singleton ready")
        except ImportError:
            log.warning("Python API unavailable — falling back to CLI subprocess (model reloads each job)")
            _mineru_instance = "cli-subprocess"
    return _mineru_instance


def _parse_via_python_api(model_instance, input_path: str, output_dir: str) -> None:
    """Use loaded model instance — no model reload cost."""
    model_instance.parse(
        input_path,
        output_dir=output_dir,
        effort=settings.MINERU_EFFORT,
        force_ocr=settings.MINERU_FORCE_OCR,
        lang=None if settings.MINERU_LANG == "auto" else settings.MINERU_LANG,
    )


def _parse_via_cli(input_path: str, output_dir: str) -> None:
    """CLI subprocess fallback. Each call reloads model — use only if Python API missing."""
    cmd = [
        "mineru",
        "-p", input_path,
        "-o", output_dir,
        "--backend", settings.MINERU_BACKEND,
        "--effort", settings.MINERU_EFFORT,
    ]
    if settings.MINERU_LANG != "auto":
        cmd += ["--lang", settings.MINERU_LANG]
    if settings.MINERU_FORCE_OCR:
        cmd.append("--force-ocr")

    env = os.environ.copy()
    env["MINERU_DEVICE"] = settings.MINERU_DEVICE
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")

    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())


def _count_artifacts(output_dir: str) -> dict:
    counts = {"pages": 0, "tables": 0, "images": 0}
    for root, _, files in os.walk(output_dir):
        for f in files:
            path = os.path.join(root, f)
            if f.endswith(".md"):
                try:
                    text = Path(path).read_text(errors="replace")
                    counts["pages"] = max(1, text.count("\f") + text.count("<!-- page_break -->") + 1)
                    counts["tables"] += text.count("| --- |")
                except Exception:
                    pass
            elif f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                counts["images"] += 1
    return counts


def _build_zip(task_output_dir: str, task_id: str) -> str:
    zip_path = os.path.join(settings.OUTPUT_DIR, f"{task_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _, files in os.walk(task_output_dir):
            for file in sorted(files):
                abs_path = os.path.join(root, file)
                arcname = os.path.relpath(abs_path, task_output_dir)
                zf.write(abs_path, arcname)
    return zip_path


def parse_document(task_id: str, input_path: str) -> dict:
    """
    Full parse pipeline with per-phase benchmarking.
    Returns timing + artifact metadata dict.
    Acquires GPU semaphore — blocks if PARALLEL_WORKERS slots full.
    """
    bench = {"queued_at": time.time()}
    task_output_dir = os.path.join(settings.OUTPUT_DIR, task_id)
    os.makedirs(task_output_dir, exist_ok=True)

    # ── Acquire GPU slot ──────────────────────────────────────────────────────
    log.info("Job queued", extra={"task_id": task_id})
    _gpu_sem.acquire()
    bench["inference_start"] = time.time()
    bench["queue_wait_ms"] = int((bench["inference_start"] - bench["queued_at"]) * 1000)
    log.info("GPU slot acquired", extra={"task_id": task_id, "queue_wait_ms": bench["queue_wait_ms"]})

    try:
        model = _load_model()
        if model != "cli-subprocess":
            log.info("Parse start (python-api)", extra={"task_id": task_id})
            _parse_via_python_api(model, input_path, task_output_dir)
        else:
            log.info("Parse start (cli-subprocess)", extra={"task_id": task_id})
            _parse_via_cli(input_path, task_output_dir)
    except Exception as exc:
        log.error("Parse failed", extra={"task_id": task_id, "error": str(exc)})
        raise
    finally:
        _gpu_sem.release()
        log.info("GPU slot released", extra={"task_id": task_id})

    bench["inference_end"] = time.time()
    bench["inference_ms"] = int((bench["inference_end"] - bench["inference_start"]) * 1000)
    log.info("Inference done", extra={"task_id": task_id, "inference_ms": bench["inference_ms"]})

    # ── Count artifacts ───────────────────────────────────────────────────────
    bench["export_start"] = time.time()
    counts = _count_artifacts(task_output_dir)
    bench["export_ms"] = int((time.time() - bench["export_start"]) * 1000)

    # ── Zip ───────────────────────────────────────────────────────────────────
    bench["zip_start"] = time.time()
    zip_path = _build_zip(task_output_dir, task_id)
    zip_size_mb = round(os.path.getsize(zip_path) / (1024 * 1024), 2)
    bench["zip_ms"] = int((time.time() - bench["zip_start"]) * 1000)

    # Cleanup raw outputs — ZIP is canonical artifact
    shutil.rmtree(task_output_dir, ignore_errors=True)

    total_ms = int((time.time() - bench["queued_at"]) * 1000)
    log.info(
        "Job complete",
        extra={
            "task_id": task_id,
            "total_ms": total_ms,
            "inference_ms": bench["inference_ms"],
            "pages": counts["pages"],
            "tables": counts["tables"],
            "images": counts["images"],
            "zip_size_mb": zip_size_mb,
        },
    )

    return {
        # artifact counts
        "pages": counts["pages"],
        "tables": counts["tables"],
        "images": counts["images"],
        "zip_size_mb": zip_size_mb,
        "zip_path": zip_path,
        # benchmark
        "benchmark": {
            "total_ms": total_ms,
            "queue_wait_ms": bench["queue_wait_ms"],
            "inference_ms": bench["inference_ms"],
            "export_ms": bench["export_ms"],
            "zip_ms": bench["zip_ms"],
            "pages_per_second": round(counts["pages"] / max(bench["inference_ms"] / 1000, 0.001), 2),
            "backend": settings.MINERU_BACKEND,
            "effort": settings.MINERU_EFFORT,
            "device": settings.MINERU_DEVICE,
            "parallel_workers": settings.PARALLEL_WORKERS,
            "model_mode": "singleton-python-api" if _mineru_instance != "cli-subprocess" else "cli-subprocess",
        },
    }
