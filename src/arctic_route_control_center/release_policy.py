"""Explicit release allowlists for the packaged control plane."""

from __future__ import annotations

RELEASE_SCENARIO_IDS = (
    "murmansk_dikson_august_2026_demo_v1",
    "murmansk_dikson_frozen_forecast_template_v1",
    "murmansk_dikson_july_2026_retrospective_v1",
    "tromso_isfjorden_august_2026_demo_v1",
    "tromso_isfjorden_frozen_forecast_template_v1",
    "tromso_isfjorden_july_2026_retrospective_v1",
)

EXCLUDED_SCENARIOS = {
    "tromso_isfjorden_february_2026_research_v1": "research replay; display-only packaged artifact",
    "tromso_isfjorden_rc2_smoke_v1": "historical RC2 smoke scenario",
    "tromso_isfjorden_winter_development_20260322_v1": "development-only winter scenario",
    "tromso_isfjorden_winter_holdout_20260222_v1": "research holdout scenario",
}

FORMAL_REQUIRED_DATA_TYPES = frozenset(
    {
        "land_sea_mask",
        "ocean_current",
        "sea_ice_concentration",
        "sea_ice_drift",
        "sea_ice_edge",
        "sea_ice_thickness",
        "sea_ice_type",
        "temperature",
        "visibility",
        "water_level",
        "wave",
        "wind_field",
    }
)
FORMAL_OPTIONAL_DATA_TYPES = frozenset({"bathymetry", "long_term_restricted_area"})
FORMAL_DATA_TYPES = FORMAL_REQUIRED_DATA_TYPES | FORMAL_OPTIONAL_DATA_TYPES
DIAGNOSTIC_DATA_TYPES = frozenset({"vessel_traffic"})
NETWORK_SOURCES = frozenset({"gfs", "copernicus", "gebco", "emodnet"})
CARRA_DATA_TYPES = frozenset({"wind_field", "temperature", "visibility"})
SOURCE_DATA_TYPES = {
    "gfs": frozenset({"wind_field", "temperature", "visibility"}),
    "copernicus": frozenset(
        {
            "wave",
            "ocean_current",
            "water_level",
            "sea_ice_concentration",
            "sea_ice_drift",
            "sea_ice_thickness",
            "sea_ice_type",
            "sea_ice_edge",
        }
    ),
    "gebco": frozenset({"bathymetry", "land_sea_mask"}),
    "emodnet": frozenset({"long_term_restricted_area"}),
}


def require_release_scenario(scenario_id: str) -> None:
    if scenario_id not in RELEASE_SCENARIO_IDS:
        reason = EXCLUDED_SCENARIOS.get(scenario_id, "not present in the release allowlist")
        raise ValueError(
            f"scenario is unavailable in the packaged workflow: {scenario_id}: {reason}"
        )


def require_formal_data_types(data_types: list[str]) -> None:
    rejected = sorted(set(data_types) - FORMAL_DATA_TYPES)
    if rejected:
        raise ValueError(
            "non-formal or unknown data types are unavailable in the packaged workflow: "
            + ", ".join(rejected)
        )


def require_sources_cover_types(sources: list[str], data_types: list[str]) -> None:
    covered = frozenset().union(*(SOURCE_DATA_TYPES[source] for source in sources))
    unsupported = sorted(set(data_types) - covered)
    if unsupported:
        raise ValueError(
            "selected sources do not provide these data types: " + ", ".join(unsupported)
        )
