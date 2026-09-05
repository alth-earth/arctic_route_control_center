"""Fail-visible discovery and promotion of immutable Viewer packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import AppPaths, safe_child

_SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _read_json(path: Path, *, max_bytes: int) -> Any:
    if path.stat().st_size > max_bytes:
        raise ValueError(f"{path.name} exceeds configured JSON size limit")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_non_finite,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_viewer_package(
    package_dir: Path,
    *,
    max_json_bytes: int = 96 * 1024 * 1024,
    verify_checksums: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    bundle_path = package_dir / "bundle.json"
    try:
        bundle = _read_json(bundle_path, max_bytes=max_json_bytes)
        if not isinstance(bundle, dict):
            raise ValueError("bundle.json is not an object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "package_dir": package_dir.name,
            "status": "incomplete",
            "reason": f"bundle invalid: {exc}",
            "bundle_path": "",
        }

    if bundle.get("schema_version") != "replay.viewer-bundle.v1":
        reasons.append("unsupported bundle schema")
    presentation = bundle.get("combined_presentation")
    if not isinstance(presentation, dict) or presentation.get("status") != "PUBLISHED":
        reasons.append("combined presentation is not PUBLISHED")
        presentation = presentation if isinstance(presentation, dict) else {}
    candidates = bundle.get("route_candidates")
    if not isinstance(candidates, dict) or candidates.get("status") != "PUBLISHED":
        reasons.append("route candidates are not PUBLISHED")
        candidates = candidates if isinstance(candidates, dict) else {}
    if len(candidates.get("candidates") or []) != 12:
        reasons.append("route candidate set is not complete (expected 12)")
    motion = bundle.get("formal_motion_inspection")
    if not isinstance(motion, dict) or motion.get("valid") is not True:
        reasons.append("formal motion validation is not PASS")
    gates = bundle.get("gates")
    if not isinstance(gates, dict) or gates.get("status") != "PASS":
        reasons.append("viewer preflight gate is not PASS")

    checksum_path = package_dir / "checksums.json"
    if verify_checksums:
        if not checksum_path.is_file():
            reasons.append("checksums.json is missing")
        else:
            try:
                checksum_doc = _read_json(checksum_path, max_bytes=max_json_bytes)
                files = checksum_doc.get("files") if isinstance(checksum_doc, dict) else None
                if not isinstance(files, dict) or not files:
                    raise ValueError("checksum file map is empty")
                if "bundle.json" not in files:
                    raise ValueError("bundle.json checksum is missing")
                for relative, expected in files.items():
                    if not isinstance(relative, str) or not isinstance(expected, str):
                        raise ValueError("checksum entry is malformed")
                    target = safe_child(package_dir, relative)
                    if not target.is_file():
                        raise ValueError(f"checksummed file is missing: {relative}")
                    if _sha256(target) != expected:
                        raise ValueError(f"checksum mismatch: {relative}")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                reasons.append(str(exc))

    replay = bundle.get("replay") if isinstance(bundle.get("replay"), dict) else {}
    risk = bundle.get("risk") if isinstance(bundle.get("risk"), dict) else {}
    risk_source = risk.get("source") if isinstance(risk.get("source"), dict) else {}
    corridor_id = risk_source.get("corridor_id") or presentation.get("corridor_id") or ""
    scenario_id = replay.get("scenario_id") or presentation.get("scenario_id") or ""
    result = {
        "package_dir": package_dir.name,
        "display_name": f"{scenario_id or package_dir.name}",
        "scenario_id": scenario_id,
        "corridor_id": corridor_id,
        "simulation_start": replay.get("start", ""),
        "simulation_end": replay.get("end", ""),
        "dataset_bundle_id": presentation.get("dataset_bundle_id", ""),
        "risk_window_id": presentation.get("risk_window_id", ""),
        "candidate_set_id": presentation.get("candidate_set_id", ""),
        "selected_candidate_id": presentation.get("selected_candidate_id", ""),
        "route_count": len(candidates.get("candidates") or []),
        "risk_frame_count": len(risk.get("frames") or []),
        "has_risk_explanation": bool(bundle.get("risk_explanation")),
        "status": "ready" if not reasons else "incomplete",
        "reason": "; ".join(reasons) if reasons else None,
        "bundle_path": f"packages/{package_dir.name}/bundle.json",
    }
    return result


def _package_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        child
        for child in sorted(root.iterdir())
        if child.is_dir() and _SAFE_PACKAGE.fullmatch(child.name)
    ]


def package_index(
    paths: AppPaths,
    *,
    max_json_bytes: int,
    embedded_only: bool = False,
) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    default = inspect_viewer_package(
        paths.viewer_static,
        max_json_bytes=max_json_bytes,
        verify_checksums=True,
    )
    default.update(
        {
            "package_dir": "viewer-root",
            "display_name": f"{default.get('display_name', '当前制品')}（打包默认）",
            "bundle_path": "bundle.json",
            "location": "embedded",
        }
    )
    packages.append(default)
    embedded_root = paths.viewer_static / "packages"
    for child in _package_dirs(embedded_root):
        item = inspect_viewer_package(child, max_json_bytes=max_json_bytes)
        item["location"] = "embedded"
        packages.append(item)
    if not embedded_only:
        for child in _package_dirs(paths.artifacts_ready):
            item = inspect_viewer_package(child, max_json_bytes=max_json_bytes)
            item["location"] = "ready"
            item["bundle_path"] = f"ready-packages/{child.name}/bundle.json"
            packages.append(item)
        for child in _package_dirs(paths.artifacts_inbox):
            item = inspect_viewer_package(child, max_json_bytes=max_json_bytes)
            item["location"] = "inbox"
            item["bundle_path"] = ""
            packages.append(item)
    return {
        "schema_version": "d.viewer-package-index.v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "default_package": "viewer-root",
        "packages": packages,
    }


def promote_from_inbox(
    paths: AppPaths, package_name: str, *, max_json_bytes: int
) -> dict[str, Any]:
    if _SAFE_PACKAGE.fullmatch(package_name) is None:
        raise ValueError("unsafe package name")
    source = safe_child(paths.artifacts_inbox, package_name)
    target = safe_child(paths.artifacts_ready, package_name)
    if not source.is_dir():
        raise ValueError("package does not exist in artifacts/inbox")
    if target.exists():
        raise ValueError("a ready package with this name already exists")
    report = inspect_viewer_package(source, max_json_bytes=max_json_bytes)
    if report["status"] != "ready":
        raise ValueError(f"package validation failed: {report['reason']}")
    os.replace(source, target)
    return inspect_viewer_package(target, max_json_bytes=max_json_bytes)
