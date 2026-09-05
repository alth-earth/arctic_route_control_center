"""Loopback-only HTTP control plane and D Viewer mount."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .artifacts import package_index, promote_from_inbox
from .catalog import contract_catalog, data_catalog, module_versions
from .jobs import JobManager
from .paths import AppPaths, safe_child
from .resources import configuration_paths
from .settings import load_settings, save_settings


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], paths: AppPaths) -> None:
        super().__init__(address, Handler)
        self.paths = paths
        self.settings = load_settings(paths.config_dir)
        self.jobs = JobManager(
            paths,
            max_parallel_jobs=int(self.settings["limits"]["max_parallel_jobs"]),
        )


class Handler(BaseHTTPRequestHandler):
    server_version = "ArcticRouteControlCenter/0.1"

    @property
    def app(self) -> ControlServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[control-center] %s\n" % (fmt % args))

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in {f"http://{host}", f"https://{host}"}

    def _body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        maximum = int(self.app.settings["limits"]["max_json_body_bytes"])
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > maximum:
            raise ValueError("request body size is invalid")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self._json(
                    200,
                    {
                        "ok": True,
                        "service": "arctic-route-control-center",
                        "host": self.app.server_address[0],
                        "port": self.app.server_address[1],
                    },
                )
                return
            if parsed.path == "/api/system":
                resources = configuration_paths()
                self._json(
                    200,
                    {
                        "ok": True,
                        "packages": module_versions(),
                        "paths": {
                            "data_root": str(self.app.paths.data_root),
                            "a_data_root": str(self.app.paths.a_data_root),
                            "artifacts_inbox": str(self.app.paths.artifacts_inbox),
                            "artifacts_ready": str(self.app.paths.artifacts_ready),
                            "viewer_static": str(self.app.paths.viewer_static),
                            "contracts_config": str(resources["contracts"]),
                        },
                        "runtime": {
                            "python": sys.version.split()[0],
                            "platform": sys.platform,
                            "frozen": bool(getattr(sys, "frozen", False)),
                        },
                    },
                )
                return
            if parsed.path == "/api/catalog":
                self._json(
                    200,
                    {"ok": True, "contracts": contract_catalog(), "data": data_catalog()},
                )
                return
            if parsed.path == "/api/settings":
                self._json(200, {"ok": True, "settings": self.app.settings})
                return
            if parsed.path == "/api/artifacts":
                self._json(200, {"ok": True, **self._package_index()})
                return
            if parsed.path == "/api/jobs":
                self._json(200, {"ok": True, "jobs": self.app.jobs.list()})
                return
            if parsed.path.startswith("/api/jobs/"):
                job_id = parsed.path.removeprefix("/api/jobs/").strip("/")
                self._json(200, {"ok": True, "job": self.app.jobs.get(job_id)})
                return
            if parsed.path == "/viewer/packages.json":
                # Embedded packages are the audited defaults, but the normal
                # writable ready store remains a live input for newly
                # received packages.  Each source is retained in the index;
                # the Viewer uses a source-specific URL when names repeat.
                self._json(200, self._package_index())
                return
            if parsed.path.startswith("/viewer/packages/"):
                self._serve_ready_artifact(parsed.path)
                return
            if parsed.path.startswith("/viewer/ready-packages/"):
                self._serve_ready_artifact(parsed.path, ready_only=True)
                return
            if parsed.path == "/viewer" or parsed.path.startswith("/viewer/"):
                relative = parsed.path.removeprefix("/viewer").lstrip("/") or "index.html"
                self._serve_file(self.app.paths.viewer_static, relative)
                return
            relative = parsed.path.lstrip("/") or "index.html"
            if relative == "favicon.ico":
                relative = "favicon.svg"
            self._serve_file(self.app.paths.control_static, relative)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def do_POST(self) -> None:
        if not self._same_origin():
            self._error(403, "cross-origin state changes are not allowed")
            return
        parsed = urlparse(self.path)
        try:
            body = self._body()
            if parsed.path == "/api/settings":
                self.app.settings = save_settings(self.app.paths.config_dir, body)
                self._json(200, {"ok": True, "settings": self.app.settings})
                return
            if parsed.path == "/api/jobs":
                job = self.app.jobs.start(body)
                self._json(202, {"ok": True, "job": job})
                return
            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                job_id = parsed.path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
                self._json(200, {"ok": True, "job": self.app.jobs.cancel(job_id)})
                return
            if parsed.path == "/api/artifacts/promote":
                name = body.get("package_name")
                if not isinstance(name, str):
                    raise ValueError("package_name must be a string")
                artifact = promote_from_inbox(
                    self.app.paths,
                    name,
                    max_json_bytes=int(self.app.settings["limits"]["max_artifact_json_bytes"]),
                )
                self._json(200, {"ok": True, "artifact": artifact})
                return
            self._error(404, "not found")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def _package_index(self, *, embedded_only: bool = False) -> dict[str, Any]:
        return package_index(
            self.app.paths,
            max_json_bytes=int(self.app.settings["limits"]["max_artifact_json_bytes"]),
            embedded_only=embedded_only,
        )

    def _serve_ready_artifact(self, request_path: str, *, ready_only: bool = False) -> None:
        prefix = "/viewer/ready-packages/" if ready_only else "/viewer/packages/"
        relative = unquote(request_path.removeprefix(prefix)).strip("/")
        parts = relative.split("/", 1)
        if len(parts) != 2:
            raise ValueError("artifact path is incomplete")
        package_name, inner = parts
        if ready_only:
            # This explicit namespace selects the writable ready store even
            # when an embedded package has the same directory name.
            package_root = safe_child(self.app.paths.artifacts_ready, package_name)
        else:
            embedded_packages = self.app.paths.viewer_static / "packages"
            embedded_root = safe_child(embedded_packages, package_name)
            if embedded_root.is_dir():
                package_root = embedded_root
            else:
                # Keep the established writable data-root/artifacts/ready path
                # as the fallback for legacy/direct package URLs.
                package_root = safe_child(self.app.paths.artifacts_ready, package_name)
        if not package_root.is_dir():
            raise ValueError("artifact package is not published")
        self._serve_file(package_root, inner)

    def _serve_file(self, root: Path, relative: str) -> None:
        target = safe_child(root, unquote(relative))
        if not target.is_file():
            self._error(404, "not found")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "image/svg+xml",
        }:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_runtime_state(paths: AppPaths, host: str, port: int) -> None:
    state = {
        "schema_version": "arctic-route-control-center.runtime.v1",
        "pid": os.getpid(),
        "host": host,
        "port": port,
    }
    target = paths.data_root / "run" / "control-center.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".json.{os.getpid()}.part")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def serve(paths: AppPaths, host: str, port: int) -> ControlServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the control center may only listen on loopback")
    server = ControlServer((host, port), paths)
    write_runtime_state(paths, str(server.server_address[0]), int(server.server_address[1]))
    return server
