#!/usr/bin/env python3
"""Black-box checks for a frozen onedir tree before AppImage assembly."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from scan_release import scan_release

_EMBEDDED_READY_NAME = "winter-rebuilt-20260215-viewer-package-v4"
_EMBEDDED_READY_BUNDLE_SHA256 = (
    "f993ac113ac7280e9378710fdc84a825338ebd6ea4b5193ce8679aeb5c3b114a"
)


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post(url: str, value: dict[str, object]) -> tuple[int, bytes]:
    body = json.dumps(value).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": url.rsplit("/", 2)[0]},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _check_internal_dispatch(executable: Path) -> None:
    stage = subprocess.run(
        [str(executable), "--orchestrator-stage-worker"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if stage.returncode != 2 or "usage: stage_worker" not in stage.stderr:
        raise RuntimeError(
            "frozen orchestrator stage dispatch failed:\n"
            f"{stage.stdout}\n{stage.stderr}"
        )
    exporter = subprocess.run(
        [
            str(executable),
            "--orchestrator-script",
            "replay_viewer_export.py",
            "--",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if exporter.returncode != 0 or "replay-viewer-export" not in exporter.stdout:
        raise RuntimeError(
            "frozen Viewer exporter dispatch failed:\n"
            f"{exporter.stdout}\n{exporter.stderr}"
        )


def _check_packaging_dependencies(executable: Path) -> None:
    """Exercise CARRA's dynamic cdsapi import without contacting CDS."""

    result = subprocess.run(
        [str(executable), "--packaging-self-test"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "frozen CARRA dependency dispatch failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    try:
        document = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(
            f"frozen CARRA dependency self-test was not JSON: {result.stdout}"
        ) from exc
    if document.get("ok") is not True or document.get("ecmwf_datastores") is not True:
        raise RuntimeError(f"frozen CARRA dependency self-test returned failure: {document}")


def _find_embedded_ready_package(artifact_root: Path) -> Path | None:
    """Return the embedded audited Viewer package, or None when none is embedded."""

    matches = sorted(
        candidate
        for candidate in artifact_root.rglob(_EMBEDDED_READY_NAME)
        if candidate.is_dir()
        and candidate.parent.name == "packages"
        and (candidate / "bundle.json").is_file()
        and (candidate / "checksums.json").is_file()
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise RuntimeError(
            "expected at most one embedded audited Viewer package, "
            f"found {len(matches)}"
        )
    import hashlib

    digest = hashlib.sha256((matches[0] / "bundle.json").read_bytes()).hexdigest()
    if digest != _EMBEDDED_READY_BUNDLE_SHA256:
        raise RuntimeError("embedded v4 bundle.json SHA256 does not match the audited artifact")
    return matches[0]


def _check_viewer_package_index(base: str, data_root: Path, artifact_root: Path) -> None:
    embedded = _find_embedded_ready_package(artifact_root)
    if embedded is not None:
        ready = data_root / "artifacts" / "ready" / embedded.name
        ready.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(embedded, ready)
    status, body = _get(base + "/viewer/packages.json")
    if status != 200:
        raise RuntimeError(f"Viewer package index failed: {status}")
    index = json.loads(body)
    packages = index.get("packages", [])
    if embedded is None:
        # Viewer data packages are optional build inputs; without an embedded
        # package the index must simply be parseable and must not claim a root.
        if index.get("default_package") == "viewer-root":
            raise RuntimeError(
                "Viewer package index claims viewer-root without embedded Viewer data"
            )
        return
    if index.get("default_package") != "viewer-root" or len(packages) < 2:
        raise RuntimeError(
            "Viewer package index did not retain root + embedded ready + external ready"
        )
    embedded_entries = [
        item
        for item in packages
        if item.get("location") == "embedded" and item.get("package_dir") == embedded.name
    ]
    ready_entries = [
        item
        for item in packages
        if item.get("location") == "ready" and item.get("package_dir") == embedded.name
    ]
    if len(embedded_entries) != 1 or len(ready_entries) != 1:
        raise RuntimeError("Viewer package index lost same-name source identity")
    from urllib.parse import quote

    encoded = quote(embedded.name, safe="")
    for source in ("packages", "ready-packages"):
        status, payload = _get(f"{base}/viewer/{source}/{encoded}/checksums.json")
        if status != 200 or not json.loads(payload).get("files"):
            raise RuntimeError(f"Viewer {source} source-specific package URL failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    artifact_root = args.artifact_root.resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"executable is missing: {executable}")
    release_scan = scan_release(
        artifact_root,
        workspace_root=args.workspace_root,
    )
    if int(release_scan["exit_code"]) != 0:
        raise ValueError(
            "release portability scan failed: "
            + json.dumps(release_scan, ensure_ascii=False, sort_keys=True)
        )
    with tempfile.TemporaryDirectory(prefix="arctic-route-cc-") as temporary:
        data_root = Path(temporary)
        self_test = subprocess.run(
            [str(executable), "--no-browser", "--self-test", "--data-root", str(data_root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if self_test.returncode != 0:
            raise RuntimeError(f"self-test failed:\n{self_test.stdout}\n{self_test.stderr}")
        document = json.loads(self_test.stdout.strip().splitlines()[-1])
        if document.get("ok") is not True:
            raise ValueError("self-test returned ok=false")
        if document.get("worker_entrypoints") is not True:
            raise ValueError("self-test did not load all frozen worker entrypoints")
        _check_internal_dispatch(executable)
        _check_packaging_dependencies(executable)
        process = subprocess.Popen(
            [
                str(executable),
                "--no-browser",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-root",
                str(data_root),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            state_path = data_root / "run" / "control-center.json"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not state_path.is_file():
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            base = f"http://127.0.0.1:{state['port']}"
            for endpoint in (
                "/api/health",
                "/api/system",
                "/api/catalog",
                "/api/artifacts",
                "/viewer/",
            ):
                status, body = _get(base + endpoint)
                if status != 200 or not body:
                    raise ValueError(f"runtime endpoint failed: {endpoint}: {status}")
            _check_viewer_package_index(base, data_root, artifact_root)
            status, _ = _get(base + "/viewer/../../config/default.json")
            if status == 200:
                raise ValueError("path traversal request unexpectedly succeeded")
            status, body = _post(
                base + "/api/jobs",
                {
                    "operation": "a_bundle",
                    "parameters": {
                        "scenario_id": "murmansk_dikson_july_2026_retrospective_v1",
                        "at": "2026-07-15T00:00:00Z",
                        "types": ["temperature"],
                        "mode": "retrospective_best_estimate",
                        "knowledge_as_of": "2026-07-23T00:00:00Z",
                    },
                },
            )
            if status != 202:
                raise ValueError(f"frozen job start failed: {status}: {body!r}")
            job_id = json.loads(body)["job"]["job_id"]
            deadline = time.monotonic() + 20
            job: dict[str, object] = {}
            while time.monotonic() < deadline:
                status, body = _get(base + f"/api/jobs/{job_id}")
                if status != 200:
                    raise ValueError(f"frozen job status failed: {status}")
                job = json.loads(body)["job"]
                if job.get("status") not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            # An empty test archive must fail closed, but only after the real
            # frozen child process entered A.  Import/config failures are a
            # packaging defect, not the expected no-data outcome.
            log_tail = str(job.get("log_tail", ""))
            if job.get("status") != "failed" or '"event": "worker_start"' not in log_tail:
                raise ValueError(f"frozen worker process was not exercised: {job}")
            if "ModuleNotFoundError" in log_tail or "vessel_traffic_model.toml" in log_tail:
                raise ValueError(f"frozen worker has a packaging defect:\n{log_tail}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print(json.dumps({"status": "PASS", "executable": str(executable)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
