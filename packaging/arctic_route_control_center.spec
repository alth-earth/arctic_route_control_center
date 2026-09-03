from pathlib import Path
import os
import re

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

project = Path(SPEC).resolve().parent.parent
assets = Path(os.environ.get("ARCTIC_ROUTE_BUILD_ASSETS", project / "build" / "runtime-assets"))
if not assets.is_dir():
    raise SystemExit(f"runtime assets are missing: {assets}")

datas = [
    (str(project / "src" / "arctic_route_control_center" / "static"), "static"),
    (str(assets / "viewer"), "viewer"),
    (str(assets / "configs"), "configs"),
    (str(assets / "orchestrator_scripts"), "orchestrator_scripts"),
    (str(assets / "runtime-assets-manifest.json"), "."),
]
binaries = []
eccodes_prefix_value = os.environ.get("ARCTIC_ROUTE_ECCODES_PREFIX", "")
if not eccodes_prefix_value:
    raise SystemExit("ARCTIC_ROUTE_ECCODES_PREFIX must name an audited native ecCodes prefix")
eccodes_prefix = Path(eccodes_prefix_value).resolve()
definition_candidates = (
    eccodes_prefix / "share" / "eccodes" / "definitions",
    eccodes_prefix / "Library" / "share" / "eccodes" / "definitions",
)
definitions = next((path for path in definition_candidates if path.is_dir()), None)
if definitions is None:
    raise SystemExit(f"ecCodes definitions are missing below {eccodes_prefix}")
datas.append((str(definitions), "eccodes/definitions"))
native_candidates = list((eccodes_prefix / "lib").glob("libeccodes.so*"))
native_candidates += list((eccodes_prefix / "Library" / "bin").glob("*eccodes*.dll"))
if not native_candidates:
    raise SystemExit(f"ecCodes native library is missing below {eccodes_prefix}")
for native in native_candidates:
    binaries.append((str(native), "."))
# On Windows, ecCodes depends on other conda-forge DLLs from the same prefix.
# Copying the audited native prefix's DLL directory prevents a developer PATH
# from hiding a missing transitive dependency during the frozen build.
if os.name == "nt":
    for native in (eccodes_prefix / "Library" / "bin").glob("*.dll"):
        item = (str(native), ".")
        if item not in binaries:
            binaries.append(item)


_METADATA_SCRUB_ROOT = project / "build" / "release-metadata-sanitized"
_METADATA_POSIX_PATH = re.compile(
    r"(?<![A-Za-z0-9_:/])/(?:root|home|mnt|tmp|workspace|workspaces|Users|opt|srv|var|run)/"
    r"[^\x00\r\n\t \"'<>]+"
)
_METADATA_WINDOWS_PATH = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"
    r"[^\x00\r\n\t \"'<>]+"
)


def copy_release_metadata(distribution):
    """Keep package versions usable without leaking build provenance/cache."""

    rejected = {"direct_url.json", "uv_cache.json"}
    entries = []
    for source, target in copy_metadata(distribution):
        source_path = Path(source)
        if source_path.name.lower() in rejected:
            continue
        if source_path.name == "METADATA":
            # Several local package descriptions contain their developer
            # checkout path in an example command.  Keep the metadata needed
            # by importlib.metadata, but make the frozen artifact portable.
            text = source_path.read_text(encoding="utf-8", errors="replace")
            text = _METADATA_POSIX_PATH.sub("<build-path-omitted>", text)
            text = _METADATA_WINDOWS_PATH.sub("<build-path-omitted>", text)
            sanitized = _METADATA_SCRUB_ROOT / target / source_path.name
            sanitized.parent.mkdir(parents=True, exist_ok=True)
            sanitized.write_text(text, encoding="utf-8")
            source = str(sanitized)
        entries.append((source, target))
    return entries


for distribution in (
    "arctic-route-control-center",
    "arctic-route-contracts",
    "arctic-route-data",
    "arctic-route-risk",
    "arctic-route-planning",
    "arctic-route-orchestrator",
    "arctic-route-display",
):
    datas += copy_release_metadata(distribution)

hiddenimports = [
    # CARRA is reached through A's dynamic ``import cdsapi`` path only when
    # the optional acquisition operation is selected.  Keep the client and
    # its ECMWF Datastores implementation in the frozen runtime explicitly.
    "cdsapi",
    "cdsapi.api",
    "ecmwf.datastores",
    "ecmwf.datastores.catalogue",
    "ecmwf.datastores.client",
    "ecmwf.datastores.config",
    "ecmwf.datastores.legacy_client",
    "ecmwf.datastores.processing",
    "ecmwf.datastores.profile",
    "ecmwf.datastores.utils",
    "ecmwf.datastores.version",
    "arctic_route_orchestrator.replay.digests",
    "arctic_route_orchestrator.replay.geospatial",
    "arctic_route_orchestrator.replay.preflight",
    "arctic_route_orchestrator.replay.presentation",
    "arctic_route_orchestrator.replay.research_route_motion",
    "arctic_route_orchestrator.route_motion",
    "arctic_route_orchestrator.route_presentation",
    "arctic_route_orchestrator.stage_worker",
    "arctic_route_orchestrator.strict_json",
    "arctic_route_orchestrator.viewer_package",
    "arctic_route_planning.publishing",
    "cfgrib.xarray_plugin",
    "h5netcdf",
    "h5py",
]
for package in ("cdsapi", "ecmwf", "copernicusmarine", "eccodes", "eccodeslib"):
    try:
        hiddenimports += collect_submodules(package)
        datas += collect_data_files(package)
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

excluded = [
    "torch",
    "safetensors",
    "arctic_route_data.legacy",
    "arctic_route_data.legacy_downloaders",
    "arctic_route_data.vessel_traffic",
    "arctic_route_planning.adapters",
    "arctic_route_planning.cli",
    "arctic_route_planning.coupling_benchmark",
    "arctic_route_planning.development",
    "arctic_route_planning.profiling",
    "arctic_route_planning.research",
    "arctic_route_planning.risk.experimental_cache",
    "arctic_route_risk.calibration_shadow",
    "arctic_route_risk.cli",
    "arctic_route_risk.formal_grid_experiments",
    "arctic_route_risk.grid_experiments",
    "arctic_route_risk.modeling.artifacts",
    "arctic_route_risk.modeling.legacy_cnn",
    "arctic_route_risk.plotting",
    "matplotlib",
    "tkinter",
    "_tkinter",
    "arctic_route_display.demo",
]

a = Analysis(
    [str(project / "packaging" / "entrypoint.py")],
    pathex=[str(project / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="arctic-route-control-center",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="arctic-route-control-center",
)
