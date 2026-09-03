"""Locate packaged configuration resources with source-checkout fallbacks."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent


def workspace_root() -> Path | None:
    override = os.environ.get("ARCTIC_ROUTE_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        if (root / "arctic_route_contracts").is_dir():
            return root
    for parent in Path(__file__).resolve().parents:
        if (parent / "arctic_route_contracts").is_dir():
            return parent
    return None


def configuration_paths() -> dict[str, Path]:
    bundled = resource_root() / "configs"
    if bundled.is_dir():
        return {
            "contracts": bundled / "contracts",
            "a": bundled / "a" / "work_package_a.toml",
            "b": bundled / "b",
            "c": bundled / "c",
        }
    root = workspace_root()
    if root is None:
        raise RuntimeError("configuration resources cannot be located")
    return {
        "contracts": root / "arctic_route_contracts" / "configs",
        "a": root / "work_package_a" / "configs" / "work_package_a.toml",
        "b": root / "work_package_b" / "configs" / "models",
        "c": root / "work_package_c" / "configs",
    }
