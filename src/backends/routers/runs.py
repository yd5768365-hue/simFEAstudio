import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from fastapi import APIRouter, Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

try:
    from ..state import remote_runs
except ImportError:
    from state import remote_runs

try:
    from ..simfea_api.config import ComputeNode, PROJECT_ROOT, settings, SolverDefinition
    from ..simfea_api.run_archive import (
        RemoteRun,
        ensure_run_files,
        load_archived_runs,
        read_optional_text,
        replay_run_events,
        run_metadata,
        save_run_metadata,
    )
    from ..simfea_api.results import generate_result_summary
    from ..simfea_api.learning import (
        compose_note_md as service_compose_note_md,
        export_learning_record,
        generate_learning_report,
        guided_questions as service_guided_questions,
        parse_note_answers as service_parse_note_answers,
    )
    from ..simfea_api.analytics import analyze_run as service_analyze_run
    from ..simfea_api.runners.solver import build_solver_run_script, public_solver
    from ..simfea_api.runners.ssh import is_local_node, remote_workdir_for, sh_quote
    from ..simfea_api.runners.slurm import build_slurm_job_script, build_slurm_submit_script
    from ..simfea_api.runners.workflow import (
        FREECAD_PREPOMAX_STEP_ALIASES,
        FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        public_freecad_prepomax_workflow,
        public_workflow,
        workflow_artifact_patterns,
    )
    from ..routers._helpers import get_compute_node, get_solver, utc_now
except ImportError:
    from simfea_api.config import ComputeNode, PROJECT_ROOT, settings, SolverDefinition
    from simfea_api.run_archive import (
        RemoteRun,
        ensure_run_files,
        load_archived_runs,
        read_optional_text,
        replay_run_events,
        run_metadata,
        save_run_metadata,
    )
    from simfea_api.results import generate_result_summary
    from simfea_api.learning import (
        compose_note_md as service_compose_note_md,
        export_learning_record,
        generate_learning_report,
        guided_questions as service_guided_questions,
        parse_note_answers as service_parse_note_answers,
    )
    from simfea_api.analytics import analyze_run as service_analyze_run
    from simfea_api.runners.solver import build_solver_run_script, public_solver
    from simfea_api.runners.ssh import is_local_node, remote_workdir_for, sh_quote
    from simfea_api.runners.slurm import build_slurm_job_script, build_slurm_submit_script
    from simfea_api.runners.workflow import (
        FREECAD_PREPOMAX_STEP_ALIASES,
        FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        public_freecad_prepomax_workflow,
        public_workflow,
        workflow_artifact_patterns,
    )
    from routers._helpers import get_compute_node, get_solver, utc_now


class T_Note(TypedDict, total=False):
    note: str
    answers: dict
    export: bool
    format: str
    target_dir: str


class T_LearningExport(TypedDict, total=False):
    format: str
    target_dir: str


class T_CustomWorkflow(TypedDict):
    steps: list[str | dict[str, object]]


runs_router = APIRouter(prefix="/v1")


@runs_router.get("/runs")
def list_runs():
    try:
        from ..execution import _load_demo_runs
    except ImportError:
        from execution import _load_demo_runs
    current = settings()
    archived = load_archived_runs()
    runs = archived if archived else _load_demo_runs()
    return {
        "message": "SimFEA Studio archived runs loaded.",
        "data": {
            "runs_root": str(current.runs_root),
            "learning_export_root": str(current.learning_export_root),
            "learning_formats": current.learning_formats,
            "learning_default_format": current.learning_default_format,
            "runs": runs,
        },
    }


