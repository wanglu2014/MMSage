from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from filelock import FileLock, Timeout

from runtime_state import job_output_dir, job_status_path, load_json, save_json
from upload_lease import begin_archive, lease_state


POLL_SECONDS = 0.5
CSV_LOAD_TIMEOUT_SECONDS = 120


def update_status(job_id: str, **fields) -> dict:
    path = job_status_path(job_id)
    current = load_json(path)
    if not isinstance(current, dict):
        current = {"job_id": job_id}
    current.update(fields)
    save_json(path, current)
    return current


def infer_step(output_dir: Path) -> str:
    if (output_dir / "step3_quadrant.json").exists():
        return "step3 (quadrant assignment)"
    if (output_dir / "step2b_agent_evidence.json").exists():
        return "step2b (multi-agent evidence)"
    if (output_dir / "step2_chain_novelty.json").exists():
        return "step2b (multi-agent evidence)"
    if (output_dir / "step1_candidates.json").exists():
        return "step2 (PubMed queries, may take 3-5 min)"
    return "step1 (MMSage signal)"


def run_job(
    job_id: str,
    csv_path: str,
    disease: str,
    bacteria_filter: str | None = None,
    max_queries: int = 15,
    max_articles_per_query: int = 20,
    client_managed: bool = False,
) -> dict:
    from run_pipeline import run_pipeline

    output_dir = job_output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    update_status(
        job_id,
        status="running",
        step="step1 (MMSage signal)",
        disease=disease,
        run_id="",
        output_dir=str(output_dir),
        error=None,
    )

    result_holder: dict = {"result": None, "error": None}

    def _inner() -> None:
        try:
            result_holder["result"] = run_pipeline(
                coordinates_file=csv_path,
                output_dir=str(output_dir),
                top_n=200,
                disease=disease,
                max_depth=3,
                bacteria_filter=bacteria_filter,
                max_queries=max_queries,
                max_articles_per_query=max_articles_per_query,
                before_archive=(lambda: begin_archive(job_id)) if client_managed else None,
            )
        except Exception as exc:  
            result_holder["error"] = exc

    worker = threading.Thread(target=_inner, daemon=True)
    worker.start()

    while worker.is_alive():
        worker.join(timeout=2)
        if worker.is_alive():
            update_status(job_id, status="running", step=infer_step(output_dir))

    if result_holder["error"] is not None:
        raise result_holder["error"]

    status_blob = result_holder["result"]
    if status_blob["status"] == "paused":
        return update_status(job_id, status="paused", step=infer_step(output_dir), error=None)
    if status_blob["status"] != "completed":
        return update_status(
            job_id,
            status="error",
            step=f"step{status_blob['current_step']}",
            error=status_blob.get("error") or "Pipeline did not complete.",
        )

    run_id = status_blob.get("catalog_run_id", "")
    if not run_id:
        return update_status(
            job_id, status="error", step="archive",
            error=status_blob.get("archive_error") or "Results archive did not return a run ID.",
        )
    candidates = load_json(output_dir / "step3_quadrant.json")
    if not isinstance(candidates, list):
        return update_status(
            job_id, status="error", step="step3",
            error="Missing or invalid candidate list in step3_quadrant.json.",
        )

    final = update_status(
        job_id,
        status="done",
        step="complete",
        disease=disease,
        run_id=run_id,
        candidates=len(candidates),
        total_duration_s=status_blob.get("total_duration_s"),
        error=None,
    )
    return final


def _stop_analysis(process: subprocess.Popen) -> None:
    # The graph builder is a child of the analysis process and shares its POSIX group.
    if os.name == "nt":
        stopped = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if stopped.returncode and process.poll() is None:
            raise RuntimeError("Could not stop the coordinate analysis process tree.")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def _run_managed(job_id, lock, arguments) -> int:
    while lease_state(job_id) != "paused":
        try:
            lock.acquire(timeout=POLL_SECONDS)
            break
        except Timeout:
            continue
    else:
        update_status(job_id, status="paused", error=None)
        return 0

    try:
        if lease_state(job_id) != "paused":
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), *arguments, "--analyze-with-lease"],
                start_new_session=os.name != "nt",
            )
            load_deadline = time.monotonic() + CSV_LOAD_TIMEOUT_SECONDS
            candidates_path = job_output_dir(job_id) / "step1_candidates.json"
            try:
                while True:
                    try:
                        return process.wait(timeout=POLL_SECONDS)
                    except subprocess.TimeoutExpired:
                        if lease_state(job_id) == "paused":
                            break
                        if load_deadline is not None:
                            if candidates_path.is_file():
                                load_deadline = None
                            elif time.monotonic() >= load_deadline:
                                raise TimeoutError("Loading the CSV timed out. Try a smaller file.")
            finally:
                if process.poll() is None:
                    _stop_analysis(process)
        status = load_json(job_status_path(job_id)) or {}
        if status.get("status") not in ("done", "error"):
            update_status(job_id, status="paused", error=None)
        return 0
    finally:
        lock.release()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run an isolated MMSage pipeline job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--disease", default="IBD")
    parser.add_argument("--bacteria-filter", default=None)
    parser.add_argument("--max-queries", type=int, default=15)
    parser.add_argument("--max-articles-per-query", type=int, default=20)
    parser.add_argument("--analyze-with-lease", action="store_true", help=argparse.SUPPRESS)
    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)

    try:
        # Keep waiting processes lightweight until the previous evidence worker releases the databases.
        jobs_dir = job_status_path(args.job_id).parent.parent
        jobs_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(jobs_dir / ".coordinate-analysis.lock")
        settings = vars(args).copy()
        managed_child = settings.pop("analyze_with_lease")
        if managed_child:
            final = run_job(**settings, client_managed=True)
        elif lease_state(args.job_id) is not None:
            return _run_managed(args.job_id, lock, arguments)
        else:
            with lock:
                final = run_job(**settings)
        return 0 if final["status"] in ("done", "paused") else 1
    except Exception as exc:  
        update_status(
            args.job_id,
            status="error",
            step="",
            disease=args.disease,
            run_id="",
            error=str(exc),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
