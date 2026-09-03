"""PyInstaller entry point with packaging-only dependency smoke dispatch."""

from __future__ import annotations

import importlib
import json
import sys


def _packaging_self_test() -> int:
    """Exercise imports that are only reached by the optional CARRA worker."""

    try:
        import cdsapi

        importlib.import_module("ecmwf.datastores")

        result = {
            "ok": True,
            "cdsapi": getattr(cdsapi, "__version__", "available"),
            "ecmwf_datastores": True,
        }
    except Exception as exc:  # pragma: no cover - frozen-environment diagnostic
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


def main() -> int:
    if sys.argv[1:] == ["--packaging-self-test"]:
        return _packaging_self_test()
    from arctic_route_control_center.cli import main as control_center_main

    return control_center_main()


raise SystemExit(main())
