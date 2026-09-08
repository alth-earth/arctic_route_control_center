from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from viewer_package_inputs import (  # noqa: E402
    ViewerInputError,
    load_viewer_inputs,
    stage_viewer_packages,
    validate_viewer_package,
)


def _write_package(path: Path, scenario: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "replay.viewer-bundle.v1",
        "replay": {"scenario_id": scenario},
        "combined_presentation": {"status": "PUBLISHED", "assembly_id": f"asm-{scenario}"},
    }
    (path / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    digest = hashlib.sha256((path / "bundle.json").read_bytes()).hexdigest()
    (path / "checksums.json").write_text(
        json.dumps({"files": {"bundle.json": digest}}), encoding="utf-8"
    )


def test_zero_packages_is_valid(tmp_path: Path) -> None:
    inputs = load_viewer_inputs([], None, "", base_dir=tmp_path)
    assert inputs == []
    assert stage_viewer_packages([], tmp_path / "out") is None


def test_first_repeated_argument_becomes_default(tmp_path: Path) -> None:
    pkg_a = tmp_path / "alpha"
    pkg_b = tmp_path / "beta"
    _write_package(pkg_a, "a")
    _write_package(pkg_b, "b")
    inputs = load_viewer_inputs([str(pkg_a), str(pkg_b)], None, "", base_dir=tmp_path)
    assert len(inputs) == 2
    assert inputs[0].default and not inputs[1].default
    out = tmp_path / "out"
    index = stage_viewer_packages([validate_viewer_package(item) for item in inputs], out)
    assert index is not None
    assert index["default_package"] == "alpha"
    assert (out / "viewer" / "bundle.json").is_file()
    assert (out / "viewer" / "packages" / "beta" / "bundle.json").is_file()
    assert (out / "viewer" / "embedded-packages.json").is_file()


def test_manifest_declares_name_and_default(tmp_path: Path) -> None:
    pkg = tmp_path / "weird-dir-name"
    _write_package(pkg, "s1")
    manifest = tmp_path / "inputs.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "arctic-route-control-center.viewer-inputs.v1",
                "packages": [{"path": str(pkg), "name": "custom", "default": True}],
            }
        ),
        encoding="utf-8",
    )
    inputs = load_viewer_inputs([], manifest, "", base_dir=tmp_path)
    assert len(inputs) == 1
    assert inputs[0].name == "custom" and inputs[0].default
    out = tmp_path / "out"
    index = stage_viewer_packages([validate_viewer_package(inputs[0])], out)
    assert index is not None
    assert index["default_package"] == "custom"
    assert (out / "viewer" / "bundle.json").is_file()


def test_missing_checksums_is_rejected(tmp_path: Path) -> None:
    pkg = tmp_path / "broken"
    pkg.mkdir()
    (pkg / "bundle.json").write_text("{}", encoding="utf-8")
    item = load_viewer_inputs([str(pkg)], None, "", base_dir=tmp_path)[0]
    try:
        validate_viewer_package(item)
    except ViewerInputError as exc:
        assert "checksums.json" in str(exc)
    else:
        raise AssertionError("expected ViewerInputError")


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    pkg = tmp_path / "tampered"
    pkg.mkdir()
    (pkg / "bundle.json").write_text('{"x": 1}', encoding="utf-8")
    (pkg / "checksums.json").write_text(
        json.dumps({"files": {"bundle.json": "0" * 64}}), encoding="utf-8"
    )
    item = load_viewer_inputs([str(pkg)], None, "", base_dir=tmp_path)[0]
    try:
        validate_viewer_package(item)
    except ViewerInputError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("expected ViewerInputError")


def test_missing_directory_is_rejected(tmp_path: Path) -> None:
    item = load_viewer_inputs([str(tmp_path / "nope")], None, "", base_dir=tmp_path)[0]
    try:
        validate_viewer_package(item)
    except ViewerInputError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected ViewerInputError")


def test_environment_variable_is_parsed(tmp_path: Path) -> None:
    pkg = tmp_path / "env-pkg"
    _write_package(pkg, "env")
    inputs = load_viewer_inputs([], None, str(pkg), base_dir=tmp_path)
    assert len(inputs) == 1
    validated = validate_viewer_package(inputs[0])
    assert validated.name == "env-pkg"
    assert validated.default


def test_duplicate_package_name_is_rejected(tmp_path: Path) -> None:
    pkg_a = tmp_path / "dir" / "dup"
    pkg_b = tmp_path / "other" / "dup"
    _write_package(pkg_a, "a")
    _write_package(pkg_b, "b")
    inputs = load_viewer_inputs([str(pkg_a), str(pkg_b)], None, "", base_dir=tmp_path)
    validated = [validate_viewer_package(item) for item in inputs]
    try:
        stage_viewer_packages(validated, tmp_path / "out")
    except ViewerInputError as exc:
        assert "duplicate viewer package name" in str(exc)
    else:
        raise AssertionError("expected ViewerInputError")


def test_manifest_with_two_defaults_is_rejected(tmp_path: Path) -> None:
    pkg_a = tmp_path / "alpha"
    pkg_b = tmp_path / "beta"
    _write_package(pkg_a, "a")
    _write_package(pkg_b, "b")
    manifest = tmp_path / "inputs.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "arctic-route-control-center.viewer-inputs.v1",
                "packages": [
                    {"path": str(pkg_a), "default": True},
                    {"path": str(pkg_b), "default": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        load_viewer_inputs([], manifest, "", base_dir=tmp_path)
    except ViewerInputError as exc:
        assert "more than one default" in str(exc)
    else:
        raise AssertionError("expected ViewerInputError")
