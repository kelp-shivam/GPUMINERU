"""
Batch client — uploads all PDFs in a folder to MinerU API, downloads ZIPs.

Usage:
    python client/batch_process.py \
        --endpoint https://YOUR-LIGHTNING-URL \
        --api-key  YOUR-API-KEY \
        --input    "/Users/shivam/Downloads/SHIVAM PDF DOCS" \
        --output   "/Users/shivam/Downloads/MINERU_OUTPUTS" \
        --workers  4
"""

import os
import sys
import time
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import httpx

POLL_INTERVAL = 5   # seconds between status polls
POLL_TIMEOUT  = 3600  # max wait per job (1 hour)
CHUNK_SIZE    = 1024 * 1024  # 1MB upload chunks


def submit(client: httpx.Client, endpoint: str, api_key: str, pdf_path: Path) -> str:
    with open(pdf_path, "rb") as f:
        resp = client.post(
            f"{endpoint}/api/v1/tasks/submit",
            headers={"X-API-Key": api_key},
            files={"file": (pdf_path.name, f, "application/pdf")},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()["task_id"]


def poll_until_done(client: httpx.Client, endpoint: str, api_key: str, task_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        resp = client.get(
            f"{endpoint}/api/v1/tasks/{task_id}",
            headers={"X-API-Key": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"Task failed: {data.get('error', 'unknown')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Task {task_id} timed out after {POLL_TIMEOUT}s")


def download_zip(client: httpx.Client, endpoint: str, api_key: str, task_id: str, out_path: Path) -> None:
    with client.stream(
        "GET",
        f"{endpoint}/api/v1/tasks/{task_id}/download",
        headers={"X-API-Key": api_key},
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_bytes(CHUNK_SIZE):
                f.write(chunk)


def get_benchmark(client: httpx.Client, endpoint: str, api_key: str, task_id: str) -> dict:
    try:
        resp = client.get(
            f"{endpoint}/api/v1/tasks/{task_id}/benchmark",
            headers={"X-API-Key": api_key},
            timeout=30,
        )
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


_print_lock = threading.Lock()

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    with _print_lock:
        print(f"[{ts}] {msg}", flush=True)


def process_one(endpoint: str, api_key: str, pdf_path: Path, output_dir: Path) -> dict:
    result = {"file": pdf_path.name, "status": "unknown", "task_id": None}
    t0 = time.time()

    with httpx.Client(timeout=None) as client:
        try:
            log(f"SUBMIT  {pdf_path.name} ({pdf_path.stat().st_size / 1e6:.1f} MB)")
            task_id = submit(client, endpoint, api_key, pdf_path)
            result["task_id"] = task_id
            log(f"QUEUED  {pdf_path.name} → {task_id[:8]}...")

            data = poll_until_done(client, endpoint, api_key, task_id)

            zip_name = pdf_path.stem + ".zip"
            zip_path = output_dir / zip_name
            download_zip(client, endpoint, api_key, task_id, zip_path)

            bench = get_benchmark(client, endpoint, api_key, task_id)
            elapsed = time.time() - t0

            meta = data.get("metadata") or {}
            result.update({
                "status": "completed",
                "zip": str(zip_path),
                "pages": meta.get("pages"),
                "tables": meta.get("tables"),
                "images": meta.get("images"),
                "inference_ms": bench.get("inference_ms"),
                "total_ms": bench.get("total_ms"),
                "pages_per_sec": bench.get("pages_per_second"),
                "wall_sec": round(elapsed, 1),
            })
            log(
                f"DONE    {pdf_path.name} | "
                f"pages={meta.get('pages')} tables={meta.get('tables')} images={meta.get('images')} | "
                f"inference={bench.get('inference_ms', '?')}ms | "
                f"wall={elapsed:.1f}s → {zip_name}"
            )

        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            log(f"FAILED  {pdf_path.name}: {exc}")

    return result


def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 72)
    print(f"{'FILE':<45} {'STATUS':<10} {'PAGES':>5} {'INF(ms)':>8} {'WALL(s)':>8}")
    print("-" * 72)
    ok, fail = 0, 0
    for r in sorted(results, key=lambda x: x["file"]):
        status = r["status"]
        if status == "completed":
            ok += 1
            print(
                f"{r['file'][:44]:<45} {'OK':<10} "
                f"{str(r.get('pages','?')):>5} "
                f"{str(r.get('inference_ms','?')):>8} "
                f"{str(r.get('wall_sec','?')):>8}"
            )
        else:
            fail += 1
            print(f"{r['file'][:44]:<45} {'FAILED':<10}  {r.get('error','')[:30]}")
    print("=" * 72)
    print(f"Completed: {ok}  Failed: {fail}  Total: {len(results)}")


def main():
    parser = argparse.ArgumentParser(description="MinerU batch client")
    parser.add_argument("--endpoint", required=True, help="API base URL e.g. https://abc.lightning.ai")
    parser.add_argument("--api-key",  required=True, help="X-API-Key value")
    parser.add_argument("--input",    required=True, help="Folder with PDFs")
    parser.add_argument("--output",   default="./mineru_outputs", help="Where to save ZIPs")
    parser.add_argument("--workers",  type=int, default=4, help="Concurrent uploads (default 4)")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {input_dir}")
        sys.exit(1)

    print(f"\nMinerU Batch Processor")
    print(f"  Endpoint : {args.endpoint}")
    print(f"  Input    : {input_dir}  ({len(pdfs)} PDFs)")
    print(f"  Output   : {output_dir}")
    print(f"  Workers  : {args.workers}\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_one, args.endpoint, args.api_key, pdf, output_dir): pdf
            for pdf in pdfs
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    print_summary(results)

    # Save benchmark JSON
    import json
    bench_path = output_dir / "batch_benchmark.json"
    with open(bench_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nBenchmark saved → {bench_path}")


if __name__ == "__main__":
    main()
