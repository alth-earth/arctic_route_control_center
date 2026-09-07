from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_ROOT / f"{name}.py")
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load script: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_prepare_runtime_assets = _load_script("prepare_runtime_assets")
_scan_release = _load_script("scan_release")
_sanitize_frozen_tree = _load_script("sanitize_frozen_tree")
CONTROL_CENTER_SOURCE_IDENTITY_INPUTS = (
    _prepare_runtime_assets.CONTROL_CENTER_SOURCE_IDENTITY_INPUTS
)
scan_release = _scan_release.scan_release
sanitize_frozen_tree = _sanitize_frozen_tree.sanitize


def _write(root: Path, relative: str, content: str = "ok\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_clean_release_tree_passes_and_has_no_exception_field(tmp_path: Path) -> None:
    _write(tmp_path, "viewer/index.html", '<a href="/viewer/">Viewer</a>\n')

    result = scan_release(tmp_path)

    assert result["status"] == "PASS"
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert "known_blockers" not in result


def test_forbidden_credentials_caches_raw_data_and_historical_paths_fail(
    tmp_path: Path,
) -> None:
    forbidden = (
        ".env.copernicus",
        ".cdsapirc",
        "credentials/token.txt",
        "direct_url.json",
        "uv_cache.json",
        "RC1/old.txt",
        "RC2/old.txt",
        "demo-engineering/notes.txt",
        "raw_grib/frame.grib2",
        "raw_temperature.csv",
        "raw/temperature.bin",
        "archive/old.nc",
    )
    for relative in forbidden:
        _write(tmp_path, relative)

    result = scan_release(tmp_path)

    assert result["status"] == "FAIL"
    assert result["exit_code"] == 1
    finding_paths = {finding["path"] for finding in result["errors"]}
    assert set(forbidden) <= finding_paths


def test_absolute_paths_and_credential_values_fail_without_echoing_values(
    tmp_path: Path,
) -> None:
    secret = "not-a-real-secret-value"
    _write(
        tmp_path,
        "viewer/bundle.json",
        '{"source":"/build/runner/_work/arctic_route/work_package_d/viewer",\n'
        '"windows":"C:\\agent\\_work\\route\\viewer\\bundle.json",\n'
        '"uri":"file:///home/build/release/viewer/bundle.json"}\n',
    )
    _write(tmp_path, "viewer/config.json", f'{{"CDSAPI_KEY":"user:{secret}"}}\n')

    result = scan_release(tmp_path)

    assert result["status"] == "FAIL"
    assert result["exit_code"] == 1
    assert {finding["kind"] for finding in result["errors"]} >= {
        "build_machine_absolute_path",
        "credential_value",
    }
    assert secret not in str(result)


def test_workspace_root_is_scanned_even_for_a_nonstandard_checkout(tmp_path: Path) -> None:
    workspace = tmp_path / "custom-build-root"
    _write(
        tmp_path,
        "viewer/manifest.json",
        f'{{"source":"{workspace / "work_package_d" / "viewer"}"}}\n',
    )

    result = scan_release(tmp_path, workspace_root=workspace)

    assert result["status"] == "FAIL"
    assert any(finding["kind"] == "build_machine_absolute_path" for finding in result["errors"])


def test_release_scanner_is_part_of_control_center_source_identity() -> None:
    assert "scripts/scan_release.py" in CONTROL_CENTER_SOURCE_IDENTITY_INPUTS
    assert "scripts/sanitize_frozen_tree.py" in CONTROL_CENTER_SOURCE_IDENTITY_INPUTS
    assert "packaging/windows" in CONTROL_CENTER_SOURCE_IDENTITY_INPUTS


def test_third_party_models_are_not_mistaken_for_project_raw_data(tmp_path: Path) -> None:
    _write(tmp_path, "_internal/botocore/data/service-2.json.gz")
    _write(tmp_path, "_internal/pyarrow/tests/fixture.parquet")
    _write(tmp_path, "_internal/viewer/leaked.grib")

    result = scan_release(tmp_path)

    assert result["status"] == "FAIL"
    finding_paths = {finding["path"] for finding in result["errors"]}
    assert "_internal/viewer/leaked.grib" in finding_paths
    assert "_internal/botocore/data/service-2.json.gz" not in finding_paths
    assert "_internal/pyarrow/tests/fixture.parquet" not in finding_paths


def test_frozen_tree_sanitizer_removes_baggage_and_build_paths(tmp_path: Path) -> None:
    _write(tmp_path, "_internal/pyarrow/tests/data/example.parquet")
    metadata = "_internal/arctic_route_data-1.dist-info/METADATA"
    _write(tmp_path, metadata, "Example: /root/build/workspace/project/data\n")

    result = sanitize_frozen_tree(tmp_path)

    assert result["removed_directories"] == 1
    assert result["sanitized_metadata"] == 1
    assert not (tmp_path / "_internal/pyarrow/tests").exists()
    assert "/root/build" not in (tmp_path / metadata).read_text(encoding="utf-8")


def test_windows_clean_machine_scan_has_the_same_fail_closed_markers() -> None:
    verifier = (_SCRIPTS_ROOT.parent / "packaging" / "windows" / "verify-windows.ps1").read_text(
        encoding="utf-8"
    )
    for marker in (
        "\\.cdsapirc",
        "direct_url\\.json",
        "uv_cache\\.json",
        "rc[12]",
    ):
        assert marker.casefold() in verifier.casefold()
    for marker in ("raw", "grib", "netcdf", "demo[-_]engineering"):
        assert marker.casefold() in verifier.casefold()
    assert "WorkspaceRoot".casefold() in verifier.casefold()
    assert "--allow-known-viewer-provenance" not in verifier
