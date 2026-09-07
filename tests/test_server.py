from __future__ import annotations

import hashlib
import json
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from arctic_route_control_center.paths import resolve_paths
from arctic_route_control_center.server import serve


def _write_embedded_package(path: Path, scenario: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "replay.viewer-bundle.v1",
        "replay": {"scenario_id": scenario},
        "combined_presentation": {"status": "PUBLISHED"},
        "route_candidates": {"status": "PUBLISHED", "candidates": [{}] * 12},
        "gates": {"status": "PASS"},
        "formal_motion_inspection": {"valid": True},
        "risk": {"frames": []},
    }
    payload = json.dumps(bundle)
    (path / "bundle.json").write_text(payload, encoding="utf-8")
    digest = hashlib.sha256((path / "bundle.json").read_bytes()).hexdigest()
    (path / "checksums.json").write_text(
        json.dumps({"files": {"bundle.json": digest}}), encoding="utf-8"
    )


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


def test_explicit_ipv6_loopback_uses_ipv6_socket(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path)
    paths.ensure()
    try:
        server = serve(paths, "::1", 0)
    except OSError as exc:
        if exc.errno in {getattr(socket, "EAI_ADDRFAMILY", -9), -9}:
            return
        raise
    try:
        assert server.address_family == socket.AF_INET6
    finally:
        server.server_close()


def test_viewer_index_keeps_embedded_defaults_and_live_ready_packages(tmp_path: Path) -> None:
    base_paths = resolve_paths(tmp_path)
    viewer = tmp_path / "viewer"
    paths = replace(base_paths, viewer_static=viewer)
    paths.ensure()
    _write_embedded_package(viewer, "root")
    _write_embedded_package(viewer / "packages" / "ready-v2", "embedded-v2")
    _write_embedded_package(paths.artifacts_ready / "ready-v2", "external-duplicate")
    _write_embedded_package(paths.artifacts_ready / "external-v4", "external-v4")
    server = serve(paths, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/viewer/packages.json") as response:
            index = json.load(response)
        assert [item["package_dir"] for item in index["packages"]] == [
            "viewer-root",
            "ready-v2",
            "external-v4",
            "ready-v2",
        ]
        assert [item["location"] for item in index["packages"]] == [
            "embedded",
            "embedded",
            "ready",
            "ready",
        ]
        with urllib.request.urlopen(base + "/viewer/packages/ready-v2/bundle.json") as response:
            assert json.load(response)["replay"]["scenario_id"] == "embedded-v2"
        ready_url = base + "/viewer/ready-packages/ready-v2/bundle.json"
        with urllib.request.urlopen(ready_url) as response:
            assert json.load(response)["replay"]["scenario_id"] == "external-duplicate"
        with urllib.request.urlopen(base + "/viewer/packages/external-v4/bundle.json") as response:
            assert json.load(response)["replay"]["scenario_id"] == "external-v4"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
