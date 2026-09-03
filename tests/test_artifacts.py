from __future__ import annotations

import hashlib
import json
from pathlib import Path

from arctic_route_control_center.artifacts import inspect_viewer_package


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
