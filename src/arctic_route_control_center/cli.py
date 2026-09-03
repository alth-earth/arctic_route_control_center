"""Console launcher: keep the backend visible and open the default browser."""

from __future__ import annotations

import argparse
import contextlib
import json
import multiprocessing
import os
import runpy
import sys
import threading
import webbrowser
from pathlib import Path

from .paths import resolve_paths
from .server import serve
from .worker import run_spec

_DLL_HANDLES: list[object] = []


def _configure_native_resources() -> None:
    candidates: list[Path] = []
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        candidates.append(Path(frozen))
    prefix = os.environ.get("ARCTIC_ROUTE_ECCODES_PREFIX")
    if prefix:
        candidates.append(Path(prefix))
    if not frozen:
        root = Path(__file__).resolve()
        for parent in root.parents:
            candidate = parent / "work_package_a" / ".mamba-env"
            if candidate.is_dir():
                candidates.append(candidate)
                break
    for candidate in candidates:
        definitions = (
            candidate / "eccodes" / "definitions",
            candidate / "share" / "eccodes" / "definitions",
            candidate / "Library" / "share" / "eccodes" / "definitions",
        )
        definition = next((item for item in definitions if item.is_dir()), None)
        if definition is not None:
            os.environ.setdefault("ECCODES_DEFINITION_PATH", str(definition))
        library_dirs = (
            candidate,
            candidate / "lib",
            candidate / "Library" / "bin",
        )
        for library_dir in library_dirs:
            if library_dir.is_dir():
                current = os.environ.get("LD_LIBRARY_PATH", "")
                os.environ["LD_LIBRARY_PATH"] = str(library_dir) + (
                    f":{current}" if current else ""
                )
                if os.name == "nt":
                    _DLL_HANDLES.append(os.add_dll_directory(str(library_dir)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arctic-route-control-center")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8130)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    _configure_native_resources()
    raw = list(argv if argv is not None else sys.argv[1:])
    if raw and raw[0] == "--orchestrator-stage-worker":
        from arctic_route_orchestrator.stage_worker import main as stage_worker_main

        return stage_worker_main(raw[1:])
    if raw and raw[0] == "--orchestrator-script":
        if len(raw) < 3 or raw[2] != "--" or raw[1] != "replay_viewer_export.py":
            raise ValueError("internal orchestrator script dispatch was rejected")
        from arctic_route_orchestrator.viewer_package import _script_path

        namespace = runpy.run_path(str(_script_path(raw[1])), run_name="_packaged_script")
        return namespace["main"](raw[3:])
    args = build_parser().parse_args(raw)
    if args.worker is not None:
        return run_spec(args.worker)
    paths = resolve_paths(args.data_root)
    paths.ensure()
    if args.self_test:
        # Exercise the imports used by frozen child processes.  A launcher-only
        # smoke test can otherwise pass while a long-running job fails as soon
        # as it enters A or the orchestrator.
        from arctic_route_data.cli import main as _a_worker_main
        from arctic_route_orchestrator.stage_worker import main as _stage_worker_main
        from arctic_route_orchestrator.viewer_package import main as _publisher_main

        from .artifacts import inspect_viewer_package
        from .catalog import contract_catalog, data_catalog, module_versions

        worker_entrypoints = all(
            callable(entrypoint)
            for entrypoint in (_a_worker_main, _stage_worker_main, _publisher_main)
        )

        artifact = inspect_viewer_package(paths.viewer_static)
        contracts = contract_catalog()
        data = data_catalog()
        native: dict[str, str | bool] = {}
        try:
            import eccodes

            native = {"eccodes": True, "eccodes_api": eccodes.codes_get_api_version()}
        except Exception as exc:  # pragma: no cover - platform-specific diagnostic
            native = {"eccodes": False, "error": str(exc)}
        result = {
            "ok": (
                artifact["status"] == "ready"
                and native["eccodes"] is True
                and worker_entrypoints
            ),
            "viewer": artifact,
            "native": native,
            "packages": module_versions(),
            "scenario_count": len(contracts["scenarios"]),
            "vessel_count": len(contracts["vessels"]),
            "data_type_count": data["count"],
            "worker_entrypoints": worker_entrypoints,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    server = serve(paths, args.host, args.port)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print("Arctic Route Control Center", flush=True)
    print(f"Backend: {url}", flush=True)
    print(f"Data:    {paths.data_root}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever(poll_interval=0.25)
    server.server_close()
    print("Backend stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
