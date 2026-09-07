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
)

# Generated replay data is intentionally kept separate from the D source
# checkout.  D ignores these files, so a clean remote checkout uses the
# tracked immutable root snapshot below while static code still comes from D.
VIEWER_ROOT_DATA_ALLOWLIST = (*VIEWER_CHECKSUM_ALLOWLIST, "checksums.json")
VIEWER_FILE_ALLOWLIST = VIEWER_STATIC_ALLOWLIST + VIEWER_ROOT_DATA_ALLOWLIST

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

# Linux AppImage and Windows onedir intentionally carry exactly two Viewer
# packages: the original dynamic replay from D as the default root package,
# plus the checksum-verified v4 package from the user's ready store.  Keep the
# ready input explicit and fail closed if a different package is supplied by
# accident (for example v2).
EMBEDDED_READY_PACKAGE_NAME = "winter-rebuilt-20260215-viewer-package-v4"
EMBEDDED_READY_PACKAGE_BUNDLE_SHA256 = (
    "f993ac113ac7280e9378710fdc84a825338ebd6ea4b5193ce8679aeb5c3b114a"
)
EMBEDDED_READY_PACKAGE_CHECKSUMS_SHA256 = (
    "92ca583e52d41d277d22750631f083b0de798cb5ce8f9b105ef7a1d0123f7d33"
)
EMBEDDED_READY_PACKAGE_ASSEMBLY_ID = (
    "winter-viewer-sha256-f3113a19243bce88f712717ad91bddd9d3c76d93c6d84ac3c57e930496dff1ad"
)


def _default_embedded_ready_package() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (
            base
            / "ArcticRouteControlCenter"
            / "artifacts"
            / "ready"
            / EMBEDDED_READY_PACKAGE_NAME
        )
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (
        base
        / "arctic-route-control-center"
        / "artifacts"
        / "ready"
        / EMBEDDED_READY_PACKAGE_NAME
    )


DEFAULT_EMBEDDED_READY_PACKAGE = _default_embedded_ready_package()

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
    "packaging/viewer-root",
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


def copy_embedded_ready_package(source: Path, output: Path) -> dict[str, object]:
    """Copy one immutable ready package without changing any of its bytes."""

    if source.name != EMBEDDED_READY_PACKAGE_NAME:
        raise ValueError(
            "the embedded ready package must be "
            f"{EMBEDDED_READY_PACKAGE_NAME}, got {source.name}"
        )
    if not source.is_dir():
        raise FileNotFoundError(f"ready Viewer package is missing: {source}")
    bundle_path = source / "bundle.json"
    checksums_path = source / "checksums.json"
    if sha256(bundle_path) != EMBEDDED_READY_PACKAGE_BUNDLE_SHA256:
        raise ValueError("ready v4 bundle.json SHA256 does not match the audited artifact")
    if sha256(checksums_path) != EMBEDDED_READY_PACKAGE_CHECKSUMS_SHA256:
        raise ValueError("ready v4 checksums.json SHA256 does not match the audited artifact")
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"ready v4 metadata is invalid: {exc}") from exc
    presentation = bundle.get("combined_presentation")
    if not isinstance(presentation, dict) or presentation.get("status") != "PUBLISHED":
        raise ValueError("ready v4 combined presentation is not PUBLISHED")
    if presentation.get("assembly_id") != EMBEDDED_READY_PACKAGE_ASSEMBLY_ID:
        raise ValueError("ready v4 assembly identity does not match the audited artifact")
    files = checksums.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("ready v4 checksums file map is malformed")
    if any(
        not isinstance(relative, str)
        or Path(relative).name != relative
        or Path(relative).is_absolute()
        or not isinstance(expected, str)
        or len(expected) != 64
        for relative, expected in files.items()
    ):
        raise ValueError("ready v4 checksum entry is malformed")
    expected_names = set(files) | {"checksums.json"}
    actual_names = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
    }
    if actual_names != expected_names:
        raise ValueError(
            "ready v4 package file set changed: "
            f"unexpected={sorted(actual_names - expected_names)}, "
            f"missing={sorted(expected_names - actual_names)}"
        )
    for relative, expected in files.items():
        if sha256(source / relative) != expected:
            raise ValueError(f"ready v4 checksum mismatch: {relative}")
    target = output / "viewer" / "packages" / EMBEDDED_READY_PACKAGE_NAME
    copy_file(checksums_path, target / "checksums.json")
    for relative in sorted(files):
        copy_file(source / relative, target / relative)
    return {
        "package_dir": EMBEDDED_READY_PACKAGE_NAME,
        "source": "artifacts/ready/" + EMBEDDED_READY_PACKAGE_NAME,
        "bundle_sha256": EMBEDDED_READY_PACKAGE_BUNDLE_SHA256,
        "checksums_sha256": EMBEDDED_READY_PACKAGE_CHECKSUMS_SHA256,
        "assembly_id": EMBEDDED_READY_PACKAGE_ASSEMBLY_ID,
        "files": sorted(expected_names),
    }


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
        "--ready-package",
        type=Path,
        default=Path(os.environ.get("ARCTIC_ROUTE_READY_PACKAGE", DEFAULT_EMBEDDED_READY_PACKAGE)),
        help="audited ready-store package to embed alongside the original dynamic package",
    )
    parser.add_argument(
        "--viewer-root",
        type=Path,
        default=Path(
            os.environ.get(
                "ARCTIC_ROUTE_VIEWER_ROOT",
                Path(__file__).resolve().parents[1] / "packaging" / "viewer-root",
            )
        ),
        help="immutable root Viewer data package (defaults to tracked packaging/viewer-root)",
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
    viewer_root = args.viewer_root.expanduser().resolve()
    checksums = json.loads((viewer_root / "checksums.json").read_text(encoding="utf-8"))
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
    root_names = {
        path.relative_to(viewer_root).as_posix()
        for path in viewer_root.rglob("*")
        if path.is_file()
    }
    if root_names != set(VIEWER_ROOT_DATA_ALLOWLIST):
        raise ValueError(
            "tracked root Viewer file set changed: "
            f"unexpected={sorted(root_names - set(VIEWER_ROOT_DATA_ALLOWLIST))}, "
            f"missing={sorted(set(VIEWER_ROOT_DATA_ALLOWLIST) - root_names)}"
        )
    for relative in VIEWER_CHECKSUM_ALLOWLIST:
        expected = files[relative]
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"current Viewer checksum is malformed: {relative}")
        relative_path = Path(relative)
        if relative_path.name != relative or relative_path.is_absolute():
            raise ValueError(f"Viewer resource path is not a flat allowlisted file: {relative}")
        source = viewer_root / relative
        if sha256(source) != expected:
            raise ValueError(f"root Viewer checksum mismatch: {relative}")
    for relative in VIEWER_STATIC_ALLOWLIST:
        copy_file(viewer_source / relative, output / "viewer" / relative)
    for relative in VIEWER_ROOT_DATA_ALLOWLIST:
        copy_file(viewer_root / relative, output / "viewer" / relative)
    embedded_ready = copy_embedded_ready_package(
        args.ready_package.expanduser().resolve(), output
    )
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
            "work_package_d/viewer static allowlist + tracked packaging/viewer-root data"
        ),
        "viewer_files": list(VIEWER_FILE_ALLOWLIST),
        "viewer_static_files": viewer_static_hashes,
        "viewer_checksum_allowlist": list(VIEWER_CHECKSUM_ALLOWLIST),
        "viewer_root_data_source": "arctic_route_control_center/packaging/viewer-root",
        "viewer_embedded_packages": [embedded_ready],
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
