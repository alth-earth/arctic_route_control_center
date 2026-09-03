"""Allowlisted job specification construction for the local HTTP API."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import AppPaths, safe_child
from .release_policy import (
    CARRA_DATA_TYPES,
    NETWORK_SOURCES,
    require_formal_data_types,
    require_release_scenario,
    require_sources_cover_types,
)

OPERATIONS = frozenset(
    {"a_acquire", "a_carra_acquire", "a_bundle", "orchestrator_run", "publish_viewer"}
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _text(value: Any, field: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{field} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{field} contains a NUL byte")
    return value.strip()


def _identifier(value: Any, field: str) -> str:
    result = _text(value, field)
    if _SAFE_ID.fullmatch(result) is None:
        raise ValueError(f"{field} is not a safe identifier")
    return result


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    return [_identifier(item, field) for item in value]


def _relative_existing(paths: AppPaths, value: Any, field: str, *, directory: bool = False) -> str:
    relative = _text(value, field)
    if Path(relative).is_absolute():
        raise ValueError(f"{field} must be relative to the application data directory")
    target = safe_child(paths.data_root, relative)
    if directory and not target.is_dir():
        raise ValueError(f"{field} directory does not exist")
    if not directory and not target.is_file():
        raise ValueError(f"{field} file does not exist")
    return str(target)


def _utc_three_hour(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{field} must include the UTC timezone")
    parsed = parsed.astimezone(UTC)
    if parsed.hour % 3 or parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError(f"{field} must align to a 3-hour UTC boundary")
    return parsed


def build_job_spec(paths: AppPaths, request: dict[str, Any], job_id: str) -> dict[str, Any]:
    operation = _text(request.get("operation"), "operation")
    if operation not in OPERATIONS:
        raise ValueError("operation is not allowlisted")
    raw = request.get("parameters")
    if not isinstance(raw, dict):
        raise ValueError("parameters must be an object")
    work = safe_child(paths.jobs_dir, job_id, "output")
    work.mkdir(parents=True, exist_ok=False)
    spec: dict[str, Any] = {
        "schema_version": "arctic-route-control-center.job-spec.v1",
        "job_id": job_id,
        "operation": operation,
        "data_root": str(paths.data_root),
        "a_data_root": str(paths.a_data_root),
        "output_dir": str(work),
        "parameters": {},
    }
    out = spec["parameters"]
    if operation == "a_acquire":
        scenario_id = _identifier(raw.get("scenario_id"), "scenario_id")
        require_release_scenario(scenario_id)
        sources = _string_list(raw.get("sources"), "sources")
        unknown_sources = sorted(set(sources) - NETWORK_SOURCES)
        if unknown_sources:
            raise ValueError("unavailable acquisition sources: " + ", ".join(unknown_sources))
        data_types = _string_list(raw.get("types"), "types")
        require_formal_data_types(data_types)
        require_sources_cover_types(sources, data_types)
        candidate_distance = raw.get("candidate_route_distance_nm")
        if candidate_distance in (None, ""):
            candidate_distance_value = None
        else:
            candidate_distance_value = float(candidate_distance)
            if not 0 < candidate_distance_value <= 10000:
                raise ValueError("candidate_route_distance_nm must be between 0 and 10000")
        out.update(
            {
                "scenario_id": scenario_id,
                "sources": sources,
                "types": data_types,
                "simulation_start": _text(
                    raw.get("simulation_start"), "simulation_start", required=False
                ),
                "candidate_route_distance_nm": candidate_distance_value,
            }
        )
    elif operation == "a_carra_acquire":
        corridor_id = _identifier(raw.get("corridor_id"), "corridor_id")
        from arctic_route_data.config import load_config

        from .resources import configuration_paths

        registered_corridors = load_config(configuration_paths()["a"]).corridors
        if corridor_id not in registered_corridors:
            raise ValueError(f"CARRA corridor is not registered in Work Package A: {corridor_id}")
        start = _utc_three_hour(raw.get("start"), "start")
        end = _utc_three_hour(raw.get("end"), "end")
        if end < start:
            raise ValueError("end must not be before start")
        window_hours = int((end - start).total_seconds() // 3600)
        if window_hours > 216:
            raise ValueError("CARRA acquisition window cannot exceed 216 hours")
        data_types = _string_list(raw.get("types"), "types")
        unsupported = sorted(set(data_types) - CARRA_DATA_TYPES)
        if unsupported:
            raise ValueError("CARRA does not provide these data types: " + ", ".join(unsupported))
        out.update(
            {
                "corridor_id": corridor_id,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "types": data_types,
                "estimated_cycles": window_hours // 3 + 1,
            }
        )
    elif operation == "a_bundle":
        scenario_id = _identifier(raw.get("scenario_id"), "scenario_id")
        require_release_scenario(scenario_id)
        data_types = _string_list(raw.get("types"), "types")
        require_formal_data_types(data_types)
        out.update(
            {
                "scenario_id": scenario_id,
                "at": _text(raw.get("at"), "at"),
                "types": data_types,
                "mode": _text(raw.get("mode", "causal"), "mode"),
                "knowledge_as_of": _text(
                    raw.get("knowledge_as_of"), "knowledge_as_of", required=False
                ),
            }
        )
    elif operation == "orchestrator_run":
        scenario_id = _identifier(raw.get("scenario_id"), "scenario_id")
        require_release_scenario(scenario_id)
        out.update(
            {
                "scenario_id": scenario_id,
                "dataset_bundle": _relative_existing(
                    paths, raw.get("dataset_bundle"), "dataset_bundle"
                ),
                "run_context": _relative_existing(paths, raw.get("run_context"), "run_context"),
                "b_config_name": _identifier(raw.get("b_config_name"), "b_config_name"),
                "planning_workers": int(raw.get("planning_workers", 3)),
                "stage_timeout_seconds": float(raw.get("stage_timeout_seconds", 3600)),
            }
        )
        if not 1 <= out["planning_workers"] <= 16:
            raise ValueError("planning_workers must be between 1 and 16")
        if not 30 <= out["stage_timeout_seconds"] <= 86400:
            raise ValueError("stage_timeout_seconds must be between 30 and 86400")
    else:
        fields = (
            "dataset_bundle",
            "run_context",
            "risk_window_commit",
            "plan_set",
            "risk_store_root",
        )
        for field in fields:
            out[field] = _relative_existing(
                paths,
                raw.get(field),
                field,
                directory=(field == "risk_store_root"),
            )
        for field in (
            "route_candidates",
            "route_integrity",
            "risk_frame_index",
            "land_mask",
            "risk_explanation_manifest",
            "winter_replay_manifest",
        ):
            value = raw.get(field)
            out[field] = _relative_existing(paths, value, field) if value else ""
        motions = raw.get("route_motion_sets") or []
        if not isinstance(motions, list):
            raise ValueError("route_motion_sets must be an array")
        out["route_motion_sets"] = [
            _relative_existing(paths, value, "route_motion_sets") for value in motions
        ]
        candidate_motions = raw.get("route_motion_candidate_sets") or []
        if not isinstance(candidate_motions, list):
            raise ValueError("route_motion_candidate_sets must be an array")
        out["route_motion_candidate_sets"] = [
            _relative_existing(paths, value, "route_motion_candidate_sets")
            for value in candidate_motions
        ]
        replay_snapshots = raw.get("winter_replay_snapshots_dir")
        out["winter_replay_snapshots_dir"] = (
            _relative_existing(
                paths,
                replay_snapshots,
                "winter_replay_snapshots_dir",
                directory=True,
            )
            if replay_snapshots
            else ""
        )
        out["scenario_id"] = _identifier(raw.get("scenario_id"), "scenario_id")
        require_release_scenario(out["scenario_id"])
        out["package_name"] = _identifier(raw.get("package_name"), "package_name")
    # Round-trip enforces JSON-safe values before a worker sees them.
    return json.loads(json.dumps(spec, allow_nan=False))
