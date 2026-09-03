from __future__ import annotations

import json
from pathlib import Path

from arctic_route_control_center.settings import save_settings
from arctic_route_control_center.worker import _a_carra_acquire


def test_carra_worker_uses_only_configured_cdsapi_path(
    tmp_path: Path, monkeypatch
) -> None:
    copernicus = tmp_path / ".env.copernicus"
    cdsapi = tmp_path / ".cdsapirc"
    for path in (copernicus, cdsapi):
        path.write_text("secret-must-not-be-read-by-control-center", encoding="utf-8")
        path.chmod(0o600)
    save_settings(
        tmp_path / "config",
        {
            "credentials": {
                "copernicus_env_file": str(copernicus),
                "cdsapi_rc_file": str(cdsapi),
            }
        },
    )
    observed: list[str] = []

    def fake_main(args: list[str]) -> int:
        observed.extend(args)
        summary = Path(args[args.index("--summary-output") + 1])
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            json.dumps(
                {
                    "schema_version": "a.carra-acquisition-summary.v1",
                    "cycles_requested": 2,
                    "cache_hits": 1,
                    "downloaded_cycles": 1,
                    "frames_processed": 2,
                    "frames_published": 2,
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr("arctic_route_data.cli.main", fake_main)
    result = _a_carra_acquire(
        {
            "data_root": str(tmp_path),
            "a_data_root": str(tmp_path / "data"),
            "output_dir": str(tmp_path / "jobs" / "job-carra" / "output"),
            "parameters": {
                "corridor_id": "tromso_to_isfjorden_outer",
                "start": "2026-02-15T00:00:00Z",
                "end": "2026-02-15T03:00:00Z",
                "types": ["temperature"],
                "estimated_cycles": 2,
            },
        }
    )

    assert observed[0] == "acquire-carra"
    assert observed[observed.index("--cdsapi-rc-file") + 1] == str(cdsapi.resolve())
    assert str(copernicus.resolve()) not in observed
    assert all("secret-must-not-be-read" not in item for item in observed)
    assert result["estimated_cycles"] == 2
    assert result["summary"]["cache_hits"] == 1
