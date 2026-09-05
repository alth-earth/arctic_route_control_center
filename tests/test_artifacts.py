from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from arctic_route_control_center.artifacts import inspect_viewer_package, package_index
from arctic_route_control_center.paths import resolve_paths


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_package_requires_checksum_and_formal_motion(tmp_path: Path) -> None:
    bundle = {
        "schema_version": "replay.viewer-bundle.v1",
        "replay": {"scenario_id": "scenario-a"},
        "combined_presentation": {"status": "PUBLISHED"},
        "route_candidates": {"status": "PUBLISHED", "candidates": [{}] * 12},
        "gates": {"status": "PASS"},
        "formal_motion_inspection": {"valid": False},
        "risk": {"frames": []},
    }
    _write(tmp_path / "bundle.json", bundle)
    digest = hashlib.sha256((tmp_path / "bundle.json").read_bytes()).hexdigest()
    _write(tmp_path / "checksums.json", {"files": {"bundle.json": digest}})
    result = inspect_viewer_package(tmp_path)
    assert result["status"] == "incomplete"
    assert "formal motion" in result["reason"]


def test_package_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    (tmp_path / "bundle.json").write_text(
        '{"schema_version":"replay.viewer-bundle.v1","schema_version":"x"}',
        encoding="utf-8",
    )
    result = inspect_viewer_package(tmp_path, verify_checksums=False)
    assert result["status"] == "incomplete"
    assert "duplicate JSON key" in result["reason"]


def _write_valid_package(path: Path, scenario: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "replay.viewer-bundle.v1",
        "replay": {
            "scenario_id": scenario,
            "start": "2026-02-15T00:00:00Z",
            "end": "2026-02-21T00:00:00Z",
        },
        "combined_presentation": {
            "status": "PUBLISHED",
            "dataset_bundle_id": "dataset-a",
            "risk_window_id": "risk-window-a",
            "assembly_id": "assembly-a",
        },
        "route_candidates": {"status": "PUBLISHED", "candidates": [{}] * 12},
        "gates": {"status": "PASS"},
        "formal_motion_inspection": {"valid": True},
        "risk": {"frames": []},
    }
    _write(path / "bundle.json", bundle)
    digest = hashlib.sha256((path / "bundle.json").read_bytes()).hexdigest()
    _write(path / "checksums.json", {"files": {"bundle.json": digest}})


def test_embedded_viewer_packages_are_preferred_and_can_be_isolated(tmp_path: Path) -> None:
    base = resolve_paths(tmp_path)
    viewer = tmp_path / "viewer"
    paths = replace(base, viewer_static=viewer)
    paths.ensure()
    _write_valid_package(viewer, "root")
    _write_valid_package(viewer / "packages" / "v2", "embedded-v2")
    _write_valid_package(paths.artifacts_ready / "v2", "external-duplicate")
    _write_valid_package(paths.artifacts_ready / "v4", "external-v4")

    embedded = package_index(paths, max_json_bytes=1024 * 1024, embedded_only=True)
    assert [item["package_dir"] for item in embedded["packages"]] == ["viewer-root", "v2"]
    assert all(item["location"] == "embedded" for item in embedded["packages"])

    full = package_index(paths, max_json_bytes=1024 * 1024)
    assert [item["package_dir"] for item in full["packages"]] == [
        "viewer-root",
        "v2",
        "v2",
        "v4",
    ]
    assert full["packages"][1]["location"] == "embedded"
    assert full["packages"][2]["location"] == "ready"
    assert full["packages"][3]["location"] == "ready"
