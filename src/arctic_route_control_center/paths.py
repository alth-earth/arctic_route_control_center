"""Platform-safe resource and writable-data paths."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_root: Path
    config_dir: Path
    artifacts_inbox: Path
    artifacts_ready: Path
    artifacts_invalid: Path
    a_data_root: Path
    jobs_dir: Path
    logs_dir: Path
    cache_dir: Path
    control_static: Path
    viewer_static: Path

    def ensure(self) -> None:
        for path in (
            self.data_root,
            self.config_dir,
            self.artifacts_inbox,
            self.artifacts_ready,
            self.artifacts_invalid,
            self.a_data_root,
            self.jobs_dir,
            self.logs_dir,
            self.cache_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _default_data_root() -> Path:
    override = os.environ.get("ARCTIC_ROUTE_DATA_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "ArcticRouteControlCenter"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "arctic-route-control-center"


def _resource_base() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent


def _workspace_root() -> Path | None:
    env = os.environ.get("ARCTIC_ROUTE_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if (root / "arctic_route_contracts").is_dir():
            return root
    for parent in Path(__file__).resolve().parents:
        if (parent / "arctic_route_contracts").is_dir():
            return parent
    return None


def resolve_paths(data_root: str | Path | None = None) -> AppPaths:
    root = Path(data_root).expanduser().resolve() if data_root else _default_data_root()
    resource = _resource_base()
    control = resource / "static"
    viewer = resource / "viewer"
    if not viewer.is_dir():
        workspace = _workspace_root()
        if workspace is not None:
            viewer = workspace / "work_package_d" / "viewer"
    return AppPaths(
        data_root=root,
        config_dir=root / "config",
        artifacts_inbox=root / "artifacts" / "inbox",
        artifacts_ready=root / "artifacts" / "ready",
        artifacts_invalid=root / "artifacts" / "invalid",
        a_data_root=root / "data" / "work-package-a",
        jobs_dir=root / "run" / "jobs",
        logs_dir=root / "logs",
        cache_dir=root / "cache",
        control_static=control,
        viewer_static=viewer,
    )


def safe_child(root: Path, *parts: str) -> Path:
    """Resolve an untrusted relative path below root or reject it."""
    candidate = root.joinpath(*parts).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and not candidate.is_relative_to(resolved_root):
        raise ValueError("path escapes configured root")
    return candidate
