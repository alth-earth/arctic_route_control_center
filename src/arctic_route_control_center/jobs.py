"""Single-host job lifecycle with persisted metadata and streamed log files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .operations import build_job_spec
from .paths import AppPaths, safe_child


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class JobManager:
    def __init__(self, paths: AppPaths, *, max_parallel_jobs: int = 1) -> None:
        self.paths = paths
        self.max_parallel_jobs = max_parallel_jobs
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._mark_interrupted_jobs()

    def _metadata_path(self, job_id: str) -> Path:
        return safe_child(self.paths.jobs_dir, job_id, "job.json")

    def _write(self, job_id: str, document: dict[str, Any]) -> None:
        path = self._metadata_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".json.{os.getpid()}.part")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _read(self, job_id: str) -> dict[str, Any]:
        return json.loads(self._metadata_path(job_id).read_text(encoding="utf-8"))

    def _mark_interrupted_jobs(self) -> None:
        if not self.paths.jobs_dir.is_dir():
            return
        for path in self.paths.jobs_dir.glob("*/job.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                if document.get("status") in {"queued", "running", "cancelling"}:
                    document.update(
                        {
                            "status": "interrupted",
                            "finished_at": _now(),
                            "message": "control center restarted before the job completed",
                        }
                    )
                    self._write(str(document["job_id"]), document)
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                continue

    def list(self) -> list[dict[str, Any]]:
        result = []
        for path in self.paths.jobs_dir.glob("*/job.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                result.append(self._decorate(document))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item.get("created_at", ""), reverse=True)

    def get(self, job_id: str) -> dict[str, Any]:
        if not job_id.startswith("job-"):
            raise ValueError("invalid job id")
        document = self._read(job_id)
        log_path = safe_child(self.paths.jobs_dir, job_id, "job.log")
        document["log_tail"] = _tail(log_path, 256 * 1024)
        return self._decorate(document)

    def _decorate(self, document: dict[str, Any]) -> dict[str, Any]:
        """Expose a bounded, credential-free CARRA progress summary when present."""

        if document.get("operation") != "a_carra_acquire":
            return document
        job_id = str(document.get("job_id", ""))
        try:
            spec = json.loads(
                safe_child(self.paths.jobs_dir, job_id, "spec.json").read_text(
                    encoding="utf-8"
                )
            )
            document["carra_progress"] = {
                "estimated_cycles": int(spec["parameters"]["estimated_cycles"])
            }
            summary_path = safe_child(
                self.paths.jobs_dir, job_id, "output", "carra-summary.json"
            )
            if summary_path.is_file() and summary_path.stat().st_size <= 1024 * 1024:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if summary.get("schema_version") == "a.carra-acquisition-summary.v1":
                    for key in (
                        "cycles_requested",
                        "cache_hits",
                        "downloaded_cycles",
                        "frames_processed",
                        "frames_published",
                    ):
                        value = summary.get(key)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            document["carra_progress"][key] = value
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        return document

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            active = sum(process.poll() is None for process in self._processes.values())
            if active >= self.max_parallel_jobs:
                raise ValueError("maximum parallel job limit reached")
            job_id = f"job-{uuid.uuid4()}"
            spec = build_job_spec(self.paths, request, job_id)
            job_dir = safe_child(self.paths.jobs_dir, job_id)
            spec_path = job_dir / "spec.json"
            spec_path.write_text(
                json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            document = {
                "schema_version": "arctic-route-control-center.job.v1",
                "job_id": job_id,
                "operation": spec["operation"],
                "status": "queued",
                "created_at": _now(),
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_dir": str(Path(spec["output_dir"]).relative_to(self.paths.data_root)),
                "message": "queued",
            }
            self._write(job_id, document)
            log_path = job_dir / "job.log"
            command = _worker_command(spec_path)
            log_handle = log_path.open("wb")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.paths.data_root,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
            except Exception:
                log_handle.close()
                raise
            document.update({"status": "running", "started_at": _now(), "message": "running"})
            self._write(job_id, document)
            self._processes[job_id] = process
            threading.Thread(
                target=self._monitor,
                args=(job_id, process, log_handle),
                daemon=True,
            ).start()
            return document

    def _monitor(
        self,
        job_id: str,
        process: subprocess.Popen[bytes],
        log_handle,
    ) -> None:
        return_code = process.wait()
        log_handle.close()
        with self._lock:
            document = self._read(job_id)
            if document.get("status") == "cancelling":
                status = "cancelled"
                message = "cancelled by operator"
            else:
                status = "completed" if return_code == 0 else "failed"
                message = "completed" if return_code == 0 else "worker returned a failure"
            document.update(
                {
                    "status": status,
                    "finished_at": _now(),
                    "return_code": return_code,
                    "message": message,
                }
            )
            self._write(job_id, document)
            self._processes.pop(job_id, None)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(job_id)
            if process is None or process.poll() is not None:
                raise ValueError("job is not running")
            document = self._read(job_id)
            document.update({"status": "cancelling", "message": "termination requested"})
            self._write(job_id, document)
            process.terminate()
            return document


def _worker_command(spec_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", str(spec_path)]
    return [sys.executable, "-m", "arctic_route_control_center.cli", "--worker", str(spec_path)]


def _tail(path: Path, max_bytes: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
