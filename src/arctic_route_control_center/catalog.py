"""Read-only system catalog built from public package contracts."""

from __future__ import annotations

import importlib.metadata
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .release_policy import (
    CARRA_DATA_TYPES,
    DIAGNOSTIC_DATA_TYPES,
    EXCLUDED_SCENARIOS,
    FORMAL_OPTIONAL_DATA_TYPES,
    FORMAL_REQUIRED_DATA_TYPES,
    RELEASE_SCENARIO_IDS,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def module_versions() -> list[dict[str, str]]:
    names = (
        "arctic-route-control-center",
        "arctic-route-contracts",
        "arctic-route-data",
        "arctic-route-risk",
        "arctic-route-planning",
        "arctic-route-orchestrator",
        "arctic-route-display",
    )
    result = []
    for name in names:
        try:
            version = importlib.metadata.version(name)
            status = "available"
        except importlib.metadata.PackageNotFoundError:
            version = "not-installed"
            status = "unavailable"
        result.append({"package": name, "version": version, "status": status})
    return result


def contract_catalog() -> dict[str, Any]:
    from arctic_route_contracts.config import (
        list_config_ids,
        load_corridor,
        load_scenario,
        load_vessel_profile,
    )

    from .resources import configuration_paths

    config_root = configuration_paths()["contracts"]
    ids = list_config_ids(config_root)
    corridors = {
        item: _jsonable(asdict(load_corridor(config_root, item))) for item in ids["corridors"]
    }
    scenarios = {
        item: _jsonable(asdict(load_scenario(config_root, item))) for item in ids["scenarios"]
    }
    vessels = {
        item: _jsonable(asdict(load_vessel_profile(config_root, item))) for item in ids["vessels"]
    }
    missing = sorted(set(RELEASE_SCENARIO_IDS) - set(scenarios))
    if missing:
        raise ValueError(f"release scenario allowlist drifted from Contracts: {missing}")
    return {
        "corridors": corridors,
        "scenarios": scenarios,
        "vessels": vessels,
        "release_scenario_ids": list(RELEASE_SCENARIO_IDS),
        "excluded_scenarios": EXCLUDED_SCENARIOS,
    }


def data_catalog() -> dict[str, Any]:
    from arctic_route_data.forecast_acquisition import COPERNICUS_FORECAST_SPECS, GFS_DATA_TYPES
    from arctic_route_data.specs import DATA_TYPE_SPECS

    rows = []
    for name, spec in sorted(DATA_TYPE_SPECS.items()):
        sources = []
        if name in GFS_DATA_TYPES:
            sources.append("gfs")
        if name in CARRA_DATA_TYPES:
            sources.append("carra")
        if name in COPERNICUS_FORECAST_SPECS:
            sources.append("copernicus")
        if name in {"bathymetry", "land_sea_mask"}:
            sources.append("gebco")
        if name == "long_term_restricted_area":
            sources.append("emodnet")
        if name == "vessel_traffic":
            sources.append("local-simulation")
        rows.append(
            {
                "name": name,
                "category": spec.category.value,
                "source_family": spec.source_family,
                "source_families": list(spec.source_families),
                "acquisition_sources": sources,
                "release_role": (
                    "required"
                    if name in FORMAL_REQUIRED_DATA_TYPES
                    else "optional"
                    if name in FORMAL_OPTIONAL_DATA_TYPES
                    else "diagnostic"
                    if name in DIAGNOSTIC_DATA_TYPES
                    else "excluded"
                ),
                "variables": [
                    {"name": variable.canonical_name, "unit": variable.canonical_unit}
                    for variable in spec.variables
                ],
            }
        )
    return {
        "count": len(rows),
        "data_types": rows,
        "formal_count": len(FORMAL_REQUIRED_DATA_TYPES | FORMAL_OPTIONAL_DATA_TYPES),
        "required_count": len(FORMAL_REQUIRED_DATA_TYPES),
        "optional_count": len(FORMAL_OPTIONAL_DATA_TYPES),
        "network_sources": ["gfs", "copernicus", "gebco", "emodnet"],
        "independent_acquisition_sources": {
            "carra": {
                "data_types": sorted(CARRA_DATA_TYPES),
                "domain": "east_domain",
                "mode": "retrospective_best_estimate",
                "cadence_hours": 3,
                "max_window_hours": 216,
            }
        },
    }
