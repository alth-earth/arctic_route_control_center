"""Small, explicit JSON settings store with atomic writes and no secret values."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

SCHEMA = "arctic-route-control-center.config.v1"
DEFAULTS: dict[str, Any] = {
    "schema_version": SCHEMA,
    "credentials": {
        "copernicus_env_file": "",
        "cdsapi_rc_file": "",
    },
    "limits": {
        "max_parallel_jobs": 1,
        "max_json_body_bytes": 1024 * 1024,
        "max_artifact_json_bytes": 96 * 1024 * 1024,
    },
}


def load_settings(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "settings.json"
    if not path.is_file():
        return json.loads(json.dumps(DEFAULTS))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise ValueError("settings.json schema_version is invalid")
    merged = json.loads(json.dumps(DEFAULTS))
    credentials = value.get("credentials")
    limits = value.get("limits")
    if isinstance(credentials, dict):
        for key in merged["credentials"]:
            candidate = credentials.get(key, "")
            if not isinstance(candidate, str):
                raise ValueError(f"credentials.{key} must be a path string")
            merged["credentials"][key] = candidate
    if isinstance(limits, dict):
        for key in merged["limits"]:
            if key in limits:
                number = limits[key]
                if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                    raise ValueError(f"limits.{key} must be a positive integer")
                merged["limits"][key] = number
    return merged


def save_settings(config_dir: Path, value: dict[str, Any]) -> dict[str, Any]:
    # Validation and normalization happen through the same reader contract.
    config_dir.mkdir(parents=True, exist_ok=True)
    candidate = {
        "schema_version": SCHEMA,
        "credentials": {
            "copernicus_env_file": str(
                (value.get("credentials") or {}).get("copernicus_env_file", "")
            ),
            "cdsapi_rc_file": str(
                (value.get("credentials") or {}).get("cdsapi_rc_file", "")
            ),
        },
        "limits": {
            key: int((value.get("limits") or {}).get(key, default))
            for key, default in DEFAULTS["limits"].items()
        },
    }
    for key, label in (
        ("copernicus_env_file", "Copernicus"),
        ("cdsapi_rc_file", "CDS/CARRA"),
    ):
        configured = candidate["credentials"][key]
        if configured:
            candidate["credentials"][key] = str(
                validate_credential_file(configured, label=label)
            )
    temporary = config_dir / f"settings.json.{os.getpid()}.part"
    temporary.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Parse the temporary file before atomically publishing it.
    parsed = json.loads(temporary.read_text(encoding="utf-8"))
    if parsed.get("schema_version") != SCHEMA:
        temporary.unlink(missing_ok=True)
        raise ValueError("settings schema validation failed")
    temporary.replace(config_dir / "settings.json")
    return load_settings(config_dir)


def validate_credential_file(value: str, *, label: str) -> Path:
    """Resolve an external credential path without reading or exposing its contents."""

    if not value:
        raise ValueError(f"{label} credential file path is not set")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{label} credential file path must be absolute")
    candidate = candidate.resolve()
    if not candidate.is_file() or not os.access(candidate, os.R_OK):
        raise ValueError(f"configured {label} credential file is not readable")
    if os.name == "posix" and stat.S_IMODE(candidate.stat().st_mode) & 0o077:
        raise ValueError(f"configured {label} credential file permissions must be 0600")
    return candidate
