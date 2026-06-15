from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
import re
from typing import Any, Iterator, Optional

from cae_preflight_lib.ai.diagnose import diagnose_results, diagnosis_result_to_dict
from cae_preflight_lib.config import settings
from cae_preflight_lib.docker import (
    CalculixDockerRunner,
    DockerSolverRunner,
    get_image_spec,
    list_image_spec_dicts,
    recommend_image_specs,
    resolve_image_reference,
    solver_config_key,
)
from cae_preflight_lib.inp import InpParser, load_kw_list
from cae_preflight_lib.runtimes import DockerRuntime
from cae_preflight_lib.solvers.base import SolveResult
from cae_preflight_lib.solvers.registry import get_solver, list_solvers


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, *, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": _safe_json_value(details or {}),
        },
    }


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {k: _safe_json_value(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted((_safe_json_value(v) for v in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    return value


def _resolve_path(raw: str | Path, *, must_exist: bool = False, kind: str = "path") -> Path:
    if isinstance(raw, str) and not raw.strip():
        raise ValueError(f"{kind} must not be empty")
    p = Path(raw).expanduser().resolve()
    if must_exist and not p.exists():
        raise FileNotFoundError(f"{kind} not found: {p}")
    return p


def _path_error(exc: Exception, *, kind: str, raw: Any) -> dict[str, Any]:
    code = "not_found" if isinstance(exc, FileNotFoundError) else "invalid_input"
    return _error(code, str(exc), details={kind: raw})


def _default_output_dir(inp_file: Path) -> Path:
    if settings.workspace_output_dir:
        return (settings.workspace_output_dir / inp_file.stem).resolve()
    return (settings.default_output_dir / inp_file.stem).resolve()


def _solve_result_to_dict(result: SolveResult) -> dict[str, Any]:
    output_files = [str(p) for p in result.output_files]
    return {
        "success": result.success,
        "output_dir": str(result.output_dir),
        "output_files": output_files,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "duration_seconds": result.duration_seconds,
        "duration": result.duration_str,
        "error_message": result.error_message,
        "warnings": list(result.warnings),
        "frd_file": str(result.frd_file) if result.frd_file else None,
        "dat_file": str(result.dat_file) if result.dat_file else None,
    }


_AGENT_TRIAGE_ORDER = {
    "safe_auto_fix": 0,
    "blocking": 1,
    "review": 2,
    "monitor": 3,
}

_SOLVER_STATUS_ROUTE_MAP: dict[str, dict[str, Any]] = {
    "failed": {
        "route": "runtime_remediation",
        "goal": "Restore a runnable solver execution before physical interpretation.",
        "primary_action": "Inspect the solver runtime failure before attempting physics diagnosis.",
        "recommended_checks": [
            "image",
            "command",
            "sidecar_inputs",
            "mount_path",
            "permissions",
            "environment",
        ],
        "blocked_actions": [
            "physics_diagnosis",
            "auto_fix_without_runtime_confirmation",
        ],
        "gate_overrides_diagnosis_plan": True,
    },
    "not_converged": {
        "route": "convergence_tuning",
        "goal": "Stabilize the run and reach convergence before trusting solver output.",
        "primary_action": "Tune convergence controls before treating the current result as a valid physics answer.",
        "recommended_checks": [
            "iteration_budget",
            "initialization",
            "time_step_control",
            "solver_settings",
            "residual_history",
        ],
        "blocked_actions": [
            "physics_diagnosis_as_final_answer",
        ],
        "gate_overrides_diagnosis_plan": True,
    },
    "success": {
        "route": "physics_diagnosis",
        "goal": "Interpret solver artifacts and evaluate physical plausibility.",
        "primary_action": "Proceed to result interpretation and physics diagnosis.",
        "recommended_checks": [
            "result_artifacts",
            "magnitude_check",
            "physical_plausibility",
            "boundary_condition_consistency",
        ],
        "blocked_actions": [],
        "gate_overrides_diagnosis_plan": False,
    },
    "unknown": {
        "route": "evidence_expansion",
        "goal": "Collect enough runtime evidence to classify the solver run reliably.",
        "primary_action": "Inspect logs and artifacts to classify solver status before auto-fix or physics diagnosis.",
        "recommended_checks": [
            "primary_log",
            "text_sources",
            "result_artifacts",
            "runtime_metadata",
        ],
        "blocked_actions": [
            "physics_diagnosis",
            "auto_fix_without_classification",
        ],
        "gate_overrides_diagnosis_plan": True,
    },
}

_ROUTE_CHECK_INSTRUCTIONS = {
    "image": "Confirm the selected solver image exists locally and matches the requested solver family.",
    "command": "Check the entry command and solver executable invocation before retrying the run.",
    "sidecar_inputs": "Verify that all referenced sidecar files were copied or mounted into the solver workspace.",
    "mount_path": "Confirm the mounted work directory points at the intended case directory.",
    "permissions": "Check read/write permissions for the mounted inputs, logs, and output directory.",
    "environment": "Review runtime environment variables, MPI settings, and backend-specific runtime assumptions.",
    "iteration_budget": "Review whether the maximum iteration budget is large enough for this case.",
    "initialization": "Inspect initial conditions and starting fields for poor initialization.",
    "time_step_control": "Review time-step, increment, or CFL-style controls for instability.",
    "solver_settings": "Inspect solver tolerances, linearization settings, and convergence criteria.",
    "residual_history": "Read the residual history to decide whether the run is improving, stalled, or diverging.",
    "result_artifacts": "Check whether the produced result artifacts are complete enough for interpretation.",
    "magnitude_check": "Validate that magnitudes and units remain plausible before trusting the solution.",
    "physical_plausibility": "Compare the result trend against expected physical behavior.",
    "boundary_condition_consistency": "Confirm the interpreted result is consistent with the prescribed loads and constraints.",
    "primary_log": "Read the primary log first to classify the run and find the dominant failure signal.",
    "text_sources": "Inspect the collected text sources for missing runtime evidence or contradictions.",
    "runtime_metadata": "Collect enough runtime metadata before choosing auto-fix or diagnosis actions.",
}

_EVIDENCE_DONE_WHEN = {
    "primary_log": "A primary solver log has been identified and attached to the route context.",
    "text_sources": "At least one relevant text evidence source is available for inspection.",
    "result_artifacts": "Result files or output artifacts are present and enumerable.",
    "convergence_summary": "A convergence summary or residual-history summary is available.",
}


def _normalize_solver_status(raw_status: Any) -> str:
    status = str(raw_status or "").strip().lower()
    if not status:
        return "unknown"
    status = re.sub(r"[\s-]+", "_", status)
    alias_map = {
        "completed": "success",
        "complete": "success",
        "ok": "success",
        "passed": "success",
        "notconverged": "not_converged",
        "did_not_converge": "not_converged",
        "max_iterations_reached": "not_converged",
        "diverged": "not_converged",
        "error": "failed",
        "fatal": "failed",
        "crashed": "failed",
    }
    normalized = alias_map.get(status, status)
    return normalized if normalized in _SOLVER_STATUS_ROUTE_MAP else "unknown"


def _normalize_path_items(items: list[Any], *, limit: int = 5) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip() if isinstance(item, (str, Path)) else ""
        if not value:
            continue
        value = value.replace("\\", "/")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_text_source_items(items: list[Any], *, limit: int = 5) -> list[dict[str, str]]:
    normalized_by_path: dict[str, dict[str, str]] = {}
    for item in items:
        path = ""
        kind = "unknown"
        if isinstance(item, dict):
            path = str(item.get("path") or "").strip()
            kind = str(item.get("kind") or "unknown").strip() or "unknown"
        elif isinstance(item, (str, Path)):
            path = str(item).strip()
        if not path:
            continue
        path = path.replace("\\", "/")
        existing = normalized_by_path.get(path)
        if existing is None:
            normalized_by_path[path] = {"path": path, "kind": kind}
            continue
        if existing.get("kind") == "unknown" and kind != "unknown":
            existing["kind"] = kind
    return list(normalized_by_path.values())[:limit]


def _agent_solver_run_context(payload: dict[str, Any]) -> dict[str, Any]:
    raw_solver_run = payload.get("solver_run") if isinstance(payload.get("solver_run"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    artifacts = raw_solver_run.get("artifacts") if isinstance(raw_solver_run.get("artifacts"), dict) else {}
    text_sources = raw_solver_run.get("text_sources") if isinstance(raw_solver_run.get("text_sources"), list) else []
    input_files = artifacts.get("input_files") if isinstance(artifacts.get("input_files"), list) else []
    log_files = artifacts.get("log_files") if isinstance(artifacts.get("log_files"), list) else []
    result_files = artifacts.get("result_files") if isinstance(artifacts.get("result_files"), list) else []

    solver = str(raw_solver_run.get("solver") or meta.get("detected_solver") or "unknown")
    status = _normalize_solver_status(raw_solver_run.get("status") or meta.get("solver_status"))
    status_reason = raw_solver_run.get("status_reason")
    raw_primary_log = raw_solver_run.get("primary_log")
    primary_log = str(raw_primary_log).strip().replace("\\", "/") if raw_primary_log else None
    input_preview = _normalize_path_items(input_files)
    log_preview = _normalize_path_items(log_files)
    result_preview = _normalize_path_items(result_files)
    text_source_preview = _normalize_text_source_items(text_sources)

    return {
        "solver": solver,
        "status": status,
        "status_reason": status_reason,
        "primary_log": primary_log,
        "has_primary_log": bool(primary_log),
        "text_source_count": len(text_sources),
        "input_file_count": len(input_files),
        "log_file_count": len(log_files),
        "result_file_count": len(result_files),
        "has_result_artifacts": bool(result_files),
        "input_files": input_preview,
        "log_files": log_preview,
        "result_files": result_preview,
        "text_sources": text_source_preview,
    }


def _agent_solver_status_gate(payload: dict[str, Any]) -> dict[str, Any]:
    solver_run = _agent_solver_run_context(payload)
    route_config = _SOLVER_STATUS_ROUTE_MAP.get(
        solver_run["status"],
        _SOLVER_STATUS_ROUTE_MAP["unknown"],
    )
    gate = dict(route_config)
    gate.update(
        {
            "solver": solver_run["solver"],
            "status": solver_run["status"],
            "status_reason": solver_run["status_reason"],
            "primary_log": solver_run["primary_log"],
            "has_primary_log": solver_run["has_primary_log"],
            "has_result_artifacts": solver_run["has_result_artifacts"],
            "log_file_count": solver_run["log_file_count"],
            "result_file_count": solver_run["result_file_count"],
            "text_source_count": solver_run["text_source_count"],
            "input_files": solver_run["input_files"],
            "log_files": solver_run["log_files"],
            "result_files": solver_run["result_files"],
            "text_sources": solver_run["text_sources"],
            "routing_ready": True,
        }
    )
    return gate


def _build_solver_route_step(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "solver_status_route",
        "route": gate.get("route"),
        "solver": gate.get("solver"),
        "status": gate.get("status"),
        "action": gate.get("primary_action"),
        "goal": gate.get("goal"),
        "status_reason": gate.get("status_reason"),
        "primary_log": gate.get("primary_log"),
    }


def _limit_items(items: list[Any], limit: int = 3) -> list[Any]:
    return list(items[:limit])


def _compact_issue_brief(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": issue.get("category"),
        "severity": issue.get("severity"),
        "message": issue.get("message") or issue.get("title"),
        "location": issue.get("location"),
        "evidence_line": issue.get("evidence_line"),
        "triage": issue.get("triage"),
        "confidence": issue.get("confidence"),
        "auto_fixable": issue.get("auto_fixable"),
    }


def _compact_similar_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": case.get("name") or case.get("case_id") or case.get("title"),
        "similarity_score": case.get("similarity_score"),
        "reason": case.get("reason"),
        "matched_issue": case.get("matched_issue"),
    }


def _select_route_issues(
    payload: dict[str, Any],
    *,
    preferred_categories: set[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    issue_items = [item for item in raw_issues if isinstance(item, dict)]
    if preferred_categories:
        prioritized = [
            item for item in issue_items
            if str(item.get("category")) in preferred_categories
        ]
        if prioritized:
            issue_items = prioritized
    return [_compact_issue_brief(item) for item in issue_items[:limit]]


def _similar_case_briefs(payload: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    raw_cases = payload.get("similar_cases") if isinstance(payload.get("similar_cases"), list) else []
    case_items = [item for item in raw_cases if isinstance(item, dict)]
    return [_compact_similar_case(item) for item in case_items[:limit]]


def _build_route_checklist(recommended_checks: list[Any]) -> list[dict[str, Any]]:
    checklist: list[dict[str, Any]] = []
    for check in recommended_checks:
        key = str(check)
        checklist.append(
            {
                "check": key,
                "instruction": _ROUTE_CHECK_INSTRUCTIONS.get(
                    key,
                    f"Inspect {key} before continuing the next solver action.",
                ),
            }
        )
    return checklist


def _artifact_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    solver_run = payload.get("solver_run") if isinstance(payload.get("solver_run"), dict) else {}
    artifacts = solver_run.get("artifacts") if isinstance(solver_run.get("artifacts"), dict) else {}
    text_sources = solver_run.get("text_sources") if isinstance(solver_run.get("text_sources"), list) else []
    input_files = artifacts.get("input_files") if isinstance(artifacts.get("input_files"), list) else []
    log_files = artifacts.get("log_files") if isinstance(artifacts.get("log_files"), list) else []
    result_files = artifacts.get("result_files") if isinstance(artifacts.get("result_files"), list) else []

    return {
        "primary_log": solver_run.get("primary_log"),
        "status_reason": solver_run.get("status_reason"),
        "input_files": _limit_items(input_files),
        "log_files": _limit_items(log_files),
        "result_files": _limit_items(result_files),
        "text_sources": _limit_items(text_sources),
        "input_file_count": len(input_files),
        "log_file_count": len(log_files),
        "result_file_count": len(result_files),
        "text_source_count": len(text_sources),
    }


def _convergence_tuning_hints(summary: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    max_iterations = summary.get("max_iterations")
    worst_final_residual = summary.get("worst_final_residual")
    residual_trends = summary.get("residual_trend_counts") if isinstance(summary.get("residual_trend_counts"), dict) else {}

    if max_iterations:
        hints.append("Review whether the solver stopped because the iteration budget was exhausted.")
    if worst_final_residual is not None:
        hints.append("Use the worst final residual as the first tuning anchor before changing physics assumptions.")
    if residual_trends.get("worsening"):
        hints.append("A worsening residual trend points to initialization, time-step, or solver-setting instability.")
    elif residual_trends.get("improving"):
        hints.append("An improving residual trend suggests the case may need more iterations before stronger changes.")
    else:
        hints.append("If no clear residual trend is available, inspect the primary convergence log before tuning.")
    return hints


def _physics_result_readiness(
    routing_context: dict[str, Any],
    artifact_snapshot: dict[str, Any],
    convergence_summary: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    has_result_artifacts = bool(artifact_snapshot.get("result_file_count"))
    convergence_files = int(convergence_summary.get("file_count") or 0)
    return {
        "solver_status": routing_context.get("status"),
        "risk_level": summary.get("risk_level", "low"),
        "has_result_artifacts": has_result_artifacts,
        "has_convergence_signals": convergence_files > 0,
        "ready_for_interpretation": bool(
            routing_context.get("status") == "success" and has_result_artifacts
        ),
    }


def _evidence_classification_gaps(
    artifact_snapshot: dict[str, Any],
    convergence_summary: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    if not artifact_snapshot.get("primary_log"):
        gaps.append("primary_log")
    if not artifact_snapshot.get("text_source_count"):
        gaps.append("text_sources")
    if not artifact_snapshot.get("result_file_count"):
        gaps.append("result_artifacts")
    if not convergence_summary.get("file_count"):
        gaps.append("convergence_summary")
    return gaps


def _routing_followup_context(payload: dict[str, Any], routing_context: dict[str, Any]) -> dict[str, Any]:
    route = str(routing_context.get("route") or "evidence_expansion")
    artifact_snapshot = _artifact_snapshot(payload)
    checklist = _build_route_checklist(list(routing_context.get("recommended_checks", [])))
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    convergence = payload.get("convergence") if isinstance(payload.get("convergence"), dict) else {}
    convergence_summary = (
        convergence.get("summary")
        if isinstance(convergence.get("summary"), dict)
        else {}
    )

    if route == "runtime_remediation":
        return {
            "focus": "runtime",
            "objective": "Recover a runnable solver execution before using solver outputs downstream.",
            "artifact_snapshot": artifact_snapshot,
            "priority_issues": _select_route_issues(
                payload,
                preferred_categories={"solver_runtime", "input_syntax"},
            ),
            "checklist": checklist,
            "handoff": {
                "needs_runtime_fix_first": True,
                "ready_for_physics_diagnosis": False,
            },
        }

    if route == "convergence_tuning":
        return {
            "focus": "convergence",
            "objective": "Improve solver stability and convergence before trusting physical interpretation.",
            "artifact_snapshot": artifact_snapshot,
            "convergence_summary": {
                "file_count": convergence_summary.get("file_count"),
                "has_not_converged": convergence_summary.get("has_not_converged"),
                "max_iterations": convergence_summary.get("max_iterations"),
                "worst_final_residual": convergence_summary.get("worst_final_residual"),
                "residual_trend_counts": dict(convergence_summary.get("residual_trend_counts", {})),
                "increment_trend_counts": dict(convergence_summary.get("increment_trend_counts", {})),
            },
            "priority_issues": _select_route_issues(
                payload,
                preferred_categories={"convergence", "solver_runtime"},
            ),
            "checklist": checklist,
            "tuning_hints": _convergence_tuning_hints(convergence_summary),
            "handoff": {
                "needs_convergence_tuning_first": True,
                "ready_for_physics_diagnosis": False,
            },
        }

    if route == "physics_diagnosis":
        return {
            "focus": "physics",
            "objective": "Interpret artifacts and evaluate whether the solved state is physically credible.",
            "artifact_snapshot": artifact_snapshot,
            "result_readiness": _physics_result_readiness(
                routing_context,
                artifact_snapshot,
                convergence_summary,
                summary,
            ),
            "top_issue": summary.get("top_issue") if isinstance(summary.get("top_issue"), dict) else None,
            "first_action": summary.get("first_action"),
            "action_items": _limit_items(list(summary.get("action_items", []))) if isinstance(summary.get("action_items"), list) else [],
            "similar_cases": _similar_case_briefs(payload),
            "priority_issues": _select_route_issues(payload),
            "checklist": checklist,
            "handoff": {
                "needs_runtime_fix_first": False,
                "ready_for_physics_diagnosis": True,
            },
        }

    gaps = _evidence_classification_gaps(artifact_snapshot, convergence_summary)
    return {
        "focus": "evidence",
        "objective": "Expand runtime evidence until the solver state can be classified with confidence.",
        "artifact_snapshot": artifact_snapshot,
        "classification_gaps": gaps,
        "next_collection_targets": _limit_items(gaps),
        "evidence_status": {
            "has_primary_log": bool(artifact_snapshot.get("primary_log")),
            "text_source_count": artifact_snapshot.get("text_source_count"),
            "result_file_count": artifact_snapshot.get("result_file_count"),
            "convergence_file_count": convergence_summary.get("file_count", 0),
        },
        "priority_issues": _select_route_issues(payload),
        "checklist": checklist,
        "handoff": {
            "needs_more_evidence": True,
            "ready_for_physics_diagnosis": False,
        },
    }


def _orchestration_routing_context(agent_context: dict[str, Any]) -> dict[str, Any]:
    solver_status_gate = (
        agent_context.get("solver_status_gate")
        if isinstance(agent_context.get("solver_status_gate"), dict)
        else {}
    )
    next_step = agent_context.get("next_step") if isinstance(agent_context.get("next_step"), dict) else None
    diagnosis_next_step = (
        agent_context.get("diagnosis_next_step")
        if isinstance(agent_context.get("diagnosis_next_step"), dict)
        else None
    )
    gate_overrides = bool(agent_context.get("gate_overrides_diagnosis_plan"))
    decision_source = "solver_status_gate" if gate_overrides or diagnosis_next_step is None else "diagnosis_plan"

    return {
        "route": solver_status_gate.get("route", "evidence_expansion"),
        "decision_source": decision_source,
        "routing_ready": bool(solver_status_gate.get("routing_ready")),
        "solver": solver_status_gate.get("solver", "unknown"),
        "status": solver_status_gate.get("status", "unknown"),
        "status_reason": solver_status_gate.get("status_reason"),
        "primary_log": solver_status_gate.get("primary_log"),
        "has_primary_log": bool(solver_status_gate.get("has_primary_log")),
        "text_source_count": int(solver_status_gate.get("text_source_count", 0) or 0),
        "log_file_count": int(solver_status_gate.get("log_file_count", 0) or 0),
        "result_file_count": int(solver_status_gate.get("result_file_count", 0) or 0),
        "input_files": list(solver_status_gate.get("input_files", [])),
        "log_files": list(solver_status_gate.get("log_files", [])),
        "result_files": list(solver_status_gate.get("result_files", [])),
        "text_sources": list(solver_status_gate.get("text_sources", [])),
        "recommended_checks": list(solver_status_gate.get("recommended_checks", [])),
        "blocked_actions": list(solver_status_gate.get("blocked_actions", [])),
        "recommended_next_action": agent_context.get("recommended_next_action"),
        "selected_next_step": next_step,
        "diagnosis_next_step": diagnosis_next_step,
        "gate_overrides_diagnosis_plan": gate_overrides,
    }


def _selected_route_action_context(
    payload: dict[str, Any],
    routing_context: dict[str, Any],
) -> dict[str, Any]:
    route = str(routing_context.get("route") or "evidence_expansion")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    builder_map: dict[str, tuple[str, Any]] = {
        "runtime_remediation": ("runtime_remediation_prompt", _build_runtime_remediation_prompt_payload),
        "convergence_tuning": ("convergence_tuning_prompt", _build_convergence_tuning_prompt_payload),
        "physics_diagnosis": ("physics_interpretation_prompt", _build_physics_interpretation_prompt_payload),
        "evidence_expansion": ("evidence_collection_plan", _build_evidence_collection_plan),
    }
    action_kind, builder = builder_map.get(
        route,
        ("evidence_collection_plan", _build_evidence_collection_plan),
    )
    route_data = {
        "applicable": True,
        "expected_route": route,
        "actual_route": route,
        "decision_source": routing_context.get("decision_source"),
        "solver": meta.get("detected_solver") or routing_context.get("solver"),
        "solver_status": meta.get("solver_status") or routing_context.get("status"),
        "recommended_next_action": routing_context.get("recommended_next_action"),
        "blocked_actions": list(routing_context.get("blocked_actions", [])),
        "followup": (
            dict(routing_context.get("followup", {}))
            if isinstance(routing_context.get("followup"), dict)
            else {}
        ),
        "solver_run": {
            "status_reason": routing_context.get("status_reason"),
            "primary_log": routing_context.get("primary_log"),
            "has_primary_log": bool(routing_context.get("has_primary_log")),
            "text_source_count": int(routing_context.get("text_source_count", 0) or 0),
            "log_file_count": int(routing_context.get("log_file_count", 0) or 0),
            "result_file_count": int(routing_context.get("result_file_count", 0) or 0),
            "input_files": list(routing_context.get("input_files", [])),
            "log_files": list(routing_context.get("log_files", [])),
            "result_files": list(routing_context.get("result_files", [])),
            "text_sources": list(routing_context.get("text_sources", [])),
        },
        "summary": {
            "issue_count": payload.get("issue_count"),
            "risk_level": summary.get("risk_level", "low"),
            "results_dir": meta.get("results_dir"),
        },
    }
    action_payload = _route_action_payload(
        route_data,
        action_kind=action_kind,
        details=builder(route_data),
    )
    selected_route_execution = _build_selected_route_execution(route_data, action_payload)
    action_payload["selected_route_execution"] = selected_route_execution
    action_payload["route_handoff"] = _build_route_handoff_summary(
        action_payload,
        selected_route_execution,
    )
    action_payload["post_route_step"] = _build_post_route_step(
        action_payload,
        selected_route_execution,
    )
    return action_payload


def _build_diagnosis_payload(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        resolved_results_dir = _resolve_path(results_dir, must_exist=True, kind="results_dir")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return None, _path_error(exc, kind="results_dir", raw=results_dir)

    if not resolved_results_dir.is_dir():
        return None, _error(
            "invalid_input",
            "results_dir must be a directory",
            details={"results_dir": str(resolved_results_dir)},
        )

    resolved_inp: Optional[Path] = None
    if inp_file:
        try:
            resolved_inp = _resolve_path(inp_file, must_exist=True, kind="inp_file")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return None, _path_error(exc, kind="inp_file", raw=inp_file)

    resolved_guardrails: Optional[Path] = None
    if guardrails_path:
        try:
            resolved_guardrails = _resolve_path(guardrails_path, must_exist=True, kind="guardrails_path")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return None, _path_error(exc, kind="guardrails_path", raw=guardrails_path)

    resolved_history_db: Optional[Path] = None
    if history_db_path:
        try:
            resolved_history_db = _resolve_path(history_db_path, must_exist=False, kind="history_db_path")
        except (OSError, ValueError) as exc:
            return None, _path_error(exc, kind="history_db_path", raw=history_db_path)

    client = None
    resolved_model_name = model_name
    model_resolution_source: str | None = "explicit" if model_name else None
    if ai:
        try:
            from cae_preflight_lib.ai.llm_client import (
                LLMClient,
                LLMConfig,
                resolve_ollama_model_name_with_source,
            )

            resolved_model_name, model_resolution_source = resolve_ollama_model_name_with_source(model_name)
            client = LLMClient(config=LLMConfig(use_ollama=True, model_name=resolved_model_name))
        except Exception as exc:
            return None, _error("ai_client_error", str(exc), details={"model_name": resolved_model_name})

    try:
        result = diagnose_results(
            resolved_results_dir,
            client=client,
            inp_file=resolved_inp,
            stream=False,
            guardrails_path=resolved_guardrails,
            history_db_path=resolved_history_db,
        )
        payload = diagnosis_result_to_dict(
            result,
            results_dir=resolved_results_dir,
            inp_file=resolved_inp,
            ai_enabled=ai,
        )
        payload = attach_agent_routing_context(payload)
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        if ai and resolved_model_name:
            meta["resolved_model_name"] = resolved_model_name
            meta["model_resolution_source"] = model_resolution_source
        payload["meta"] = meta
        return payload, None
    except Exception as exc:
        return None, _error(
            "diagnose_failed",
            str(exc),
            details={"results_dir": str(resolved_results_dir)},
        )


def _agent_diagnosis_context(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    raw_plan = summary.get("execution_plan") if isinstance(summary, dict) else []
    plan_items = [item for item in raw_plan if isinstance(item, dict)]
    ordered_plan = sorted(
        plan_items,
        key=lambda item: (
            _AGENT_TRIAGE_ORDER.get(str(item.get("triage", "")), 99),
            int(item.get("step", 9999) or 9999),
        ),
    )
    agent_plan: list[dict[str, Any]] = []
    for idx, item in enumerate(ordered_plan, 1):
        planned_item = dict(item)
        planned_item["source_step"] = item.get("step")
        planned_item["step"] = idx
        agent_plan.append(planned_item)

    diagnosis_next_step = agent_plan[0] if agent_plan else None
    solver_run = _agent_solver_run_context(payload)
    solver_status_gate = _agent_solver_status_gate(payload)
    gate_overrides = bool(solver_status_gate.get("gate_overrides_diagnosis_plan"))

    if gate_overrides:
        next_step = _build_solver_route_step(solver_status_gate)
    elif diagnosis_next_step is not None:
        next_step = diagnosis_next_step
    else:
        next_step = _build_solver_route_step(solver_status_gate)

    return {
        "workflow_order": [
            "solver_status_gate",
            "route_post_action",
            "safe_auto_fix",
            "blocking",
            "review",
            "monitor",
        ],
        "solver_run": solver_run,
        "solver_status_gate": solver_status_gate,
        "recommended_next_action": (
            next_step.get("action")
            if next_step
            else "No diagnosis action required."
        ),
        "next_step": next_step,
        "diagnosis_next_step": diagnosis_next_step,
        "gate_overrides_diagnosis_plan": gate_overrides,
        "execution_plan": agent_plan,
        "safe_auto_fix_available": any(
            item.get("triage") == "safe_auto_fix" for item in agent_plan
        ),
        "blocking_count": int(summary.get("blocking_count", 0) or 0),
        "needs_review_count": int(summary.get("needs_review_count", 0) or 0),
        "risk_level": summary.get("risk_level", "low"),
    }


def attach_agent_routing_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach MCP-style agent/routing context to a diagnosis payload."""
    payload = dict(payload)
    agent_context = _agent_diagnosis_context(payload)
    routing_context = _orchestration_routing_context(agent_context)
    routing_context["followup"] = _routing_followup_context(payload, routing_context)
    routing_context["action_context"] = _selected_route_action_context(payload, routing_context)
    agent_context["selected_route_context"] = routing_context["action_context"]
    agent_context["selected_route_execution"] = (
        routing_context["action_context"].get("selected_route_execution")
        if isinstance(routing_context["action_context"], dict)
        else {}
    )
    agent_context["selected_route_handoff"] = (
        routing_context["action_context"].get("route_handoff")
        if isinstance(routing_context["action_context"], dict)
        else {}
    )
    agent_context["post_route_step"] = (
        routing_context["action_context"].get("post_route_step")
        if isinstance(routing_context["action_context"], dict)
        else {}
    )
    agent_context["recommended_post_route_action"] = (
        agent_context["post_route_step"].get("action")
        if isinstance(agent_context["post_route_step"], dict)
        else None
    )
    routing_context["selected_route_handoff"] = agent_context["selected_route_handoff"]
    routing_context["post_route_step"] = agent_context["post_route_step"]
    routing_context["recommended_post_route_action"] = agent_context[
        "recommended_post_route_action"
    ]
    payload["agent"] = agent_context
    payload["routing"] = routing_context
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    meta["routing_route"] = payload["routing"]["route"]
    meta["routing_decision_source"] = payload["routing"]["decision_source"]
    payload["meta"] = meta
    return payload


def _clear_solver_cache(solver_instance: Any) -> None:
    finder = getattr(solver_instance, "_find_binary", None)
    cache_clear = getattr(finder, "cache_clear", None)
    if callable(cache_clear):
        try:
            cache_clear()
        except Exception:
            pass


@contextmanager
def _temporary_solver_path(solver_path: Path | None) -> Iterator[None]:
    if solver_path is None:
        yield
        return

    had_solver_path = "solver_path" in settings._data
    previous_solver_path = settings._data.get("solver_path")
    settings._data["solver_path"] = str(solver_path)
    try:
        yield
    finally:
        if had_solver_path:
            settings._data["solver_path"] = previous_solver_path
        else:
            settings._data.pop("solver_path", None)


def tool_health() -> dict[str, Any]:
    try:
        solver_info = list_solvers()
    except Exception as exc:
        return _error("solver_probe_failed", str(exc))

    default_solver = settings.default_solver
    installed_solver_names = [item["name"] for item in solver_info if item.get("installed")]
    return _ok(
        {
            "service": "cae-cli-mcp",
            "default_solver": default_solver,
            "installed_solvers": installed_solver_names,
            "solvers": solver_info,
        }
    )


def tool_solvers() -> dict[str, Any]:
    try:
        return _ok({"solvers": list_solvers()})
    except Exception as exc:
        return _error("solver_probe_failed", str(exc))


def tool_docker_status() -> dict[str, Any]:
    try:
        return _ok(_safe_json_value(DockerRuntime().inspect()))
    except Exception as exc:
        return _error("docker_probe_failed", str(exc))


def tool_docker_catalog(
    *,
    solver: str | None = None,
    capability: str | None = None,
    include_experimental: bool = True,
    runnable_only: bool = False,
) -> dict[str, Any]:
    return _ok(
        {
            "images": list_image_spec_dicts(
                solver=solver,
                capability=capability,
                include_experimental=include_experimental,
                runnable_only=runnable_only,
            )
        }
    )


def tool_docker_recommend(*, query: str, limit: int = 5) -> dict[str, Any]:
    if not query.strip():
        return _error("invalid_input", "query must not be empty")
    return _ok(
        {
            "query": query,
            "recommendations": [
                _safe_json_value(spec)
                for spec in recommend_image_specs(query, limit=limit)
            ],
        }
    )


def tool_docker_images() -> dict[str, Any]:
    try:
        return _ok({"images": DockerRuntime().list_images()})
    except Exception as exc:
        return _error("docker_images_failed", str(exc))


def tool_docker_pull(
    *,
    image: str = "calculix",
    timeout: int = 3600,
    set_default: bool = False,
    use_default_config: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})
    resolved_image = resolve_image_reference(image)
    spec = get_image_spec(image)
    try:
        runtime = DockerRuntime()
        already_present = runtime.image_exists(resolved_image)
        skipped_pull = already_present and not refresh
        result = None
        if not skipped_pull:
            result = runtime.pull_image(
                resolved_image,
                timeout=timeout,
                use_default_config=use_default_config,
            )
        image_present = (
            skipped_pull
            or (result.returncode == 0 if result else False)
            or runtime.image_exists(resolved_image)
        )
    except Exception as exc:
        return _error("docker_pull_failed", str(exc), details={"image": image})

    payload = {
        "requested": image,
        "image": resolved_image,
        "alias": spec.alias if spec else None,
        "success": image_present,
        "returncode": 0 if result is None else result.returncode,
        "image_present": image_present,
        "skipped_pull": skipped_pull,
        "stdout": "" if result is None else result.stdout,
        "stderr": "" if result is None else result.stderr,
        "command": [] if result is None else result.command,
        "default_saved": False,
    }
    if image_present and set_default:
        default_key = solver_config_key(spec.solver if spec else "solver")
        settings.set(default_key, resolved_image)
        payload["default_saved"] = True
        payload["default_key"] = default_key
    return _ok(_safe_json_value(payload))


def tool_docker_run(
    *,
    image: str,
    input_path: str,
    output_dir: str | None = None,
    command: str | None = None,
    timeout: int = 3600,
    cpus: str | None = None,
    memory: str | None = None,
    network: str = "none",
) -> dict[str, Any]:
    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})
    try:
        case_path = _resolve_path(input_path, must_exist=True, kind="input_path")
        out_path = (
            _resolve_path(output_dir, kind="output_dir")
            if output_dir
            else Path.cwd() / "results" / f"docker-{case_path.stem if case_path.is_file() else case_path.name}"
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="input_path", raw=input_path)

    try:
        result = DockerSolverRunner().run(
            image,
            case_path,
            out_path,
            command=command,
            timeout=timeout,
            cpus=cpus,
            memory=memory,
            network=network,
        )
    except Exception as exc:
        return _error("docker_run_failed", str(exc), details={"image": image, "input_path": input_path})

    return _ok(_safe_json_value(result))


def tool_docker_build_su2_runtime(
    *,
    tag: str = "local/su2-runtime:8.3.0",
    su2_version: str = "8.3.0",
    base_image: str = "mambaorg/micromamba:1.5.10",
    timeout: int = 3600,
    pull_base: bool = True,
    set_default: bool = True,
) -> dict[str, Any]:
    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})

    dockerfile = Path(__file__).resolve().parent / "docker" / "assets" / "su2-runtime-conda.Dockerfile"
    try:
        result = DockerRuntime().build_image(
            context_dir=dockerfile.parent,
            dockerfile=dockerfile,
            tag=tag,
            build_args={
                "SU2_VERSION": su2_version,
                "MICROMAMBA_IMAGE": base_image,
            },
            timeout=timeout,
            pull=pull_base,
        )
    except Exception as exc:
        return _error("docker_build_failed", str(exc), details={"tag": tag})

    payload = {
        "tag": tag,
        "su2_version": su2_version,
        "base_image": base_image,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": result.command,
        "default_saved": False,
    }
    if result.returncode == 0 and set_default:
        settings.set("docker_su2_image", tag)
        payload["default_saved"] = True
    return _ok(_safe_json_value(payload))


def tool_docker_calculix(
    *,
    inp_file: str,
    output_dir: str | None = None,
    image: str | None = None,
    timeout: int = 3600,
    cpus: str | None = None,
    memory: str | None = None,
) -> dict[str, Any]:
    try:
        inp_path = _resolve_path(inp_file, must_exist=True, kind="inp_file")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="inp_file", raw=inp_file)

    if not inp_path.is_file():
        return _error("invalid_input", "inp_file must be a file", details={"inp_file": str(inp_path)})
    if inp_path.suffix.lower() != ".inp":
        return _error("invalid_input", "inp_file must end with .inp", details={"inp_file": str(inp_path)})
    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})

    if output_dir is None:
        out_path = _default_output_dir(inp_path)
    else:
        try:
            out_path = _resolve_path(output_dir, must_exist=False, kind="output_dir")
        except (OSError, ValueError) as exc:
            return _path_error(exc, kind="output_dir", raw=output_dir)

    try:
        result = CalculixDockerRunner().run(
            inp_path,
            out_path,
            image=resolve_image_reference(image) if image else None,
            timeout=timeout,
            cpus=cpus,
            memory=memory,
        )
    except Exception as exc:
        return _error(
            "docker_calculix_failed",
            str(exc),
            details={"inp_file": str(inp_path), "output_dir": str(out_path)},
        )

    return _ok(_safe_json_value(_solve_result_to_dict(result)))


def tool_solve(
    *,
    inp_file: str,
    output_dir: str | None = None,
    solver: str | None = None,
    timeout: int = 3600,
    solver_path: str | None = None,
) -> dict[str, Any]:
    try:
        inp_path = _resolve_path(inp_file, must_exist=True, kind="inp_file")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="inp_file", raw=inp_file)

    if not inp_path.is_file():
        return _error("invalid_input", "inp_file must be a file", details={"inp_file": str(inp_path)})
    if inp_path.suffix.lower() != ".inp":
        return _error("invalid_input", "inp_file must end with .inp", details={"inp_file": str(inp_path)})

    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})

    resolved_solver_path: Path | None = None
    if solver_path:
        try:
            resolved_solver_path = _resolve_path(solver_path, must_exist=True, kind="solver_path")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return _path_error(exc, kind="solver_path", raw=solver_path)

    solver_name = solver or settings.default_solver
    try:
        solver_instance = get_solver(solver_name)
    except ValueError as exc:
        return _error("invalid_solver", str(exc), details={"solver": solver_name})

    if output_dir is None:
        out_path = _default_output_dir(inp_path)
    else:
        try:
            out_path = _resolve_path(output_dir, must_exist=False, kind="output_dir")
        except (OSError, ValueError) as exc:
            return _path_error(exc, kind="output_dir", raw=output_dir)

    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error("output_error", str(exc), details={"output_dir": str(out_path)})

    try:
        with _temporary_solver_path(resolved_solver_path):
            _clear_solver_cache(solver_instance)
            result = solver_instance.solve(inp_path, out_path, timeout=timeout)
    except Exception as exc:
        return _error(
            "solve_failed",
            str(exc),
            details={
                "inp_file": str(inp_path),
                "output_dir": str(out_path),
                "solver": solver_name,
            },
        )
    finally:
        _clear_solver_cache(solver_instance)

    return _ok(_safe_json_value(_solve_result_to_dict(result)))


def tool_diagnose(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    payload, error = _build_diagnosis_payload(
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )
    if error is not None:
        return error
    return _ok(_safe_json_value(payload))


def _route_data_from_diagnosis_payload(
    payload: dict[str, Any],
    *,
    expected_route: str | None = None,
) -> dict[str, Any]:
    routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    followup = routing.get("followup") if isinstance(routing.get("followup"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    actual_route = str(routing.get("route") or "evidence_expansion")
    resolved_expected = expected_route or actual_route

    route_payload = {
        "applicable": actual_route == resolved_expected,
        "expected_route": resolved_expected,
        "actual_route": actual_route,
        "decision_source": routing.get("decision_source"),
        "solver": meta.get("detected_solver"),
        "solver_status": meta.get("solver_status"),
        "recommended_next_action": routing.get("recommended_next_action"),
        "blocked_actions": list(routing.get("blocked_actions", [])),
        "followup": followup,
        "solver_run": {
            "status_reason": routing.get("status_reason"),
            "primary_log": routing.get("primary_log"),
            "has_primary_log": bool(routing.get("has_primary_log")),
            "text_source_count": int(routing.get("text_source_count", 0) or 0),
            "log_file_count": int(routing.get("log_file_count", 0) or 0),
            "result_file_count": int(routing.get("result_file_count", 0) or 0),
            "input_files": list(routing.get("input_files", [])),
            "log_files": list(routing.get("log_files", [])),
            "result_files": list(routing.get("result_files", [])),
            "text_sources": list(routing.get("text_sources", [])),
        },
        "summary": {
            "issue_count": payload.get("issue_count"),
            "risk_level": summary.get("risk_level", "low"),
            "results_dir": meta.get("results_dir"),
        },
    }
    if actual_route != resolved_expected:
        route_payload["message"] = (
            f"Diagnosis routed this case to '{actual_route}', not '{resolved_expected}'."
        )
    return route_payload


def _route_followup_tool(
    *,
    expected_route: str,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    payload, error = _build_diagnosis_payload(
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )
    if error is not None:
        return error

    route_payload = _route_data_from_diagnosis_payload(payload, expected_route=expected_route)
    return _ok(_safe_json_value(route_payload))


def tool_runtime_remediation(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _route_followup_tool(
        expected_route="runtime_remediation",
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_convergence_tuning(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _route_followup_tool(
        expected_route="convergence_tuning",
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_physics_diagnosis(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _route_followup_tool(
        expected_route="physics_diagnosis",
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_evidence_expansion(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _route_followup_tool(
        expected_route="evidence_expansion",
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def _route_action_payload(
    route_data: dict[str, Any],
    *,
    action_kind: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    solver_run_branch = _infer_solver_run_branch(route_data, solver_run_snapshot)
    payload = {
        "action_kind": action_kind,
        "applicable": bool(route_data.get("applicable")),
        "expected_route": route_data.get("expected_route"),
        "actual_route": route_data.get("actual_route"),
        "decision_source": route_data.get("decision_source"),
        "solver": route_data.get("solver"),
        "solver_status": route_data.get("solver_status"),
        "recommended_next_action": route_data.get("recommended_next_action"),
        "solver_run": solver_run_snapshot,
        "solver_run_branch": solver_run_branch,
        "summary": dict(route_data.get("summary", {})),
    }
    message = route_data.get("message")
    if message:
        payload["message"] = message
    payload.update(details)
    return payload


def _run_route_action_tool(
    route_tool: Any,
    *,
    action_kind: str,
    builder: Any,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    route_payload = route_tool(
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )
    if not route_payload.get("ok"):
        return route_payload

    route_data = route_payload.get("data") if isinstance(route_payload.get("data"), dict) else {}
    details = builder(route_data)
    return _ok(_safe_json_value(_route_action_payload(route_data, action_kind=action_kind, details=details)))


def _list_from_mapping(mapping: dict[str, Any], key: str) -> list[Any]:
    value = mapping.get(key)
    return value if isinstance(value, list) else []


def _int_count(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _route_solver_run_snapshot(route_data: dict[str, Any]) -> dict[str, Any]:
    solver_run = route_data.get("solver_run") if isinstance(route_data.get("solver_run"), dict) else {}
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    artifact_snapshot = (
        followup.get("artifact_snapshot")
        if isinstance(followup.get("artifact_snapshot"), dict)
        else {}
    )
    primary_log = solver_run.get("primary_log") or artifact_snapshot.get("primary_log")
    status_reason = solver_run.get("status_reason") or artifact_snapshot.get("status_reason")
    input_files = _list_from_mapping(solver_run, "input_files") or _list_from_mapping(artifact_snapshot, "input_files")
    log_files = _list_from_mapping(solver_run, "log_files") or _list_from_mapping(artifact_snapshot, "log_files")
    result_files = _list_from_mapping(solver_run, "result_files") or _list_from_mapping(artifact_snapshot, "result_files")
    text_sources = _list_from_mapping(solver_run, "text_sources") or _list_from_mapping(artifact_snapshot, "text_sources")
    normalized_input_files = _normalize_path_items(input_files)
    normalized_log_files = _normalize_path_items(log_files)
    normalized_result_files = _normalize_path_items(result_files)
    normalized_text_sources = _normalize_text_source_items(text_sources)

    return {
        "status_reason": status_reason,
        "primary_log": str(primary_log).replace("\\", "/") if primary_log else None,
        "has_primary_log": bool(primary_log or solver_run.get("has_primary_log")),
        "text_source_count": _int_count(
            solver_run.get("text_source_count")
            or artifact_snapshot.get("text_source_count")
            or len(text_sources),
            fallback=len(normalized_text_sources),
        ),
        "log_file_count": _int_count(
            solver_run.get("log_file_count")
            or artifact_snapshot.get("log_file_count")
            or len(log_files),
            fallback=len(normalized_log_files),
        ),
        "result_file_count": _int_count(
            solver_run.get("result_file_count")
            or artifact_snapshot.get("result_file_count")
            or len(result_files),
            fallback=len(normalized_result_files),
        ),
        "input_files": normalized_input_files,
        "log_files": normalized_log_files,
        "result_files": normalized_result_files,
        "text_sources": normalized_text_sources,
    }


def _render_solver_run_preview_lines(snapshot: dict[str, Any]) -> list[str]:
    return [
        f"Primary log: {snapshot.get('primary_log')}",
        f"Log files: {snapshot.get('log_files')}",
        f"Input files: {snapshot.get('input_files')}",
        f"Result files: {snapshot.get('result_files')}",
        f"Text sources: {snapshot.get('text_sources')}",
    ]


def _render_solver_run_branch_lines(branch: dict[str, Any]) -> list[str]:
    return [
        f"Branch: {branch.get('branch')}",
        f"Branch action: {branch.get('action')}",
        f"Branch goal: {branch.get('goal')}",
        f"Branch evidence: {branch.get('evidence')}",
    ]


def _snapshot_path_values(snapshot: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("primary_log", "input_files", "log_files", "result_files"):
        value = snapshot.get(key)
        if isinstance(value, list):
            values.extend(str(item).lower() for item in value)
        elif value:
            values.append(str(value).lower())
    for item in list(snapshot.get("text_sources", [])):
        if isinstance(item, dict):
            values.append(str(item.get("path") or "").lower())
        elif item:
            values.append(str(item).lower())
    return values


def _snapshot_signal_text(snapshot: dict[str, Any]) -> str:
    values = _snapshot_path_values(snapshot)
    reason = str(snapshot.get("status_reason") or "").lower()
    return " ".join([reason, *values])


def _branch_payload(
    *,
    route: str,
    branch: str,
    action: str,
    goal: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "route": route,
        "branch": branch,
        "action": action,
        "goal": goal,
        "evidence": _limit_items(evidence, limit=5),
    }


def _infer_runtime_solver_run_branch(
    solver: str,
    snapshot: dict[str, Any],
    signal_text: str,
) -> dict[str, Any]:
    if any(token in signal_text for token in ("no such file", "not found", "missing", "cannot open")):
        return _branch_payload(
            route="runtime_remediation",
            branch="missing_runtime_input",
            action="Check input files, sidecar files, and in-container path mapping first.",
            goal="Recover required runtime files before diagnosing physics or convergence.",
            evidence=["missing file signal found in status reason or logs"],
        )
    if solver == "openfoam" or any(token in signal_text for token in ("controlDict", "fvsolution", "polymesh", "icofoam", "openfoam")):
        return _branch_payload(
            route="runtime_remediation",
            branch="openfoam_case_repair",
            action="Inspect OpenFOAM case tree, system dictionaries, boundary, and 0/* fields.",
            goal="Restore OpenFOAM case structure and dictionary consistency first.",
            evidence=["openfoam case or log signal found"],
        )
    if solver == "code_aster" or any(token in signal_text for token in (".export", ".comm", "code_aster")):
        return _branch_payload(
            route="runtime_remediation",
            branch="code_aster_export_reconcile",
            action="Inspect Code_Aster export, comm, and mesh references against actual files.",
            goal="Make the Code_Aster job resolve command and mesh files before retrying.",
            evidence=["code_aster export or comm signal found"],
        )
    if "docker" in signal_text:
        return _branch_payload(
            route="runtime_remediation",
            branch="docker_runtime_recovery",
            action="Inspect image, mounts, workdir, permissions, and container entry command.",
            goal="Confirm the container runtime path before editing solver inputs.",
            evidence=["docker marker found in primary log or log files"],
        )
    return _branch_payload(
        route="runtime_remediation",
        branch="runtime_failure_classification",
        action="Continue reading the primary log and text evidence to classify the runtime failure.",
        goal="Collect enough runtime evidence before selecting a concrete repair surface.",
        evidence=["no solver-specific runtime branch matched"],
    )


def _infer_convergence_solver_run_branch(
    solver: str,
    snapshot: dict[str, Any],
    signal_text: str,
) -> dict[str, Any]:
    if solver == "su2" or any(token in signal_text for token in ("history.csv", ".cfg", "su2")):
        return _branch_payload(
            route="convergence_tuning",
            branch="su2_cfl_iteration_tuning",
            action="Inspect SU2 CFL, iteration budget, linear solver controls, and residual history first.",
            goal="Move the SU2 run toward stable convergence with the smallest parameter changes.",
            evidence=["su2 history or cfg signal found"],
        )
    if solver == "openfoam" or any(token in signal_text for token in ("controlDict", "fvsolution", "courant", "openfoam")):
        return _branch_payload(
            route="convergence_tuning",
            branch="openfoam_time_step_relaxation_tuning",
            action="Inspect OpenFOAM time step, Courant behavior, relaxationFactors, and fvSolution.",
            goal="Stabilize time advancement and linear-solver controls before physics interpretation.",
            evidence=["openfoam convergence signal found"],
        )
    if solver == "calculix" or any(token in signal_text for token in (".sta", ".inp", "calculix")):
        return _branch_payload(
            route="convergence_tuning",
            branch="calculix_increment_contact_tuning",
            action="Inspect CalculiX increments, contact setup, constraints, and material scale first.",
            goal="Address nonlinear increment or contact-driven non-convergence before broader edits.",
            evidence=["calculix sta or inp signal found"],
        )
    return _branch_payload(
        route="convergence_tuning",
        branch="generic_convergence_tuning",
        action="Use residual trends and iteration limits to choose the lowest-risk tuning direction.",
        goal="Keep convergence edits conservative when the solver-specific signal is weak.",
        evidence=["no solver-specific convergence branch matched"],
    )


def _infer_physics_solver_run_branch(snapshot: dict[str, Any], signal_text: str) -> dict[str, Any]:
    if int(snapshot.get("result_file_count") or 0) > 0:
        return _branch_payload(
            route="physics_diagnosis",
            branch="result_interpretation",
            action="Interpret available result files and check loads, constraints, units, and magnitudes.",
            goal="Turn available solver artifacts into a grounded physics judgment.",
            evidence=["result artifacts available"],
        )
    if any(token in signal_text for token in (".frd", ".vtk", ".vtu", ".dat", ".csv")):
        return _branch_payload(
            route="physics_diagnosis",
            branch="result_artifact_check",
            action="Confirm result artifacts are complete, readable, and produced by the current run.",
            goal="Avoid interpreting stale or incomplete result artifacts.",
            evidence=["result-like path signal found without reliable count"],
        )
    return _branch_payload(
        route="physics_diagnosis",
        branch="physics_evidence_gap",
        action="Collect result artifacts or convergence evidence before physics interpretation.",
        goal="Keep physics interpretation tied to verifiable solver output.",
        evidence=["no result artifacts available"],
    )


def _infer_evidence_solver_run_branch(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not bool(snapshot.get("has_primary_log")):
        return _branch_payload(
            route="evidence_expansion",
            branch="collect_primary_log",
            action="Find the primary solver log or container runtime log first.",
            goal="Capture the first evidence needed to classify solver status.",
            evidence=["primary log missing"],
        )
    if int(snapshot.get("text_source_count") or 0) <= 0:
        return _branch_payload(
            route="evidence_expansion",
            branch="collect_text_sources",
            action="Collect stderr, history, sta, log.*, and other parseable text evidence.",
            goal="Avoid routing from filenames alone when text evidence is missing.",
            evidence=["text sources missing"],
        )
    if int(snapshot.get("result_file_count") or 0) <= 0:
        return _branch_payload(
            route="evidence_expansion",
            branch="collect_result_artifacts",
            action="Look for result files or output artifacts next.",
            goal="Decide whether the current run produced interpretable results.",
            evidence=["result artifacts missing"],
        )
    return _branch_payload(
        route="evidence_expansion",
        branch="classify_mixed_evidence",
        action="Reconcile logs, text evidence, and result files into a solver-status decision.",
        goal="Normalize mixed evidence into a clear solver status.",
        evidence=["primary log, text sources, and result artifacts available"],
    )


def _infer_solver_run_branch(route_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    route = str(route_data.get("actual_route") or route_data.get("expected_route") or "evidence_expansion")
    solver = str(route_data.get("solver") or "unknown").lower()
    signal_text = _snapshot_signal_text(snapshot)
    if route == "runtime_remediation":
        return _infer_runtime_solver_run_branch(solver, snapshot, signal_text)
    if route == "convergence_tuning":
        return _infer_convergence_solver_run_branch(solver, snapshot, signal_text)
    if route == "physics_diagnosis":
        return _infer_physics_solver_run_branch(snapshot, signal_text)
    if route == "evidence_expansion":
        return _infer_evidence_solver_run_branch(snapshot)
    return _branch_payload(
        route=route,
        branch="continue_route_analysis",
        action="Continue route-specific analysis.",
        goal="Keep the current route grounded in available evidence.",
        evidence=["route has no specialized solver-run branch"],
    )


def _is_docker_runtime_case(artifact_snapshot: dict[str, Any]) -> bool:
    primary_log = str(artifact_snapshot.get("primary_log") or "").lower()
    log_files = artifact_snapshot.get("log_files") if isinstance(artifact_snapshot.get("log_files"), list) else []
    return primary_log.startswith("docker-") or any(str(item).lower().startswith("docker-") for item in log_files)


def _docker_runtime_retry_checks(route_data: dict[str, Any], artifact_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not _is_docker_runtime_case(artifact_snapshot):
        return []

    checks = [
        {
            "area": "docker_image_reference",
            "instruction": "Confirm the configured Docker image/tag resolves to the intended solver runtime before retrying.",
            "trigger": "docker_runtime_detected",
        },
        {
            "area": "container_mounts_and_workdir",
            "instruction": "Verify the mounted case directory, writable output path, and container workdir all point at the same solver case.",
            "trigger": "docker_runtime_detected",
        },
        {
            "area": "container_entry_command",
            "instruction": "Check that the container entry command and case filename match the selected solver family.",
            "trigger": "docker_runtime_detected",
        },
        {
            "area": "container_sidecar_inputs",
            "instruction": "Verify that every sidecar input referenced by the case file was copied into the mounted container workspace.",
            "trigger": "docker_runtime_detected",
        },
        {
            "area": "container_output_writeability",
            "instruction": "Confirm the container can write logs and solver outputs into the mounted result directory.",
            "trigger": "docker_runtime_detected",
        },
    ]

    solver = str(route_data.get("solver") or "")
    if solver == "openfoam":
        checks.append(
            {
                "area": "openfoam_case_tree",
                "instruction": "Confirm the OpenFOAM case still has a valid `0/`, `constant/`, and `system/` layout inside the mounted container workspace.",
                "trigger": "solver=openfoam",
            }
        )
    if solver == "su2":
        checks.append(
            {
                "area": "su2_cfg_sidecars",
                "instruction": "Confirm every SU2 config reference, especially mesh and restart sidecars, is available inside the container workspace.",
                "trigger": "solver=su2",
            }
        )
    return checks


def _infer_runtime_failure_modes(route_data: dict[str, Any], artifact_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    solver = str(route_data.get("solver") or "")
    status_reason = str(artifact_snapshot.get("status_reason") or "")
    issue_messages = " ".join(
        str(item.get("message") or item.get("evidence_line") or "")
        for item in (artifact_snapshot.get("priority_issues") or [])
        if isinstance(item, dict)
    )
    evidence = f"{status_reason} {issue_messages}".lower()
    modes: list[dict[str, Any]] = []

    if any(token in evidence for token in ("no such file", "not found", "cannot find", "can't open")):
        modes.append(
            {
                "mode": "missing_sidecar_or_mount_path",
                "reason": "The runtime evidence points to a missing file, sidecar, or mount-path mismatch inside the container.",
            }
        )
    if any(token in evidence for token in ("permission denied", "read-only", "operation not permitted")):
        modes.append(
            {
                "mode": "container_permissions_or_output_path",
                "reason": "The runtime evidence points to a permission or output-writeability problem in the mounted workspace.",
            }
        )
    if any(token in evidence for token in ("command not found", "executable file not found", "unknown option", "usage:")):
        modes.append(
            {
                "mode": "container_command_or_entrypoint_mismatch",
                "reason": "The runtime evidence points to an image/entry-command mismatch rather than a physics issue.",
            }
        )
    if solver == "openfoam" and any(token in evidence for token in ("patch", "field", "dictionary")):
        modes.append(
            {
                "mode": "openfoam_case_structure_mismatch",
                "reason": "The OpenFOAM runtime evidence points to patch, field, or dictionary inconsistency in the case tree.",
            }
        )
    if solver == "su2" and any(token in evidence for token in ("marker", "mesh", "restart", ".cfg")):
        modes.append(
            {
                "mode": "su2_config_or_sidecar_mismatch",
                "reason": "The SU2 runtime evidence points to config-sidecar or marker/mesh inconsistency.",
            }
        )
    if solver == "code_aster" and any(token in evidence for token in ("command file", "<f>", ".comm", ".export")):
        modes.append(
            {
                "mode": "code_aster_export_or_command_mismatch",
                "reason": "The Code_Aster runtime evidence points to an export/command-file mismatch or missing sidecar input.",
            }
        )
    if solver == "elmer" and any(token in evidence for token in ("mesh", "elmersolver", ".sif")):
        modes.append(
            {
                "mode": "elmer_mesh_or_sif_reference_mismatch",
                "reason": "The Elmer runtime evidence points to a mesh-path or SIF reference problem in the mounted workspace.",
            }
        )
    return modes


def _solver_specific_runtime_checks(route_data: dict[str, Any], artifact_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    solver = str(route_data.get("solver") or "")
    primary_log = str(artifact_snapshot.get("primary_log") or "")
    checks: list[dict[str, Any]] = []

    if solver == "openfoam":
        checks.extend(
            [
                {
                    "area": "openfoam_boundary_fields",
                    "instruction": "Inspect boundary field names and patch references when the OpenFOAM log reports a patch or field lookup failure.",
                    "trigger": primary_log or "solver=openfoam",
                },
                {
                    "area": "openfoam_dictionary_consistency",
                    "instruction": "Review `controlDict`, `fvSchemes`, and `fvSolution` for missing dictionaries or incompatible case setup.",
                    "trigger": "solver=openfoam",
                },
            ]
        )
    elif solver == "su2":
        checks.extend(
            [
                {
                    "area": "su2_marker_consistency",
                    "instruction": "Verify SU2 marker names in the config match the mesh boundary markers exactly.",
                    "trigger": primary_log or "solver=su2",
                },
                {
                    "area": "su2_mesh_and_restart_inputs",
                    "instruction": "Check mesh, restart, and auxiliary input paths referenced by the SU2 config before retrying.",
                    "trigger": "solver=su2",
                },
            ]
        )
    elif solver == "code_aster":
        checks.extend(
            [
                {
                    "area": "code_aster_export_sidecars",
                    "instruction": "Confirm the `.export` file, referenced `.comm`, and every mesh/material sidecar exist inside the mounted container workspace.",
                    "trigger": primary_log or "solver=code_aster",
                },
                {
                    "area": "code_aster_command_pairing",
                    "instruction": "Verify the Code_Aster command file and execution wrapper are launching the intended case from the correct working directory.",
                    "trigger": "solver=code_aster",
                },
            ]
        )
    elif solver == "elmer":
        checks.extend(
            [
                {
                    "area": "elmer_mesh_db_and_sidecars",
                    "instruction": "Check the Elmer `Header/Mesh DB` references and confirm the required mesh sidecars are present in the container workspace.",
                    "trigger": primary_log or "solver=elmer",
                },
                {
                    "area": "elmer_sif_solver_sections",
                    "instruction": "Review the SIF solver sections, output settings, and referenced material/boundary blocks before retrying.",
                    "trigger": "solver=elmer",
                },
            ]
        )
    return checks


def _build_runtime_retry_checks(route_data: dict[str, Any]) -> dict[str, Any]:
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    artifact_snapshot = (
        followup.get("artifact_snapshot")
        if isinstance(followup.get("artifact_snapshot"), dict)
        else {}
    )
    artifact_snapshot = {
        **artifact_snapshot,
        **{
            key: value
            for key, value in solver_run_snapshot.items()
            if value not in (None, "", [], {})
        },
    }
    docker_checks = _docker_runtime_retry_checks(route_data, artifact_snapshot)
    solver_specific_checks = _solver_specific_runtime_checks(route_data, artifact_snapshot)
    failure_modes = _infer_runtime_failure_modes(
        route_data,
        {
            **artifact_snapshot,
            "priority_issues": list(followup.get("priority_issues", [])),
        },
    )
    return {
        "retry_ready": bool(route_data.get("applicable")),
        "pre_retry_checks": list(followup.get("checklist", [])),
        "docker_runtime_checks": docker_checks,
        "solver_specific_checks": solver_specific_checks,
        "suspected_failure_modes": failure_modes,
        "blocking_signals": {
            "primary_log": artifact_snapshot.get("primary_log"),
            "status_reason": artifact_snapshot.get("status_reason"),
            "priority_issues": list(followup.get("priority_issues", [])),
        },
        "retry_guardrails": [
            "Do not retry until the primary runtime failure has a concrete explanation.",
            "Keep physics diagnosis blocked until runtime remediation finishes.",
        ],
    }


def _solver_specific_convergence_suggestions(
    route_data: dict[str, Any],
    convergence_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    solver = str(route_data.get("solver") or "")
    suggestions: list[dict[str, Any]] = []

    if solver == "su2":
        suggestions.extend(
            [
                {
                    "parameter_area": "cfl_or_time_step",
                    "suggestion": "Reduce CFL growth or pseudo-time-step aggressiveness in the SU2 config before retrying.",
                    "trigger": "solver=su2",
                },
                {
                    "parameter_area": "linear_solver",
                    "suggestion": "Review the SU2 linear solver, preconditioner, and residual tolerances when iterations stall.",
                    "trigger": "solver=su2",
                },
                {
                    "parameter_area": "marker_and_mesh_consistency",
                    "suggestion": "Verify marker naming and mesh boundary consistency before deeper convergence tuning.",
                    "trigger": "solver=su2",
                },
            ]
        )
    elif solver == "openfoam":
        suggestions.extend(
            [
                {
                    "parameter_area": "deltaT_maxCo",
                    "suggestion": "Reduce `deltaT` or `maxCo` so the OpenFOAM case evolves under a safer Courant target.",
                    "trigger": "solver=openfoam",
                },
                {
                    "parameter_area": "fvSolution_relaxation",
                    "suggestion": "Review linear solver tolerances and relaxation factors in `fvSolution` before retrying.",
                    "trigger": "solver=openfoam",
                },
                {
                    "parameter_area": "mesh_and_boundary_fields",
                    "suggestion": "Inspect mesh quality and boundary fields under `0/` and `constant/` when OpenFOAM residuals do not settle.",
                    "trigger": "solver=openfoam",
                },
            ]
        )
    elif solver == "elmer":
        suggestions.extend(
            [
                {
                    "parameter_area": "linear_system_controls",
                    "suggestion": "Review Elmer linear-system settings, preconditioners, and tolerances before changing the physical model.",
                    "trigger": "solver=elmer",
                },
                {
                    "parameter_area": "nonlinear_system_controls",
                    "suggestion": "Tune Elmer nonlinear-system relaxation and iteration limits when residual reduction stalls.",
                    "trigger": "solver=elmer",
                },
                {
                    "parameter_area": "timestep_or_steady_controls",
                    "suggestion": "Revisit steady/transient control settings in the SIF when Elmer fails to settle cleanly.",
                    "trigger": "solver=elmer",
                },
            ]
        )
    elif solver == "code_aster":
        suggestions.extend(
            [
                {
                    "parameter_area": "newton_increment_control",
                    "suggestion": "Review Code_Aster Newton controls and increment refinement before stronger model changes.",
                    "trigger": "solver=code_aster",
                },
                {
                    "parameter_area": "line_search_or_contact",
                    "suggestion": "Inspect line-search, contact, or constitutive settings when Code_Aster iterations oscillate or stall.",
                    "trigger": "solver=code_aster",
                },
                {
                    "parameter_area": "time_step_refinement",
                    "suggestion": "Reduce the active time-step or increment growth to make the next Code_Aster pass more stable.",
                    "trigger": "solver=code_aster",
                },
            ]
        )

    if convergence_summary.get("worst_final_residual") is not None and solver in {"su2", "openfoam", "elmer", "code_aster"}:
        suggestions.append(
            {
                "parameter_area": "residual_target",
                "suggestion": "Use the current worst final residual as the baseline when judging whether the next tuning pass actually improved convergence.",
                "trigger": f"worst_final_residual={convergence_summary.get('worst_final_residual')}",
            }
        )
    return suggestions


def _build_convergence_parameter_suggestions(route_data: dict[str, Any]) -> dict[str, Any]:
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    convergence_summary = (
        followup.get("convergence_summary")
        if isinstance(followup.get("convergence_summary"), dict)
        else {}
    )
    residual_trends = (
        convergence_summary.get("residual_trend_counts")
        if isinstance(convergence_summary.get("residual_trend_counts"), dict)
        else {}
    )
    suggestions: list[dict[str, Any]] = []

    if convergence_summary.get("max_iterations"):
        suggestions.append(
            {
                "parameter_area": "iteration_budget",
                "suggestion": "Increase the iteration budget before stronger model changes.",
                "trigger": f"max_iterations={convergence_summary.get('max_iterations')}",
            }
        )
    if residual_trends.get("worsening"):
        suggestions.append(
            {
                "parameter_area": "time_step_control",
                "suggestion": "Reduce the time step or increment size to stabilize a worsening residual trend.",
                "trigger": "residual_trend=worsening",
            }
        )
        suggestions.append(
            {
                "parameter_area": "initialization",
                "suggestion": "Review initial fields and restart assumptions before retrying.",
                "trigger": "residual_trend=worsening",
            }
        )
    elif residual_trends.get("improving"):
        suggestions.append(
            {
                "parameter_area": "solver_settings",
                "suggestion": "Keep the current setup mostly intact and tune tolerances or iteration limits gradually.",
                "trigger": "residual_trend=improving",
            }
        )
    if not convergence_summary.get("file_count"):
        suggestions.append(
            {
                "parameter_area": "residual_history",
                "suggestion": "Capture residual history before applying deeper convergence changes.",
                "trigger": "missing_convergence_summary",
            }
        )

    solver_specific_suggestions = _solver_specific_convergence_suggestions(route_data, convergence_summary)
    return {
        "parameter_suggestions": suggestions,
        "solver_specific_suggestions": solver_specific_suggestions,
        "tuning_hints": list(followup.get("tuning_hints", [])),
        "priority_issues": list(followup.get("priority_issues", [])),
    }


def _render_prompt_items(
    items: list[dict[str, Any]],
    *,
    primary_key: str,
    secondary_key: str,
) -> list[str]:
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        primary = str(item.get(primary_key) or "").strip()
        secondary = str(item.get(secondary_key) or "").strip()
        if primary and secondary:
            lines.append(f"- {primary}: {secondary}")
        elif secondary:
            lines.append(f"- {secondary}")
        elif primary:
            lines.append(f"- {primary}")
    return lines


def _solver_runtime_prompt_focus(solver: str) -> str:
    if solver == "openfoam":
        return "Prioritize OpenFOAM case-tree consistency, patch fields, and dictionary references before any rerun."
    if solver == "su2":
        return "Prioritize SU2 config-marker consistency and every mesh/restart sidecar referenced by the cfg."
    if solver == "code_aster":
        return "Prioritize the Code_Aster `.export`/`.comm` pair, working directory, and mounted sidecar inputs."
    if solver == "elmer":
        return "Prioritize the Elmer `.sif` references, mesh database paths, and required sidecar files in the mounted workspace."
    return "Prioritize evidence-backed runtime blockers and keep the next step tied to the observed failure mode."


def _solver_convergence_prompt_focus(solver: str) -> str:
    if solver == "openfoam":
        return "Prefer OpenFOAM controls such as `deltaT`, `maxCo`, `fvSolution`, and mesh/boundary consistency over broad physics changes."
    if solver == "su2":
        return "Prefer SU2 controls such as CFL growth, pseudo-time stepping, linear-solver tolerances, and marker consistency."
    if solver == "code_aster":
        return "Prefer Code_Aster Newton, line-search/contact, and time-increment controls before changing constitutive assumptions."
    if solver == "elmer":
        return "Prefer Elmer linear/nonlinear solver controls and steady-transient settings before changing the physical model."
    return "Prefer incremental numerical-control changes before proposing larger model edits."


def _fallback_runtime_target_paths(solver: str) -> dict[str, list[str]]:
    common = {
        "docker_image_reference": ["selected solver runtime image", "stored image/tag reference"],
        "container_mounts_and_workdir": ["mounted case directory", "container workdir", "mounted result directory"],
        "container_entry_command": ["container entry command", "solver launch arguments"],
        "container_sidecar_inputs": ["mounted case workspace", "referenced sidecar inputs"],
        "container_output_writeability": ["mounted result directory", "container write permissions"],
    }
    solver_specific: dict[str, dict[str, list[str]]] = {
        "openfoam": {
            "openfoam_boundary_fields": ["0/ boundary fields", "patch field names"],
            "openfoam_dictionary_consistency": ["system/controlDict", "system/fvSchemes", "system/fvSolution"],
        },
        "su2": {
            "su2_marker_consistency": ["primary SU2 cfg", "mesh boundary marker names"],
            "su2_mesh_and_restart_inputs": ["primary SU2 cfg", "mesh/restart sidecars"],
        },
        "code_aster": {
            "code_aster_export_sidecars": [".export file", ".comm file", "mesh/material sidecars"],
            "code_aster_command_pairing": ["execution wrapper", "working directory", "selected Code_Aster case command"],
        },
        "elmer": {
            "elmer_mesh_db_and_sidecars": [".sif file", "Header/Mesh DB", "mesh sidecar bundle"],
            "elmer_sif_solver_sections": [".sif Solver sections", "output/material/boundary blocks"],
        },
    }
    merged = dict(common)
    merged.update(solver_specific.get(solver, {}))
    return merged


def _default_bounded_edit_scopes(
    target_id: str,
    path_hints: list[str],
    *,
    allowed_actions: list[str],
    change_guard: str,
    block_hints: list[str] | None = None,
    parameter_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for idx, path_hint in enumerate(path_hints, 1):
        scopes.append(
            {
                "scope_id": f"{target_id}_{idx}",
                "path_hint": path_hint,
                "block_hints": list(block_hints or []),
                "parameter_hints": list(parameter_hints or []),
                "allowed_actions": list(allowed_actions),
                "change_guard": change_guard,
            }
        )
    return scopes


def _runtime_target_bounded_edit_scopes(
    solver: str,
    target_id: str,
    path_hints: list[str],
) -> list[dict[str, Any]]:
    common: dict[str, list[dict[str, Any]]] = {
        "sidecar_input_bundle": [
            {
                "scope_id": "runtime_sidecar_bundle",
                "path_hint": "mounted case directory",
                "block_hints": ["referenced sidecar filenames", "relative path references"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_relative_paths", "copy_missing_sidecars"],
                "change_guard": "Limit changes to missing-file references and copied sidecars before any rerun.",
            }
        ],
        "result_directory_permissions": [
            {
                "scope_id": "runtime_result_directory",
                "path_hint": "mounted result directory",
                "block_hints": ["write permissions", "output path ownership"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_output_path"],
                "change_guard": "Keep changes inside output path or writeability checks; do not alter solver physics here.",
            }
        ],
        "container_entry_command": [
            {
                "scope_id": "runtime_container_command",
                "path_hint": "solver launch arguments",
                "block_hints": ["solver executable", "case filename", "working directory"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_runtime_configuration"],
                "change_guard": "Limit changes to entrypoint or launch-argument pairing for the already selected solver.",
            }
        ],
        "docker_image_reference": [
            {
                "scope_id": "runtime_image_reference",
                "path_hint": "stored image/tag reference",
                "block_hints": ["selected image tag", "solver family tag"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_runtime_configuration"],
                "change_guard": "Only reconcile the selected image/tag reference; do not switch solver family implicitly.",
            }
        ],
        "container_mounts_and_workdir": [
            {
                "scope_id": "runtime_mounts_workdir",
                "path_hint": "mounted case directory",
                "block_hints": ["mount source", "container workdir", "mounted result directory"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_mount_paths"],
                "change_guard": "Limit changes to mount/workdir alignment so the same case is visible inside the container.",
            }
        ],
        "container_sidecar_inputs": [
            {
                "scope_id": "runtime_sidecar_mounts",
                "path_hint": "referenced sidecar inputs",
                "block_hints": ["copied sidecars", "relative include paths"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_relative_paths", "copy_missing_sidecars"],
                "change_guard": "Keep edits inside sidecar presence and path alignment for the mounted workspace.",
            }
        ],
        "container_output_writeability": [
            {
                "scope_id": "runtime_output_writeability",
                "path_hint": "mounted result directory",
                "block_hints": ["write permissions", "generated log path"],
                "parameter_hints": [],
                "allowed_actions": ["inspect", "reconcile_output_path"],
                "change_guard": "Only change output path/writeability settings while the runtime failure remains unresolved.",
            }
        ],
    }
    solver_specific: dict[str, dict[str, list[dict[str, Any]]]] = {
        "openfoam": {
            "openfoam_case_tree": [
                {
                    "scope_id": "openfoam_case_layout",
                    "path_hint": "case directory mount",
                    "block_hints": ["0/", "constant/", "system/"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "restore_case_layout"],
                    "change_guard": "Only reconcile missing case-layout pieces or broken patch references before rerunning.",
                },
                {
                    "scope_id": "openfoam_boundary_definition",
                    "path_hint": "constant/polyMesh/boundary",
                    "block_hints": ["patch names", "boundary field coverage"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_patch_names"],
                    "change_guard": "Keep changes limited to patch-name alignment between dictionaries and field files.",
                },
            ],
            "openfoam_boundary_fields": [
                {
                    "scope_id": "openfoam_field_boundaries",
                    "path_hint": "0/ boundary fields",
                    "block_hints": ["field boundary entries", "patch coverage"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_patch_field_entries"],
                    "change_guard": "Only update missing or mismatched patch entries; avoid broader model edits.",
                }
            ],
            "openfoam_dictionary_consistency": [
                {
                    "scope_id": "openfoam_dictionary_controls",
                    "path_hint": "system/controlDict",
                    "block_hints": ["application", "startFrom", "writeInterval"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_dictionary_references"],
                    "change_guard": "Limit changes to dictionary references needed for runtime consistency.",
                },
                {
                    "scope_id": "openfoam_dictionary_solver",
                    "path_hint": "system/fvSolution",
                    "block_hints": ["solvers", "relaxationFactors"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_dictionary_references"],
                    "change_guard": "Only align solver dictionary blocks with the existing case layout and application.",
                },
            ],
        },
        "su2": {
            "su2_cfg_sidecars": [
                {
                    "scope_id": "su2_cfg_references",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["MESH_FILENAME", "RESTART_SOL", "MARKER_*"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_cfg_references"],
                    "change_guard": "Keep edits inside cfg-to-sidecar references and marker naming before any rerun.",
                }
            ],
            "su2_marker_consistency": [
                {
                    "scope_id": "su2_marker_consistency",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["MARKER_* entries", "mesh boundary markers"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_marker_names"],
                    "change_guard": "Only align marker names between cfg and mesh; do not tune numerics in this step.",
                }
            ],
            "su2_mesh_and_restart_inputs": [
                {
                    "scope_id": "su2_mesh_restart_inputs",
                    "path_hint": "mesh/restart sidecars",
                    "block_hints": ["mesh path", "restart path"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_cfg_references", "copy_missing_sidecars"],
                    "change_guard": "Keep changes limited to mesh/restart sidecar presence and cfg references.",
                }
            ],
        },
        "code_aster": {
            "code_aster_export_bundle": [
                {
                    "scope_id": "code_aster_export_file",
                    "path_hint": ".export file",
                    "block_hints": ["F comm", "F mmed", "working directory"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_export_references"],
                    "change_guard": "Only reconcile export-path entries and working-directory references before rerunning.",
                },
                {
                    "scope_id": "code_aster_comm_pairing",
                    "path_hint": ".comm file",
                    "block_hints": ["mesh/material include references", "command pairing"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_sidecar_references"],
                    "change_guard": "Keep changes inside the .comm sidecar references required by the current export bundle.",
                },
            ],
            "code_aster_export_sidecars": [
                {
                    "scope_id": "code_aster_sidecars",
                    "path_hint": ".export file",
                    "block_hints": ["mesh/material sidecar entries"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_export_references", "copy_missing_sidecars"],
                    "change_guard": "Only repair missing sidecar references that are already declared by the export bundle.",
                }
            ],
            "code_aster_command_pairing": [
                {
                    "scope_id": "code_aster_command_pairing",
                    "path_hint": "execution wrapper",
                    "block_hints": ["aster command", "working directory", "selected .export file"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_runtime_configuration"],
                    "change_guard": "Limit changes to wrapper/.export pairing for the existing Code_Aster case.",
                }
            ],
        },
        "elmer": {
            "elmer_sif_mesh_bundle": [
                {
                    "scope_id": "elmer_sif_mesh_db",
                    "path_hint": ".sif file",
                    "block_hints": ["Header", "Mesh DB", "Include Path"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_sif_references"],
                    "change_guard": "Keep edits inside SIF mesh/include references and avoid broader physics changes.",
                }
            ],
            "elmer_mesh_db_and_sidecars": [
                {
                    "scope_id": "elmer_mesh_sidecars",
                    "path_hint": "mesh directory",
                    "block_hints": ["mesh database files", "sidecar presence"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "copy_missing_sidecars", "reconcile_sif_references"],
                    "change_guard": "Only repair mesh database or sidecar references required by the current SIF.",
                }
            ],
            "elmer_sif_solver_sections": [
                {
                    "scope_id": "elmer_solver_sections",
                    "path_hint": ".sif Solver sections",
                    "block_hints": ["Solver", "Equation", "Boundary Condition", "Material"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect", "reconcile_sif_references"],
                    "change_guard": "Limit changes to sections referenced by the current mesh and boundary naming.",
                }
            ],
        },
    }
    merged = dict(common)
    merged.update(solver_specific.get(solver, {}))
    scopes = merged.get(target_id)
    if scopes is not None:
        return [dict(scope) for scope in scopes]

    allowed_actions = ["inspect"]
    change_guard = "Stay inside the observed runtime mismatch until the blocking failure path is concrete."
    if target_id in {"sidecar_input_bundle", "container_sidecar_inputs"}:
        allowed_actions = ["inspect", "reconcile_relative_paths"]
        change_guard = "Only reconcile missing sidecar references or copies for the mounted runtime workspace."
    elif target_id in {"result_directory_permissions", "container_output_writeability"}:
        allowed_actions = ["inspect", "reconcile_output_path"]
        change_guard = "Limit changes to output path or writeability while the runtime blocker is unresolved."
    elif target_id in {"container_entry_command", "docker_image_reference", "container_mounts_and_workdir"}:
        allowed_actions = ["inspect", "reconcile_runtime_configuration"]
        change_guard = "Only change runtime configuration that directly matches the observed launch failure."
    return _default_bounded_edit_scopes(
        target_id,
        path_hints,
        allowed_actions=allowed_actions,
        change_guard=change_guard,
    )


def _runtime_failure_mode_targets(solver: str) -> dict[str, dict[str, Any]]:
    return {
        "missing_sidecar_or_mount_path": {
            "target_id": "sidecar_input_bundle",
            "target_kind": "runtime_input_bundle",
            "scope": "mounted case inputs",
            "path_hints": {
                "openfoam": ["case directory mount", "0/", "constant/", "system/"],
                "su2": ["primary SU2 cfg", "mesh/restart sidecars", "marker references"],
                "code_aster": [".export file", ".comm file", "referenced mesh/material sidecars"],
                "elmer": [".sif file", "mesh directory", "referenced sidecars"],
                "default": ["mounted case directory", "referenced input sidecars"],
            },
            "suggested_action": "verify_sidecar_presence_and_mount_paths",
            "priority": "high",
        },
        "container_permissions_or_output_path": {
            "target_id": "result_directory_permissions",
            "target_kind": "runtime_filesystem",
            "scope": "mounted result directory",
            "path_hints": {"default": ["mounted result directory", "container workdir permissions"]},
            "suggested_action": "verify_output_writeability",
            "priority": "high",
        },
        "container_command_or_entrypoint_mismatch": {
            "target_id": "container_entry_command",
            "target_kind": "runtime_command",
            "scope": "container launch command",
            "path_hints": {"default": ["container entry command", "solver launch arguments", "selected image tag"]},
            "suggested_action": "verify_entrypoint_and_command_pairing",
            "priority": "high",
        },
        "openfoam_case_structure_mismatch": {
            "target_id": "openfoam_case_tree",
            "target_kind": "solver_case_structure",
            "scope": "OpenFOAM case tree",
            "path_hints": {"default": ["0/ boundary fields", "constant/", "system/ dictionaries"]},
            "suggested_action": "reconcile_case_tree_and_patch_fields",
            "priority": "high",
        },
        "su2_config_or_sidecar_mismatch": {
            "target_id": "su2_cfg_sidecars",
            "target_kind": "solver_config_bundle",
            "scope": "SU2 config inputs",
            "path_hints": {"default": ["primary SU2 cfg", "mesh/restart sidecars", "marker definitions"]},
            "suggested_action": "reconcile_cfg_references_and_marker_names",
            "priority": "high",
        },
        "code_aster_export_or_command_mismatch": {
            "target_id": "code_aster_export_bundle",
            "target_kind": "solver_input_bundle",
            "scope": "Code_Aster export/command pair",
            "path_hints": {"default": [".export file", ".comm file", "execution wrapper", "working directory"]},
            "suggested_action": "reconcile_export_command_and_sidecars",
            "priority": "high",
        },
        "elmer_mesh_or_sif_reference_mismatch": {
            "target_id": "elmer_sif_mesh_bundle",
            "target_kind": "solver_input_bundle",
            "scope": "Elmer SIF and mesh references",
            "path_hints": {"default": [".sif file", "Header/Mesh DB", "mesh directory sidecars"]},
            "suggested_action": "reconcile_sif_mesh_references",
            "priority": "high",
        },
    }


def _build_runtime_remediation_targets(
    route_data: dict[str, Any],
    runtime_details: dict[str, Any],
) -> list[dict[str, Any]]:
    solver = str(route_data.get("solver") or "unknown")
    blocking_signals = (
        runtime_details.get("blocking_signals")
        if isinstance(runtime_details.get("blocking_signals"), dict)
        else {}
    )
    failure_modes = [
        item for item in list(runtime_details.get("suspected_failure_modes", []))
        if isinstance(item, dict)
    ]
    mode_map = _runtime_failure_mode_targets(solver)
    fallback_paths = _fallback_runtime_target_paths(solver)
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_target(target: dict[str, Any]) -> None:
        target_id = str(target.get("target_id") or "").strip()
        if not target_id or target_id in seen:
            return
        seen.add(target_id)
        target["bounded_edit_scopes"] = _runtime_target_bounded_edit_scopes(
            solver,
            target_id,
            list(target.get("path_hints", [])),
        )
        targets.append(target)

    for failure_mode in failure_modes:
        mode_key = str(failure_mode.get("mode") or "")
        spec = mode_map.get(mode_key)
        if spec is None:
            continue
        path_hints = list(spec.get("path_hints", {}).get(solver) or spec.get("path_hints", {}).get("default") or [])
        add_target(
            {
                "target_id": spec["target_id"],
                "target_kind": spec["target_kind"],
                "scope": spec["scope"],
                "path_hints": path_hints,
                "suggested_action": spec["suggested_action"],
                "priority": spec["priority"],
                "source": "failure_mode",
                "requires_human_review": False,
                "evidence": {
                    "failure_mode": mode_key,
                    "reason": failure_mode.get("reason"),
                    "primary_log": blocking_signals.get("primary_log"),
                    "status_reason": blocking_signals.get("status_reason"),
                },
            }
        )

    for check in [
        item for item in list(runtime_details.get("docker_runtime_checks", []))
        if isinstance(item, dict)
    ] + [
        item for item in list(runtime_details.get("solver_specific_checks", []))
        if isinstance(item, dict)
    ]:
        area = str(check.get("area") or "").strip()
        if not area:
            continue
        add_target(
            {
                "target_id": area,
                "target_kind": "runtime_check_target",
                "scope": area,
                "path_hints": list(fallback_paths.get(area, [])),
                "suggested_action": "inspect_and_reconcile_runtime_target",
                "priority": "medium",
                "source": "check_area",
                "requires_human_review": False,
                "evidence": {
                    "trigger": check.get("trigger"),
                    "instruction": check.get("instruction"),
                    "primary_log": blocking_signals.get("primary_log"),
                },
            }
        )

    return targets


def _solver_parameter_target_hints(solver: str) -> dict[str, list[str]]:
    common = {
        "iteration_budget": ["solver iteration budget", "outer iteration limits"],
        "time_step_control": ["time-step or increment controls"],
        "initialization": ["initial field or restart controls"],
        "solver_settings": ["solver tolerances", "iteration limits", "relaxation settings"],
        "residual_history": ["residual history output", "convergence log export"],
        "residual_target": ["residual baseline", "stopping criteria"],
    }
    solver_specific: dict[str, dict[str, list[str]]] = {
        "openfoam": {
            "deltaT_maxCo": ["system/controlDict", "deltaT", "maxCo"],
            "fvSolution_relaxation": ["system/fvSolution", "relaxationFactors", "linear solver tolerances"],
            "mesh_and_boundary_fields": ["0/ boundary fields", "constant/polyMesh", "boundary definitions"],
            "iteration_budget": ["system/controlDict", "endTime or iteration controls"],
            "time_step_control": ["system/controlDict", "deltaT", "maxCo"],
            "residual_target": ["residual log baseline", "solver stopping criteria"],
        },
        "su2": {
            "cfl_or_time_step": ["primary SU2 cfg", "CFL controls", "pseudo-time-step settings"],
            "linear_solver": ["primary SU2 cfg", "linear solver and preconditioner settings"],
            "marker_and_mesh_consistency": ["primary SU2 cfg", "mesh boundary markers"],
            "iteration_budget": ["primary SU2 cfg", "outer iteration budget"],
            "time_step_control": ["primary SU2 cfg", "time-step/CFL controls"],
            "initialization": ["primary SU2 cfg", "restart / initial-field settings"],
            "residual_target": ["history.csv baseline", "residual stopping criteria"],
        },
        "elmer": {
            "linear_system_controls": [".sif Solver sections", "Linear System settings"],
            "nonlinear_system_controls": [".sif Solver sections", "Nonlinear System settings"],
            "timestep_or_steady_controls": [".sif Simulation section", "steady/transient controls"],
            "iteration_budget": [".sif Solver sections", "iteration limits"],
            "time_step_control": [".sif Simulation section", "timestep sizes / intervals"],
            "initialization": [".sif initial condition blocks", "restart settings"],
            "residual_target": ["residual log baseline", "Solver convergence thresholds"],
        },
        "code_aster": {
            "newton_increment_control": [".comm nonlinear solve block", "Newton and increment settings"],
            "line_search_or_contact": [".comm contact blocks", "line-search or constitutive settings"],
            "time_step_refinement": [".comm time increment list", "increment refinement controls"],
            "iteration_budget": [".comm nonlinear iteration limits"],
            "time_step_control": [".comm increment controls", "time-step list"],
            "initialization": [".comm initial state or restart blocks"],
            "residual_target": ["residual log baseline", "convergence stopping criteria"],
        },
    }
    merged = dict(common)
    merged.update(solver_specific.get(solver, {}))
    return merged


def _convergence_target_bounded_edit_scopes(
    solver: str,
    parameter_area: str,
    path_hints: list[str],
    change_strategy: str,
) -> list[dict[str, Any]]:
    common: dict[str, list[dict[str, Any]]] = {
        "iteration_budget": [
            {
                "scope_id": "generic_iteration_budget",
                "path_hint": "solver iteration budget",
                "block_hints": ["outer iteration limits", "iteration stop criteria"],
                "parameter_hints": ["iteration budget"],
                "allowed_actions": ["inspect", "increase_single_limit"],
                "change_guard": "Increase only one iteration-related limit at a time and keep the previous baseline.",
            }
        ],
        "time_step_control": [
            {
                "scope_id": "generic_time_step_control",
                "path_hint": "time-step or increment controls",
                "block_hints": ["time-step size", "step limiter"],
                "parameter_hints": ["time-step"],
                "allowed_actions": ["inspect", "reduce_time_step_aggressiveness"],
                "change_guard": "Reduce aggressiveness in one bounded step before touching other solver controls.",
            }
        ],
        "initialization": [
            {
                "scope_id": "generic_initialization",
                "path_hint": "initial field or restart controls",
                "block_hints": ["restart source", "initial conditions"],
                "parameter_hints": ["restart or initial field"],
                "allowed_actions": ["inspect", "reconcile_restart_or_initial_fields"],
                "change_guard": "Only reconcile restart or initialization inputs after preserving the current baseline.",
            }
        ],
        "solver_settings": [
            {
                "scope_id": "generic_solver_settings",
                "path_hint": "solver tolerances",
                "block_hints": ["tolerance", "iteration limit", "relaxation"],
                "parameter_hints": ["solver tolerance", "relaxation"],
                "allowed_actions": ["inspect", "tune_single_solver_control"],
                "change_guard": "Adjust one solver-control family at a time and preserve the baseline settings.",
            }
        ],
        "residual_history": [
            {
                "scope_id": "generic_residual_history",
                "path_hint": "residual history output",
                "block_hints": ["history export", "residual logging"],
                "parameter_hints": ["history export"],
                "allowed_actions": ["inspect", "record_baseline"],
                "change_guard": "Do not change solver numerics when only the residual baseline/export is missing.",
            }
        ],
        "residual_target": [
            {
                "scope_id": "generic_residual_target",
                "path_hint": "stopping criteria",
                "block_hints": ["residual threshold", "stop criteria"],
                "parameter_hints": ["residual threshold"],
                "allowed_actions": ["inspect", "record_baseline", "tighten_residual_target"],
                "change_guard": "Only tighten stopping criteria after the residual trend is stable enough to compare.",
            }
        ],
    }
    solver_specific: dict[str, dict[str, list[dict[str, Any]]]] = {
        "openfoam": {
            "deltaT_maxCo": [
                {
                    "scope_id": "openfoam_control_dict_courant",
                    "path_hint": "system/controlDict",
                    "block_hints": ["deltaT", "maxCo", "adjustTimeStep"],
                    "parameter_hints": ["deltaT", "maxCo"],
                    "allowed_actions": ["inspect", "decrease_deltaT", "decrease_maxCo"],
                    "change_guard": "Change only one time-step aggressiveness control per pass so the effect stays attributable.",
                }
            ],
            "fvSolution_relaxation": [
                {
                    "scope_id": "openfoam_fvsolution_solver_controls",
                    "path_hint": "system/fvSolution",
                    "block_hints": ["solvers", "PIMPLE/PISO/SIMPLE", "relaxationFactors"],
                    "parameter_hints": ["tolerance", "relTol", "relaxationFactors"],
                    "allowed_actions": ["inspect", "tighten_solver_tolerance", "reduce_relaxation"],
                    "change_guard": "Adjust one solver-control family at a time before rerunning the case.",
                }
            ],
            "mesh_and_boundary_fields": [
                {
                    "scope_id": "openfoam_mesh_boundary_review",
                    "path_hint": "0/ boundary fields",
                    "block_hints": ["patch entries", "field coverage"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect"],
                    "change_guard": "Treat mesh or boundary mismatches as review-before-edit, not as blind numeric tuning.",
                }
            ],
            "iteration_budget": [
                {
                    "scope_id": "openfoam_runtime_window",
                    "path_hint": "system/controlDict",
                    "block_hints": ["endTime", "deltaT", "writeInterval"],
                    "parameter_hints": ["endTime"],
                    "allowed_actions": ["inspect", "extend_iteration_window"],
                    "change_guard": "Only extend the runtime window after preserving the previous stop condition baseline.",
                }
            ],
            "residual_target": [
                {
                    "scope_id": "openfoam_residual_control",
                    "path_hint": "system/fvSolution",
                    "block_hints": ["residualControl"],
                    "parameter_hints": ["residualControl"],
                    "allowed_actions": ["inspect", "record_baseline", "tighten_residual_target"],
                    "change_guard": "Only tighten residual targets once the trend is consistently improving.",
                }
            ],
        },
        "su2": {
            "cfl_or_time_step": [
                {
                    "scope_id": "su2_cfl_controls",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["CFL_NUMBER", "CFL_ADAPT", "TIME_STEP"],
                    "parameter_hints": ["CFL_NUMBER", "TIME_STEP"],
                    "allowed_actions": ["inspect", "decrease_cfl_growth", "reduce_time_step_aggressiveness"],
                    "change_guard": "Reduce CFL or time-step aggressiveness in one bounded step so the next pass stays interpretable.",
                }
            ],
            "linear_solver": [
                {
                    "scope_id": "su2_linear_solver_controls",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["LINEAR_SOLVER", "LINEAR_SOLVER_PREC", "LINEAR_SOLVER_ERROR"],
                    "parameter_hints": ["LINEAR_SOLVER", "LINEAR_SOLVER_ERROR"],
                    "allowed_actions": ["inspect", "tighten_linear_solver_settings"],
                    "change_guard": "Only tune one linear-solver control family per pass.",
                }
            ],
            "marker_and_mesh_consistency": [
                {
                    "scope_id": "su2_marker_review",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["MARKER_*", "MESH_FILENAME"],
                    "parameter_hints": [],
                    "allowed_actions": ["inspect"],
                    "change_guard": "Review marker and mesh consistency before any numeric tuning or retry.",
                }
            ],
            "iteration_budget": [
                {
                    "scope_id": "su2_iteration_budget",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["EXT_ITER", "INNER_ITER"],
                    "parameter_hints": ["EXT_ITER", "INNER_ITER"],
                    "allowed_actions": ["inspect", "increase_single_limit"],
                    "change_guard": "Increase one SU2 iteration budget control at a time to keep the delta attributable.",
                }
            ],
            "initialization": [
                {
                    "scope_id": "su2_restart_controls",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["RESTART_SOL", "SOLUTION_FILENAME"],
                    "parameter_hints": ["RESTART_SOL"],
                    "allowed_actions": ["inspect", "reconcile_restart_or_initial_fields"],
                    "change_guard": "Only reconcile restart or initialization settings after checking the current sidecars.",
                }
            ],
            "residual_target": [
                {
                    "scope_id": "su2_residual_target",
                    "path_hint": "primary SU2 cfg",
                    "block_hints": ["CONV_RESIDUAL_MINVAL", "CONV_FIELD"],
                    "parameter_hints": ["CONV_RESIDUAL_MINVAL"],
                    "allowed_actions": ["inspect", "record_baseline", "tighten_residual_target"],
                    "change_guard": "Tighten SU2 residual targets only after the history trend is stable enough to compare.",
                }
            ],
        },
    }

    solver_specific.update(
        {
            "elmer": {
                "linear_system_controls": [
                    {
                        "scope_id": "elmer_linear_system_controls",
                        "path_hint": ".sif Solver sections",
                        "block_hints": [
                            "Linear System Solver",
                            "Linear System Max Iterations",
                            "Linear System Convergence Tolerance",
                        ],
                        "parameter_hints": [
                            "Linear System Max Iterations",
                            "Linear System Convergence Tolerance",
                        ],
                        "allowed_actions": ["inspect", "tune_linear_system_limits"],
                        "change_guard": "Only tune one linear-system control family per pass.",
                    }
                ],
                "nonlinear_system_controls": [
                    {
                        "scope_id": "elmer_nonlinear_system_controls",
                        "path_hint": ".sif Solver sections",
                        "block_hints": [
                            "Nonlinear System Max Iterations",
                            "Nonlinear System Convergence Tolerance",
                            "Nonlinear System Relaxation Factor",
                        ],
                        "parameter_hints": [
                            "Nonlinear System Max Iterations",
                            "Nonlinear System Convergence Tolerance",
                        ],
                        "allowed_actions": ["inspect", "tune_nonlinear_system_limits"],
                        "change_guard": "Keep changes inside nonlinear solver controls and vary one control family per pass.",
                    }
                ],
                "timestep_or_steady_controls": [
                    {
                        "scope_id": "elmer_simulation_controls",
                        "path_hint": ".sif Simulation section",
                        "block_hints": ["Simulation Type", "Steady State Max Iterations", "Timestep Sizes"],
                        "parameter_hints": ["Steady State Max Iterations", "Timestep Sizes"],
                        "allowed_actions": ["inspect", "reduce_time_step_aggressiveness"],
                        "change_guard": "Reduce transient or steady-state aggressiveness in one bounded step before broader edits.",
                    }
                ],
            },
            "code_aster": {
                "newton_increment_control": [
                    {
                        "scope_id": "code_aster_newton_increment",
                        "path_hint": ".comm nonlinear solve block",
                        "block_hints": ["NEWTON", "CONVERGENCE", "INCREMENT"],
                        "parameter_hints": ["ITER_GLOB_MAXI", "PAS_MINI"],
                        "allowed_actions": ["inspect", "tighten_newton_or_increment"],
                        "change_guard": "Adjust one Newton or increment control family per pass so the effect is traceable.",
                    }
                ],
                "line_search_or_contact": [
                    {
                        "scope_id": "code_aster_contact_review",
                        "path_hint": ".comm contact blocks",
                        "block_hints": ["RECH_LINEAIRE", "CONTACT"],
                        "parameter_hints": [],
                        "allowed_actions": ["inspect"],
                        "change_guard": "Treat contact or line-search issues as review-before-edit instead of blind numeric tuning.",
                    }
                ],
                "time_step_refinement": [
                    {
                        "scope_id": "code_aster_time_increment_list",
                        "path_hint": ".comm time increment list",
                        "block_hints": ["LIST_INST", "DEFI_LIST_REEL", "SUBD_PAS"],
                        "parameter_hints": ["PAS_MINI", "SUBD_PAS"],
                        "allowed_actions": ["inspect", "refine_time_increment"],
                        "change_guard": "Refine increment controls in one bounded step before touching constitutive choices.",
                    }
                ],
            },
        }
    )
    merged = dict(common)
    merged.update(solver_specific.get(solver, {}))
    scopes = merged.get(parameter_area)
    if scopes is not None:
        return [dict(scope) for scope in scopes]

    allowed_actions = ["inspect"]
    change_guard = "Stay inside the observed convergence issue and change one bounded control family at a time."
    if change_strategy == "increase_limit_gradually":
        allowed_actions = ["inspect", "increase_single_limit"]
        change_guard = "Increase one iteration-related limit at a time and preserve the current baseline."
    elif change_strategy == "reduce_aggressiveness":
        allowed_actions = ["inspect", "reduce_time_step_aggressiveness"]
        change_guard = "Reduce aggressiveness in one bounded step before changing other controls."
    elif change_strategy == "tune_solver_controls":
        allowed_actions = ["inspect", "tune_single_solver_control"]
        change_guard = "Only tune one solver-control family per pass."
    elif change_strategy == "review_restart_or_initial_fields":
        allowed_actions = ["inspect", "reconcile_restart_or_initial_fields"]
        change_guard = "Only reconcile restart or initial-field inputs after preserving the baseline setup."
    elif change_strategy == "capture_or_record_baseline":
        allowed_actions = ["inspect", "record_baseline"]
        change_guard = "Capture the missing baseline first; avoid changing solver numerics in the same pass."
    return _default_bounded_edit_scopes(
        parameter_area,
        path_hints,
        allowed_actions=allowed_actions,
        change_guard=change_guard,
    )


def _collect_bounded_edit_scopes(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        for scope in list(target.get("bounded_edit_scopes", [])):
            if not isinstance(scope, dict):
                continue
            scope_id = str(scope.get("scope_id") or "").strip()
            if not scope_id or scope_id in seen:
                continue
            seen.add(scope_id)
            scopes.append(dict(scope))
    return scopes


def _scope_write_policy(
    *,
    route_kind: str,
    allowed_actions: list[str],
    requires_human_review: bool,
    change_strategy: str | None = None,
) -> str:
    action_set = {str(item).strip() for item in allowed_actions if str(item).strip()}
    if requires_human_review or not action_set or action_set <= {"inspect"}:
        return "inspect_only"
    if route_kind == "runtime":
        if action_set & {"reconcile_output_path", "reconcile_mount_paths", "reconcile_runtime_configuration"}:
            return "runtime_configuration_reconcile"
        if action_set & {
            "copy_missing_sidecars",
            "reconcile_relative_paths",
            "reconcile_export_references",
            "reconcile_sidecar_references",
            "reconcile_cfg_references",
            "reconcile_marker_names",
            "reconcile_sif_references",
            "reconcile_patch_names",
            "reconcile_patch_field_entries",
            "reconcile_dictionary_references",
            "restore_case_layout",
        }:
            return "runtime_input_reconcile"
        return "inspect_only"
    if change_strategy == "review_consistency_before_numeric_changes":
        return "inspect_only"
    if change_strategy == "capture_or_record_baseline":
        return "baseline_capture_only"
    if change_strategy == "review_restart_or_initial_fields":
        return "restart_or_initialization_reconcile"
    return "bounded_numeric_tuning"


def _is_scope_proposal_ready(write_policy: str) -> bool:
    return write_policy in {
        "runtime_configuration_reconcile",
        "runtime_input_reconcile",
        "restart_or_initialization_reconcile",
        "bounded_numeric_tuning",
    }


def _preferred_scope_action(scope: dict[str, Any], write_policy: str) -> str | None:
    actions = [str(item).strip() for item in list(scope.get("allowed_actions", [])) if str(item).strip()]
    action_set = {item for item in actions if item != "inspect"}
    if not action_set:
        return None
    preferred_by_policy = {
        "runtime_configuration_reconcile": [
            "reconcile_mount_paths",
            "reconcile_output_path",
            "reconcile_runtime_configuration",
        ],
        "runtime_input_reconcile": [
            "copy_missing_sidecars",
            "reconcile_relative_paths",
            "reconcile_export_references",
            "reconcile_sidecar_references",
            "reconcile_cfg_references",
            "reconcile_marker_names",
            "reconcile_sif_references",
            "reconcile_patch_names",
            "reconcile_patch_field_entries",
            "reconcile_dictionary_references",
            "restore_case_layout",
        ],
        "restart_or_initialization_reconcile": ["reconcile_restart_or_initial_fields"],
        "bounded_numeric_tuning": [
            "decrease_deltaT",
            "decrease_maxCo",
            "decrease_cfl_growth",
            "reduce_time_step_aggressiveness",
            "tighten_solver_tolerance",
            "reduce_relaxation",
            "tighten_linear_solver_settings",
            "increase_single_limit",
            "extend_iteration_window",
            "tighten_residual_target",
            "tune_linear_system_limits",
            "tune_nonlinear_system_limits",
            "tighten_newton_or_increment",
            "refine_time_increment",
        ],
    }
    for candidate in preferred_by_policy.get(write_policy, []):
        if candidate in action_set:
            return candidate
    return sorted(action_set)[0]


def _candidate_kind_for_write_policy(write_policy: str) -> str:
    mapping = {
        "runtime_configuration_reconcile": "runtime_configuration_candidate",
        "runtime_input_reconcile": "runtime_input_candidate",
        "restart_or_initialization_reconcile": "restart_or_initialization_candidate",
        "bounded_numeric_tuning": "bounded_numeric_tuning_candidate",
    }
    return mapping.get(write_policy, "inspect_only")


def _annotate_scope_write_policies(
    targets: list[dict[str, Any]],
    *,
    route_kind: str,
) -> list[dict[str, Any]]:
    for target in targets:
        requires_human_review = bool(target.get("requires_human_review"))
        change_strategy = str(target.get("change_strategy") or "").strip() or None
        for scope in list(target.get("bounded_edit_scopes", [])):
            if not isinstance(scope, dict):
                continue
            write_policy = _scope_write_policy(
                route_kind=route_kind,
                allowed_actions=list(scope.get("allowed_actions", [])),
                requires_human_review=requires_human_review,
                change_strategy=change_strategy,
            )
            scope["write_policy"] = write_policy
            scope["proposal_ready"] = _is_scope_proposal_ready(write_policy)
    return targets


def _build_write_policy_summary(scopes: list[dict[str, Any]]) -> dict[str, Any]:
    policy_counts: dict[str, int] = {}
    proposal_ready_count = 0
    for scope in scopes:
        policy = str(scope.get("write_policy") or "inspect_only")
        policy_counts[policy] = int(policy_counts.get(policy, 0)) + 1
        if bool(scope.get("proposal_ready")):
            proposal_ready_count += 1
    return {
        "policy_counts": policy_counts,
        "proposal_ready_count": proposal_ready_count,
        "read_first_scope_count": int(policy_counts.get("inspect_only", 0))
        + int(policy_counts.get("baseline_capture_only", 0)),
    }


def _build_controlled_edit_candidates(
    targets: list[dict[str, Any]],
    *,
    route_kind: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        target_id = str(target.get("target_id") or "").strip()
        change_strategy = str(target.get("change_strategy") or "").strip() or None
        evidence = target.get("evidence") if isinstance(target.get("evidence"), dict) else {}
        for scope in list(target.get("bounded_edit_scopes", [])):
            if not isinstance(scope, dict):
                continue
            write_policy = str(scope.get("write_policy") or "inspect_only")
            if not bool(scope.get("proposal_ready")):
                continue
            scope_id = str(scope.get("scope_id") or "").strip()
            proposed_action = _preferred_scope_action(scope, write_policy)
            if not target_id or not scope_id or not proposed_action:
                continue
            candidate_id = f"{route_kind}:{target_id}:{scope_id}:{proposed_action}"
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_kind": _candidate_kind_for_write_policy(write_policy),
                    "target_id": target_id,
                    "scope_id": scope_id,
                    "write_policy": write_policy,
                    "proposed_action": proposed_action,
                    "path_hint": scope.get("path_hint"),
                    "block_hints": list(scope.get("block_hints", [])),
                    "parameter_hints": list(scope.get("parameter_hints", [])),
                    "change_guard": scope.get("change_guard"),
                    "requires_human_review": bool(target.get("requires_human_review")),
                    "source": target.get("source"),
                    "change_strategy": change_strategy,
                    "evidence": {
                        "trigger": evidence.get("trigger"),
                        "failure_mode": evidence.get("failure_mode"),
                        "reason": evidence.get("reason"),
                        "primary_log": evidence.get("primary_log"),
                    },
                }
            )
    return candidates


def _placeholder_target(label: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return f"<{token or 'target'}>"


def _candidate_file_targets(path_hint: str) -> list[str]:
    normalized = str(path_hint or "").strip()
    explicit_map = {
        "system/controlDict": ["system/controlDict"],
        "system/fvSolution": ["system/fvSolution"],
        "constant/polyMesh/boundary": ["constant/polyMesh/boundary"],
        "0/ boundary fields": ["0/*"],
        "0/": ["0/"],
        "constant/": ["constant/"],
        "system/": ["system/"],
        "primary SU2 cfg": ["<primary_su2_cfg>"],
        ".export file": ["<case>.export"],
        ".comm file": ["<case>.comm"],
        ".sif file": ["<case>.sif"],
        ".sif Solver sections": ["<case>.sif"],
        ".sif Simulation section": ["<case>.sif"],
        "mesh/restart sidecars": ["<mesh_or_restart_sidecar>"],
        "mesh directory": ["<elmer_mesh_dir>"],
        "execution wrapper": ["<runtime_wrapper_config>"],
        "solver launch arguments": ["<runtime_command_config>"],
        "stored image/tag reference": ["<solver_image_reference>"],
        "mounted result directory": ["<results_dir>"],
        "mounted case directory": ["<case_dir>"],
        "case directory mount": ["<case_dir>"],
        "referenced sidecar inputs": ["<referenced_input_sidecars>"],
    }
    if normalized in explicit_map:
        return list(explicit_map[normalized])
    if "/" in normalized or normalized.startswith("."):
        return [normalized]
    return [_placeholder_target(normalized)]


def _runtime_candidate_operations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(candidate.get("proposed_action") or "").strip()
    block_hints = list(candidate.get("block_hints", []))
    selector_hints = block_hints or list(candidate.get("parameter_hints", []))
    action_map: dict[str, list[dict[str, Any]]] = {
        "copy_missing_sidecars": [
            {
                "operation_kind": "copy_declared_sidecars",
                "selector_mode": "declared_missing_only",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_relative_paths": [
            {
                "operation_kind": "rewrite_declared_paths",
                "selector_mode": "relative_path_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_export_references": [
            {
                "operation_kind": "rewrite_declared_paths",
                "selector_mode": "export_reference_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_sidecar_references": [
            {
                "operation_kind": "rewrite_declared_paths",
                "selector_mode": "sidecar_reference_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_cfg_references": [
            {
                "operation_kind": "rewrite_declared_paths",
                "selector_mode": "cfg_reference_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_marker_names": [
            {
                "operation_kind": "rename_declared_symbols",
                "selector_mode": "marker_name_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_sif_references": [
            {
                "operation_kind": "rewrite_declared_paths",
                "selector_mode": "sif_reference_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_patch_names": [
            {
                "operation_kind": "rename_declared_symbols",
                "selector_mode": "patch_name_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_patch_field_entries": [
            {
                "operation_kind": "repair_missing_entries",
                "selector_mode": "patch_field_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_dictionary_references": [
            {
                "operation_kind": "repair_dictionary_references",
                "selector_mode": "dictionary_reference_entries",
                "selector_hints": selector_hints,
            }
        ],
        "restore_case_layout": [
            {
                "operation_kind": "restore_required_layout",
                "selector_mode": "required_case_paths",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_mount_paths": [
            {
                "operation_kind": "normalize_runtime_paths",
                "selector_mode": "mount_path_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_output_path": [
            {
                "operation_kind": "normalize_runtime_paths",
                "selector_mode": "output_path_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_runtime_configuration": [
            {
                "operation_kind": "normalize_runtime_configuration",
                "selector_mode": "runtime_configuration_entries",
                "selector_hints": selector_hints,
            }
        ],
        "reconcile_restart_or_initial_fields": [
            {
                "operation_kind": "switch_declared_input_source",
                "selector_mode": "restart_or_initial_entries",
                "selector_hints": selector_hints,
            }
        ],
    }
    return [dict(item) for item in action_map.get(action, [])]


def _bounded_parameter_operation(
    *,
    parameter: str,
    modifier: str,
    step_policy: str = "single_step",
) -> dict[str, Any]:
    return {
        "operation_kind": "parameter_update",
        "parameter": parameter,
        "modifier": modifier,
        "step_policy": step_policy,
    }


def _numeric_candidate_operations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(candidate.get("proposed_action") or "").strip()
    hints = [str(item).strip() for item in list(candidate.get("parameter_hints", [])) if str(item).strip()]
    primary_hint = hints[0] if hints else "parameter"
    action_map: dict[str, list[dict[str, Any]]] = {
        "decrease_deltaT": [_bounded_parameter_operation(parameter="deltaT", modifier="decrease")],
        "decrease_maxCo": [_bounded_parameter_operation(parameter="maxCo", modifier="decrease")],
        "decrease_cfl_growth": [_bounded_parameter_operation(parameter="CFL_NUMBER", modifier="decrease")],
        "reduce_time_step_aggressiveness": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="decrease")
        ],
        "tighten_solver_tolerance": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="tighten")
        ],
        "reduce_relaxation": [
            _bounded_parameter_operation(parameter="relaxationFactors", modifier="decrease")
        ],
        "tighten_linear_solver_settings": [
            _bounded_parameter_operation(parameter="LINEAR_SOLVER_ERROR", modifier="tighten")
        ],
        "increase_single_limit": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="increase")
        ],
        "extend_iteration_window": [
            _bounded_parameter_operation(parameter="endTime", modifier="increase")
        ],
        "tighten_residual_target": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="tighten")
        ],
        "tune_linear_system_limits": [
            _bounded_parameter_operation(parameter="Linear System Max Iterations", modifier="increase")
        ],
        "tune_nonlinear_system_limits": [
            _bounded_parameter_operation(parameter="Nonlinear System Max Iterations", modifier="increase")
        ],
        "tighten_newton_or_increment": [
            _bounded_parameter_operation(parameter="ITER_GLOB_MAXI", modifier="increase")
        ],
        "refine_time_increment": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="decrease")
        ],
        "tune_single_solver_control": [
            _bounded_parameter_operation(parameter=primary_hint, modifier="adjust")
        ],
    }
    return [dict(item) for item in action_map.get(action, [])]


def _edit_payload_executor_kind(write_policy: str) -> str:
    mapping = {
        "runtime_configuration_reconcile": "runtime_configuration_patch",
        "runtime_input_reconcile": "runtime_input_patch",
        "restart_or_initialization_reconcile": "restart_or_initialization_patch",
        "bounded_numeric_tuning": "bounded_numeric_parameter_update",
    }
    return mapping.get(write_policy, "inspect_only")


def _edit_payload_preconditions(candidate: dict[str, Any], executor_kind: str) -> list[str]:
    conditions: list[str] = []
    change_guard = str(candidate.get("change_guard") or "").strip()
    if change_guard:
        conditions.append(change_guard)
    if executor_kind == "bounded_numeric_parameter_update":
        conditions.append("Apply only one numeric-control family from this payload before the next pass.")
    elif executor_kind == "runtime_configuration_patch":
        conditions.append("Keep the solver family and selected runtime image unchanged while reconciling runtime paths.")
    elif executor_kind == "runtime_input_patch":
        conditions.append("Limit edits to declared input references or missing sidecars for the current case.")
    elif executor_kind == "restart_or_initialization_patch":
        conditions.append("Preserve the current baseline or restart source before switching initialization inputs.")
    return conditions


def _edit_payload_success_criteria(candidate: dict[str, Any], executor_kind: str) -> list[str]:
    if executor_kind == "bounded_numeric_parameter_update":
        return [
            "Exactly one bounded parameter family was changed.",
            "The next solver pass can compare against the previous residual baseline.",
        ]
    if executor_kind in {
        "runtime_configuration_patch",
        "runtime_input_patch",
        "restart_or_initialization_patch",
    }:
        return [
            "The edited references resolve on the intended runtime surface.",
            "The next solver pass can start without introducing a broader model change.",
        ]
    return ["No write-ready success criteria were recorded."]


def _build_edit_payload_templates(
    controlled_edit_candidates: list[dict[str, Any]],
    *,
    solver: str,
    route_kind: str,
) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in controlled_edit_candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        write_policy = str(candidate.get("write_policy") or "inspect_only")
        executor_kind = _edit_payload_executor_kind(write_policy)
        if not candidate_id or executor_kind == "inspect_only":
            continue
        payload_id = f"payload:{candidate_id}"
        if payload_id in seen:
            continue
        seen.add(payload_id)
        operations = (
            _numeric_candidate_operations(candidate)
            if executor_kind == "bounded_numeric_parameter_update"
            else _runtime_candidate_operations(candidate)
        )
        templates.append(
            {
                "payload_id": payload_id,
                "candidate_id": candidate_id,
                "solver": solver,
                "route_kind": route_kind,
                "executor_kind": executor_kind,
                "write_policy": write_policy,
                "target_files": _candidate_file_targets(str(candidate.get("path_hint") or "")),
                "selector_hints": {
                    "block_hints": list(candidate.get("block_hints", [])),
                    "parameter_hints": list(candidate.get("parameter_hints", [])),
                },
                "operations": operations,
                "preconditions": _edit_payload_preconditions(candidate, executor_kind),
                "success_criteria": _edit_payload_success_criteria(candidate, executor_kind),
                "change_guard": candidate.get("change_guard"),
                "requires_human_review": bool(candidate.get("requires_human_review")),
            }
        )
    return templates


def _edit_execution_artifacts(template: dict[str, Any]) -> list[dict[str, Any]]:
    executor_kind = str(template.get("executor_kind") or "")
    artifacts: list[dict[str, Any]] = []
    for operation in list(template.get("operations", [])):
        if not isinstance(operation, dict):
            continue
        if executor_kind == "bounded_numeric_parameter_update":
            artifacts.append(
                {
                    "artifact_kind": "parameter_update_blueprint",
                    "parameter": operation.get("parameter"),
                    "modifier": operation.get("modifier"),
                    "step_policy": operation.get("step_policy"),
                }
            )
        else:
            artifacts.append(
                {
                    "artifact_kind": "patch_blueprint",
                    "operation_kind": operation.get("operation_kind"),
                    "selector_mode": operation.get("selector_mode"),
                    "selector_hints": list(operation.get("selector_hints", [])),
                    "target_files": list(template.get("target_files", [])),
                }
            )
    return artifacts


def _edit_execution_steps(template: dict[str, Any]) -> list[dict[str, Any]]:
    executor_kind = str(template.get("executor_kind") or "")
    target_files = list(template.get("target_files", []))
    steps: list[dict[str, Any]] = []
    operations = [item for item in list(template.get("operations", [])) if isinstance(item, dict)]
    for idx, operation in enumerate(operations, 1):
        if executor_kind == "bounded_numeric_parameter_update":
            parameter = operation.get("parameter")
            modifier = operation.get("modifier")
            steps.append(
                {
                    "step": idx,
                    "step_kind": "parameter_update_preview",
                    "instruction": f"Prepare a single {modifier} update for {parameter}.",
                    "parameter": parameter,
                    "modifier": modifier,
                    "step_policy": operation.get("step_policy"),
                    "target_files": target_files,
                }
            )
        else:
            steps.append(
                {
                    "step": idx,
                    "step_kind": "structured_patch_preview",
                    "instruction": (
                        f"Prepare a scoped patch for {', '.join(target_files) or 'the selected file surface'} "
                        f"using {operation.get('operation_kind')}."
                    ),
                    "operation_kind": operation.get("operation_kind"),
                    "selector_mode": operation.get("selector_mode"),
                    "selector_hints": list(operation.get("selector_hints", [])),
                    "target_files": target_files,
                }
            )
    return steps


def _edit_execution_verification_checks(template: dict[str, Any]) -> list[str]:
    executor_kind = str(template.get("executor_kind") or "")
    checks = [
        "Confirm the plan touches only the declared target files.",
        "Confirm the plan stays inside the recorded change guard.",
    ]
    if executor_kind == "bounded_numeric_parameter_update":
        checks.extend(
            [
                "Confirm only one bounded parameter family is updated in this plan.",
                "Capture a before/after baseline so the next residual trend remains comparable.",
            ]
        )
    else:
        checks.extend(
            [
                "Confirm only declared references or scoped config blocks are changed.",
                "Confirm the resulting runtime surface can be retried without broader model edits.",
            ]
        )
    return checks


def _edit_execution_non_goals(template: dict[str, Any]) -> list[str]:
    executor_kind = str(template.get("executor_kind") or "")
    common = [
        "Do not touch unrelated files outside the declared target surface.",
        "Do not mix multiple independent edit families into one deterministic pass.",
    ]
    if executor_kind == "bounded_numeric_parameter_update":
        common.append("Do not change mesh, boundary naming, or physical model assumptions in this plan.")
    else:
        common.append("Do not introduce broad physics or constitutive changes while resolving runtime setup issues.")
    return common


def _build_edit_execution_plans(
    edit_payload_templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    seen: set[str] = set()
    for template in edit_payload_templates:
        payload_id = str(template.get("payload_id") or "").strip()
        if not payload_id:
            continue
        plan_id = f"plan:{payload_id}"
        if plan_id in seen:
            continue
        seen.add(plan_id)
        plans.append(
            {
                "plan_id": plan_id,
                "payload_id": payload_id,
                "solver": template.get("solver"),
                "route_kind": template.get("route_kind"),
                "executor_kind": template.get("executor_kind"),
                "preview_only": True,
                "touches_unrelated_files": False,
                "target_files": list(template.get("target_files", [])),
                "steps": _edit_execution_steps(template),
                "artifacts": _edit_execution_artifacts(template),
                "preconditions": list(template.get("preconditions", [])),
                "verification_checks": _edit_execution_verification_checks(template),
                "success_criteria": list(template.get("success_criteria", [])),
                "non_goals": _edit_execution_non_goals(template),
                "change_guard": template.get("change_guard"),
                "requires_human_review": bool(template.get("requires_human_review")),
            }
        )
    return plans


def _parameter_change_strategy(parameter_area: str) -> str:
    if parameter_area in {"iteration_budget"}:
        return "increase_limit_gradually"
    if parameter_area in {"time_step_control", "cfl_or_time_step", "time_step_refinement"}:
        return "reduce_aggressiveness"
    if parameter_area in {
        "solver_settings",
        "linear_solver",
        "linear_system_controls",
        "nonlinear_system_controls",
        "newton_increment_control",
        "fvSolution_relaxation",
    }:
        return "tune_solver_controls"
    if parameter_area in {"initialization"}:
        return "review_restart_or_initial_fields"
    if parameter_area in {
        "marker_and_mesh_consistency",
        "mesh_and_boundary_fields",
        "line_search_or_contact",
        "timestep_or_steady_controls",
    }:
        return "review_consistency_before_numeric_changes"
    if parameter_area in {"residual_history", "residual_target"}:
        return "capture_or_record_baseline"
    return "review_and_tune"


def _build_convergence_edit_targets(
    route_data: dict[str, Any],
    convergence_details: dict[str, Any],
    convergence_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    solver = str(route_data.get("solver") or "unknown")
    hints_map = _solver_parameter_target_hints(solver)
    residual_trends = (
        convergence_summary.get("residual_trend_counts")
        if isinstance(convergence_summary.get("residual_trend_counts"), dict)
        else {}
    )
    suggestion_groups = [
        ("parameter_suggestion", list(convergence_details.get("parameter_suggestions", []))),
        ("solver_specific_suggestion", list(convergence_details.get("solver_specific_suggestions", []))),
    ]
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source, items in suggestion_groups:
        for item in items:
            if not isinstance(item, dict):
                continue
            parameter_area = str(item.get("parameter_area") or "").strip()
            if not parameter_area or parameter_area in seen:
                continue
            seen.add(parameter_area)
            targets.append(
                {
                    "target_id": parameter_area,
                    "target_kind": "solver_parameter_target",
                    "scope": parameter_area,
                    "path_hints": list(hints_map.get(parameter_area, [])),
                    "change_strategy": _parameter_change_strategy(parameter_area),
                    "priority": (
                        "low"
                        if parameter_area in {"residual_history", "residual_target"}
                        else "high" if source == "solver_specific_suggestion" else "medium"
                    ),
                    "source": source,
                    "requires_human_review": parameter_area in {"marker_and_mesh_consistency", "mesh_and_boundary_fields", "line_search_or_contact"},
                    "evidence": {
                        "trigger": item.get("trigger"),
                        "suggestion": item.get("suggestion"),
                        "max_iterations": convergence_summary.get("max_iterations"),
                        "worst_final_residual": convergence_summary.get("worst_final_residual"),
                        "residual_trend_counts": residual_trends,
                    },
                    "bounded_edit_scopes": _convergence_target_bounded_edit_scopes(
                        solver,
                        parameter_area,
                        list(hints_map.get(parameter_area, [])),
                        _parameter_change_strategy(parameter_area),
                    ),
                }
            )
    return targets


def _build_runtime_remediation_prompt_payload(route_data: dict[str, Any]) -> dict[str, Any]:
    runtime_details = _build_runtime_retry_checks(route_data)
    solver = str(route_data.get("solver") or "unknown")
    blocking_signals = runtime_details.get("blocking_signals") if isinstance(runtime_details.get("blocking_signals"), dict) else {}
    suspected_modes = runtime_details.get("suspected_failure_modes") if isinstance(runtime_details.get("suspected_failure_modes"), list) else []
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    solver_run_branch = _infer_solver_run_branch(route_data, solver_run_snapshot)
    remediation_targets = _build_runtime_remediation_targets(route_data, runtime_details)
    remediation_targets = _annotate_scope_write_policies(remediation_targets, route_kind="runtime")
    bounded_edit_scopes = _collect_bounded_edit_scopes(remediation_targets)
    write_policy_summary = _build_write_policy_summary(bounded_edit_scopes)
    controlled_edit_candidates = _build_controlled_edit_candidates(
        remediation_targets,
        route_kind="runtime",
    )
    edit_payload_templates = _build_edit_payload_templates(
        controlled_edit_candidates,
        solver=solver,
        route_kind="runtime",
    )
    edit_execution_plans = _build_edit_execution_plans(edit_payload_templates)
    prompt_lines = [
        "You are preparing the next runtime-remediation pass for a CAE solver run.",
        f"Solver family: {solver}",
        f"Solver status: {route_data.get('solver_status')}",
        f"Recommended next action: {route_data.get('recommended_next_action')}",
        f"Runtime focus: {_solver_runtime_prompt_focus(solver)}",
        f"Primary log: {blocking_signals.get('primary_log')}",
        f"Status reason: {blocking_signals.get('status_reason')}",
        "Solver-run evidence preview:",
        *_render_solver_run_preview_lines(solver_run_snapshot),
        "Solver-run branch:",
        *_render_solver_run_branch_lines(solver_run_branch),
        "Use the structured checks below and stay inside runtime remediation until the failure path is concrete.",
        "Pre-retry checklist:",
        *(_render_prompt_items(list(runtime_details.get("pre_retry_checks", [])), primary_key="check", secondary_key="instruction") or ["- None recorded."]),
        "Docker/runtime checks:",
        *(_render_prompt_items(list(runtime_details.get("docker_runtime_checks", [])), primary_key="area", secondary_key="instruction") or ["- No Docker-specific checks recorded."]),
        "Solver-specific runtime checks:",
        *(_render_prompt_items(list(runtime_details.get("solver_specific_checks", [])), primary_key="area", secondary_key="instruction") or ["- No solver-specific checks recorded."]),
        "Suspected failure modes:",
        *(_render_prompt_items(list(suspected_modes), primary_key="mode", secondary_key="reason") or ["- No concrete failure mode inferred yet."]),
        "Machine-stable remediation targets:",
        *(_render_prompt_items(list(remediation_targets), primary_key="target_id", secondary_key="suggested_action") or ["- No remediation targets recorded."]),
        "Bounded file/block scopes:",
        *(_render_prompt_items(list(bounded_edit_scopes), primary_key="scope_id", secondary_key="path_hint") or ["- No bounded edit scopes recorded."]),
        "Write-policy summary:",
        *(_render_prompt_items(
            [{"policy": key, "count": value} for key, value in sorted(write_policy_summary.get("policy_counts", {}).items())],
            primary_key="policy",
            secondary_key="count",
        ) or ["- No write policies recorded."]),
        "Controlled edit candidates:",
        *(_render_prompt_items(list(controlled_edit_candidates), primary_key="candidate_id", secondary_key="proposed_action") or ["- No controlled edit candidates are proposal-ready yet."]),
        "Edit payload templates:",
        *(_render_prompt_items(list(edit_payload_templates), primary_key="payload_id", secondary_key="executor_kind") or ["- No edit payload templates were prepared."]),
        "Edit execution plans:",
        *(_render_prompt_items(list(edit_execution_plans), primary_key="plan_id", secondary_key="executor_kind") or ["- No edit execution plans were prepared."]),
        "Return format:",
        "1. Primary failure hypothesis tied to the current evidence.",
        "2. Ordered inspection/remediation steps for the next retry.",
        "3. Exact files, directories, or config blocks to inspect.",
        "4. Controlled edit candidates that remain inside the current write policy.",
        "5. Edit payload templates prepared for the next deterministic pass.",
        "6. Edit execution plans that stay preview-only and scoped to one deterministic pass.",
        "7. Bounded scopes or runtime config surfaces allowed for the next pass.",
        "8. Retry gate: what must be true before rerunning the solver.",
    ]
    return {
        **runtime_details,
        "agent_focus": "runtime_remediation",
        "solver_run": solver_run_snapshot,
        "solver_run_branch": solver_run_branch,
        "output_contract": [
            "primary_failure_hypothesis",
            "ordered_runtime_remediation_steps",
            "inspection_targets",
            "remediation_targets",
            "bounded_edit_scopes",
            "write_policy_summary",
            "controlled_edit_candidates",
            "edit_payload_templates",
            "edit_execution_plans",
            "retry_gate",
        ],
        "remediation_targets": remediation_targets,
        "bounded_edit_scopes": bounded_edit_scopes,
        "write_policy_summary": write_policy_summary,
        "controlled_edit_candidates": controlled_edit_candidates,
        "edit_payload_templates": edit_payload_templates,
        "edit_execution_plans": edit_execution_plans,
        "prompt": "\n".join(prompt_lines),
    }


def _build_convergence_tuning_prompt_payload(route_data: dict[str, Any]) -> dict[str, Any]:
    convergence_details = _build_convergence_parameter_suggestions(route_data)
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    convergence_summary = (
        followup.get("convergence_summary")
        if isinstance(followup.get("convergence_summary"), dict)
        else {}
    )
    solver = str(route_data.get("solver") or "unknown")
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    solver_run_branch = _infer_solver_run_branch(route_data, solver_run_snapshot)
    tuning_hint_lines = [f"- {item}" for item in list(convergence_details.get("tuning_hints", []))]
    edit_targets = _build_convergence_edit_targets(route_data, convergence_details, convergence_summary)
    edit_targets = _annotate_scope_write_policies(edit_targets, route_kind="convergence")
    bounded_edit_scopes = _collect_bounded_edit_scopes(edit_targets)
    write_policy_summary = _build_write_policy_summary(bounded_edit_scopes)
    controlled_edit_candidates = _build_controlled_edit_candidates(
        edit_targets,
        route_kind="convergence",
    )
    edit_payload_templates = _build_edit_payload_templates(
        controlled_edit_candidates,
        solver=solver,
        route_kind="convergence",
    )
    edit_execution_plans = _build_edit_execution_plans(edit_payload_templates)
    prompt_lines = [
        "You are preparing the next convergence-tuning pass for a CAE solver run.",
        f"Solver family: {solver}",
        f"Solver status: {route_data.get('solver_status')}",
        f"Recommended next action: {route_data.get('recommended_next_action')}",
        f"Convergence focus: {_solver_convergence_prompt_focus(solver)}",
        f"Max iterations seen: {convergence_summary.get('max_iterations')}",
        f"Worst final residual: {convergence_summary.get('worst_final_residual')}",
        f"Residual trend counts: {convergence_summary.get('residual_trend_counts')}",
        "Solver-run evidence preview:",
        *_render_solver_run_preview_lines(solver_run_snapshot),
        "Solver-run branch:",
        *_render_solver_run_branch_lines(solver_run_branch),
        "Use the structured suggestions below and keep the response grounded in numerical controls first.",
        "Generic parameter suggestions:",
        *(_render_prompt_items(list(convergence_details.get("parameter_suggestions", [])), primary_key="parameter_area", secondary_key="suggestion") or ["- No generic suggestions recorded."]),
        "Solver-specific tuning suggestions:",
        *(_render_prompt_items(list(convergence_details.get("solver_specific_suggestions", [])), primary_key="parameter_area", secondary_key="suggestion") or ["- No solver-specific suggestions recorded."]),
        "Existing tuning hints:",
        *(tuning_hint_lines or ["- No tuning hints recorded."]),
        "Machine-stable edit targets:",
        *(_render_prompt_items(list(edit_targets), primary_key="target_id", secondary_key="change_strategy") or ["- No edit targets recorded."]),
        "Bounded file/block scopes:",
        *(_render_prompt_items(list(bounded_edit_scopes), primary_key="scope_id", secondary_key="path_hint") or ["- No bounded edit scopes recorded."]),
        "Write-policy summary:",
        *(_render_prompt_items(
            [{"policy": key, "count": value} for key, value in sorted(write_policy_summary.get("policy_counts", {}).items())],
            primary_key="policy",
            secondary_key="count",
        ) or ["- No write policies recorded."]),
        "Controlled edit candidates:",
        *(_render_prompt_items(list(controlled_edit_candidates), primary_key="candidate_id", secondary_key="proposed_action") or ["- No controlled edit candidates are proposal-ready yet."]),
        "Edit payload templates:",
        *(_render_prompt_items(list(edit_payload_templates), primary_key="payload_id", secondary_key="executor_kind") or ["- No edit payload templates were prepared."]),
        "Edit execution plans:",
        *(_render_prompt_items(list(edit_execution_plans), primary_key="plan_id", secondary_key="executor_kind") or ["- No edit execution plans were prepared."]),
        "Return format:",
        "1. Primary convergence diagnosis tied to the current residual behavior.",
        "2. Ordered parameter changes with smallest-risk options first.",
        "3. Exact solver controls or files to edit next.",
        "4. Controlled edit candidates that stay inside the current tuning policy.",
        "5. Edit payload templates prepared for the next deterministic pass.",
        "6. Edit execution plans that stay preview-only and scoped to one deterministic pass.",
        "7. Bounded scopes allowed for the next tuning pass.",
        "8. Success criteria for the next tuning pass.",
    ]
    return {
        **convergence_details,
        "agent_focus": "convergence_tuning",
        "solver_run": solver_run_snapshot,
        "solver_run_branch": solver_run_branch,
        "convergence_summary": convergence_summary,
        "edit_targets": edit_targets,
        "bounded_edit_scopes": bounded_edit_scopes,
        "write_policy_summary": write_policy_summary,
        "controlled_edit_candidates": controlled_edit_candidates,
        "edit_payload_templates": edit_payload_templates,
        "edit_execution_plans": edit_execution_plans,
        "output_contract": [
            "primary_convergence_diagnosis",
            "ordered_parameter_changes",
            "edit_targets",
            "bounded_edit_scopes",
            "write_policy_summary",
            "controlled_edit_candidates",
            "edit_payload_templates",
            "edit_execution_plans",
            "next_pass_success_criteria",
        ],
        "prompt": "\n".join(prompt_lines),
    }


def _build_physics_interpretation_prompt_payload(route_data: dict[str, Any]) -> dict[str, Any]:
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    solver_run_branch = _infer_solver_run_branch(route_data, solver_run_snapshot)
    artifact_snapshot = (
        followup.get("artifact_snapshot")
        if isinstance(followup.get("artifact_snapshot"), dict)
        else {}
    )
    result_readiness = (
        followup.get("result_readiness")
        if isinstance(followup.get("result_readiness"), dict)
        else {}
    )
    questions = [
        "Are the result magnitudes plausible for the stated loads, materials, and units?",
        "Do the interpreted fields remain consistent with the imposed boundary conditions?",
        "Which artifact or issue most limits confidence in the physical interpretation?",
    ]
    prompt = "\n".join(
        [
            "Interpret the current solver results using grounded evidence only.",
            f"Solver status: {route_data.get('solver_status')}",
            f"Primary log: {artifact_snapshot.get('primary_log')}",
            f"Result files: {artifact_snapshot.get('result_files')}",
            "Solver-run evidence preview:",
            *_render_solver_run_preview_lines(solver_run_snapshot),
            "Solver-run branch:",
            *_render_solver_run_branch_lines(solver_run_branch),
            f"Top issue: {(followup.get('top_issue') or {}).get('message') if isinstance(followup.get('top_issue'), dict) else None}",
            f"First action: {followup.get('first_action')}",
            f"Similar cases: {followup.get('similar_cases')}",
            "Answer these questions:",
            *[f"- {question}" for question in questions],
        ]
    )
    return {
        "solver_run": solver_run_snapshot,
        "solver_run_branch": solver_run_branch,
        "result_readiness": result_readiness,
        "interpretation_questions": questions,
        "prompt": prompt,
        "similar_cases": list(followup.get("similar_cases", [])),
    }


def _build_evidence_collection_plan(route_data: dict[str, Any]) -> dict[str, Any]:
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    solver_run_snapshot = _route_solver_run_snapshot(route_data)
    solver_run_branch = _infer_solver_run_branch(route_data, solver_run_snapshot)
    targets = list(followup.get("next_collection_targets", []))
    steps: list[dict[str, Any]] = []
    for idx, target in enumerate(targets, 1):
        target_key = str(target)
        steps.append(
            {
                "step": idx,
                "target": target_key,
                "instruction": _ROUTE_CHECK_INSTRUCTIONS.get(
                    target_key,
                    f"Collect evidence for {target_key}.",
                ),
                "done_when": _EVIDENCE_DONE_WHEN.get(
                    target_key,
                    f"{target_key} is available in the route context.",
                ),
            }
        )
    return {
        "solver_run": solver_run_snapshot,
        "solver_run_branch": solver_run_branch,
        "classification_gaps": list(followup.get("classification_gaps", [])),
        "collection_steps": steps,
        "evidence_status": dict(followup.get("evidence_status", {})),
        "available_evidence": {
            "has_primary_log": bool(solver_run_snapshot.get("has_primary_log")),
            "text_source_count": solver_run_snapshot.get("text_source_count"),
            "log_file_count": solver_run_snapshot.get("log_file_count"),
            "result_file_count": solver_run_snapshot.get("result_file_count"),
        },
    }


def _normalize_edit_selection_kind(
    selection_id: str,
    selection_kind: str | None,
) -> str:
    normalized = str(selection_kind or "").strip().lower()
    if normalized in {"", "auto"}:
        if selection_id.startswith("payload:"):
            return "payload_template"
        if selection_id.startswith("plan:"):
            return "execution_plan"
        return "auto"
    if normalized in {"payload", "payload_template"}:
        return "payload_template"
    if normalized in {"plan", "execution_plan"}:
        return "execution_plan"
    raise ValueError("selection_kind must be one of: payload_template, execution_plan, or auto")


def _available_edit_selection_ids(details: dict[str, Any]) -> dict[str, list[str]]:
    payload_ids = [
        str(item.get("payload_id"))
        for item in list(details.get("edit_payload_templates", []))
        if isinstance(item, dict) and str(item.get("payload_id") or "").strip()
    ]
    plan_ids = [
        str(item.get("plan_id"))
        for item in list(details.get("edit_execution_plans", []))
        if isinstance(item, dict) and str(item.get("plan_id") or "").strip()
    ]
    return {"payload_ids": payload_ids, "plan_ids": plan_ids}


def _find_edit_payload_template(details: dict[str, Any], payload_id: str) -> dict[str, Any] | None:
    for item in list(details.get("edit_payload_templates", [])):
        if isinstance(item, dict) and str(item.get("payload_id") or "").strip() == payload_id:
            return dict(item)
    return None


def _find_edit_execution_plan(details: dict[str, Any], plan_id: str) -> dict[str, Any] | None:
    for item in list(details.get("edit_execution_plans", [])):
        if isinstance(item, dict) and str(item.get("plan_id") or "").strip() == plan_id:
            return dict(item)
    return None


def _select_edit_template_and_plan(
    details: dict[str, Any],
    *,
    selection_id: str,
    selection_kind: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if selection_kind == "payload_template":
        selected_template = _find_edit_payload_template(details, selection_id)
        if selected_template is None:
            return None, None
        selected_plan_list = _build_edit_execution_plans([selected_template])
        selected_plan = selected_plan_list[0] if selected_plan_list else None
        return selected_template, selected_plan

    if selection_kind == "execution_plan":
        selected_plan = _find_edit_execution_plan(details, selection_id)
        if selected_plan is None:
            return None, None
        payload_id = str(selected_plan.get("payload_id") or "").strip()
        selected_template = _find_edit_payload_template(details, payload_id) if payload_id else None
        return selected_template, selected_plan

    selected_template = _find_edit_payload_template(details, selection_id)
    if selected_template is not None:
        selected_plan_list = _build_edit_execution_plans([selected_template])
        selected_plan = selected_plan_list[0] if selected_plan_list else None
        return selected_template, selected_plan
    selected_plan = _find_edit_execution_plan(details, selection_id)
    if selected_plan is not None:
        payload_id = str(selected_plan.get("payload_id") or "").strip()
        selected_template = _find_edit_payload_template(details, payload_id) if payload_id else None
        return selected_template, selected_plan
    return None, None


def _target_surface_specificity(target: str) -> int:
    normalized = str(target or "").strip()
    if not normalized:
        return 0
    if normalized in {"<case>.export", "<case>.comm", "<case>.sif", "<primary_su2_cfg>"}:
        return 4
    if normalized.startswith("<") and normalized.endswith(">"):
        return 2
    if "*" in normalized or normalized.endswith("/"):
        return 1
    if Path(normalized).suffix:
        return 5
    if "/" in normalized:
        return 3
    return 2


def _plan_preference_score(plan: dict[str, Any]) -> int:
    targets = [str(item).strip() for item in list(plan.get("target_files", [])) if str(item).strip()]
    best_target = max((_target_surface_specificity(target) for target in targets), default=0)
    score = best_target * 10
    if len(targets) == 1:
        score += 3
    if bool(plan.get("preview_only")):
        score += 1
    if bool(plan.get("requires_human_review")):
        score -= 5
    if bool(plan.get("touches_unrelated_files")):
        score -= 10
    return score


def _plan_search_text(plan: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "plan_id",
        "payload_id",
        "solver",
        "route_kind",
        "executor_kind",
        "change_guard",
    ):
        value = plan.get(key)
        if value:
            parts.append(str(value))
    for key in ("target_files", "preconditions", "success_criteria", "non_goals"):
        parts.extend(str(item) for item in list(plan.get(key, [])))
    for step in list(plan.get("steps", [])):
        if isinstance(step, dict):
            parts.extend(str(value) for value in step.values() if value is not None)
            parts.extend(str(item) for item in list(step.get("selector_hints", [])))
            parts.extend(str(item) for item in list(step.get("target_files", [])))
    for artifact in list(plan.get("artifacts", [])):
        if isinstance(artifact, dict):
            parts.extend(str(value) for value in artifact.values() if value is not None)
            parts.extend(str(item) for item in list(artifact.get("selector_hints", [])))
            parts.extend(str(item) for item in list(artifact.get("target_files", [])))
    return " ".join(parts).lower()


def _branch_preference_terms(branch: str) -> list[tuple[str, int]]:
    mapping: dict[str, list[tuple[str, int]]] = {
        "openfoam_case_repair": [
            ("restore_case_layout", 45),
            ("openfoam_case_tree", 35),
            ("required_case_paths", 30),
            ("<case_dir>", 25),
            ("repair_dictionary_references", 22),
            ("system/controldict", 18),
            ("system/fvsolution", 18),
            ("openfoam_dictionary", 16),
        ],
        "missing_runtime_input": [
            ("copy_missing_sidecars", 40),
            ("rewrite_declared_paths", 28),
            ("relative_path_entries", 26),
            ("sidecar", 20),
            ("<referenced_input_sidecars>", 18),
        ],
        "code_aster_export_reconcile": [
            ("export_reference_entries", 42),
            ("<case>.export", 34),
            ("reconcile_export_references", 30),
            (".export", 20),
        ],
        "docker_runtime_recovery": [
            ("runtime_configuration", 32),
            ("mount_path_entries", 28),
            ("runtime_configuration_entries", 28),
            ("<runtime_command_config>", 22),
            ("<solver_image_reference>", 22),
            ("<case_dir>", 18),
        ],
        "su2_cfl_iteration_tuning": [
            ("decrease_cfl_growth", 46),
            ("cfl_number", 42),
            ("cfl_or_time_step", 34),
            ("su2_cfl_controls", 30),
            ("time_step", 20),
            ("ext_iter", 12),
            ("inner_iter", 12),
            ("iteration_budget", 8),
        ],
        "openfoam_time_step_relaxation_tuning": [
            ("decrease_deltat", 42),
            ("decrease_maxco", 40),
            ("relaxationfactors", 34),
            ("system/controldict", 28),
            ("system/fvsolution", 26),
            ("openfoam_control_dict_courant", 24),
        ],
        "calculix_increment_contact_tuning": [
            ("iter_glob_maxi", 35),
            ("refine_time_increment", 30),
            ("contact", 26),
            ("<primary_calculix_inp>", 20),
            (".inp", 12),
        ],
    }
    return mapping.get(branch, [])


def _plan_branch_preference_score(plan: dict[str, Any], solver_run_branch: dict[str, Any]) -> int:
    branch = str(solver_run_branch.get("branch") or "").strip()
    if not branch:
        return 0
    search_text = _plan_search_text(plan)
    return sum(weight for term, weight in _branch_preference_terms(branch) if term in search_text)


def _plan_branch_preference_matches(
    plan: dict[str, Any],
    solver_run_branch: dict[str, Any],
) -> list[dict[str, Any]]:
    branch = str(solver_run_branch.get("branch") or "").strip()
    if not branch:
        return []
    search_text = _plan_search_text(plan)
    return [
        {"term": term, "weight": weight}
        for term, weight in _branch_preference_terms(branch)
        if term in search_text
    ]


def _plan_preference_breakdown(
    plan: dict[str, Any],
    solver_run_branch: dict[str, Any],
) -> dict[str, Any]:
    branch = str(solver_run_branch.get("branch") or "").strip() or None
    branch_matches = _plan_branch_preference_matches(plan, solver_run_branch)
    branch_score = sum(int(item.get("weight", 0) or 0) for item in branch_matches)
    base_score = _plan_preference_score(plan)
    matched_terms = [str(item.get("term") or "") for item in branch_matches if item.get("term")]
    if branch and matched_terms:
        reason = (
            f"Selected because solver_run_branch '{branch}' matched "
            f"{', '.join(matched_terms[:5])}; base plan score was {base_score}."
        )
    elif branch:
        reason = (
            f"Selected by base plan score {base_score}; solver_run_branch '{branch}' "
            "did not match any branch-specific plan terms."
        )
    else:
        reason = f"Selected by base plan score {base_score}; no solver_run_branch was available."
    return {
        "branch": branch,
        "branch_score": branch_score,
        "base_score": base_score,
        "total_score": branch_score + base_score,
        "matched_branch_terms": branch_matches,
        "selection_reason": reason,
    }


def _plan_preference_sort_key(
    plan: dict[str, Any],
    solver_run_branch: dict[str, Any],
) -> tuple[int, int]:
    breakdown = _plan_preference_breakdown(plan, solver_run_branch)
    return int(breakdown.get("branch_score", 0) or 0), int(breakdown.get("base_score", 0) or 0)


def _preferred_edit_execution_plan_id(details: dict[str, Any]) -> str | None:
    plans = [
        dict(item)
        for item in list(details.get("edit_execution_plans", []))
        if isinstance(item, dict) and str(item.get("plan_id") or "").strip()
    ]
    if not plans:
        return None
    solver_run_branch = (
        details.get("solver_run_branch")
        if isinstance(details.get("solver_run_branch"), dict)
        else {}
    )
    preferred = max(
        enumerate(plans),
        key=lambda item: (
            *_plan_preference_sort_key(item[1], solver_run_branch),
            -item[0],
        ),
    )[1]
    return str(preferred.get("plan_id") or "").strip() or None


def _write_readiness_branch(status: str) -> str:
    mapping = {
        "ready_for_write_guard": "guarded_write_candidate",
        "needs_path_resolution": "resolve_declared_targets",
        "needs_selector_review": "inspect_target_surface",
        "needs_surface_review": "narrow_edit_surface",
        "no_execution_plan": "continue_route_analysis",
    }
    return mapping.get(status, "continue_route_analysis")


def _selected_route_execution_flags(status: str) -> dict[str, bool]:
    return {
        "ready_for_write_guard": status == "ready_for_write_guard",
        "needs_path_resolution": status == "needs_path_resolution",
        "needs_selector_review": status == "needs_selector_review",
        "needs_surface_review": status == "needs_surface_review",
        "no_execution_plan": status == "no_execution_plan",
    }


def _build_selected_route_execution(
    route_data: dict[str, Any],
    action_payload: dict[str, Any],
) -> dict[str, Any]:
    solver_run_branch = (
        action_payload.get("solver_run_branch")
        if isinstance(action_payload.get("solver_run_branch"), dict)
        else {}
    )
    preferred_plan_id = _preferred_edit_execution_plan_id(action_payload)
    if not preferred_plan_id:
        status = "no_execution_plan"
        return {
            "available": False,
            "selection_id": None,
            "selection_kind": None,
            "selected_plan_id": None,
            "selected_payload_id": None,
            "executor_kind": None,
            "output_kind": None,
            "preview_kind": None,
            "write_readiness": status,
            "write_guard_passed": False,
            "preferred_agent_branch": _write_readiness_branch(status),
            "status_flags": _selected_route_execution_flags(status),
            "requires_route_tool_refetch": False,
            "selection_reason": "No deterministic edit execution plan was available for this route.",
            "branch_score_breakdown": {
                "branch": solver_run_branch.get("branch"),
                "branch_score": 0,
                "base_score": 0,
                "total_score": 0,
                "matched_branch_terms": [],
            },
            "message": "The selected route does not expose deterministic edit execution plans.",
        }

    selected = _build_selected_edit_execution_details(
        route_data,
        selection_id=preferred_plan_id,
        selection_kind="execution_plan",
    )
    if not bool(selected.get("selection_found")):
        status = "no_execution_plan"
        return {
            "available": False,
            "selection_id": preferred_plan_id,
            "selection_kind": "execution_plan",
            "selected_plan_id": None,
            "selected_payload_id": None,
            "executor_kind": None,
            "output_kind": None,
            "preview_kind": None,
            "write_readiness": status,
            "write_guard_passed": False,
            "preferred_agent_branch": _write_readiness_branch(status),
            "status_flags": _selected_route_execution_flags(status),
            "requires_route_tool_refetch": False,
            "selection_reason": "No deterministic route execution plan could be selected.",
            "branch_score_breakdown": {
                "branch": solver_run_branch.get("branch"),
                "branch_score": 0,
                "base_score": 0,
                "total_score": 0,
                "matched_branch_terms": [],
            },
            "message": selected.get("message") or "No deterministic route execution plan could be selected.",
        }

    selected_template = (
        selected.get("selected_payload_template")
        if isinstance(selected.get("selected_payload_template"), dict)
        else {}
    )
    selected_plan = (
        selected.get("selected_edit_execution_plan")
        if isinstance(selected.get("selected_edit_execution_plan"), dict)
        else {}
    )
    execution_output = (
        selected.get("execution_output")
        if isinstance(selected.get("execution_output"), dict)
        else {}
    )
    rendered_execution_preview = (
        selected.get("rendered_execution_preview")
        if isinstance(selected.get("rendered_execution_preview"), dict)
        else {}
    )
    dry_run_validation = (
        selected.get("dry_run_validation")
        if isinstance(selected.get("dry_run_validation"), dict)
        else {}
    )
    status = str(dry_run_validation.get("status") or "no_execution_plan")
    preference_breakdown = _plan_preference_breakdown(selected_plan, solver_run_branch)
    return {
        "available": True,
        "selection_id": selected.get("selection_id"),
        "selection_kind": selected.get("selection_kind"),
        "selected_plan_id": selected_plan.get("plan_id"),
        "selected_payload_id": selected_template.get("payload_id"),
        "executor_kind": selected_plan.get("executor_kind"),
        "output_kind": execution_output.get("output_kind"),
        "preview_kind": rendered_execution_preview.get("render_kind"),
        "write_readiness": status,
        "write_guard_passed": bool(dry_run_validation.get("write_guard_passed")),
        "preferred_agent_branch": _write_readiness_branch(status),
        "status_flags": _selected_route_execution_flags(status),
        "requires_route_tool_refetch": False,
        "selection_reason": preference_breakdown.get("selection_reason"),
        "branch_score_breakdown": {
            key: value
            for key, value in preference_breakdown.items()
            if key != "selection_reason"
        },
        "execution_output": execution_output,
        "rendered_execution_preview": rendered_execution_preview,
        "dry_run_validation": dry_run_validation,
    }


def _build_route_handoff_summary(
    action_payload: dict[str, Any],
    selected_route_execution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "handoff_kind": "route_execution_summary",
        "route": action_payload.get("actual_route"),
        "action_kind": action_payload.get("action_kind"),
        "selected_execution_available": bool(selected_route_execution.get("available")),
        "selection_id": selected_route_execution.get("selection_id"),
        "selection_kind": selected_route_execution.get("selection_kind"),
        "write_readiness": selected_route_execution.get("write_readiness"),
        "write_guard_passed": bool(selected_route_execution.get("write_guard_passed")),
        "preferred_agent_branch": selected_route_execution.get("preferred_agent_branch"),
        "solver_run_branch": dict(action_payload.get("solver_run_branch", {})),
        "selection_reason": selected_route_execution.get("selection_reason"),
        "branch_score_breakdown": dict(selected_route_execution.get("branch_score_breakdown", {})),
        "status_flags": dict(selected_route_execution.get("status_flags", {})),
        "requires_route_tool_refetch": False,
    }


def _post_route_action_and_goal(branch: str, route: str) -> tuple[str, str]:
    branch_map = {
        "guarded_write_candidate": (
            "Advance the selected preview plan into the guarded write executor.",
            "Carry one bounded edit plan from preview into a guarded single-surface write.",
        ),
        "resolve_declared_targets": (
            "Resolve the declared target files and placeholders before any write attempt.",
            "Turn the selected preview plan into concrete files inside the current results directory.",
        ),
        "inspect_target_surface": (
            "Inspect the target surface and confirm the selector tokens before any write attempt.",
            "Prove the selected patch or parameter update still points at the intended block or field.",
        ),
        "narrow_edit_surface": (
            "Narrow the edit surface until the plan touches only one bounded target surface.",
            "Reduce the selected plan to one guarded file surface inside the current results directory.",
        ),
    }
    if branch in branch_map:
        return branch_map[branch]

    fallback_map = {
        "runtime_remediation": (
            "Continue runtime remediation analysis before selecting a guarded write candidate.",
            "Stabilize the current runtime lane before attempting deterministic edits.",
        ),
        "convergence_tuning": (
            "Continue convergence tuning analysis before selecting a guarded write candidate.",
            "Tighten the current convergence lane before attempting deterministic edits.",
        ),
        "physics_diagnosis": (
            "Continue grounded physics interpretation for the selected route.",
            "Use the current result evidence to refine physical interpretation before edit planning.",
        ),
        "evidence_expansion": (
            "Continue evidence collection for the selected route.",
            "Collect the missing runtime and artifact evidence before proposing deterministic edits.",
        ),
    }
    return fallback_map.get(
        route,
        (
            "Continue route-specific analysis before attempting deterministic edits.",
            "Keep the current route grounded before escalating into edits or broader diagnosis actions.",
        ),
    )


def _post_route_step_details(selected_route_execution: dict[str, Any]) -> dict[str, Any]:
    status = str(selected_route_execution.get("write_readiness") or "no_execution_plan")
    dry_run_validation = (
        selected_route_execution.get("dry_run_validation")
        if isinstance(selected_route_execution.get("dry_run_validation"), dict)
        else {}
    )
    target_file_checks = [
        item
        for item in list(dry_run_validation.get("target_file_checks", []))
        if isinstance(item, dict)
    ]
    selector_checks = [
        item
        for item in list(dry_run_validation.get("selector_checks", []))
        if isinstance(item, dict)
    ]
    single_surface_check = (
        dry_run_validation.get("single_surface_check")
        if isinstance(dry_run_validation.get("single_surface_check"), dict)
        else {}
    )
    execution_output = (
        selected_route_execution.get("execution_output")
        if isinstance(selected_route_execution.get("execution_output"), dict)
        else {}
    )
    if status == "needs_path_resolution":
        unresolved_targets = [
            str(item.get("declared_target") or "")
            for item in target_file_checks
            if item.get("resolution_status") in {"unresolved_placeholder", "missing_relative"}
            and str(item.get("declared_target") or "").strip()
        ]
        return {
            "unresolved_targets": _limit_items(unresolved_targets, limit=5),
            "target_check_count": len(target_file_checks),
        }
    if status == "needs_selector_review":
        unresolved_selectors = [
            str(item.get("selector_scope") or "")
            for item in selector_checks
            if item.get("status") in {"unmatched", "no_existing_file"}
            and str(item.get("selector_scope") or "").strip()
        ]
        return {
            "unresolved_selectors": _limit_items(unresolved_selectors, limit=5),
            "selector_check_count": len(selector_checks),
        }
    if status == "needs_surface_review":
        return {
            "resolved_target_count": single_surface_check.get("resolved_target_count"),
            "touches_unrelated_files": bool(
                single_surface_check.get("preview_touches_unrelated_files")
            ),
            "all_resolved_targets_within_results_root": single_surface_check.get(
                "all_resolved_targets_within_results_root"
            ),
        }
    if status == "ready_for_write_guard":
        verified_target_files = [
            str(item.get("matched_path") or "")
            for item in target_file_checks
            if str(item.get("matched_path") or "").strip()
        ]
        return {
            "verified_target_files": _limit_items(verified_target_files, limit=5),
            "verification_check_count": len(
                list(execution_output.get("verification_checks", []))
            ),
        }
    return {
        "selected_execution_available": bool(selected_route_execution.get("available")),
    }


def _build_post_route_step(
    action_payload: dict[str, Any],
    selected_route_execution: dict[str, Any],
) -> dict[str, Any]:
    route = str(action_payload.get("actual_route") or action_payload.get("expected_route") or "unknown")
    branch = str(
        selected_route_execution.get("preferred_agent_branch")
        or "continue_route_analysis"
    )
    action, goal = _post_route_action_and_goal(branch, route)
    return {
        "kind": "route_post_action",
        "route": route,
        "action_kind": action_payload.get("action_kind"),
        "branch": branch,
        "write_readiness": selected_route_execution.get("write_readiness"),
        "selection_id": selected_route_execution.get("selection_id"),
        "selection_kind": selected_route_execution.get("selection_kind"),
        "executor_kind": selected_route_execution.get("executor_kind"),
        "preview_kind": selected_route_execution.get("preview_kind"),
        "solver_run_branch": dict(action_payload.get("solver_run_branch", {})),
        "selection_reason": selected_route_execution.get("selection_reason"),
        "branch_score_breakdown": dict(selected_route_execution.get("branch_score_breakdown", {})),
        "selected_execution_available": bool(selected_route_execution.get("available")),
        "write_guard_passed": bool(selected_route_execution.get("write_guard_passed")),
        "action": action,
        "goal": goal,
        "details": _post_route_step_details(selected_route_execution),
    }


def _build_exact_execution_output(selected_plan: dict[str, Any]) -> dict[str, Any]:
    executor_kind = str(selected_plan.get("executor_kind") or "")
    base = {
        "output_kind": (
            "parameter_change_plan"
            if executor_kind == "bounded_numeric_parameter_update"
            else "structured_patch_plan"
        ),
        "preview_only": bool(selected_plan.get("preview_only")),
        "executor_kind": executor_kind,
        "target_files": list(selected_plan.get("target_files", [])),
        "verification_checks": list(selected_plan.get("verification_checks", [])),
        "success_criteria": list(selected_plan.get("success_criteria", [])),
        "non_goals": list(selected_plan.get("non_goals", [])),
        "change_guard": selected_plan.get("change_guard"),
    }
    if executor_kind == "bounded_numeric_parameter_update":
        parameter_updates = []
        for artifact in list(selected_plan.get("artifacts", [])):
            if not isinstance(artifact, dict) or artifact.get("artifact_kind") != "parameter_update_blueprint":
                continue
            parameter_updates.append(
                {
                    "target_files": list(base["target_files"]),
                    "parameter": artifact.get("parameter"),
                    "modifier": artifact.get("modifier"),
                    "step_policy": artifact.get("step_policy"),
                    "value_policy": "bounded_single_adjustment",
                }
            )
        base["parameter_updates"] = parameter_updates
        return base

    patch_operations = []
    for artifact in list(selected_plan.get("artifacts", [])):
        if not isinstance(artifact, dict) or artifact.get("artifact_kind") != "patch_blueprint":
            continue
        patch_operations.append(
            {
                "target_files": list(artifact.get("target_files", [])),
                "operation_kind": artifact.get("operation_kind"),
                "selector_mode": artifact.get("selector_mode"),
                "selector_hints": list(artifact.get("selector_hints", [])),
                "patch_strategy": "scoped_single_surface_patch",
            }
        )
    base["patch_operations"] = patch_operations
    return base


def _patch_preview_replacement(operation_kind: str) -> tuple[str, str]:
    replacements = {
        "copy_declared_sidecars": (
            "<missing referenced sidecar absent from runtime workspace>",
            "<referenced sidecar copied into the selected runtime workspace>",
        ),
        "rewrite_declared_paths": (
            "<current declared path that does not resolve in the selected runtime surface>",
            "<normalized path that resolves in the selected runtime surface>",
        ),
        "rename_declared_symbols": (
            "<current declared symbol that does not match the runtime case>",
            "<normalized declared symbol aligned with the current case>",
        ),
        "repair_missing_entries": (
            "<missing entry or incomplete block>",
            "<single repaired entry consistent with the selected scope>",
        ),
        "repair_dictionary_references": (
            "<dictionary reference that no longer resolves>",
            "<dictionary reference normalized to the active case layout>",
        ),
        "restore_required_layout": (
            "<missing required case-layout element>",
            "<required case-layout element restored for the current runtime surface>",
        ),
        "normalize_runtime_paths": (
            "<runtime path that points outside the intended surface>",
            "<runtime path normalized to the selected case/output surface>",
        ),
        "normalize_runtime_configuration": (
            "<runtime configuration value that mismatches the selected solver surface>",
            "<runtime configuration value aligned with the selected solver surface>",
        ),
        "switch_declared_input_source": (
            "<restart or initialization source currently referenced>",
            "<restart or initialization source selected for this single deterministic pass>",
        ),
    }
    return replacements.get(
        operation_kind,
        (
            "<current scoped value>",
            "<proposed scoped value>",
        ),
    )


def _render_patch_text_preview(execution_output: dict[str, Any]) -> str:
    lines = [
        "*** Begin Preview Patch",
        f"# executor_kind: {execution_output.get('executor_kind')}",
        "# preview_only: true",
    ]
    for operation in list(execution_output.get("patch_operations", [])):
        if not isinstance(operation, dict):
            continue
        target_files = [str(item) for item in list(operation.get("target_files", [])) if str(item).strip()] or ["<target_file>"]
        before_text, after_text = _patch_preview_replacement(str(operation.get("operation_kind") or ""))
        selector_mode = str(operation.get("selector_mode") or "scoped_selector")
        selector_hints = [str(item) for item in list(operation.get("selector_hints", [])) if str(item).strip()]
        for target_file in target_files:
            lines.extend(
                [
                    f"*** Update File: {target_file}",
                    f"@@ selector_mode={selector_mode}",
                    *([f"@@ selector_hints={', '.join(selector_hints)}"] if selector_hints else []),
                    f"- {before_text}",
                    f"+ {after_text}",
                ]
            )
    lines.append("*** End Preview Patch")
    return "\n".join(lines)


def _value_expression_for_modifier(modifier: str) -> str:
    mapping = {
        "decrease": "0.5 * <current_value>",
        "increase": "2.0 * <current_value>",
        "tighten": "0.1 * <current_value>",
        "adjust": "<bounded_adjustment_from_current_value>",
    }
    return mapping.get(modifier, "<bounded_adjustment_from_current_value>")


def _render_parameter_write_payload(execution_output: dict[str, Any]) -> dict[str, Any]:
    assignments: list[dict[str, Any]] = []
    for item in list(execution_output.get("parameter_updates", [])):
        if not isinstance(item, dict):
            continue
        modifier = str(item.get("modifier") or "adjust")
        assignments.append(
            {
                "target_files": list(item.get("target_files", [])),
                "parameter": item.get("parameter"),
                "modifier": modifier,
                "step_policy": item.get("step_policy"),
                "value_policy": item.get("value_policy"),
                "value_expression": _value_expression_for_modifier(modifier),
                "write_scope": "single_parameter_family",
            }
        )
    return {
        "preview_only": True,
        "assignment_count": len(assignments),
        "assignments": assignments,
    }


def _render_execution_preview(execution_output: dict[str, Any]) -> dict[str, Any]:
    output_kind = str(execution_output.get("output_kind") or "")
    if output_kind == "parameter_change_plan":
        return {
            "render_kind": "parameter_write_payload",
            "parameter_write_payload": _render_parameter_write_payload(execution_output),
        }
    return {
        "render_kind": "patch_text_preview",
        "patch_text": _render_patch_text_preview(execution_output),
    }


def _route_results_root(route_data: dict[str, Any]) -> Path | None:
    summary = route_data.get("summary") if isinstance(route_data.get("summary"), dict) else {}
    raw = summary.get("results_dir")
    if not raw:
        return None
    try:
        return Path(str(raw))
    except Exception:
        return None


def _route_artifact_input_paths(route_data: dict[str, Any], results_root: Path | None) -> list[Path]:
    followup = route_data.get("followup") if isinstance(route_data.get("followup"), dict) else {}
    artifact_snapshot = (
        followup.get("artifact_snapshot")
        if isinstance(followup.get("artifact_snapshot"), dict)
        else {}
    )
    paths: list[Path] = []
    for item in list(artifact_snapshot.get("input_files", [])):
        raw = str(item).strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute() and results_root is not None:
            path = results_root / raw
        paths.append(path)
    return paths


def _artifact_paths_with_suffix(paths: list[Path], *suffixes: str) -> list[Path]:
    allowed = {item.lower() for item in suffixes}
    return [path for path in paths if path.suffix.lower() in allowed]


def _resolve_declared_target_paths(
    route_data: dict[str, Any],
    declared_target: str,
) -> list[Path]:
    results_root = _route_results_root(route_data)
    artifact_input_paths = _route_artifact_input_paths(route_data, results_root)
    target = str(declared_target or "").strip()
    if not target:
        return []

    placeholder_map: dict[str, list[Path]] = {
        "<case>.export": _artifact_paths_with_suffix(artifact_input_paths, ".export"),
        "<case>.comm": _artifact_paths_with_suffix(artifact_input_paths, ".comm"),
        "<case>.sif": _artifact_paths_with_suffix(artifact_input_paths, ".sif"),
        "<primary_su2_cfg>": _artifact_paths_with_suffix(artifact_input_paths, ".cfg"),
        "<referenced_input_sidecars>": list(artifact_input_paths),
        "<mesh_or_restart_sidecar>": _artifact_paths_with_suffix(
            artifact_input_paths,
            ".su2",
            ".msh",
            ".mesh",
            ".dat",
            ".rst",
            ".res",
        ),
        "<results_dir>": [results_root] if results_root is not None else [],
        "<case_dir>": [results_root] if results_root is not None else [],
        "<elmer_mesh_dir>": (
            [results_root / "mesh"] if results_root is not None else []
        ),
        "<runtime_wrapper_config>": [],
        "<runtime_command_config>": [],
        "<solver_image_reference>": [],
    }
    if target in placeholder_map:
        return [Path(path) for path in placeholder_map[target]]

    has_glob_pattern = any(token in target for token in ("*", "?", "["))
    path = Path(target)
    if path.is_absolute():
        if has_glob_pattern:
            return sorted(path.parent.glob(path.name), key=str)
        return [path]
    if results_root is not None:
        if has_glob_pattern:
            return sorted(results_root.glob(target), key=str)
        return [results_root / target]
    return [path]


def _target_file_checks(
    route_data: dict[str, Any],
    execution_output: dict[str, Any],
) -> list[dict[str, Any]]:
    results_root = _route_results_root(route_data)
    checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for declared_target in list(execution_output.get("target_files", [])):
        target_key = str(declared_target).strip()
        if not target_key or target_key in seen:
            continue
        seen.add(target_key)
        candidate_paths = _resolve_declared_target_paths(route_data, target_key)
        existing_paths = [path for path in candidate_paths if path.exists()]
        matched_path = existing_paths[0] if existing_paths else None
        within_results_root = (
            all(path.is_relative_to(results_root) for path in existing_paths)
            if existing_paths and results_root is not None
            else None
        )
        is_placeholder = target_key.startswith("<") and target_key.endswith(">")
        if existing_paths:
            resolution_status = "resolved_placeholder" if is_placeholder else "resolved_relative"
        elif is_placeholder:
            resolution_status = "unresolved_placeholder"
        else:
            resolution_status = "missing_relative"
        checks.append(
            {
                "declared_target": target_key,
                "resolved_paths": [str(path) for path in candidate_paths],
                "matched_path": str(matched_path) if matched_path is not None else None,
                "matched_paths": [str(path) for path in existing_paths],
                "exists": bool(existing_paths),
                "is_placeholder": is_placeholder,
                "within_results_root": within_results_root,
                "resolution_status": resolution_status,
            }
        )
    return checks


def _resolved_existing_paths_from_check(file_check: dict[str, Any] | None) -> list[Path]:
    if not isinstance(file_check, dict):
        return []
    raw_paths = [
        str(item).strip()
        for item in list(file_check.get("matched_paths", []))
        if str(item).strip()
    ]
    if not raw_paths and str(file_check.get("matched_path") or "").strip():
        raw_paths = [str(file_check.get("matched_path")).strip()]
    resolved: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(Path(raw))
    return resolved


def _concrete_selector_tokens(hints: list[str]) -> list[str]:
    stop_words = {
        "current",
        "selected",
        "runtime",
        "surface",
        "declared",
        "missing",
        "normalized",
        "aligned",
        "single",
        "scoped",
        "entries",
        "entry",
        "path",
        "paths",
        "file",
        "files",
        "case",
        "workspace",
        "reference",
        "references",
        "required",
        "output",
        "input",
        "directory",
        "directories",
        "solver",
        "configuration",
        "config",
        "block",
        "blocks",
    }
    tokens: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        for token in re.findall(r"[A-Za-z0-9_./*-]+", str(hint)):
            normalized = token.strip()
            if len(normalized) < 3:
                continue
            if normalized.lower() in stop_words:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(normalized)
    return tokens


def _find_openfoam_named_block_span(text: str, block_name: str) -> tuple[int, int] | None:
    header = re.search(
        rf"(?mi)^\s*{re.escape(str(block_name).strip())}\b.*$",
        text,
    )
    if header is None:
        return None
    open_index = text.find("{", header.start())
    if open_index == -1:
        return None
    depth = 0
    for index in range(open_index, len(text)):
        token = text[index]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return open_index, index + 1
    return None


def _is_openfoam_boundary_name_candidate(token: str) -> bool:
    return bool(
        token
        and token not in {"(", ")", "{", "}"}
        and not token.endswith(";")
        and not token.isdigit()
        and re.fullmatch(r"[A-Za-z0-9_./-]+", token)
    )


def _openfoam_boundary_patch_entries(boundary_text: str) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    seen: set[str] = set()
    lines = boundary_text.splitlines()
    line_count = len(lines)
    index = 0
    while index < line_count:
        token = lines[index].strip()
        if not _is_openfoam_boundary_name_candidate(token):
            index += 1
            continue
        next_index = index + 1
        next_nonempty: str | None = None
        while next_index < line_count:
            stripped = lines[next_index].strip()
            if stripped:
                next_nonempty = stripped
                break
            next_index += 1
        if next_nonempty != "{":
            index += 1
            continue

        depth = 0
        block_lines: list[str] = []
        cursor = next_index
        while cursor < line_count:
            raw_line = lines[cursor]
            block_lines.append(raw_line)
            depth += raw_line.count("{")
            depth -= raw_line.count("}")
            cursor += 1
            if depth <= 0:
                break
        block_text = "\n".join(block_lines)
        patch_type_match = re.search(
            r"(?mi)^\s*type\s+([A-Za-z0-9_./-]+)\s*;",
            block_text,
        )
        patch_type = (
            str(patch_type_match.group(1)).strip()
            if patch_type_match is not None
            else None
        )

        key = token.lower()
        if key not in seen:
            seen.add(key)
            entries.append(
                {
                    "name": token,
                    "type": patch_type,
                }
            )
        index = cursor
    return entries


def _openfoam_boundary_patch_names(boundary_text: str) -> list[str]:
    return [
        str(entry.get("name"))
        for entry in _openfoam_boundary_patch_entries(boundary_text)
        if str(entry.get("name") or "").strip()
    ]


def _openfoam_boundary_patch_type_map(boundary_text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in _openfoam_boundary_patch_entries(boundary_text):
        name = str(entry.get("name") or "").strip()
        patch_type = str(entry.get("type") or "").strip()
        if not name or not patch_type:
            continue
        key = name.lower()
        if key in mapping:
            continue
        mapping[key] = patch_type
    return mapping


def _openfoam_block_has_named_entry(block_text: str, entry_name: str) -> bool:
    return bool(
        re.search(
            rf"(?ms)^\s*{re.escape(entry_name)}\s*(?:\n\s*)?\{{",
            block_text,
        )
    )


def _openfoam_block_named_entries(block_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?m)^\s*([A-Za-z0-9_./-]+)\s*(?:\n\s*)?\{", block_text):
        token = str(match.group(1) or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(token)
    return names


def _openfoam_boundary_field_entry_names(field_text: str) -> list[str]:
    span = _find_openfoam_named_block_span(field_text, "boundaryField")
    if span is None:
        return []
    return _openfoam_block_named_entries(field_text[span[0] : span[1]])


def _openfoam_field_files_under_results_root(results_root: Path | None) -> list[Path]:
    if results_root is None:
        return []
    fields_dir = results_root / "0"
    if not fields_dir.exists() or not fields_dir.is_dir():
        return []
    files: list[Path] = []
    seen: set[str] = set()
    for path in sorted(fields_dir.glob("*"), key=str):
        if not path.is_file():
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        files.append(path)
    return files


def _patch_name_selector_check(
    route_data: dict[str, Any],
    operation: dict[str, Any],
    check_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    boundary_files: list[Path] = []
    seen_boundary_paths: set[str] = set()
    for target in list(operation.get("target_files", [])):
        file_check = check_map.get(str(target))
        for matched_path in _resolved_existing_paths_from_check(file_check):
            if not matched_path.exists() or not matched_path.is_file():
                continue
            key = str(matched_path).lower()
            if key in seen_boundary_paths:
                continue
            seen_boundary_paths.add(key)
            boundary_files.append(matched_path)
    if len(boundary_files) != 1:
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "no_existing_file",
            "expected_tokens": [],
            "matched_tokens": [],
            "missing_tokens": [],
            "field_only_tokens": [],
        }

    boundary_text = boundary_files[0].read_text(encoding="utf-8", errors="ignore")
    expected_tokens = _openfoam_boundary_patch_names(boundary_text)
    if not expected_tokens:
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "indeterminate_no_tokens",
            "expected_tokens": [],
            "matched_tokens": [],
            "missing_tokens": [],
            "field_only_tokens": [],
        }

    results_root = _route_results_root(route_data)
    field_files = _openfoam_field_files_under_results_root(results_root)
    if not field_files:
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "matched",
            "expected_tokens": expected_tokens,
            "matched_tokens": list(expected_tokens),
            "missing_tokens": [],
            "field_only_tokens": [],
            "selector_note": "field_files_missing_for_patch_name_compare",
        }

    field_tokens: list[str] = []
    seen_field_tokens: set[str] = set()
    for field_file in field_files:
        field_text = field_file.read_text(encoding="utf-8", errors="ignore")
        for token in _openfoam_boundary_field_entry_names(field_text):
            key = token.lower()
            if key in seen_field_tokens:
                continue
            seen_field_tokens.add(key)
            field_tokens.append(token)

    matched_tokens = [
        token for token in expected_tokens if token.lower() in seen_field_tokens
    ]
    missing_tokens = [token for token in expected_tokens if token not in matched_tokens]
    expected_token_keys = {token.lower() for token in expected_tokens}
    field_only_tokens = [
        token for token in field_tokens if token.lower() not in expected_token_keys
    ]
    return {
        "selector_scope": operation.get("selector_mode"),
        "target_files": list(operation.get("target_files", [])),
        "status": "matched",
        "expected_tokens": expected_tokens,
        "matched_tokens": matched_tokens,
        "missing_tokens": missing_tokens,
        "field_only_tokens": field_only_tokens,
    }


def _patch_field_selector_check(
    route_data: dict[str, Any],
    operation: dict[str, Any],
    check_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    results_root = _route_results_root(route_data)
    boundary_file = (
        results_root / "constant" / "polyMesh" / "boundary"
        if results_root is not None
        else None
    )
    if boundary_file is None or not boundary_file.exists() or not boundary_file.is_file():
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "no_existing_file",
            "expected_tokens": [],
            "matched_tokens": [],
            "missing_tokens": [],
            "field_patch_coverage": [],
        }

    boundary_text = boundary_file.read_text(encoding="utf-8", errors="ignore")
    expected_tokens = _openfoam_boundary_patch_names(boundary_text)
    if not expected_tokens:
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "indeterminate_no_tokens",
            "expected_tokens": [],
            "matched_tokens": [],
            "missing_tokens": [],
            "field_patch_coverage": [],
        }

    field_files: list[Path] = []
    seen_paths: set[str] = set()
    for target in list(operation.get("target_files", [])):
        file_check = check_map.get(str(target))
        for matched_path in _resolved_existing_paths_from_check(file_check):
            if not matched_path.exists() or not matched_path.is_file():
                continue
            key = str(matched_path).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            field_files.append(matched_path)

    if not field_files:
        return {
            "selector_scope": operation.get("selector_mode"),
            "target_files": list(operation.get("target_files", [])),
            "status": "no_existing_file",
            "expected_tokens": expected_tokens,
            "matched_tokens": [],
            "missing_tokens": [],
            "field_patch_coverage": [],
        }

    field_patch_coverage: list[dict[str, Any]] = []
    missing_set: set[str] = set()
    has_boundary_field = False
    for field_path in field_files:
        text = field_path.read_text(encoding="utf-8", errors="ignore")
        span = _find_openfoam_named_block_span(text, "boundaryField")
        if span is None:
            field_patch_coverage.append(
                {
                    "path": str(field_path),
                    "has_boundary_field": False,
                    "missing_tokens": list(expected_tokens),
                }
            )
            missing_set.update(expected_tokens)
            continue
        has_boundary_field = True
        block_text = text[span[0] : span[1]]
        missing_tokens = [
            token
            for token in expected_tokens
            if not _openfoam_block_has_named_entry(block_text, token)
        ]
        missing_set.update(missing_tokens)
        field_patch_coverage.append(
            {
                "path": str(field_path),
                "has_boundary_field": True,
                "missing_tokens": missing_tokens,
            }
        )

    missing_tokens = [token for token in expected_tokens if token in missing_set]
    matched_tokens = [token for token in expected_tokens if token not in missing_set]
    return {
        "selector_scope": operation.get("selector_mode"),
        "target_files": list(operation.get("target_files", [])),
        "status": "matched" if has_boundary_field else "unmatched",
        "expected_tokens": expected_tokens,
        "matched_tokens": matched_tokens,
        "missing_tokens": missing_tokens,
        "field_patch_coverage": field_patch_coverage,
    }


def _selector_checks(
    route_data: dict[str, Any],
    execution_output: dict[str, Any],
    target_file_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    check_map = {
        str(item.get("declared_target") or ""): item
        for item in target_file_checks
        if isinstance(item, dict)
    }
    output_kind = str(execution_output.get("output_kind") or "")
    checks: list[dict[str, Any]] = []
    if output_kind == "parameter_change_plan":
        for update in list(execution_output.get("parameter_updates", [])):
            if not isinstance(update, dict):
                continue
            tokens = _concrete_selector_tokens([str(update.get("parameter") or "")])
            file_texts: list[str] = []
            for target in list(update.get("target_files", [])):
                file_check = check_map.get(str(target))
                for matched_path in _resolved_existing_paths_from_check(file_check):
                    if matched_path.exists() and matched_path.is_file():
                        file_texts.append(
                            matched_path.read_text(
                                encoding="utf-8",
                                errors="ignore",
                            )
                        )
            if not tokens:
                status = "indeterminate_no_tokens"
                matched_tokens: list[str] = []
            elif not file_texts:
                status = "no_existing_file"
                matched_tokens = []
            else:
                matched_tokens = [
                    token
                    for token in tokens
                    if any(token.lower() in text.lower() for text in file_texts)
                ]
                status = "matched" if matched_tokens else "unmatched"
            checks.append(
                {
                    "selector_scope": update.get("parameter"),
                    "target_files": list(update.get("target_files", [])),
                    "status": status,
                    "expected_tokens": tokens,
                    "matched_tokens": matched_tokens,
                }
            )
        return checks

    for operation in list(execution_output.get("patch_operations", [])):
        if not isinstance(operation, dict):
            continue
        selector_mode = str(operation.get("selector_mode") or "")
        if selector_mode == "patch_name_entries":
            checks.append(
                _patch_name_selector_check(route_data, operation, check_map)
            )
            continue
        if selector_mode == "patch_field_entries":
            checks.append(
                _patch_field_selector_check(route_data, operation, check_map)
            )
            continue
        tokens = _concrete_selector_tokens(list(operation.get("selector_hints", [])))
        file_texts = []
        directory_token_checks: list[dict[str, Any]] = []
        for target in list(operation.get("target_files", [])):
            file_check = check_map.get(str(target))
            for matched_path in _resolved_existing_paths_from_check(file_check):
                if matched_path.exists() and matched_path.is_file():
                    file_texts.append(
                        matched_path.read_text(encoding="utf-8", errors="ignore")
                    )
                elif (
                    matched_path.exists()
                    and matched_path.is_dir()
                    and selector_mode == "required_case_paths"
                ):
                    required_paths = [
                        str(item).strip()
                        for item in list(operation.get("selector_hints", []))
                        if str(item).strip()
                    ]
                    directory_token_checks.append(
                        {
                            "required_paths": required_paths,
                            "existing_paths": [
                                token
                                for token in required_paths
                                if (matched_path / str(token).strip().rstrip("/\\")).exists()
                            ],
                            "missing_paths": [
                                token
                                for token in required_paths
                                if not (matched_path / str(token).strip().rstrip("/\\")).exists()
                            ],
                        }
                    )
        if not tokens:
            status = "indeterminate_no_tokens"
            matched_tokens = []
            missing_tokens: list[str] = []
        elif not file_texts:
            if directory_token_checks:
                status = "matched"
                matched_tokens = list(directory_token_checks[0]["existing_paths"])
                missing_tokens = list(directory_token_checks[0]["missing_paths"])
            else:
                status = "no_existing_file"
                matched_tokens = []
                missing_tokens = []
        else:
            matched_tokens = [
                token
                for token in tokens
                if any(token.lower() in text.lower() for text in file_texts)
            ]
            status = "matched" if matched_tokens else "unmatched"
            missing_tokens = [
                token for token in tokens if token not in matched_tokens
            ]
        checks.append(
            {
                "selector_scope": operation.get("selector_mode"),
                "target_files": list(operation.get("target_files", [])),
                "status": status,
                "expected_tokens": tokens,
                "matched_tokens": matched_tokens,
                "missing_tokens": missing_tokens,
            }
        )
    return checks


def _single_surface_check(
    route_data: dict[str, Any],
    selected_plan: dict[str, Any],
    target_file_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    results_root = _route_results_root(route_data)
    resolved_targets = [
        item for item in target_file_checks
        if isinstance(item, dict) and item.get("exists")
    ]
    return {
        "preview_touches_unrelated_files": bool(selected_plan.get("touches_unrelated_files")),
        "resolved_target_count": len(resolved_targets),
        "all_resolved_targets_within_results_root": all(
            item.get("within_results_root") is not False for item in resolved_targets
        ),
        "single_surface_ok": (
            not bool(selected_plan.get("touches_unrelated_files"))
            and all(item.get("within_results_root") is not False for item in resolved_targets)
            and (results_root is not None)
        ),
    }


def _build_dry_run_validation(
    route_data: dict[str, Any],
    selected_plan: dict[str, Any],
    execution_output: dict[str, Any],
) -> dict[str, Any]:
    target_file_checks = _target_file_checks(route_data, execution_output)
    selector_checks = _selector_checks(route_data, execution_output, target_file_checks)
    single_surface_check = _single_surface_check(route_data, selected_plan, target_file_checks)
    needs_path_resolution = any(
        item.get("resolution_status") in {"unresolved_placeholder", "missing_relative"}
        for item in target_file_checks
    )
    needs_selector_review = any(
        item.get("status") in {"unmatched", "no_existing_file"}
        for item in selector_checks
    )
    if needs_path_resolution:
        status = "needs_path_resolution"
    elif needs_selector_review:
        status = "needs_selector_review"
    elif not bool(single_surface_check.get("single_surface_ok")):
        status = "needs_surface_review"
    else:
        status = "ready_for_write_guard"
    write_guard_passed = status == "ready_for_write_guard"
    return {
        "validation_mode": "preview_only_dry_run",
        "status": status,
        "write_guard_passed": write_guard_passed,
        "write_permitted": False,
        "results_root": str(_route_results_root(route_data)) if _route_results_root(route_data) is not None else None,
        "target_file_checks": target_file_checks,
        "selector_checks": selector_checks,
        "single_surface_check": single_surface_check,
    }


def _build_selected_edit_execution_details(
    route_data: dict[str, Any],
    *,
    selection_id: str,
    selection_kind: str | None,
) -> dict[str, Any]:
    actual_route = str(route_data.get("actual_route") or route_data.get("expected_route") or "unknown")
    builder_map: dict[str, Any] = {
        "runtime_remediation": _build_runtime_remediation_prompt_payload,
        "convergence_tuning": _build_convergence_tuning_prompt_payload,
    }
    builder = builder_map.get(actual_route)
    if builder is None:
        return {
            "applicable": False,
            "selection_id": selection_id,
            "selection_kind": selection_kind,
            "selection_found": False,
            "available_selection_ids": {"payload_ids": [], "plan_ids": []},
            "message": (
                f"Route '{actual_route}' does not expose deterministic edit execution plans."
            ),
        }

    normalized_kind = _normalize_edit_selection_kind(selection_id, selection_kind)
    details = builder(route_data)
    available_selection_ids = _available_edit_selection_ids(details)
    selected_template, selected_plan = _select_edit_template_and_plan(
        details,
        selection_id=selection_id,
        selection_kind=normalized_kind,
    )
    if selected_plan is None:
        return {
            "selection_id": selection_id,
            "selection_kind": normalized_kind,
            "selection_found": False,
            "available_selection_ids": available_selection_ids,
            "message": (
                f"No deterministic edit selection matched '{selection_id}' for route '{actual_route}'."
            ),
        }

    execution_output = _build_exact_execution_output(selected_plan)
    return {
        "selection_id": selection_id,
        "selection_kind": normalized_kind,
        "selection_found": True,
        "available_selection_ids": available_selection_ids,
        "selected_payload_template": selected_template,
        "selected_edit_execution_plan": selected_plan,
        "execution_output": execution_output,
        "rendered_execution_preview": _render_execution_preview(execution_output),
        "dry_run_validation": _build_dry_run_validation(
            route_data,
            selected_plan,
            execution_output,
        ),
        "output_contract": [
            "selected_payload_template",
            "selected_edit_execution_plan",
            "execution_output",
            "rendered_execution_preview",
            "dry_run_validation",
        ],
    }


_NUMERIC_LITERAL_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _guarded_numeric_value(current_value: float, modifier: str) -> float:
    modifier_key = str(modifier or "adjust").strip().lower()
    if modifier_key == "decrease":
        return current_value * 0.5
    if modifier_key == "increase":
        return current_value * 2.0
    if modifier_key == "tighten":
        return current_value * 0.1
    if modifier_key == "adjust":
        return current_value * 0.8
    raise ValueError(f"Unsupported guarded modifier '{modifier}'.")


def _format_guarded_numeric_literal(original_literal: str, updated_value: float) -> str:
    if re.fullmatch(r"[-+]?\d+", str(original_literal).strip()) and float(updated_value).is_integer():
        return str(int(updated_value))
    return format(updated_value, ".12g")


def _parameter_assignment_patterns(parameter: str) -> list[re.Pattern[str]]:
    escaped = re.escape(str(parameter or "").strip())
    if not escaped:
        return []
    return [
        re.compile(
            rf"(?m)^(\s*{escaped}\s*=\s*)({_NUMERIC_LITERAL_PATTERN})(\s*(?:[!#%].*)?)$"
        ),
        re.compile(
            rf"(?m)^(\s*{escaped}\s+)({_NUMERIC_LITERAL_PATTERN})(\s*;.*)$"
        ),
    ]


def _apply_guarded_parameter_update_to_text(
    text: str,
    *,
    parameter: str,
    modifier: str,
) -> tuple[str, dict[str, Any]]:
    matches: list[re.Match[str]] = []
    for pattern in _parameter_assignment_patterns(parameter):
        matches.extend(list(pattern.finditer(text)))
    if not matches:
        raise ValueError(f"Parameter '{parameter}' was not found on a writable numeric assignment line.")
    if len(matches) > 1:
        raise ValueError(
            f"Parameter '{parameter}' matched multiple writable numeric assignment lines; the guarded executor requires one unambiguous target."
        )
    match = matches[0]
    prefix = match.group(1)
    current_literal = match.group(2)
    suffix = match.group(3) or ""
    current_value = float(current_literal)
    updated_value = _guarded_numeric_value(current_value, modifier)
    updated_literal = _format_guarded_numeric_literal(current_literal, updated_value)
    replacement = f"{prefix}{updated_literal}{suffix}"
    updated_text = f"{text[:match.start()]}{replacement}{text[match.end():]}"
    return updated_text, {
        "parameter": parameter,
        "modifier": modifier,
        "before_value": current_literal,
        "after_value": updated_literal,
        "matched_line": match.group(0).strip(),
    }


def _matched_target_paths_map(
    dry_run_validation: dict[str, Any],
) -> dict[str, list[Path]]:
    path_map: dict[str, list[Path]] = {}
    for item in list(dry_run_validation.get("target_file_checks", [])):
        if not isinstance(item, dict):
            continue
        declared_target = str(item.get("declared_target") or "").strip()
        if not declared_target:
            continue
        matched_paths = _resolved_existing_paths_from_check(item)
        if matched_paths:
            path_map[declared_target] = matched_paths
    return path_map


def _matched_target_path_map(dry_run_validation: dict[str, Any]) -> dict[str, Path]:
    path_map: dict[str, Path] = {}
    for declared_target, matched_paths in _matched_target_paths_map(
        dry_run_validation
    ).items():
        if matched_paths:
            path_map[declared_target] = matched_paths[0]
    return path_map


def _guarded_backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.cae-cli.bak")


def _execute_guarded_parameter_plan(
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    target_path_map = _matched_target_path_map(dry_run_validation)
    staged_texts: dict[Path, str] = {}
    original_texts: dict[Path, str] = {}
    applied_updates: list[dict[str, Any]] = []

    for update in list(execution_output.get("parameter_updates", [])):
        if not isinstance(update, dict):
            continue
        parameter = str(update.get("parameter") or "").strip()
        modifier = str(update.get("modifier") or "adjust").strip()
        resolved_paths = [
            target_path_map[str(target).strip()]
            for target in list(update.get("target_files", []))
            if str(target).strip() in target_path_map
        ]
        unique_paths = list(dict.fromkeys(resolved_paths))
        if len(unique_paths) != 1:
            raise ValueError(
                f"Guarded parameter writes currently require exactly one resolved target file per update; got {len(unique_paths)} for '{parameter}'."
            )
        target_path = unique_paths[0]
        if not target_path.is_file():
            raise ValueError(
                f"Guarded parameter write target is not a file: {target_path}"
            )
        if target_path not in staged_texts:
            original_texts[target_path] = target_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            staged_texts[target_path] = original_texts[target_path]
        staged_texts[target_path], change = _apply_guarded_parameter_update_to_text(
            staged_texts[target_path],
            parameter=parameter,
            modifier=modifier,
        )
        applied_updates.append(
            {
                **change,
                "path": str(target_path),
                "value_policy": update.get("value_policy"),
                "step_policy": update.get("step_policy"),
            }
        )

    if not applied_updates:
        raise ValueError("No guarded parameter updates were prepared for execution.")

    backup_files: list[str] = []
    changed_files: list[str] = []
    for path, updated_text in staged_texts.items():
        original_text = original_texts[path]
        if updated_text == original_text:
            continue
        backup_path = _guarded_backup_path(path)
        backup_path.write_text(original_text, encoding="utf-8")
        path.write_text(updated_text, encoding="utf-8")
        backup_files.append(str(backup_path))
        changed_files.append(str(path))

    return {
        "execution_mode": "guarded_write",
        "status": "applied",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "parameter_updates_applied": applied_updates,
        "message": (
            "Applied the guarded parameter update plan."
            if changed_files
            else "The guarded parameter plan matched the target files but did not change any file contents."
        ),
    }


def _write_guarded_file_updates(staged_texts: dict[Path, str]) -> tuple[list[str], list[str]]:
    backup_files: list[str] = []
    changed_files: list[str] = []
    for path, updated_text in staged_texts.items():
        original_text = path.read_text(encoding="utf-8", errors="ignore")
        if updated_text == original_text:
            continue
        backup_path = _guarded_backup_path(path)
        backup_path.write_text(original_text, encoding="utf-8")
        path.write_text(updated_text, encoding="utf-8")
        backup_files.append(str(backup_path))
        changed_files.append(str(path))
    return changed_files, backup_files


def _apply_guarded_single_line_replacement(
    text: str,
    *,
    pattern: re.Pattern[str],
    replacement_value: str,
    label: str,
) -> tuple[str, dict[str, Any] | None]:
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"Guarded structured patch could not find the '{label}' line.")
    if len(matches) > 1:
        raise ValueError(
            f"Guarded structured patch matched multiple '{label}' lines; the executor requires one unambiguous target."
        )
    match = matches[0]
    before_value = match.group(2)
    if before_value == replacement_value:
        return text, None
    replacement = f"{match.group(1)}{replacement_value}{match.group(3)}"
    updated_text = f"{text[:match.start()]}{replacement}{text[match.end():]}"
    return updated_text, {
        "label": label,
        "before_value": before_value,
        "after_value": replacement_value,
        "matched_line": match.group(0).strip(),
    }


def _guarded_export_reference_specs(route_data: dict[str, Any]) -> list[dict[str, Any]]:
    results_root = _route_results_root(route_data)
    artifact_input_paths = _route_artifact_input_paths(route_data, results_root)
    specs: list[dict[str, Any]] = []

    comm_candidates = _artifact_paths_with_suffix(artifact_input_paths, ".comm")
    if comm_candidates:
        specs.append(
            {
                "label": "F comm",
                "pattern": re.compile(r"(?mi)^(\s*F\s+comm\s+)(\S+)(\s+.*)$"),
                "replacement_value": comm_candidates[0].name,
            }
        )

    mesh_candidates = _artifact_paths_with_suffix(
        artifact_input_paths,
        ".med",
        ".mmed",
        ".mail",
        ".msh",
        ".mesh",
    )
    if mesh_candidates:
        specs.append(
            {
                "label": "F mmed",
                "pattern": re.compile(r"(?mi)^(\s*F\s+mmed\s+)(\S+)(\s+.*)$"),
                "replacement_value": mesh_candidates[0].name,
            }
        )

    return specs


def _execute_guarded_export_reference_patch(
    route_data: dict[str, Any],
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    target_path_map = _matched_target_path_map(dry_run_validation)
    target_files = [
        target_path_map[str(target).strip()]
        for target in list(execution_output.get("target_files", []))
        if str(target).strip() in target_path_map
    ]
    unique_targets = list(dict.fromkeys(target_files))
    if len(unique_targets) != 1:
        raise ValueError(
            f"Guarded structured patch requires exactly one resolved target file; got {len(unique_targets)}."
        )
    target_path = unique_targets[0]
    if not target_path.is_file():
        raise ValueError(f"Guarded structured patch target is not a file: {target_path}")

    operations = [
        item
        for item in list(execution_output.get("patch_operations", []))
        if isinstance(item, dict)
    ]
    if len(operations) != 1:
        raise ValueError(
            f"Guarded structured patch currently supports exactly one patch operation; got {len(operations)}."
        )
    operation = operations[0]
    if str(operation.get("operation_kind") or "") != "rewrite_declared_paths" or str(
        operation.get("selector_mode") or ""
    ) != "export_reference_entries":
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "executor_kind": execution_output.get("executor_kind"),
            "message": (
                "The guarded structured patch executor currently supports only Code_Aster export-reference rewrites."
            ),
        }

    staged_text = target_path.read_text(encoding="utf-8", errors="ignore")
    applied_changes: list[dict[str, Any]] = []
    for spec in _guarded_export_reference_specs(route_data):
        staged_text, change = _apply_guarded_single_line_replacement(
            staged_text,
            pattern=spec["pattern"],
            replacement_value=str(spec["replacement_value"]),
            label=str(spec["label"]),
        )
        if change is not None:
            applied_changes.append(change)

    if not applied_changes:
        return {
            "execution_mode": "guarded_write",
            "status": "no_change",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "structured_patch_changes": [],
            "message": "The guarded export-reference patch found no concrete path updates to apply.",
        }

    changed_files, backup_files = _write_guarded_file_updates({target_path: staged_text})
    return {
        "execution_mode": "guarded_write",
        "status": "applied",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "structured_patch_changes": [
            {**change, "path": str(target_path)}
            for change in applied_changes
        ],
        "message": "Applied the guarded structured patch plan.",
    }


def _execute_guarded_required_case_layout_patch(
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    target_path_map = _matched_target_path_map(dry_run_validation)
    target_files = [
        target_path_map[str(target).strip()]
        for target in list(execution_output.get("target_files", []))
        if str(target).strip() in target_path_map
    ]
    unique_targets = list(dict.fromkeys(target_files))
    if len(unique_targets) != 1:
        raise ValueError(
            f"Guarded case-layout restore requires exactly one resolved target directory; got {len(unique_targets)}."
        )
    target_path = unique_targets[0]
    if not target_path.is_dir():
        raise ValueError(
            f"Guarded case-layout restore target is not a directory: {target_path}"
        )

    operations = [
        item
        for item in list(execution_output.get("patch_operations", []))
        if isinstance(item, dict)
    ]
    if len(operations) != 1:
        raise ValueError(
            f"Guarded case-layout restore currently supports exactly one patch operation; got {len(operations)}."
        )
    operation = operations[0]
    if str(operation.get("operation_kind") or "") != "restore_required_layout" or str(
        operation.get("selector_mode") or ""
    ) != "required_case_paths":
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "executor_kind": execution_output.get("executor_kind"),
            "message": (
                "The guarded case-layout executor currently supports only required-case-path restoration."
            ),
        }

    created_paths: list[str] = []
    for token in [
        str(item).strip()
        for item in list(operation.get("selector_hints", []))
        if str(item).strip()
    ]:
        desired_path = target_path / str(token).strip().rstrip("/\\")
        if desired_path.exists():
            continue
        desired_path.mkdir(parents=True, exist_ok=True)
        created_paths.append(str(desired_path))

    return {
        "execution_mode": "guarded_write",
        "status": "applied" if created_paths else "no_change",
        "applied": bool(created_paths),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": 0,
        "changed_files": [],
        "backup_files": [],
        "created_paths": created_paths,
        "message": (
            "Restored the missing required case-layout paths."
            if created_paths
            else "The required case-layout paths already existed."
        ),
    }


def _missing_selector_tokens(dry_run_validation: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for item in list(dry_run_validation.get("selector_checks", [])):
        if not isinstance(item, dict):
            continue
        for token in list(item.get("missing_tokens", [])):
            normalized = str(token).strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            tokens.append(normalized)
    return tokens


def _guarded_openfoam_patch_boundary_names(
    dry_run_validation: dict[str, Any],
) -> list[str]:
    results_root_raw = str(dry_run_validation.get("results_root") or "").strip()
    if not results_root_raw:
        return []
    boundary_path = Path(results_root_raw) / "constant" / "polyMesh" / "boundary"
    if not boundary_path.exists() or not boundary_path.is_file():
        return []
    boundary_text = boundary_path.read_text(encoding="utf-8", errors="ignore")
    return _openfoam_boundary_patch_names(boundary_text)


def _guarded_openfoam_patch_type_map(
    dry_run_validation: dict[str, Any],
) -> dict[str, str]:
    results_root_raw = str(dry_run_validation.get("results_root") or "").strip()
    if not results_root_raw:
        return {}
    boundary_path = Path(results_root_raw) / "constant" / "polyMesh" / "boundary"
    if not boundary_path.exists() or not boundary_path.is_file():
        return {}
    boundary_text = boundary_path.read_text(encoding="utf-8", errors="ignore")
    return _openfoam_boundary_patch_type_map(boundary_text)


def _apply_guarded_boundary_patch_name_rename(
    text: str,
    *,
    from_name: str,
    to_name: str,
) -> tuple[str, bool]:
    escaped = re.escape(from_name)
    pattern = re.compile(
        rf"(?ms)^(\s*){escaped}(\s*)$(?=\s*\n\s*\{{)",
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return text, False
    if len(matches) > 1:
        raise ValueError(
            f"Guarded patch-name rename matched multiple '{from_name}' headers; expected one."
        )
    match = matches[0]
    replacement = f"{match.group(1)}{to_name}{match.group(2)}"
    updated = f"{text[:match.start()]}{replacement}{text[match.end():]}"
    return updated, True


_PATCH_NAME_TRAILING_NOISE_TOKENS = {
    "typo",
    "tmp",
    "temp",
    "old",
    "wrong",
    "fix",
    "fixed",
    "bad",
    "err",
    "error",
    "miss",
    "missing",
    "copy",
    "bak",
    "backup",
}


def _normalized_patch_name_for_matching(name: str) -> str:
    lowered = str(name or "").strip().lower()
    if not lowered:
        return ""
    tokens = [token for token in re.split(r"[_./-]+", lowered) if token]
    while tokens and tokens[-1] in _PATCH_NAME_TRAILING_NOISE_TOKENS:
        tokens.pop()
    if tokens:
        return "_".join(tokens)
    collapsed = re.sub(r"[^a-z0-9]+", "", lowered)
    return collapsed or lowered


def _levenshtein_distance(source: str, target: str) -> int:
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)
    prev = list(range(len(target) + 1))
    for row, source_char in enumerate(source, 1):
        curr = [row]
        for col, target_char in enumerate(target, 1):
            cost = 0 if source_char == target_char else 1
            curr.append(
                min(
                    prev[col] + 1,
                    curr[col - 1] + 1,
                    prev[col - 1] + cost,
                )
            )
        prev = curr
    return prev[-1]


def _patch_name_similarity_score(
    boundary_name: str,
    field_name: str,
) -> tuple[int, int, int] | None:
    normalized_boundary = _normalized_patch_name_for_matching(boundary_name)
    normalized_field = _normalized_patch_name_for_matching(field_name)
    if not normalized_boundary or not normalized_field:
        return None
    if normalized_boundary == normalized_field:
        return (
            0,
            _levenshtein_distance(
                str(boundary_name).strip().lower(),
                str(field_name).strip().lower(),
            ),
            abs(len(str(boundary_name).strip()) - len(str(field_name).strip())),
        )

    distance = _levenshtein_distance(normalized_boundary, normalized_field)
    max_len = max(len(normalized_boundary), len(normalized_field))
    allowed_distance = 1 if max_len <= 4 else 2
    if distance > allowed_distance:
        return None
    if normalized_boundary[0] != normalized_field[0]:
        return None
    return (
        1,
        distance,
        abs(len(normalized_boundary) - len(normalized_field)),
    )


def _infer_unambiguous_patch_rename_pairs(
    missing_boundary_names: list[str],
    field_only_names: list[str],
) -> tuple[list[tuple[str, str]], str | None]:
    if len(missing_boundary_names) != len(field_only_names):
        return [], "rename_pair_count_mismatch"
    if not missing_boundary_names:
        return [], "no_missing_boundary_names"

    missing_to_field: dict[str, str] = {}
    for boundary_name in missing_boundary_names:
        scored_candidates: list[tuple[tuple[int, int, int], str]] = []
        for field_name in field_only_names:
            score = _patch_name_similarity_score(boundary_name, field_name)
            if score is None:
                continue
            scored_candidates.append((score, field_name))
        if not scored_candidates:
            return [], f"no_candidate_for:{boundary_name}"
        scored_candidates.sort(key=lambda item: (item[0], str(item[1]).lower()))
        best_score = scored_candidates[0][0]
        tied = [
            field_name
            for score, field_name in scored_candidates
            if score == best_score
        ]
        if len(tied) != 1:
            return [], f"ambiguous_target_for:{boundary_name}"
        missing_to_field[boundary_name] = tied[0]

    chosen_targets = [missing_to_field[name] for name in missing_boundary_names]
    if len({target.lower() for target in chosen_targets}) != len(chosen_targets):
        return [], "multiple_boundary_names_map_to_same_field_name"

    for field_name in field_only_names:
        scored_candidates: list[tuple[tuple[int, int, int], str]] = []
        for boundary_name in missing_boundary_names:
            score = _patch_name_similarity_score(boundary_name, field_name)
            if score is None:
                continue
            scored_candidates.append((score, boundary_name))
        if not scored_candidates:
            return [], f"no_reverse_candidate_for:{field_name}"
        scored_candidates.sort(key=lambda item: (item[0], str(item[1]).lower()))
        best_score = scored_candidates[0][0]
        tied = [
            boundary_name
            for score, boundary_name in scored_candidates
            if score == best_score
        ]
        if len(tied) != 1:
            return [], f"ambiguous_source_for:{field_name}"
        reverse_boundary = tied[0]
        mapped_field = missing_to_field.get(reverse_boundary)
        if mapped_field is None or mapped_field.lower() != field_name.lower():
            return [], f"not_mutual_best_match:{field_name}"

    return [
        (boundary_name, missing_to_field[boundary_name])
        for boundary_name in missing_boundary_names
    ], None


def _execute_guarded_openfoam_patch_name_entries(
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    operations = [
        item
        for item in list(execution_output.get("patch_operations", []))
        if isinstance(item, dict)
    ]
    if len(operations) != 1:
        raise ValueError(
            f"Guarded OpenFOAM patch-name repair currently supports exactly one patch operation; got {len(operations)}."
        )
    operation = operations[0]
    if str(operation.get("operation_kind") or "") != "rename_declared_symbols" or str(
        operation.get("selector_mode") or ""
    ) != "patch_name_entries":
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-name executor supports only patch_name_entries rename restoration."
            ),
        }

    target_path_map = _matched_target_path_map(dry_run_validation)
    target_files = [
        target_path_map[str(target).strip()]
        for target in list(execution_output.get("target_files", []))
        if str(target).strip() in target_path_map
    ]
    unique_targets = list(dict.fromkeys(target_files))
    if len(unique_targets) != 1:
        raise ValueError(
            f"Guarded OpenFOAM patch-name repair requires exactly one resolved target boundary file; got {len(unique_targets)}."
        )
    boundary_path = unique_targets[0]
    if not boundary_path.is_file():
        raise ValueError(
            f"Guarded OpenFOAM patch-name repair target is not a file: {boundary_path}"
        )

    boundary_text = boundary_path.read_text(encoding="utf-8", errors="ignore")
    boundary_names = _openfoam_boundary_patch_names(boundary_text)
    if not boundary_names:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-name executor requires concrete patch names in constant/polyMesh/boundary."
            ),
        }

    results_root_raw = str(dry_run_validation.get("results_root") or "").strip()
    results_root = Path(results_root_raw) if results_root_raw else None
    field_files = _openfoam_field_files_under_results_root(results_root)
    if not field_files:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-name executor requires at least one field file under 0/ for deterministic alignment."
            ),
        }

    field_names: list[str] = []
    seen_field_names: set[str] = set()
    for field_file in field_files:
        field_text = field_file.read_text(encoding="utf-8", errors="ignore")
        for token in _openfoam_boundary_field_entry_names(field_text):
            key = token.lower()
            if key in seen_field_names:
                continue
            seen_field_names.add(key)
            field_names.append(token)

    boundary_name_keys = {name.lower() for name in boundary_names}
    missing_boundary_names = [
        name for name in boundary_names if name.lower() not in seen_field_names
    ]
    field_only_names = [
        name for name in field_names if name.lower() not in boundary_name_keys
    ]
    if not missing_boundary_names:
        return {
            "execution_mode": "guarded_write",
            "status": "no_change",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "structured_patch_changes": [],
            "message": "The boundary patch names already align with the available boundaryField entries.",
        }

    rename_pairs, pairing_error = _infer_unambiguous_patch_rename_pairs(
        missing_boundary_names,
        field_only_names,
    )
    if not rename_pairs:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-name executor requires unambiguous rename pairs between boundary patch names and 0/* field entries."
                f" pairing_error={pairing_error}"
            ),
        }

    updated_text = boundary_text
    structured_changes: list[dict[str, Any]] = []
    for from_name, to_name in rename_pairs:
        updated_text, changed = _apply_guarded_boundary_patch_name_rename(
            updated_text,
            from_name=from_name,
            to_name=to_name,
        )
        if not changed:
            return {
                "execution_mode": "guarded_write",
                "status": "unsupported_executor",
                "applied": False,
                "executor_supported": False,
                "write_guard_status": dry_run_validation.get("status"),
                "changed_file_count": 0,
                "changed_files": [],
                "backup_files": [],
                "message": (
                    "The guarded OpenFOAM patch-name executor could not locate a unique boundary patch header for rename."
                ),
            }
        structured_changes.append(
            {
                "path": str(boundary_path),
                "label": "patch_name_entries",
                "before_value": from_name,
                "after_value": to_name,
            }
        )

    changed_files, backup_files = _write_guarded_file_updates(
        {boundary_path: updated_text}
    )
    return {
        "execution_mode": "guarded_write",
        "status": "applied" if changed_files else "no_change",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "structured_patch_changes": structured_changes if changed_files else [],
        "message": (
            f"Renamed {len(structured_changes)} OpenFOAM boundary patch name(s) to align with field boundary entries."
            if changed_files
            else "The boundary patch names already align with the available boundaryField entries."
        ),
    }


def _openfoam_field_class_name(field_text: str) -> str | None:
    match = re.search(r"(?mi)^\s*class\s+([A-Za-z0-9_]+)\s*;", field_text)
    if match is None:
        return None
    return str(match.group(1)).strip() or None


def _openfoam_uniform_value_literal_for_field_class(field_class: str | None) -> str:
    normalized = str(field_class or "").strip().lower()
    if normalized == "volvectorfield":
        return "(0 0 0)"
    if normalized == "volsphericaltensorfield":
        return "(0)"
    if normalized == "volsymmtensorfield":
        return "(0 0 0 0 0 0)"
    if normalized == "voltensorfield":
        return "(0 0 0 0 0 0 0 0 0)"
    return "0"


def _openfoam_patch_entry_template(
    *,
    patch_name: str,
    patch_type: str | None,
    field_name: str,
    field_class: str | None,
) -> dict[str, Any]:
    normalized_patch_type = str(patch_type or "").strip().lower()
    normalized_patch_name = str(patch_name or "").strip().lower()
    normalized_field_name = str(field_name or "").strip().lower()
    normalized_field_class = str(field_class or "").strip().lower()

    passthrough_types = {
        "empty",
        "symmetry",
        "symmetryplane",
        "wedge",
        "cyclic",
        "cyclicami",
        "processor",
        "processorcyclic",
    }
    if normalized_patch_type in passthrough_types:
        return {
            "entry_type": str(patch_type).strip(),
            "value_expression": None,
        }

    is_vector_like = (
        normalized_field_class == "volvectorfield"
        or normalized_field_name == "u"
    )
    if normalized_patch_type == "wall" and is_vector_like:
        return {
            "entry_type": "noSlip",
            "value_expression": None,
        }

    inlet_like = "inlet" in normalized_patch_name or "inflow" in normalized_patch_name
    outlet_like = "outlet" in normalized_patch_name or "outflow" in normalized_patch_name
    if inlet_like:
        return {
            "entry_type": "fixedValue",
            "value_expression": (
                "uniform "
                + _openfoam_uniform_value_literal_for_field_class(field_class)
            ),
        }
    if outlet_like:
        return {
            "entry_type": "zeroGradient",
            "value_expression": None,
        }

    return {
        "entry_type": "zeroGradient",
        "value_expression": None,
    }


def _render_openfoam_patch_entry_block(
    patch_name: str,
    *,
    entry_type: str,
    value_expression: str | None,
) -> str:
    parts = [
        "    " + str(patch_name).strip() + "\n",
        "    {\n",
        "        type " + str(entry_type).strip() + ";\n",
    ]
    if value_expression is not None and str(value_expression).strip():
        parts.append("        value " + str(value_expression).strip() + ";\n")
    parts.append("    }\n")
    return "".join(parts)


def _apply_guarded_boundary_field_patch_entries(
    text: str,
    missing_patches: list[str],
    *,
    patch_type_map: dict[str, str],
    field_name: str,
) -> tuple[str, list[dict[str, Any]]]:
    span = _find_openfoam_named_block_span(text, "boundaryField")
    if span is None:
        return text, []
    block_start, block_end = span
    block_text = text[block_start:block_end]
    additions = [
        patch
        for patch in missing_patches
        if not _openfoam_block_has_named_entry(block_text, patch)
    ]
    if not additions:
        return text, []

    field_class = _openfoam_field_class_name(text)

    insert_at = block_end - 1
    insertion_parts = []
    if insert_at > 0 and text[insert_at - 1] != "\n":
        insertion_parts.append("\n")
    patch_additions: list[dict[str, Any]] = []
    for patch in additions:
        patch_type = patch_type_map.get(str(patch).lower())
        template = _openfoam_patch_entry_template(
            patch_name=patch,
            patch_type=patch_type,
            field_name=field_name,
            field_class=field_class,
        )
        insertion_parts.append(
            _render_openfoam_patch_entry_block(
                patch,
                entry_type=str(template.get("entry_type")),
                value_expression=(
                    str(template.get("value_expression"))
                    if template.get("value_expression") is not None
                    else None
                ),
            )
        )
        patch_additions.append(
            {
                "patch": patch,
                "entry_type": str(template.get("entry_type")),
                "value_expression": template.get("value_expression"),
                "boundary_patch_type": patch_type,
                "field_name": field_name,
                "field_class": field_class,
            }
        )
    insertion = "".join(insertion_parts)
    return text[:insert_at] + insertion + text[insert_at:], patch_additions


def _execute_guarded_openfoam_patch_field_entries(
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    operations = [
        item
        for item in list(execution_output.get("patch_operations", []))
        if isinstance(item, dict)
    ]
    if len(operations) != 1:
        raise ValueError(
            f"Guarded OpenFOAM patch-field repair currently supports exactly one patch operation; got {len(operations)}."
        )
    operation = operations[0]
    if str(operation.get("operation_kind") or "") != "repair_missing_entries" or str(
        operation.get("selector_mode") or ""
    ) != "patch_field_entries":
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-field executor supports only patch_field_entries missing-entry restoration."
            ),
        }

    expected_patches = _guarded_openfoam_patch_boundary_names(dry_run_validation)
    patch_type_map = _guarded_openfoam_patch_type_map(dry_run_validation)
    if not expected_patches:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-field executor requires a readable constant/polyMesh/boundary file with concrete patch names."
            ),
        }

    target_paths_map = _matched_target_paths_map(dry_run_validation)
    target_files: list[Path] = []
    seen: set[str] = set()
    for declared_target in list(execution_output.get("target_files", [])):
        normalized_target = str(declared_target).strip()
        for target_path in target_paths_map.get(normalized_target, []):
            if not target_path.exists() or not target_path.is_file():
                continue
            key = str(target_path).lower()
            if key in seen:
                continue
            seen.add(key)
            target_files.append(target_path)
    if not target_files:
        raise ValueError("Guarded OpenFOAM patch-field repair requires at least one resolved target field file.")

    staged_texts: dict[Path, str] = {}
    structured_changes: list[dict[str, Any]] = []
    boundary_field_file_count = 0
    for target_path in target_files:
        text = target_path.read_text(encoding="utf-8", errors="ignore")
        span = _find_openfoam_named_block_span(text, "boundaryField")
        if span is None:
            continue
        boundary_field_file_count += 1
        block_text = text[span[0] : span[1]]
        missing_patches = [
            patch
            for patch in expected_patches
            if not _openfoam_block_has_named_entry(block_text, patch)
        ]
        updated_text, additions = _apply_guarded_boundary_field_patch_entries(
            text,
            missing_patches,
            patch_type_map=patch_type_map,
            field_name=target_path.name,
        )
        if not additions:
            continue
        staged_texts[target_path] = updated_text
        structured_changes.append(
            {
                "path": str(target_path),
                "label": "boundaryField",
                "before_value": None,
                "after_value": ",".join(
                    str(item.get("patch") or "").strip()
                    for item in additions
                    if str(item.get("patch") or "").strip()
                ),
                "added_patches": [
                    str(item.get("patch") or "").strip()
                    for item in additions
                    if str(item.get("patch") or "").strip()
                ],
                "added_patch_templates": additions,
            }
        )

    if boundary_field_file_count == 0:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded OpenFOAM patch-field executor requires boundaryField blocks in at least one target file."
            ),
        }

    if not staged_texts:
        return {
            "execution_mode": "guarded_write",
            "status": "no_change",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "structured_patch_changes": [],
            "message": "All target boundaryField entries already cover the declared OpenFOAM patch names.",
        }

    changed_files, backup_files = _write_guarded_file_updates(staged_texts)
    return {
        "execution_mode": "guarded_write",
        "status": "applied",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "structured_patch_changes": structured_changes,
        "message": "Restored missing OpenFOAM boundaryField patch entries.",
    }


def _apply_guarded_control_dict_write_interval_patch(
    target_path: Path,
    *,
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    text = target_path.read_text(encoding="utf-8", errors="ignore")
    missing_tokens = _missing_selector_tokens(dry_run_validation)
    has_application = bool(
        re.search(r"(?mi)^\s*application\s+\S+\s*;\s*$", text)
    )
    has_start_from = bool(
        re.search(r"(?mi)^\s*startFrom\s+\S+\s*;\s*$", text)
    )
    has_write_interval = bool(
        re.search(r"(?mi)^\s*writeInterval\s+\S+\s*;\s*$", text)
    )
    if has_write_interval:
        return {
            "execution_mode": "guarded_write",
            "status": "no_change",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "structured_patch_changes": [],
            "message": "The guarded controlDict patch found that writeInterval already exists.",
        }
    unsupported_missing = [
        token for token in missing_tokens if token.lower() not in {"writeinterval"}
    ]
    if unsupported_missing:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded controlDict executor currently supports only missing writeInterval restoration."
            ),
        }
    if not has_application or not has_start_from:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded controlDict executor requires existing application and startFrom entries before restoring writeInterval."
            ),
        }
    updated_text = text.rstrip() + "\nwriteInterval 1;\n"
    changed_files, backup_files = _write_guarded_file_updates({target_path: updated_text})
    return {
        "execution_mode": "guarded_write",
        "status": "applied",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "structured_patch_changes": [
            {
                "path": str(target_path),
                "label": "writeInterval",
                "before_value": None,
                "after_value": "1",
            }
        ],
        "message": "Restored the missing controlDict writeInterval entry.",
    }


def _apply_guarded_fvsolution_relaxation_patch(
    target_path: Path,
    *,
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    text = target_path.read_text(encoding="utf-8", errors="ignore")
    missing_tokens = _missing_selector_tokens(dry_run_validation)
    has_solvers = bool(
        re.search(r"(?mi)^\s*solvers\s*$", text)
    )
    has_relaxation = bool(
        re.search(r"(?mi)^\s*relaxationFactors\s*$", text)
    )
    if has_relaxation:
        return {
            "execution_mode": "guarded_write",
            "status": "no_change",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "structured_patch_changes": [],
            "message": "The guarded fvSolution patch found that relaxationFactors already exists.",
        }
    unsupported_missing = [
        token for token in missing_tokens if token.lower() not in {"relaxationfactors"}
    ]
    if unsupported_missing:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded fvSolution executor currently supports only missing relaxationFactors restoration."
            ),
        }
    if not has_solvers:
        return {
            "execution_mode": "guarded_write",
            "status": "unsupported_executor",
            "applied": False,
            "executor_supported": False,
            "write_guard_status": dry_run_validation.get("status"),
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded fvSolution executor requires an existing solvers block before restoring relaxationFactors."
            ),
        }
    block = (
        "\nrelaxationFactors\n"
        "{\n"
        "    fields\n"
        "    {\n"
        "        p 0.3;\n"
        "    }\n"
        "    equations\n"
        "    {\n"
        "        U 0.7;\n"
        "    }\n"
        "}\n"
    )
    updated_text = text.rstrip() + block
    changed_files, backup_files = _write_guarded_file_updates({target_path: updated_text})
    return {
        "execution_mode": "guarded_write",
        "status": "applied",
        "applied": bool(changed_files),
        "executor_supported": True,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "backup_files": backup_files,
        "structured_patch_changes": [
            {
                "path": str(target_path),
                "label": "relaxationFactors",
                "before_value": None,
                "after_value": "fields:p=0.3,equations:U=0.7",
            }
        ],
        "message": "Restored the missing fvSolution relaxationFactors block.",
    }


def _execute_guarded_openfoam_dictionary_patch(
    execution_output: dict[str, Any],
    dry_run_validation: dict[str, Any],
) -> dict[str, Any]:
    target_path_map = _matched_target_path_map(dry_run_validation)
    target_files = [
        target_path_map[str(target).strip()]
        for target in list(execution_output.get("target_files", []))
        if str(target).strip() in target_path_map
    ]
    unique_targets = list(dict.fromkeys(target_files))
    if len(unique_targets) != 1:
        raise ValueError(
            f"Guarded OpenFOAM dictionary repair requires exactly one resolved target file; got {len(unique_targets)}."
        )
    target_path = unique_targets[0]
    if not target_path.is_file():
        raise ValueError(
            f"Guarded OpenFOAM dictionary repair target is not a file: {target_path}"
        )
    if target_path.name == "controlDict":
        return _apply_guarded_control_dict_write_interval_patch(
            target_path,
            dry_run_validation=dry_run_validation,
        )
    if target_path.name == "fvSolution":
        return _apply_guarded_fvsolution_relaxation_patch(
            target_path,
            dry_run_validation=dry_run_validation,
        )
    return {
        "execution_mode": "guarded_write",
        "status": "unsupported_executor",
        "applied": False,
        "executor_supported": False,
        "write_guard_status": dry_run_validation.get("status"),
        "changed_file_count": 0,
        "changed_files": [],
        "backup_files": [],
        "message": (
            "The guarded OpenFOAM dictionary executor currently supports controlDict writeInterval and fvSolution relaxationFactors restoration."
        ),
    }


def _build_guarded_execution_result(
    route_data: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    if not bool(details.get("selection_found")):
        return {
            "execution_mode": "guarded_write",
            "status": "selection_not_found",
            "applied": False,
            "executor_supported": False,
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": details.get("message")
            or "No deterministic edit selection matched the requested identifier.",
        }

    execution_output = (
        details.get("execution_output")
        if isinstance(details.get("execution_output"), dict)
        else {}
    )
    dry_run_validation = (
        details.get("dry_run_validation")
        if isinstance(details.get("dry_run_validation"), dict)
        else {}
    )
    selected_plan = (
        details.get("selected_edit_execution_plan")
        if isinstance(details.get("selected_edit_execution_plan"), dict)
        else {}
    )
    write_guard_status = str(dry_run_validation.get("status") or "unknown")
    if write_guard_status != "ready_for_write_guard" or not bool(
        dry_run_validation.get("write_guard_passed")
    ):
        return {
            "execution_mode": "guarded_write",
            "status": "blocked_by_write_guard",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": write_guard_status,
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": (
                "The guarded executor did not run because the selected plan has not passed the write guard."
            ),
        }

    output_kind = str(execution_output.get("output_kind") or "")
    try:
        if output_kind == "parameter_change_plan":
            return _execute_guarded_parameter_plan(execution_output, dry_run_validation)
        if output_kind == "structured_patch_plan":
            operations = [
                item
                for item in list(execution_output.get("patch_operations", []))
                if isinstance(item, dict)
            ]
            first_operation = operations[0] if operations else {}
            operation_kind = str(first_operation.get("operation_kind") or "")
            selector_mode = str(first_operation.get("selector_mode") or "")
            if (
                operation_kind == "rewrite_declared_paths"
                and selector_mode == "export_reference_entries"
            ):
                return _execute_guarded_export_reference_patch(
                    route_data,
                    execution_output,
                    dry_run_validation,
                )
            if (
                operation_kind == "restore_required_layout"
                and selector_mode == "required_case_paths"
            ):
                return _execute_guarded_required_case_layout_patch(
                    execution_output,
                    dry_run_validation,
                )
            if (
                operation_kind == "rename_declared_symbols"
                and selector_mode == "patch_name_entries"
            ):
                return _execute_guarded_openfoam_patch_name_entries(
                    execution_output,
                    dry_run_validation,
                )
            if (
                operation_kind == "repair_missing_entries"
                and selector_mode == "patch_field_entries"
            ):
                return _execute_guarded_openfoam_patch_field_entries(
                    execution_output,
                    dry_run_validation,
                )
            if (
                operation_kind == "repair_dictionary_references"
                and selector_mode == "dictionary_reference_entries"
            ):
                return _execute_guarded_openfoam_dictionary_patch(
                    execution_output,
                    dry_run_validation,
                )
            return {
                "execution_mode": "guarded_write",
                "status": "unsupported_executor",
                "applied": False,
            "executor_supported": False,
            "write_guard_status": write_guard_status,
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "executor_kind": selected_plan.get("executor_kind"),
            "message": (
                f"Guarded execution is not available for output kind '{output_kind}'."
            ),
        }
    except Exception as exc:
        return {
            "execution_mode": "guarded_write",
            "status": "failed",
            "applied": False,
            "executor_supported": True,
            "write_guard_status": write_guard_status,
            "changed_file_count": 0,
            "changed_files": [],
            "backup_files": [],
            "message": str(exc),
        }


def tool_runtime_retry_checks(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_runtime_remediation,
        action_kind="runtime_retry_checks",
        builder=_build_runtime_retry_checks,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_convergence_parameter_suggestions(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_convergence_tuning,
        action_kind="convergence_parameter_suggestions",
        builder=_build_convergence_parameter_suggestions,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_physics_interpretation_prompt(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
    ) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_physics_diagnosis,
        action_kind="physics_interpretation_prompt",
        builder=_build_physics_interpretation_prompt_payload,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_runtime_remediation_prompt(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_runtime_remediation,
        action_kind="runtime_remediation_prompt",
        builder=_build_runtime_remediation_prompt_payload,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_convergence_tuning_prompt(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_convergence_tuning,
        action_kind="convergence_tuning_prompt",
        builder=_build_convergence_tuning_prompt_payload,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_evidence_collection_plan(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    return _run_route_action_tool(
        tool_evidence_expansion,
        action_kind="evidence_collection_plan",
        builder=_build_evidence_collection_plan,
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )


def tool_selected_edit_execution_plan(
    *,
    results_dir: str,
    selection_id: str,
    selection_kind: str | None = None,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    payload, error = _build_diagnosis_payload(
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )
    if error is not None:
        return error

    try:
        route_data = _route_data_from_diagnosis_payload(payload)
        details = _build_selected_edit_execution_details(
            route_data,
            selection_id=selection_id,
            selection_kind=selection_kind,
        )
    except ValueError as exc:
        return _error("invalid_input", str(exc), details={"selection_id": selection_id, "selection_kind": selection_kind})

    return _ok(
        _safe_json_value(
            _route_action_payload(
                route_data,
                action_kind="selected_edit_execution_plan",
                details=details,
            )
        )
    )


def tool_execute_guarded_edit_plan(
    *,
    results_dir: str,
    selection_id: str,
    selection_kind: str | None = None,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    payload, error = _build_diagnosis_payload(
        results_dir=results_dir,
        inp_file=inp_file,
        ai=ai,
        guardrails_path=guardrails_path,
        history_db_path=history_db_path,
        model_name=model_name,
    )
    if error is not None:
        return error

    try:
        route_data = _route_data_from_diagnosis_payload(payload)
        details = _build_selected_edit_execution_details(
            route_data,
            selection_id=selection_id,
            selection_kind=selection_kind,
        )
    except ValueError as exc:
        return _error(
            "invalid_input",
            str(exc),
            details={"selection_id": selection_id, "selection_kind": selection_kind},
        )

    details = dict(details)
    details["execution_result"] = _build_guarded_execution_result(route_data, details)
    details["output_contract"] = list(details.get("output_contract", [])) + [
        "execution_result"
    ]
    return _ok(
        _safe_json_value(
            _route_action_payload(
                route_data,
                action_kind="execute_guarded_edit_plan",
                details=details,
            )
        )
    )


def tool_inp_check(*, inp_file: str) -> dict[str, Any]:
    try:
        inp_path = _resolve_path(inp_file, must_exist=True, kind="inp_file")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="inp_file", raw=inp_file)

    if not inp_path.is_file():
        return _error("invalid_input", "inp_file must be a file", details={"inp_file": str(inp_path)})

    parser = InpParser()
    try:
        blocks = parser.parse(inp_path)
    except Exception as exc:
        return _error("parse_error", str(exc), details={"inp_file": str(inp_path)})

    kw_list = load_kw_list()
    unknown_keywords: list[str] = []
    missing_required: list[dict[str, str]] = []
    seen_missing: set[tuple[str, str]] = set()

    for block in blocks:
        kw_def = kw_list.get(block.keyword_name)
        if kw_def is None:
            if block.keyword_name not in unknown_keywords:
                unknown_keywords.append(block.keyword_name)
            continue

        for arg in kw_def.get("arguments", []):
            arg_name = str(arg.get("name", "")).strip()
            if not arg_name:
                continue
            if bool(arg.get("required")) and not block.get_param(arg_name):
                key = (block.keyword_name, arg_name)
                if key in seen_missing:
                    continue
                seen_missing.add(key)
                missing_required.append(
                    {
                        "keyword": block.keyword_name,
                        "argument": arg_name,
                        "reason": "required_argument_missing",
                    }
                )

    return _ok(
        {
            "valid": not unknown_keywords and not missing_required,
            "inp_file": str(inp_path),
            "block_count": len(blocks),
            "unknown_keywords": unknown_keywords,
            "missing_required": missing_required,
        }
    )


def create_mcp_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - import is environment-dependent
        raise RuntimeError(
            "mcp is not installed. Install with: pip install \"cae-cxx[mcp]\""
        ) from exc

    mcp = FastMCP("cae-cli", json_response=True)

    @mcp.tool()
    def cae_health() -> dict[str, Any]:
        """Return runtime health and solver availability."""
        return tool_health()

    @mcp.tool()
    def cae_solvers() -> dict[str, Any]:
        """List registered solvers and installation status."""
        return tool_solvers()

    @mcp.tool()
    def cae_docker_status() -> dict[str, Any]:
        """Return Docker runtime availability, including Windows WSL Docker."""
        return tool_docker_status()

    @mcp.tool()
    def cae_docker_catalog(
        solver: str | None = None,
        capability: str | None = None,
        include_experimental: bool = True,
        runnable_only: bool = False,
    ) -> dict[str, Any]:
        """List built-in Docker solver image aliases."""
        return tool_docker_catalog(
            solver=solver,
            capability=capability,
            include_experimental=include_experimental,
            runnable_only=runnable_only,
        )

    @mcp.tool()
    def cae_docker_recommend(query: str, limit: int = 5) -> dict[str, Any]:
        """Recommend solver container aliases for a problem description."""
        return tool_docker_recommend(query=query, limit=limit)

    @mcp.tool()
    def cae_docker_images() -> dict[str, Any]:
        """List local Docker images visible to the Docker backend."""
        return tool_docker_images()

    @mcp.tool()
    def cae_docker_pull(
        image: str = "calculix",
        timeout: int = 3600,
        set_default: bool = False,
        use_default_config: bool = False,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Pull a Docker image by alias or direct image reference."""
        return tool_docker_pull(
            image=image,
            timeout=timeout,
            set_default=set_default,
            use_default_config=use_default_config,
            refresh=refresh,
        )

    @mcp.tool()
    def cae_docker_run(
        image: str,
        input_path: str,
        output_dir: str | None = None,
        command: str | None = None,
        timeout: int = 3600,
        cpus: str | None = None,
        memory: str | None = None,
        network: str = "none",
    ) -> dict[str, Any]:
        """Run a cataloged solver container with a generic case workflow."""
        return tool_docker_run(
            image=image,
            input_path=input_path,
            output_dir=output_dir,
            command=command,
            timeout=timeout,
            cpus=cpus,
            memory=memory,
            network=network,
        )

    @mcp.tool()
    def cae_docker_build_su2_runtime(
        tag: str = "local/su2-runtime:8.3.0",
        su2_version: str = "8.3.0",
        base_image: str = "mambaorg/micromamba:1.5.10",
        timeout: int = 3600,
        pull_base: bool = True,
        set_default: bool = True,
    ) -> dict[str, Any]:
        """Build a local SU2 runtime image exposing SU2_CFD."""
        return tool_docker_build_su2_runtime(
            tag=tag,
            su2_version=su2_version,
            base_image=base_image,
            timeout=timeout,
            pull_base=pull_base,
            set_default=set_default,
        )

    @mcp.tool()
    def cae_docker_calculix(
        inp_file: str,
        output_dir: str | None = None,
        image: str | None = None,
        timeout: int = 3600,
        cpus: str | None = None,
        memory: str | None = None,
    ) -> dict[str, Any]:
        """Run CalculiX through the standalone Docker feature."""
        return tool_docker_calculix(
            inp_file=inp_file,
            output_dir=output_dir,
            image=image,
            timeout=timeout,
            cpus=cpus,
            memory=memory,
        )

    @mcp.tool()
    def cae_solve(
        inp_file: str,
        output_dir: str | None = None,
        solver: str | None = None,
        timeout: int = 3600,
        solver_path: str | None = None,
    ) -> dict[str, Any]:
        """Run FEA solve for an .inp file and return structured output."""
        return tool_solve(
            inp_file=inp_file,
            output_dir=output_dir,
            solver=solver,
            timeout=timeout,
            solver_path=solver_path,
        )

    @mcp.tool()
    def cae_diagnose(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Run diagnosis and return structured evidence JSON."""
        return tool_diagnose(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_runtime_remediation(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return runtime-remediation follow-up context for failed solver runs."""
        return tool_runtime_remediation(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_convergence_tuning(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return convergence-tuning follow-up context for not-converged runs."""
        return tool_convergence_tuning(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_physics_diagnosis(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return physics-diagnosis follow-up context for successful solver runs."""
        return tool_physics_diagnosis(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_evidence_expansion(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return evidence-expansion follow-up context for unclassified solver runs."""
        return tool_evidence_expansion(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_runtime_retry_checks(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return a pre-retry runtime checklist for failed solver runs."""
        return tool_runtime_retry_checks(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_convergence_parameter_suggestions(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return deterministic convergence-parameter suggestions for not-converged runs."""
        return tool_convergence_parameter_suggestions(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_runtime_remediation_prompt(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return an Agent-ready runtime-remediation prompt package."""
        return tool_runtime_remediation_prompt(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_convergence_tuning_prompt(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return an Agent-ready convergence-tuning prompt package."""
        return tool_convergence_tuning_prompt(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_physics_interpretation_prompt(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return a grounded prompt/context package for physics interpretation."""
        return tool_physics_interpretation_prompt(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_evidence_collection_plan(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return an ordered evidence-collection plan for unclassified runs."""
        return tool_evidence_collection_plan(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_selected_edit_execution_plan(
        results_dir: str,
        selection_id: str,
        selection_kind: str | None = None,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Expand one deterministic edit payload or execution plan into a single preview-only write plan."""
        return tool_selected_edit_execution_plan(
            results_dir=results_dir,
            selection_id=selection_id,
            selection_kind=selection_kind,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_execute_guarded_edit_plan(
        results_dir: str,
        selection_id: str,
        selection_kind: str | None = None,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute one guarded write plan after the selected preview plan passes the write guard."""
        return tool_execute_guarded_edit_plan(
            results_dir=results_dir,
            selection_id=selection_id,
            selection_kind=selection_kind,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_inp_check(inp_file: str) -> dict[str, Any]:
        """Validate INP structure and required keyword arguments."""
        return tool_inp_check(inp_file=inp_file)

    return mcp


def main() -> None:  # pragma: no cover - exercised in real MCP runtime
    try:
        mcp = create_mcp_server()
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
