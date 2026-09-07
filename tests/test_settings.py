from __future__ import annotations

import json
from pathlib import Path

import pytest

from arctic_route_control_center.settings import (
    load_settings,
    save_settings,
    validate_credential_file,
)


def test_legacy_settings_adds_empty_cdsapi_path(tmp_path: Path) -> None:
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "schema_version": "arctic-route-control-center.config.v1",
                "credentials": {"copernicus_env_file": "/external/copernicus.env"},
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(tmp_path)
    assert settings["credentials"] == {
        "copernicus_env_file": "/external/copernicus.env",
        "cdsapi_rc_file": "",
    }


def test_two_credential_paths_round_trip_independently(tmp_path: Path) -> None:
    external_root = tmp_path.parents[2] / f"{tmp_path.name}-external"
    external_root.mkdir()
    copernicus = external_root / ".env.copernicus"
    cdsapi = external_root / ".cdsapirc"
    for path in (copernicus, cdsapi):
        path.write_text("not-a-real-secret", encoding="utf-8")
        path.chmod(0o600)
    settings = save_settings(
        tmp_path,
        {
            "credentials": {
                "copernicus_env_file": str(copernicus),
                "cdsapi_rc_file": str(cdsapi),
            }
        },
    )
    assert settings["credentials"]["copernicus_env_file"].endswith(".env.copernicus")
    assert settings["credentials"]["cdsapi_rc_file"].endswith(".cdsapirc")


def test_credential_file_must_be_absolute_readable_and_private(tmp_path: Path) -> None:
    credential = tmp_path / ".cdsapirc"
    credential.write_text("not-a-real-secret", encoding="utf-8")
    credential.chmod(0o600)
    assert validate_credential_file(str(credential), label="CDS/CARRA") == credential.resolve()
    credential.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        validate_credential_file(str(credential), label="CDS/CARRA")


def test_save_settings_rejects_credentials_inside_data_root(tmp_path: Path) -> None:
    credential = tmp_path / ".cdsapirc"
    credential.write_text("not-a-real-secret", encoding="utf-8")
    credential.chmod(0o600)
    with pytest.raises(ValueError, match="outside"):
        save_settings(
            tmp_path / "config",
            {"credentials": {"cdsapi_rc_file": str(credential)}},
        )
