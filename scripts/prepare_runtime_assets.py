#!/usr/bin/env python3
"""Create a clean, allowlisted runtime resource tree for freezing."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from arctic_route_control_center.release_policy import RELEASE_SCENARIO_IDS

# This is deliberately a literal list.  The D Viewer directory contains
# proof images, self-contained/demo HTML, helper scripts and historical
# packages in addition to the release bundle.  Copying the directory (or
# accepting every key from a changed checksums.json) would make a new file a
# release input without a review of this project.
VIEWER_CHECKSUM_ALLOWLIST = (
    "basemap_metadata.json",
    "bundle.json",
    "four-layer-route-plan-set-v3.json",
    "gebco_basemap.png",
    "replay-viewer-preflight.json",
    "route-motion-candidate-set-r1.json",
    "route-motion-candidate-set-r2.json",
    "route-motion-candidate-set-r3.json",
    "route-motion-candidate-set-r4.json",
    "route-motion-candidate-set-r5.json",
    "route-motion-candidate-set-r6.json",
    "route-motion-candidate-set-r7.json",
    "route-motion-candidate-set-r8.json",
    "route-motion-candidate-set-r9.json",
    "route-motion-set-r1.json",
    "route-motion-set-r2.json",
    "route-motion-set-r3.json",
    "route-motion-set-r4.json",
    "route-motion-set-r5.json",
    "route-motion-set-r6.json",
    "route-motion-set-r7.json",
    "route-motion-set-r8.json",
    "route-motion-set-r9.json",
    "winter-combined-viewer-manifest.json",
    "publish-summary.json",
)

VIEWER_STATIC_ALLOWLIST = (
    "index.html",
    "style.css",
    "app.js",
    "package_picker.js",
    "package_picker.css",
    "research_candidates.js",
    "risk_explanation.js",
    "route_motion.js",
    "runtime_route_candidates.js",
    "route_visual_smoothing.js",
    "favicon.svg",
    "checksums.json",
)

VIEWER_FILE_ALLOWLIST = VIEWER_STATIC_ALLOWLIST + VIEWER_CHECKSUM_ALLOWLIST

# Keep this copy boundary independent from the source tree layout.  A new
# contract file must be explicitly reviewed here before it can enter a
# frozen package.
RELEASE_SCENARIO_ALLOWLIST = (
    "murmansk_dikson_august_2026_demo_v1",
    "murmansk_dikson_frozen_forecast_template_v1",
    "murmansk_dikson_july_2026_retrospective_v1",
    "tromso_isfjorden_august_2026_demo_v1",
    "tromso_isfjorden_frozen_forecast_template_v1",
    "tromso_isfjorden_july_2026_retrospective_v1",
)
RELEASE_CORRIDOR_ALLOWLIST = (
    "offshore_murmansk_to_offshore_dikson.toml",
    "tromso_to_isfjorden_outer.toml",
)
RELEASE_VESSEL_ALLOWLIST = ("nordic_odyssey_reference_v1.toml",)

CONTROL_CENTER_SOURCE_IDENTITY_INPUTS = (
    "src",
    "packaging/entrypoint.py",
    "packaging/arctic_route_control_center.spec",
    "packaging/linux",
    "packaging/windows",
    "scripts/prepare_runtime_assets.py",
    "scripts/scan_release.py",
    "scripts/sanitize_frozen_tree.py",
    "scripts/verify_runtime.py",
    "pyproject.toml",
    "uv.lock",
)

if tuple(RELEASE_SCENARIO_IDS) != RELEASE_SCENARIO_ALLOWLIST:
    raise RuntimeError(
        "release scenario policy drift: update the reviewed packaging allowlist"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"required runtime file is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_tree_identity(root: Path, inputs: tuple[str, ...]) -> dict[str, object]:
    """Digest the actual source inputs, including uncommitted/new code."""

    records: list[tuple[str, str]] = []
    for relative in inputs:
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(f"source identity input is missing: {source}")
        candidates = source.rglob("*") if source.is_dir() else (source,)
        for path in candidates:
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            records.append((path.relative_to(root).as_posix(), sha256(path)))
    records.sort()
    digest = hashlib.sha256()
    for relative, file_digest in records:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return {"sha256": digest.hexdigest(), "file_count": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace_root.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    viewer_source = root / "work_package_d" / "viewer"
    checksums = json.loads((viewer_source / "checksums.json").read_text(encoding="utf-8"))
    files = checksums.get("files")
    if not isinstance(files, dict) or "bundle.json" not in files:
        raise ValueError("current Viewer checksums.json is malformed")
    checksum_paths = tuple(files)
    if set(checksum_paths) != set(VIEWER_CHECKSUM_ALLOWLIST):
        unexpected = sorted(set(checksum_paths) - set(VIEWER_CHECKSUM_ALLOWLIST))
        missing = sorted(set(VIEWER_CHECKSUM_ALLOWLIST) - set(checksum_paths))
        raise ValueError(
            "current Viewer checksum allowlist drift: "
            f"unexpected={unexpected}, missing={missing}"
        )
    for relative in VIEWER_CHECKSUM_ALLOWLIST:
        expected = files[relative]
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"current Viewer checksum is malformed: {relative}")
        relative_path = Path(relative)
        if relative_path.name != relative or relative_path.is_absolute():
            raise ValueError(f"Viewer resource path is not a flat allowlisted file: {relative}")
        source = viewer_source / relative
        if sha256(source) != expected:
            raise ValueError(f"current Viewer checksum mismatch: {relative}")
    for relative in VIEWER_FILE_ALLOWLIST:
        copy_file(viewer_source / relative, output / "viewer" / relative)

    contracts = root / "arctic_route_contracts" / "configs"
    for scenario_id in RELEASE_SCENARIO_ALLOWLIST:
        copy_file(
            contracts / "scenarios" / f"{scenario_id}.toml",
            output / "configs" / "contracts" / "scenarios" / f"{scenario_id}.toml",
        )
    for corridor_name in RELEASE_CORRIDOR_ALLOWLIST:
        copy_file(
            contracts / "corridors" / corridor_name,
            output / "configs" / "contracts" / "corridors" / corridor_name,
        )
    for vessel_name in RELEASE_VESSEL_ALLOWLIST:
        copy_file(
            contracts / "vessels" / vessel_name,
            output / "configs" / "contracts" / "vessels" / vessel_name,
        )
    copy_file(
        Path(__file__).resolve().parents[1] / "config" / "work_package_a.release.toml",
        output / "configs" / "a" / "work_package_a.toml",
    )
    for name in ("final_delivery_comprehensive_risk_v1.json",):
        copy_file(
            root / "work_package_b" / "configs" / "models" / name,
            output / "configs" / "b" / name,
        )
    for relative in (
        "planner/default.toml",
        "replanning/default.toml",
        "vessel_models/nordic_odyssey_reference_v1.toml",
    ):
        copy_file(
            root / "work_package_c" / "configs" / relative,
            output / "configs" / "c" / relative,
        )

    for name in ("replay_viewer_export.py",):
        copy_file(
            root / "arctic_route_orchestrator" / "scripts" / name,
            output / "orchestrator_scripts" / name,
        )

    repos = (
        "arctic_route_contracts",
        "arctic_route_orchestrator",
        "work_package_a",
        "work_package_b",
        "work_package_c",
        "work_package_d",
    )
    source_inputs = {
        "arctic_route_control_center": CONTROL_CENTER_SOURCE_IDENTITY_INPUTS,
        "arctic_route_contracts": ("src", "configs", "pyproject.toml"),
        "arctic_route_orchestrator": (
            "src",
            "scripts/replay_viewer_export.py",
            "pyproject.toml",
        ),
        "work_package_a": ("src", "pyproject.toml"),
        "work_package_b": ("src", "pyproject.toml"),
        "work_package_c": ("src", "pyproject.toml"),
        "work_package_d": ("src", "pyproject.toml"),
    }
    source_roots = {name: root / name for name in repos}
    source_roots["arctic_route_control_center"] = Path(__file__).resolve().parents[1]
    manifest = {
        "schema_version": "arctic-route-control-center.runtime-assets.v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_commits": {name: git_head(root / name) for name in repos},
        "source_tree_identities": {
            name: source_tree_identity(source_roots[name], inputs)
            for name, inputs in source_inputs.items()
        },
        "viewer_source": "work_package_d/viewer (current checksum-verified package)",
        "viewer_files": list(VIEWER_FILE_ALLOWLIST),
        "viewer_checksum_allowlist": list(VIEWER_CHECKSUM_ALLOWLIST),
        "contract_scenario_allowlist": list(RELEASE_SCENARIO_ALLOWLIST),
        "contract_corridor_allowlist": list(RELEASE_CORRIDOR_ALLOWLIST),
        "contract_vessel_allowlist": list(RELEASE_VESSEL_ALLOWLIST),
        "excluded_profiles": [
            "work_package_b model-cpu and legacy CNN",
            "work_package_b calibration/grid experiments",
            "work_package_c research configs and synthetic/legacy CLIs",
            "work_package_d legacy demo server and historical output packages",
            "RC1/RC2/demo-engineering source branches and backups",
        ],
    }
    manifest["files"] = {
        path.relative_to(output).as_posix(): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    (output / "runtime-assets-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "output": str(output), "files": len(manifest["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
