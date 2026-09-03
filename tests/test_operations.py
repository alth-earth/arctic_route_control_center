from __future__ import annotations

from pathlib import Path

import pytest

from arctic_route_control_center.operations import build_job_spec
from arctic_route_control_center.paths import resolve_paths, safe_child


def _paths(tmp_path: Path):
    paths = resolve_paths(tmp_path)
    paths.ensure()
    return paths


def test_safe_child_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        safe_child(tmp_path, "../outside")


def test_acquisition_rejects_diagnostic_type(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    request = {
        "operation": "a_acquire",
        "parameters": {
            "scenario_id": "murmansk_dikson_august_2026_demo_v1",
            "sources": ["gfs"],
            "types": ["vessel_traffic"],
            "simulation_start": "",
        },
    }
    with pytest.raises(ValueError, match="non-formal"):
        build_job_spec(paths, request, "job-diagnostic")


def test_acquisition_rejects_source_type_mismatch(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    request = {
        "operation": "a_acquire",
        "parameters": {
            "scenario_id": "murmansk_dikson_august_2026_demo_v1",
            "sources": ["gfs"],
            "types": ["sea_ice_type"],
            "simulation_start": "",
        },
    }
    with pytest.raises(ValueError, match="do not provide"):
        build_job_spec(paths, request, "job-source-mismatch")


def test_shared_acquisition_spec_has_template_fields_not_overrides(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    request = {
        "operation": "a_acquire",
        "parameters": {
            "scenario_id": "murmansk_dikson_frozen_forecast_template_v1",
            "sources": ["gfs"],
            "types": ["temperature"],
            "simulation_start": "2026-01-12T00:00:00Z",
            "candidate_route_distance_nm": 1500,
        },
    }
    spec = build_job_spec(paths, request, "job-template")
    assert spec["parameters"]["simulation_start"] == "2026-01-12T00:00:00Z"
    assert spec["parameters"]["candidate_route_distance_nm"] == 1500
    assert "mode" not in spec["parameters"]
    assert "start" not in spec["parameters"]
    assert "end" not in spec["parameters"]


def test_research_scenario_is_not_executable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    request = {
        "operation": "a_bundle",
        "parameters": {
            "scenario_id": "tromso_isfjorden_february_2026_research_v1",
            "at": "2026-02-15T00:00:00Z",
            "types": ["temperature"],
            "mode": "causal",
        },
    }
    with pytest.raises(ValueError, match="unavailable"):
        build_job_spec(paths, request, "job-research")


def test_carra_independent_window_is_normalized(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    spec = build_job_spec(
        paths,
        {
            "operation": "a_carra_acquire",
            "parameters": {
                "corridor_id": "tromso_to_isfjorden_outer",
                "start": "2026-02-15T00:00:00Z",
                "end": "2026-02-21T00:00:00Z",
                "types": ["wind_field", "temperature", "visibility"],
            },
        },
        "job-carra",
    )
    assert spec["parameters"]["estimated_cycles"] == 49
    assert spec["parameters"]["start"] == "2026-02-15T00:00:00Z"


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2026-02-15T01:00:00Z", "2026-02-16T00:00:00Z", "3-hour"),
        ("2026-02-15T00:00:00", "2026-02-16T00:00:00Z", "UTC"),
        ("2026-02-15T00:00:00Z", "2026-03-01T00:00:00Z", "216"),
    ],
)
def test_carra_window_rejects_invalid_time_range(
    tmp_path: Path, start: str, end: str, message: str
) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match=message):
        build_job_spec(
            paths,
            {
                "operation": "a_carra_acquire",
                "parameters": {
                    "corridor_id": "tromso_to_isfjorden_outer",
                    "start": start,
                    "end": end,
                    "types": ["temperature"],
                },
            },
            "job-carra-invalid",
        )


def test_carra_rejects_non_carra_type(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="does not provide"):
        build_job_spec(
            paths,
            {
                "operation": "a_carra_acquire",
                "parameters": {
                    "corridor_id": "tromso_to_isfjorden_outer",
                    "start": "2026-02-15T00:00:00Z",
                    "end": "2026-02-16T00:00:00Z",
                    "types": ["wave"],
                },
            },
            "job-carra-type",
        )


def test_carra_rejects_unregistered_corridor(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="not registered"):
        build_job_spec(
            paths,
            {
                "operation": "a_carra_acquire",
                "parameters": {
                    "corridor_id": "unknown_arctic_corridor",
                    "start": "2026-02-15T00:00:00Z",
                    "end": "2026-02-16T00:00:00Z",
                    "types": ["temperature"],
                },
            },
            "job-carra-unknown",
        )