@runs_router.get("/runs/{run_id}")
def get_run(run_id: str):
    try:
        from ..execution import _DEMO_RUNS_DIR
    except ImportError:
        from execution import _DEMO_RUNS_DIR
    # Demo data fallback
    demo_dir = _DEMO_RUNS_DIR / run_id
    if demo_dir.is_dir():
        meta_path = demo_dir / "meta.json"
        if meta_path.exists():
            demo_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            demo_meta["note"] = read_optional_text(demo_dir / "note.md")
            demo_meta["report"] = read_optional_text(demo_dir / "learning_report.md")
            demo_meta["stdout"] = read_optional_text(demo_dir / "stdout.log")
            demo_meta["stderr"] = read_optional_text(demo_dir / "stderr.log")
            return {"message": "Demo run loaded.", "data": demo_meta}

    run = remote_runs.get(run_id)
    if run is not None:
        summary = generate_result_summary(run.local_dir)
        note = (run.local_dir / "note.md").read_text(encoding="utf-8")
        report = read_optional_text(run.local_dir / "learning_report.md")
        data = run_metadata(run)
        meta_path = run.local_dir / "meta.json"
        if meta_path.exists():
            archived_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for key in ("learning_export", "learning_exports"):
                if key in archived_meta:
                    data[key] = archived_meta[key]
        return {
            "message": "SimFEA Studio run loaded.",
            "data": {
                **data,
                "note": note,
                "report": report,
                "summary": summary,
            },
        }

    runs_root = settings().runs_root
    run_dir = runs_root / run_id
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    note_path = runs_root / run_id / "note.md"
    report_path = runs_root / run_id / "learning_report.md"
    meta.setdefault("toolchain", settings().toolchain)
    meta["note"] = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    meta["report"] = read_optional_text(report_path)
    meta["summary"] = summary
    if report_path.exists():
        meta["learning_report"] = "learning_report.md"
    return {
        "message": "SimFEA Studio archived run loaded.",
        "data": meta,
    }


@runs_router.get("/runs/{run_id}/result-summary")
def get_run_result_summary(run_id: str):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    return {
        "message": "SimFEA Studio result summary generated.",
        "data": {
            "run_id": run_id,
            "summary_path": str(run_dir / "artifacts" / "result_summary.json"),
            "summary": summary,
        },
    }


@runs_router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
def get_run_artifact(run_id: str, artifact_path: str):
    run_dir = (settings().runs_root / run_id).resolve()
    artifact = (run_dir / artifact_path).resolve()

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        artifact.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")

    media_type = "text/plain"
    if artifact.suffix.lower() == ".json":
        media_type = "application/json"
    elif artifact.suffix.lower() in {".vtk", ".vtu"}:
        media_type = "model/vnd.vtk"

    return FileResponse(artifact, media_type=media_type, filename=artifact.name)


@runs_router.get("/runs/{run_id}/report")
def get_run_report(run_id: str):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["learning_report"] = "learning_report.md"
        meta["result_summary"] = "artifacts/result_summary.json" if summary else None
        meta.setdefault("toolchain", settings().toolchain)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "message": "SimFEA Studio learning report generated.",
        "data": {
            "run_id": run_id,
            "report_path": str(report_path),
            "report": report_path.read_text(encoding="utf-8"),
            "summary": summary,
        },
    }


@runs_router.post("/runs/{run_id}/learning-export")
def export_run_learning_record(run_id: str, payload: T_LearningExport = Body(default={})):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "exported": False,
                "run_id": run_id,
            },
        }

    try:
        export_result = export_learning_record(
            run_dir,
            payload.get("format"),
            payload.get("target_dir"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "SimFEA Studio learning record exported.",
        "data": {
            "exported": True,
            **export_result,
        },
    }


@runs_router.post("/runs/{alias}/demo")
async def start_demo_run(alias: str):
    try:
        from ..execution import build_evidence_demo_script, execute_local_run, execute_remote_run
    except ImportError:
        from execution import build_evidence_demo_script, execute_local_run, execute_remote_run
    node = get_compute_node(alias)
    current = settings()
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    remote_workdir = remote_workdir_for(node, run_id)
    local_dir = current.runs_root / run_id
    run = RemoteRun(
        run_id=run_id,
        case_name="远程闭环样例",
        solver="demo-shell",
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=remote_workdir,
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="",
        created_at=utc_now(),
        toolchain=current.toolchain,
    )
    ensure_run_files(run)
    remote_runs[run_id] = run
    if is_local_node(node):
        asyncio.create_task(execute_local_run(run))
    else:
        run.command = f"bash -lc {sh_quote(build_evidence_demo_script(run))}"
        save_run_metadata(run)
        asyncio.create_task(execute_remote_run(run, node))
    return {
        "message": f"{node.alias} remote evidence run started.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
        },
    }


