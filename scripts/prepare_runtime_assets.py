#!/usr/bin/env python3
"""Create a clean, allowlisted runtime resource tree for freezing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from viewer_package_inputs import (
    load_viewer_inputs,
    stage_viewer_packages,
    validate_viewer_package,
)

from arctic_route_control_center.release_policy import RELEASE_SCENARIO_IDS

# Viewer UI files copied from the work_package_d checkout.  This is the
# application shell (HTML/CSS/JS), not Viewer data: data packages are supplied
# per build via scripts/viewer_package_inputs.py and are never listed here.
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
)

REQUIRED_REPOSITORIES = (
    "arctic_route_contracts",
    "arctic_route_orchestrator",
    "work_package_a",
    "work_package_b",
    "work_package_c",
    "work_package_d",
)
EXPECTED_BRANCHES = {
    "arctic_route_control_center": "main",
    "work_package_d": "research-validation-system",
}

# Viewer data packages are declared per build; see scripts/viewer_package_inputs.py.
# No package name, default on-disk path, expected digest or file list is baked
# into this script, so packages can be added or retired without code changes.

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
    "scripts/viewer_package_inputs.py",
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





def git_output(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_head(path: Path) -> str:
    return git_output(path, "rev-parse", "HEAD")


def git_branch(path: Path) -> str:
    """Return a named branch; detached release inputs are not reproducible."""

    return git_output(path, "symbolic-ref", "--quiet", "--short", "HEAD")


def git_status(path: Path) -> str:
    return git_output(path, "status", "--porcelain", "--untracked-files=all")


def validate_source_repositories(root: Path, project_root: Path) -> dict[str, dict[str, object]]:
    """Require the exact branch boundary and clean source worktrees."""

    paths = {name: root / name for name in REQUIRED_REPOSITORIES}
    paths["arctic_route_control_center"] = project_root
    provenance: dict[str, dict[str, object]] = {}
    for name, path in paths.items():
        if not path.is_dir():
            raise FileNotFoundError(f"required source repository is missing: {path}")
        branch = git_branch(path)
        expected = EXPECTED_BRANCHES.get(name)
        if expected and branch != expected:
            raise ValueError(
                f"{name} must be checked out on {expected!r}; found {branch!r}"
            )
        dirty_files = git_status(path).splitlines()
        if dirty_files:
            raise ValueError(
                f"{name} worktree is dirty; commit or stash release inputs before building: "
                + ", ".join(dirty_files[:5])
            )
        provenance[name] = {
            "branch": branch,
            "dirty": False,
            "commit": git_head(path),
        }
    return provenance


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
    parser.add_argument(
        "--viewer-package",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Viewer data package directory to embed; repeat the flag for several "
            "packages. The first is the default package unless a manifest says "
            "otherwise. Omit entirely to embed no Viewer data."
        ),
    )
    parser.add_argument(
        "--viewer-manifest",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "JSON manifest listing the Viewer packages to embed "
            "(entries: path, optional name, optional default flag)."
        ),
    )
    args = parser.parse_args()
    root = args.workspace_root.resolve()
    output = args.output.resolve()
    project_root = Path(__file__).resolve().parents[1]
    source_provenance = validate_source_repositories(root, project_root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    viewer_source = root / "work_package_d" / "viewer"
    viewer_inputs = load_viewer_inputs(
        list(args.viewer_package),
        args.viewer_manifest,
        os.environ.get("ARCTIC_ROUTE_VIEWER_PACKAGES", ""),
        base_dir=project_root,
    )
    validated_packages = [validate_viewer_package(item) for item in viewer_inputs]
    if validated_packages:
        print(f"embedding {len(validated_packages)} viewer package(s)")
    else:
        print("no viewer package supplied: embedding viewer UI only")
    for relative in VIEWER_STATIC_ALLOWLIST:
        copy_file(viewer_source / relative, output / "viewer" / relative)
    embedded_index = stage_viewer_packages(validated_packages, output)
    viewer_static_hashes = {
        relative: sha256(viewer_source / relative) for relative in VIEWER_STATIC_ALLOWLIST
    }

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
        "work_package_d": ("src", "viewer", "pyproject.toml"),
    }
    source_roots = {name: root / name for name in repos}
    source_roots["arctic_route_control_center"] = project_root
    manifest = {
        "schema_version": "arctic-route-control-center.runtime-assets.v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_commits": {
            name: details["commit"] for name, details in source_provenance.items()
        },
        "source_provenance": source_provenance,
        "source_tree_identities": {
            name: source_tree_identity(source_roots[name], inputs)
            for name, inputs in source_inputs.items()
        },
        "viewer_source": (
            "work_package_d/viewer static allowlist + viewer packages supplied "
            "by this build"
        ),
        "viewer_static_files": viewer_static_hashes,
        "viewer_packages": embedded_index["packages"] if embedded_index else [],
        "default_viewer_package": (
            embedded_index["default_package"] if embedded_index else ""
        ),
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
