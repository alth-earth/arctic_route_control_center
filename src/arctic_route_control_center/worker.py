"""Worker dispatch for allowlisted long-running system operations."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .operations import OPERATIONS
from .resources import configuration_paths
from .settings import load_settings, validate_credential_file


def run_spec(path: str | Path) -> int:
    os.environ["ARCTIC_ROUTE_PRODUCTION_PACKAGE"] = "1"
    spec_path = Path(path).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != "arctic-route-control-center.job-spec.v1":
        raise ValueError("unsupported job specification")
    operation = spec.get("operation")
    if operation not in OPERATIONS:
        raise ValueError("worker operation is not allowlisted")
    print(json.dumps({"event": "worker_start", "operation": operation}), flush=True)
    functions = {
        "a_acquire": _a_acquire,
        "a_carra_acquire": _a_carra_acquire,
        "a_bundle": _a_bundle,
        "orchestrator_run": _orchestrator_run,
        "publish_viewer": _publish_viewer,
    }
    result = functions[operation](spec)
    print(
        json.dumps({"event": "worker_done", "operation": operation, "result": result}), flush=True
    )
    return 0


def _a_acquire(spec: dict[str, Any]) -> dict[str, Any]:
    from arctic_route_data.cli import main as a_main

    resources = configuration_paths()
    params = spec["parameters"]
    args = [
        "acquire-forecast",
        "--config",
        str(resources["a"]),
        "--data-root",
        spec["a_data_root"],
        "--shared-scenario",
        params["scenario_id"],
        "--contracts-config-root",
        str(resources["contracts"]),
        "--sources",
        *params["sources"],
        "--types",
        *params["types"],
    ]
    if params["simulation_start"]:
        args += ["--shared-simulation-start", params["simulation_start"]]
    if params["candidate_route_distance_nm"] is not None:
        args += [
            "--shared-candidate-route-distance-nm",
            str(params["candidate_route_distance_nm"]),
        ]
    settings = load_settings(Path(spec["data_root"]) / "config")
    credential_path = settings["credentials"]["copernicus_env_file"]
    if "copernicus" in params["sources"]:
        if not credential_path:
            raise ValueError("Copernicus source selected but credential env-file path is not set")
        credentials = validate_credential_file(credential_path, label="Copernicus")
        args += ["--copernicus-env-file", str(credentials)]
    code = a_main(args)
    if code:
        raise RuntimeError(f"arctic-data acquire-forecast failed with code {code}")
    return {"status": "PASS", "a_data_root": spec["a_data_root"]}


def _a_carra_acquire(spec: dict[str, Any]) -> dict[str, Any]:
    from arctic_route_data.cli import main as a_main

    resources = configuration_paths()
    params = spec["parameters"]
    settings = load_settings(Path(spec["data_root"]) / "config")
    credentials = validate_credential_file(
        settings["credentials"]["cdsapi_rc_file"], label="CDS/CARRA"
    )
    args = [
        "acquire-carra",
        "--config",
        str(resources["a"]),
        "--data-root",
        spec["a_data_root"],
        "--corridor",
        params["corridor_id"],
        "--start",
        params["start"],
        "--end",
        params["end"],
        "--types",
        *params["types"],
        "--cdsapi-rc-file",
        str(credentials),
        "--summary-output",
        str(Path(spec["output_dir"]) / "carra-summary.json"),
    ]
    code = a_main(args)
    if code:
        raise RuntimeError(f"arctic-data acquire-carra failed with code {code}")
    summary_path = Path(spec["output_dir"]) / "carra-summary.json"
    if not summary_path.is_file():
        raise RuntimeError("arctic-data acquire-carra did not write its task summary")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != "a.carra-acquisition-summary.v1":
        raise RuntimeError("arctic-data acquire-carra wrote an unsupported task summary")
    return {
        "status": "PASS",
        "a_data_root": spec["a_data_root"],
        "estimated_cycles": params["estimated_cycles"],
        "summary": summary,
    }


def _a_bundle(spec: dict[str, Any]) -> dict[str, Any]:
    from arctic_route_contracts.config import load_scenario
    from arctic_route_data.cli import main as a_main

    resources = configuration_paths()
    params = spec["parameters"]
    scenario = load_scenario(resources["contracts"], params["scenario_id"])
    output = Path(spec["output_dir"])
    bundle = output / "dataset-bundle.json"
    context = output / "run-context.json"
    args = [
        "replay",
        "--config",
        str(resources["a"]),
        "--data-root",
        spec["a_data_root"],
        "--route-id",
        scenario.corridor_id,
        "--at",
        params["at"],
        "--mode",
        params["mode"],
        "--types",
        *params["types"],
        "--horizon-hours",
        str(scenario.horizon_hours),
        "--bundle-output",
        str(bundle),
        "--summary-only",
    ]
    if params["knowledge_as_of"]:
        args += ["--knowledge-as-of", params["knowledge_as_of"]]
    code = a_main(args)
    if code or not bundle.is_file():
        raise RuntimeError(f"arctic-data replay did not publish a complete bundle (code {code})")
    args = [
        "shared-scenario",
        "--scenario",
        params["scenario_id"],
        "--contracts-config-root",
        str(resources["contracts"]),
        "--dataset-bundle",
        str(bundle),
        "--run-context-output",
        str(context),
        "--run-id",
        f"run-{uuid.uuid4()}",
    ]
    code = a_main(args)
    if code or not context.is_file():
        raise RuntimeError(f"run-context publication failed with code {code}")
    return {"status": "PASS", "dataset_bundle": str(bundle), "run_context": str(context)}


def _orchestrator_run(spec: dict[str, Any]) -> dict[str, Any]:
    from arctic_route_orchestrator.cli import main as orchestrator_main
    from arctic_route_orchestrator.models import ExecutionSpec

    resources = configuration_paths()
    params = spec["parameters"]
    context = json.loads(Path(params["run_context"]).read_text(encoding="utf-8"))
    output = Path(spec["output_dir"])
    execution_path = output / "execution-spec.json"
    generated_at = datetime.now(UTC)
    execution = ExecutionSpec(
        schema_version="orchestrator.execution-spec.v2",
        run_id=context["run_id"],
        scenario_id=params["scenario_id"],
        generation_id=int(context.get("generation_id", 0)),
        input_revision=0,
        generated_at=generated_at,
        planning_contract="cd.four-layer-route-plan-set.v3",
        per_stage_timeout_seconds=params["stage_timeout_seconds"],
        planning_workers=params["planning_workers"],
        parallel_pool_mode="persistent",
    )
    execution_path.write_text(
        json.dumps(execution.to_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    b_config = resources["b"] / f"{params['b_config_name']}.json"
    if not b_config.is_file():
        raise ValueError(f"packaged B configuration does not exist: {params['b_config_name']}")
    result_dir = output / "formal-run"
    risk_store = output / "risk-store"
    args = [
        "run",
        "--execution-spec",
        str(execution_path),
        "--bundle",
        params["dataset_bundle"],
        "--run-context",
        params["run_context"],
        "--a-data-root",
        spec["a_data_root"],
        "--b-config",
        str(b_config),
        "--c-config-root",
        str(resources["c"]),
        "--contracts-config-root",
        str(resources["contracts"]),
        "--risk-store-root",
        str(risk_store),
        "--output-dir",
        str(result_dir),
    ]
    code = orchestrator_main(args)
    if code:
        raise RuntimeError(f"arctic-route-orchestrator failed with code {code}")
    return {"status": "PASS", "formal_run": str(result_dir), "risk_store": str(risk_store)}


def _publish_viewer(spec: dict[str, Any]) -> dict[str, Any]:
    from arctic_route_orchestrator.viewer_package import main as publisher_main

    resources = configuration_paths()
    params = spec["parameters"]
    target = Path(spec["data_root"]) / "artifacts" / "inbox" / params["package_name"]
    args = [
        "--scenario-id",
        params["scenario_id"],
        "--contracts-config-root",
        str(resources["contracts"]),
        "--dataset-bundle",
        params["dataset_bundle"],
        "--run-context",
        params["run_context"],
        "--risk-store-root",
        params["risk_store_root"],
        "--risk-window-commit",
        params["risk_window_commit"],
        "--plan-set",
        params["plan_set"],
        "--output-dir",
        str(target),
    ]
    option_map = {
        "route_candidates": "--route-candidates",
        "route_integrity": "--route-integrity",
        "risk_frame_index": "--risk-frame-index",
        "land_mask": "--land-mask",
        "risk_explanation_manifest": "--risk-explanation-manifest",
        "winter_replay_manifest": "--winter-replay-manifest",
        "winter_replay_snapshots_dir": "--winter-replay-snapshots-dir",
    }
    for key, option in option_map.items():
        if params[key]:
            args += [option, params[key]]
    for motion in params["route_motion_sets"]:
        args += ["--route-motion-set", motion]
    for motion in params["route_motion_candidate_sets"]:
        args += ["--route-motion-candidate-set", motion]
    code = publisher_main(args)
    if code:
        raise RuntimeError(f"viewer package publication failed with code {code}")
    return {"status": "PASS", "inbox_package": str(target)}