@runs_router.post("/runs/{alias}/slurm-demo")
async def start_slurm_demo_run(alias: str):
    try:
        from ..execution import execute_slurm_run
    except ImportError:
        from execution import execute_slurm_run
    node = get_compute_node(alias)
    current = settings()
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    remote_workdir = remote_workdir_for(node, run_id)
    local_dir = current.runs_root / run_id
    run = RemoteRun(
        run_id=run_id,
        case_name="Slurm 远程闭环样例",
        solver="demo-slurm-shell",
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=remote_workdir,
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="",
        created_at=utc_now(),
        runner="SlurmRunner",
        toolchain=current.toolchain,
        scheduler="slurm",
        partition="dg83",
        requested_cpus=4,
        requested_memory="8G",
    )
    run.slurm_script = build_slurm_job_script(run)
    run.command = f"bash -lc {sh_quote(build_slurm_submit_script(run))}"
    ensure_run_files(run)
    remote_runs[run_id] = run
    asyncio.create_task(execute_slurm_run(run, node))
    return {
        "message": f"{node.alias} Slurm evidence run submitted.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
            "scheduler": run.scheduler,
            "partition": run.partition,
            "requested_cpus": run.requested_cpus,
            "requested_memory": run.requested_memory,
        },
    }


@runs_router.post("/runs/{alias}/solvers/{solver_alias}")
async def start_solver_run(alias: str, solver_alias: str):
    try:
        from ..execution import _execute_docker_run, execute_local_run, execute_remote_run
    except ImportError:
        from execution import _execute_docker_run, execute_local_run, execute_remote_run
    node = get_compute_node(alias)
    solver = get_solver(solver_alias)
    current = settings()

    # ── Preflight check on INP content ──
    preflight_warnings: list[dict] = []
    inp_content = solver.input_files.get("model.inp", "")
    if not inp_content:
        # Find first .inp file
        for k, v in solver.input_files.items():
            if k.lower().endswith(".inp"):
                inp_content = v
                break
    if inp_content:
        try:
            import tempfile as _tmp
            from cae_preflight_lib.preflight import run_preflight as _run_preflight
            tf = _tmp.NamedTemporaryFile(mode="w", suffix=".inp", delete=False, encoding="utf-8")
            try:
                tf.write(inp_content)
                tf.close()
                pf_result = _run_preflight(Path(tf.name))
                for issue in pf_result.issues:
                    if issue.severity in ("error", "warning"):
                        preflight_warnings.append({
                            "severity": issue.severity,
                            "category": issue.category,
                            "message": issue.message,
                        })
            finally:
                try:
                    os.unlink(tf.name)
                except OSError:
                    pass
        except Exception:
            pass  # preflight is best-effort, don't block submission

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    remote_workdir = remote_workdir_for(node, run_id)
    local_dir = current.runs_root / run_id
    run = RemoteRun(
        run_id=run_id,
        case_name=f"{solver.label} solver adapter run",
        solver=solver.alias,
        solver_label=solver.label,
        solver_kind=solver.kind,
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=remote_workdir,
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="",
        created_at=utc_now(),
        runner="SolverRunner",
        toolchain=current.toolchain,
        artifact_patterns=solver.artifact_patterns,
        input_files=solver.input_files,
    )
    ensure_run_files(run)
    remote_runs[run_id] = run
    if getattr(node, "node_type", "") == "docker":
        asyncio.create_task(_execute_docker_run(run, solver))
    elif is_local_node(node):
        asyncio.create_task(execute_local_run(run, solver))
    else:
        run.command = f"bash -lc {sh_quote(build_solver_run_script(run, solver))}"
        save_run_metadata(run)
        asyncio.create_task(execute_remote_run(run, node))
    return {
        "message": f"{node.alias} {solver.alias} solver run started.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
            "solver": public_solver(solver),
            "preflight_issues": preflight_warnings,
        },
    }


