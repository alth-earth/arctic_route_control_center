from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from arctic_route_control_center.paths import resolve_paths
from arctic_route_control_center.server import serve


def test_loopback_server_endpoints_and_traversal_rejection(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    paths.ensure()
    server = serve(paths, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/health") as response:
            assert json.load(response)["ok"] is True
        with urllib.request.urlopen(base + "/api/catalog") as response:
            catalog = json.load(response)
            assert len(catalog["contracts"]["release_scenario_ids"]) == 6
        try:
            urllib.request.urlopen(base + "/viewer/../../config/default.json")
        except urllib.error.HTTPError as exc:
            assert exc.code in {400, 404}
        else:
            raise AssertionError("path traversal unexpectedly succeeded")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
