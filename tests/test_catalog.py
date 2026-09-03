from __future__ import annotations

from arctic_route_control_center.catalog import contract_catalog, data_catalog


def test_release_catalog_separates_formal_and_diagnostic_inputs() -> None:
    contracts = contract_catalog()
    assert len(contracts["release_scenario_ids"]) == 6
    assert set(contracts["release_scenario_ids"]).issubset(contracts["scenarios"])
    assert "tromso_isfjorden_rc2_smoke_v1" not in contracts["release_scenario_ids"]
    data = data_catalog()
    assert data["count"] == 15
    assert data["required_count"] == 12
    assert data["optional_count"] == 2
    roles = {item["name"]: item["release_role"] for item in data["data_types"]}
    assert roles["vessel_traffic"] == "diagnostic"
    assert roles["bathymetry"] == "optional"
    assert roles["sea_ice_concentration"] == "required"