@runs_router.post("/runs/{alias}/workflows/freecad-prepomax")
async def start_freecad_prepomax_workflow(alias: str):
    try:
        from ..execution import execute_local_workflow_run
    except ImportError:
        from execution import execute_local_workflow_run
    node = get_compute_node(alias)
    if not is_local_node(node):
        raise HTTPException(status_code=400, detail="FreeCAD -> PrePoMax workflow currently runs on the local node.")

    solvers = [get_solver(step_alias) for step_alias in FREECAD_PREPOMAX_STEP_ALIASES]
    current = settings()
    run_id = f"run_{FREECAD_PREPOMAX_WORKFLOW_ALIAS}_{uuid.uuid4().hex[:8]}"
    local_dir = current.runs_root / run_id
    workflow = public_freecad_prepomax_workflow(solvers)
    run = RemoteRun(
        run_id=run_id,
        case_name="FreeCAD to PrePoMax workflow run",
        solver=FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        solver_label=workflow["label"],
        solver_kind=workflow["kind"],
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=str(local_dir),
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="WorkflowRunner",
        created_at=utc_now(),
        runner="WorkflowRunner",
        toolchain=current.toolchain,
        artifact_patterns=workflow_artifact_patterns(solvers),
    )
    ensure_run_files(run)
    remote_runs[run_id] = run
    asyncio.create_task(execute_local_workflow_run(run, solvers))
    return {
        "message": f"{node.alias} FreeCAD -> PrePoMax workflow started.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
            "workflow": workflow,
        },
    }


@runs_router.post("/runs/{alias}/workflows/custom")
async def start_custom_workflow(alias: str, payload: T_CustomWorkflow = Body(...)):
    try:
        from ..execution import execute_local_workflow_run
    except ImportError:
        from execution import execute_local_workflow_run
    node = get_compute_node(alias)
    if not is_local_node(node):
        raise HTTPException(status_code=400, detail="Custom workflow currently runs on the local node only.")

    current = settings()
    requested_steps = payload.get("steps", [])

    # Normalize steps: accept both string aliases and {solver, params} dicts
    step_params: dict[str, dict] = {}
    step_aliases: list[str] = []
    for item in requested_steps:
        if isinstance(item, str):
            step_aliases.append(item)
        elif isinstance(item, dict):
            alias = str(item.get("solver", ""))
            if alias:
                step_aliases.append(alias)
                step_params[alias] = {k: v for k, v in item.items() if k != "solver"}

    solvers: list[SolverDefinition] = []
    skipped: list[str] = []
    for step_alias in step_aliases:
        solver = current.solvers.get(step_alias)
        if solver is not None:
            solvers.append(solver)
        else:
            skipped.append(step_alias)

    if not solvers:
        raise HTTPException(
            status_code=400,
            detail=f"No executable solver steps found. Skipped (no config): {', '.join(skipped) if skipped else 'none'}",
        )

    slug = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"run_wf_custom_{slug}_{uuid.uuid4().hex[:8]}"
    local_dir = current.runs_root / run_id
    label = " -> ".join(s.label for s in solvers)
    workflow = public_workflow("custom", label, solvers)

    run = RemoteRun(
        run_id=run_id,
        case_name=f"Custom workflow: {label}",
        solver="custom-workflow",
        solver_label=workflow["label"],
        solver_kind=workflow["kind"],
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=str(local_dir),
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="WorkflowRunner",
        created_at=utc_now(),
        runner="WorkflowRunner",
        toolchain=current.toolchain,
        artifact_patterns=workflow_artifact_patterns(solvers),
    )
    ensure_run_files(run)
    remote_runs[run_id] = run

    # Store per-step parameters in metadata for workflow execution
    if step_params:
        meta = run_metadata(run)
        meta["workflow_step_params"] = step_params
        save_run_metadata(run, meta)

    asyncio.create_task(execute_local_workflow_run(run, solvers))

    return {
        "message": f"Custom workflow ({len(solvers)} steps: {label}) started on {node.alias}.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
            "workflow": workflow,
            "skipped_steps": skipped,
        },
    }


