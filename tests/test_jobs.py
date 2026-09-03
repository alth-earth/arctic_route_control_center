from __future__ import annotations

import json
from pathlib import Path

from arctic_route_control_center.jobs import JobManager
from arctic_route_control_center.paths import resolve_paths


def test_carra_job_exposes_bounded_progress_summary(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    paths.ensure()
    job_id = "job-carra-progress"
    job_dir = paths.jobs_dir / job_id
    output = job_dir / "output"
    output.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "operation": "a_carra_acquire",
                "status": "completed",
                "created_at": "2026-09-03T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "spec.json").write_text(
        json.dumps({"parameters": {"estimated_cycles": 3}}), encoding="utf-8"
    )
    (output / "carra-summary.json").write_text(
        json.dumps(
            {
                "schema_version": "a.carra-acquisition-summary.v1",
                "cycles_requested": 3,
                "cache_hits": 2,
                "downloaded_cycles": 1,
                "frames_processed": 6,
                "frames_published": 6,
                "source_snapshot_ids": ["not-exposed-by-job-api"],
            }
        ),
        encoding="utf-8",
    )

    progress = JobManager(paths).get(job_id)["carra_progress"]
    assert progress == {
        "estimated_cycles": 3,
        "cycles_requested": 3,
        "cache_hits": 2,
        "downloaded_cycles": 1,
        "frames_processed": 6,
        "frames_published": 6,
    }
