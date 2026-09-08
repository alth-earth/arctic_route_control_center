"""Explicit Viewer data package inputs for release packaging.

Viewer data packages are supplied by whoever runs the build: nothing about a
package name, a default on-disk location, an expected digest, or a fixed file
list lives in this repository.  A package is accepted when it carries its own
``bundle.json`` plus ``checksums.json`` and every listed file matches, so new
packages can be added and old ones retired without touching this code.

Three equivalent input channels are supported and may be combined:

* repeated ``--viewer-package <dir>`` arguments,
* a JSON manifest ``--viewer-manifest <file>`` (paths plus optional name and
  ``default`` flag),
* the environment variable ``ARCTIC_ROUTE_VIEWER_PACKAGES`` (Windows: ``;``
  separated, POSIX: ``:`` separated).

Zero packages is a valid input: the frozen build then carries only the Viewer
UI and loads data from the runtime data root.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "arctic-route-control-center.viewer-inputs.v1"
EMBEDDED_INDEX_NAME = "embedded-packages.json"
REQUIRED_FILES = ("bundle.json", "checksums.json")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ViewerInputError(ValueError):
    """Raised when a supplied Viewer package input is unusable."""


@dataclass(frozen=True)
class ViewerPackageInput:
    """One requested package before validation."""

    path: Path
    name: str | None = None
    default: bool = False


@dataclass(frozen=True)
class ValidatedPackage:
    """One package that passed self-describing validation."""

    name: str
    source: Path
    default: bool
    files: tuple[str, ...]
    checksums_sha256: str
    bundle_sha256: str
    scenario_id: str
    assembly_id: str
    status: str


def _split_environment(value: str) -> list[str]:
    if not value.strip():
        return []
    separator = ";" if os_name_is_nt() else ":"
    return [item.strip() for item in value.split(separator) if item.strip()]


def os_name_is_nt() -> bool:
    import os

    return os.name == "nt"


def _safe_relative(relative: str) -> bool:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    return bool(_SAFE_NAME.match(candidate.name))


def load_viewer_inputs(
    specs: list[str] | tuple[str, ...],
    manifest: Path | None,
    env_value: str,
    *,
    base_dir: Path,
) -> list[ViewerPackageInput]:
    """Normalise the three input channels into an ordered package list."""

    inputs: list[ViewerPackageInput] = []
    explicit_default = False

    if manifest is not None:
        manifest_path = manifest.expanduser()
        if not manifest_path.is_file():
            raise ViewerInputError(f"viewer manifest is missing: {manifest_path}")
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ViewerInputError(f"viewer manifest is not readable JSON: {exc}") from exc
        entries = document.get("packages")
        if not isinstance(entries, list):
            raise ViewerInputError("viewer manifest has no packages list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not entry.get("path"):
                raise ViewerInputError(f"viewer manifest entry {index} lacks a path")
            path = Path(str(entry["path"])).expanduser()
            if not path.is_absolute():
                path = (base_dir / path).resolve()
            name = str(entry["name"]) if entry.get("name") else None
            default = bool(entry.get("default"))
            if default and explicit_default:
                raise ViewerInputError("viewer manifest declares more than one default package")
            explicit_default = explicit_default or default
            inputs.append(ViewerPackageInput(path=path, name=name, default=default))

    for raw in list(specs) + _split_environment(env_value):
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        inputs.append(ViewerPackageInput(path=path))

    deduped: list[ViewerPackageInput] = []
    seen: set[Path] = set()
    for item in inputs:
        key = item.path
        if key in seen:
            raise ViewerInputError(f"duplicate viewer package input: {key}")
        seen.add(key)
        deduped.append(item)

    if not any(item.default for item in deduped) and deduped:
        deduped = [ViewerPackageInput(deduped[0].path, deduped[0].name, True), *deduped[1:]]
    return deduped


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_viewer_package(item: ViewerPackageInput) -> ValidatedPackage:
    """Validate one package against its own bundle/checksums manifest."""

    source = item.path
    if not source.is_dir():
        raise ViewerInputError(f"viewer package directory is missing: {source}")
    name = item.name or source.name
    if not _SAFE_NAME.match(name):
        raise ViewerInputError(f"unsafe viewer package name: {name}")
    for required in REQUIRED_FILES:
        if not (source / required).is_file():
            raise ViewerInputError(f"viewer package {name} is missing {required}")

    checksums_path = source / "checksums.json"
    try:
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ViewerInputError(f"viewer package {name} has unreadable checksums: {exc}") from exc
    files = checksums.get("files")
    if not isinstance(files, dict) or not files:
        raise ViewerInputError(f"viewer package {name} checksums has no files map")
    if "bundle.json" not in files:
        raise ViewerInputError(f"viewer package {name} does not checksum bundle.json")

    normalised: list[str] = []
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ViewerInputError(f"viewer package {name} has a malformed checksum entry")
        if not _safe_relative(relative):
            raise ViewerInputError(f"viewer package {name} lists an unsafe path: {relative}")
        if len(expected) != 64:
            raise ViewerInputError(f"viewer package {name} checksum is malformed: {relative}")
        target = source / relative
        if not target.is_file():
            raise ViewerInputError(f"viewer package {name} is missing file: {relative}")
        if _sha256(target) != expected.lower():
            raise ViewerInputError(f"viewer package {name} checksum mismatch: {relative}")
        normalised.append(relative)

    bundle_path = source / "bundle.json"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ViewerInputError(f"viewer package {name} bundle is unreadable: {exc}") from exc
    presentation = bundle.get("combined_presentation")
    presentation = presentation if isinstance(presentation, dict) else {}
    replay = bundle.get("replay")
    replay = replay if isinstance(replay, dict) else {}

    return ValidatedPackage(
        name=name,
        source=source,
        default=item.default,
        files=tuple(sorted(normalised)),
        checksums_sha256=_sha256(checksums_path),
        bundle_sha256=_sha256(bundle_path),
        scenario_id=str(replay.get("scenario_id") or presentation.get("scenario_id") or ""),
        assembly_id=str(presentation.get("assembly_id") or ""),
        status=str(presentation.get("status") or ""),
    )


def stage_viewer_packages(
    packages: list[ValidatedPackage], output: Path
) -> dict[str, object] | None:
    """Copy validated packages into the release tree and write their index.

    The default package lands at ``viewer/`` (its files flat, which is the
    layout the Viewer UI already loads); every other package lands at
    ``viewer/packages/<name>/``.  Returns the index written to
    ``viewer/embedded-packages.json``, or None when nothing was supplied.
    """

    if not packages:
        return None

    defaults = [item for item in packages if item.default]
    if len(defaults) != 1:
        raise ViewerInputError("exactly one viewer package must be the default")
    default = defaults[0]
    viewer_root = output / "viewer"
    viewer_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, object]] = []
    for package in packages:
        target = viewer_root if package.default else viewer_root / "packages" / package.name
        target.mkdir(parents=True, exist_ok=True)
        for relative in (*package.files, "checksums.json"):
            source = package.source / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        location = "embedded-root" if package.default else "embedded"
        bundle_path = "bundle.json" if package.default else f"packages/{package.name}/bundle.json"
        entries.append(
            {
                "package_dir": package.name,
                "location": location,
                "bundle_path": bundle_path,
                "source": str(package.source),
                "scenario_id": package.scenario_id,
                "assembly_id": package.assembly_id,
                "status": package.status,
                "file_count": len(package.files),
                "bundle_sha256": package.bundle_sha256,
                "checksums_sha256": package.checksums_sha256,
            }
        )

    index = {
        "schema_version": SCHEMA_VERSION,
        "default_package": default.name,
        "packages": entries,
    }
    index_path = viewer_root / EMBEDDED_INDEX_NAME
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index