@runs_router.post("/runs/{run_id}/note")
def save_run_note(run_id: str, payload: T_Note = Body(...)):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "saved": False,
                "run_id": run_id,
            },
        }

    answers = payload.get("answers")
    note_path = run_dir / "note.md"

    if answers and isinstance(answers, dict):
        meta_path = run_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        note_path.write_text(service_compose_note_md(answers, meta), encoding="utf-8")
    else:
        note = payload.get("note", "")
        note_path.write_text(note, encoding="utf-8")

    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    export_result = None
    if payload.get("export"):
        export_result = export_learning_record(
            run_dir,
            payload.get("format"),
            payload.get("target_dir"),
        )
    return {
        "message": "SimFEA Studio learning note saved.",
        "data": {
            "saved": True,
            "run_id": run_id,
            "note_path": str(note_path),
            "report_path": str(report_path),
            "summary_path": str(run_dir / "artifacts" / "result_summary.json") if summary else "",
            "learning_export": export_result,
        },
    }


@runs_router.get("/runs/{run_id}/guided-questions")
def get_guided_questions(run_id: str):
    run_dir = settings().runs_root / run_id
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    analysis = service_analyze_run(run_dir)
    questions = service_guided_questions(meta, analysis)

    # Fill in existing answers from note.md
    note_path = run_dir / "note.md"
    if note_path.exists():
        existing = service_parse_note_answers(read_optional_text(note_path, "").strip())
        if existing:
            for q in questions:
                if q["id"] in existing:
                    q["answer"] = existing[q["id"]]
                elif "note" in existing and q["id"] == "purpose":
                    # Legacy free-text note: use as the "purpose" answer
                    q["answer"] = existing["note"]

    return {
        "message": "Guided note questions for this run.",
        "data": {
            "run_id": run_id,
            "questions": questions,
        },
    }


@runs_router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    try:
        from ..execution import cancel_slurm_job, emit_remote_event
    except ImportError:
        from execution import cancel_slurm_job, emit_remote_event
    run = remote_runs.get(run_id)
    if run is None:
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "run_id": run_id,
                "cancel_requested": False,
                "status": "missing",
            },
        }

    if run.status not in {"created", "submitting", "queued", "running", "canceling"}:
        return {
            "message": "SimFEA Studio run is already finished.",
            "data": {
                "run_id": run_id,
                "cancel_requested": False,
                "status": run.status,
                "exit_code": run.exit_code,
            },
        }

    run.cancel_requested = True
    run.status = "canceling"
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="canceling",
        line="已请求取消远程任务，正在终止 SSH 通道。",
    )

    if run.runner == "SlurmRunner" and run.job_id:
        try:
            await cancel_slurm_job(run, get_compute_node(run.node_alias))
        except Exception as exc:
            await emit_remote_event(run, "stderr", line=f"Slurm 取消请求失败：{exc}")
    elif run.process is not None and run.process.returncode is None:
        try:
            run.process.terminate()
        except ProcessLookupError:
            pass

    return {
        "message": "SimFEA Studio cancel request sent.",
        "data": {
            "run_id": run_id,
            "cancel_requested": True,
            "status": run.status,
        },
    }


@runs_router.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str, from_seq: int | None = None):
    run = remote_runs.get(run_id)
    if run is None:
        async def missing_run_events():
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "run_id": run_id,
                        "type": "finished",
                        "seq": 0,
                        "archive_path": "",
                        "status": "failed",
                        "exit_code": -1,
                        "line": "没有找到这个运行任务。",
                    },
                    ensure_ascii=False,
                ),
            }

        return EventSourceResponse(missing_run_events())

    async def event_generator():
        replayed = replay_run_events(run, from_seq)
        for event in replayed:
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

        if run._stream_closed or run.status in ("finished", "failed", "canceled"):
            if replayed and replayed[-1].get("type") == "finished":
                return
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "run_id": run.run_id,
                        "type": "finished",
                        "seq": run._event_seq,
                        "archive_path": str(run.local_dir),
                        "status": run.status,
                        "exit_code": run.exit_code if run.exit_code is not None else -1,
                        "line": "运行已结束。",
                    },
                    ensure_ascii=False,
                ),
            }
            return

        while True:
            event = await run.queue.get()
            if event is None:
                run._stream_closed = True
                break
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
