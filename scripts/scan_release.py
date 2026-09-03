#!/usr/bin/env python3
"""Scan a frozen release tree for content that must never be shipped.

The scanner intentionally has no project-package imports so that it can be
used from a build venv, a verification-only checkout, or a Windows handoff.
It checks both path names and text payloads.  Every finding is a release
failure: there is no provenance, credential, or other allow-list exception.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path

_TEXT_SUFFIXES = frozenset(
    {
        ".bat",
        ".cfg",
        ".css",
        ".desktop",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".pyi",
        ".sh",
        ".svg",
        ".toml",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
_CONTENT_CHUNK_SIZE = 1024 * 1024
_CONTENT_CARRY_SIZE = 1024

_POSIX_ABSOLUTE = re.compile(
    rb"(?<![A-Za-z0-9_/:])/(?:root|home|mnt|tmp|workspace|workspaces|Users|opt|srv|var|run|build|builds|agent|runner|project|repo|repos|checkout|checkouts|code|src|work)/"
    rb"[^\x00\r\n\t \"'<>]{1,240}"
)
_WINDOWS_ABSOLUTE = re.compile(
    rb"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"
    rb"[^\x00\r\n\t \\\"'<>]{1,96}[\\/]"
    rb"[^\x00\r\n\t \\\"'<>]{1,240}"
)
_UNC_ABSOLUTE = re.compile(
    rb"(?<![A-Za-z0-9_])\\\\(?:Users|home|root|workspaces?|builds?|agents?|runners?|projects?|repos?|checkouts?|code|src|work)\\"
    rb"[^\x00\r\n\t \"'<>]{1,240}"
)
_FILE_URI = re.compile(rb"file:///(?:[^\x00\r\n\t \"'<>]{1,240})")
_SECRET_ASSIGNMENT = re.compile(
    rb"(?im)(?<![A-Za-z0-9_])[\"']?(?:"
    rb"COPERNICUSMARINE_(?:SERVICE_)?(?:USERNAME|PASSWORD)|"
    rb"CDSAPI_(?:KEY|URL)|"
    rb"(?:API|ACCESS|SECRET)[_-]?KEY|PASSWORD"
    rb")[\"']?\s*[:=]\s*[\"']?\S+"
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _project_experimental_marker(relative: str) -> str | None:
    """Return a marker only for project code, not third-party data names."""

    parts = relative.casefold().split("/")
    project_namespace = any(part.startswith("arctic_route_") for part in parts)
    if not project_namespace:
        return None
    markers = (
        "experimental",
        "calibration_shadow",
        "formal_grid_experiments",
        "grid_experiments",
        "model-cpu",
        "model_cpu",
        "legacy_cnn",
        "legacy-cnn",
        "coupling_benchmark",
        "profiling",
        "development",
    )
    for part in parts:
        if any(marker in part for marker in markers):
            return part
    # The packaged D replay intentionally contains this one research-side
    # display script.  Other research modules from A/B/C/Orchestrator are not
    # release dependencies.
    if "viewer" not in parts:
        for part in parts:
            if part == "research" or part.startswith("research_"):
                return part
    return None


def _is_project_managed_release_file(relative: str) -> bool:
    """Separate audited app resources from opaque third-party package data."""

    parts = relative.casefold().split("/")
    try:
        internal_index = parts.index("_internal")
    except ValueError:
        return True
    if internal_index + 1 >= len(parts):
        return True
    root = parts[internal_index + 1]
    return root in {
        "configs",
        "orchestrator_scripts",
        "runtime-assets-manifest.json",
        "static",
        "viewer",
    } or root.startswith("arctic_route_")


def _path_findings(root: Path, path: Path) -> list[dict[str, str]]:
    relative = _relative(root, path)
    findings: list[dict[str, str]] = []
    forbidden_data_suffix = _is_project_managed_release_file(
        relative
    ) and path.suffix.casefold() in {
        ".bz2",
        ".csv",
        ".gz",
        ".grib",
        ".grib1",
        ".grib2",
        ".grb",
        ".grb1",
        ".grb2",
        ".nc",
        ".nc4",
        ".netcdf",
        ".h5",
        ".hdf5",
        ".jp2",
        ".parquet",
        ".tar",
        ".tif",
        ".tiff",
        ".zarr",
    }
    for part in relative.casefold().split("/"):
        if (
            part in {"direct_url.json", "uv_cache.json", ".cdsapirc"}
            or part in {"torch", "safetensors"}
            or part.startswith("torch-")
            or part.startswith("safetensors-")
            or part == ".env"
            or part.startswith(".env.")
            or part in {"credentials", "credential"}
            or part.startswith("credentials.")
            or part.startswith("credential.")
            or "demo-engineering" in part
            or "demo_engineering" in part
            or part
            in {
                "raw",
                "raw_data",
                "raw-data",
                "rawdata",
                "raw_grib",
                "raw-grib",
                "original",
                "original_data",
                "original-data",
                "downloads",
                "download",
                "archives",
                "archive",
            }
            or part.startswith(
                (
                    "raw_",
                    "raw-",
                    "original_",
                    "original-",
                    "download_",
                    "download-",
                    "archive_",
                    "archive-",
                )
            )
        ):
            findings.append(
                {
                    "kind": "forbidden_path",
                    "path": relative,
                    "detail": f"forbidden release path segment: {part}",
                }
            )
        if re.search(r"(?:^|[_.-])rc[12](?:$|[_.-])", part):
            findings.append(
                {
                    "kind": "forbidden_path",
                    "path": relative,
                    "detail": f"historical RC marker in release path: {part}",
                }
            )
        if part in {"historical", "history"} and any(
            item.startswith("arctic_route_") for item in relative.casefold().split("/")
        ):
            # Do not reject ecCodes' own legacy/history definitions.  A
            # project-owned historical directory is still an accidental
            # release input.
            findings.append(
                {
                    "kind": "forbidden_path",
                    "path": relative,
                    "detail": f"historical project path segment: {part}",
                }
            )
    if forbidden_data_suffix:
        findings.append(
            {
                "kind": "forbidden_path",
                "path": relative,
                "detail": f"raw data file suffix is not allowed: {path.suffix.casefold()}",
            }
        )
    marker = _project_experimental_marker(relative)
    if marker is not None:
        findings.append(
            {
                "kind": "experimental_dependency",
                "path": relative,
                "detail": f"experimental project path segment: {marker}",
            }
        )
    return findings


def _content_match(path: Path, workspace_root: Path | None) -> str | None:
    patterns: list[tuple[str, re.Pattern[bytes]]] = [
        ("build_machine_absolute_path", _POSIX_ABSOLUTE),
        ("build_machine_absolute_path", _WINDOWS_ABSOLUTE),
        ("build_machine_absolute_path", _UNC_ABSOLUTE),
        ("build_machine_absolute_path", _FILE_URI),
        ("credential_value", _SECRET_ASSIGNMENT),
    ]
    if workspace_root is not None:
        # Also catch a non-standard CI checkout such as /build/runner/project
        # or E:\\agent\\_work\\route. Both separator spellings are checked so
        # the scanner can audit an artifact copied between operating systems.
        for value in {
            str(workspace_root),
            str(workspace_root).replace("/", "\\"),
            str(workspace_root).replace("\\", "/"),
        }:
            if len(value) > 3:
                patterns.append(
                    (
                        "build_machine_absolute_path",
                        re.compile(re.escape(value).encode("utf-8")),
                    )
                )
    try:
        with path.open("rb") as handle:
            carry = b""
            while True:
                chunk = handle.read(_CONTENT_CHUNK_SIZE)
                if not chunk:
                    return None
                window = carry + chunk
                for label, pattern in patterns:
                    if pattern.search(window):
                        return label
                carry = window[-_CONTENT_CARRY_SIZE:]
    except OSError as exc:
        return f"unreadable_release_file: {exc}"


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def scan_release(
    root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"release root is missing or not a directory: {root}")
    errors: list[dict[str, str]] = []
    scanned_files = 0
    for path in _iter_files(root):
        scanned_files += 1
        relative = _relative(root, path)
        errors.extend(_path_findings(root, path))
        if path.suffix.casefold() not in _TEXT_SUFFIXES and path.name != "METADATA":
            continue
        # Third-party wheels can legitimately contain credential field names in
        # AWS/JSON-Schema models.  Secret-shaped content scanning therefore
        # applies to the app-owned allowlist; absolute build paths remain a
        # whole-artifact failure and are checked for every text file.
        content_workspace = workspace_root
        match = _content_match(path, content_workspace)
        if match == "credential_value" and not _is_project_managed_release_file(relative):
            match = None
        if match is None:
            continue
        finding = {
            "kind": match,
            "path": relative,
            "detail": "content contains a build-machine path or credential-shaped value",
        }
        errors.append(finding)

    if errors:
        status = "FAIL"
        exit_code = 1
    else:
        status = "PASS"
        exit_code = 0
    return {
        "status": status,
        "exit_code": exit_code,
        "root": str(root),
        "scanned_files": scanned_files,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="frozen AppDir/EXE directory")
    parser.add_argument(
        "--workspace-root", type=Path, help="optional source workspace for audit logs"
    )
    args = parser.parse_args()
    result = scan_release(
        args.root,
        workspace_root=args.workspace_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
