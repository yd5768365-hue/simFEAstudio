import asyncio
import json
import subprocess
import os
import signal
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from uvicorn import Config, Server

try:
    from .inference import infer_text_api
except ImportError:
    from inference import infer_text_api

try:
    from .routers.benchmarks import benchmarks_router
    from .routers.config import config_router
    from .routers.compute_nodes import compute_nodes_router
    from .routers._helpers import get_compute_node, get_solver, parse_key_value_stdout, public_compute_node, utc_now
    from .routers.experiments import experiments_router
    from .routers.knowledge import knowledge_router
    from .routers.preflight import preflight_router
    from .routers.runs import runs_router
    from .routers.toolchain import toolchain_router
except ImportError:
    from routers.benchmarks import benchmarks_router
    from routers.config import config_router
    from routers.compute_nodes import compute_nodes_router
    from routers._helpers import get_compute_node, get_solver, parse_key_value_stdout, public_compute_node, utc_now
    from routers.experiments import experiments_router
    from routers.knowledge import knowledge_router
    from routers.preflight import preflight_router
    from routers.runs import runs_router
    from routers.toolchain import toolchain_router

try:
    from .simfea_api.config import ComputeNode, PROJECT_ROOT, SolverDefinition, settings
    from .simfea_api.run_archive import (
        RemoteRun,
        append_text,
        ensure_run_files,
        load_archived_runs,
        remember_run_event,
        read_optional_text,
        replay_run_events,
        run_metadata,
        save_run_metadata,
    )
    from .simfea_api.analytics import analyze_run as service_analyze_run
    from .simfea_api.learning import (
        compose_note_md as service_compose_note_md,
        export_learning_record as service_export_learning_record,
        generate_learning_report as service_generate_learning_report,
        guided_questions as service_guided_questions,
        parse_note_answers as service_parse_note_answers,
    )
    from .simfea_api.results import (
        generate_result_summary as service_generate_result_summary,
        post_process_solver_artifacts,
        run_artifacts as service_run_artifacts,
    )
    from .simfea_api.runners.ssh import (
        build_scp_command as runner_build_scp_command,
        build_ssh_command as runner_build_ssh_command,
        is_local_node as runner_is_local_node,
        remote_workdir_for as runner_remote_workdir_for,
        run_command as runner_run_command,
        sh_quote as runner_sh_quote,
    )
    from .cae_preflight_lib.sta_monitor import StaMonitor
    from .simfea_api.runners.slurm import (
        build_slurm_job_script as runner_build_slurm_job_script,
        build_slurm_submit_script as runner_build_slurm_submit_script,
        parse_sbatch_job_id as runner_parse_sbatch_job_id,
        query_slurm_state as runner_query_slurm_state,
        request_slurm_cancel as runner_request_slurm_cancel,
    )
    from .simfea_api.runners.remote_files import (
        download_remote_file as runner_download_remote_file,
        download_remote_artifacts as runner_download_remote_artifacts,
        download_remote_result as runner_download_remote_result,
        download_slurm_artifacts as runner_download_slurm_artifacts,
        read_remote_text as runner_read_remote_text,
        sync_remote_log_file as runner_sync_remote_log_file,
    )
    from .simfea_api.runners.slurm_polling import (
        apply_slurm_completion_status as runner_apply_slurm_completion_status,
        poll_slurm_until_done as runner_poll_slurm_until_done,
    )
    from .simfea_api.runners.solver import (
        build_solver_probe_command as runner_build_solver_probe_command,
        probe_local_solvers as runner_probe_local_solvers,
        build_solver_run_script as runner_build_solver_run_script,
        public_solver as runner_public_solver,
        render_command_template as runner_render_command_template,
    )
    from .simfea_api.runners.workflow import (
        FREECAD_PREPOMAX_STEP_ALIASES,
        FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        public_freecad_prepomax_workflow,
        public_workflow,
        workflow_artifact_patterns,
    )
    from .simfea_api.cleanup import cleanup_old_runs
    from .simfea_api.install import start_install, event_generator
    from .simfea_api.toolchain import _scan_solver_install, update_solver_executable, verify_solver_install
    from .simfea_api.logger import create_logger
    from .simfea_api.security import safe_child_dir, safe_upload_path
except ImportError:
    from simfea_api.cleanup import cleanup_old_runs
    from simfea_api.config import ComputeNode, PROJECT_ROOT, SolverDefinition, settings
    from simfea_api.run_archive import (
        RemoteRun,
        append_text,
        ensure_run_files,
        load_archived_runs,
        remember_run_event,
        read_optional_text,
        replay_run_events,
        run_metadata,
        save_run_metadata,
    )
    from simfea_api.analytics import analyze_run as service_analyze_run
    from simfea_api.learning import (
        compose_note_md as service_compose_note_md,
        export_learning_record as service_export_learning_record,
        generate_learning_report as service_generate_learning_report,
        guided_questions as service_guided_questions,
        parse_note_answers as service_parse_note_answers,
    )
    from simfea_api.results import (
        generate_result_summary as service_generate_result_summary,
        post_process_solver_artifacts,
        run_artifacts as service_run_artifacts,
    )
    from simfea_api.runners.ssh import (
        build_scp_command as runner_build_scp_command,
        build_ssh_command as runner_build_ssh_command,
        is_local_node as runner_is_local_node,
        remote_workdir_for as runner_remote_workdir_for,
        run_command as runner_run_command,
        sh_quote as runner_sh_quote,
    )
    from simfea_api.runners.slurm import (
        build_slurm_job_script as runner_build_slurm_job_script,
        build_slurm_submit_script as runner_build_slurm_submit_script,
        parse_sbatch_job_id as runner_parse_sbatch_job_id,
        query_slurm_state as runner_query_slurm_state,
        request_slurm_cancel as runner_request_slurm_cancel,
    )
    from simfea_api.runners.remote_files import (
        download_remote_file as runner_download_remote_file,
        download_remote_artifacts as runner_download_remote_artifacts,
        download_remote_result as runner_download_remote_result,
        download_slurm_artifacts as runner_download_slurm_artifacts,
        read_remote_text as runner_read_remote_text,
        sync_remote_log_file as runner_sync_remote_log_file,
    )
    from simfea_api.runners.slurm_polling import (
        apply_slurm_completion_status as runner_apply_slurm_completion_status,
        poll_slurm_until_done as runner_poll_slurm_until_done,
    )
    from simfea_api.runners.solver import (
        build_solver_probe_command as runner_build_solver_probe_command,
        probe_local_solvers as runner_probe_local_solvers,
        build_solver_run_script as runner_build_solver_run_script,
        public_solver as runner_public_solver,
        render_command_template as runner_render_command_template,
    )
    from simfea_api.runners.workflow import (
        FREECAD_PREPOMAX_STEP_ALIASES,
        FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        public_freecad_prepomax_workflow,
        public_workflow,
        workflow_artifact_patterns,
    )
    from simfea_api.install import start_install, event_generator
    from simfea_api.toolchain import _scan_solver_install, update_solver_executable, verify_solver_install
    from simfea_api.logger import create_logger
    from simfea_api.security import safe_child_dir, safe_upload_path

log = create_logger("sidecar")

server_instance = None

try:
    from .state import remote_runs
except ImportError:
    from state import remote_runs

try:
    from .execution import (
        build_evidence_demo_script,
        cancel_slurm_job,
        docker_cli_executable,
        emit_finished_event,
        emit_remote_event,
        execute_local_run,
        execute_local_workflow_run,
        execute_remote_run,
        execute_slurm_run,
        persist_run_outputs,
        read_stream_lines,
        _execute_docker_run,
        _load_demo_runs,
        _run_local_command,
        _run_local_solver_step,
    )
except ImportError:
    from execution import (
        build_evidence_demo_script,
        cancel_slurm_job,
        docker_cli_executable,
        emit_finished_event,
        emit_remote_event,
        execute_local_run,
        execute_local_workflow_run,
        execute_remote_run,
        execute_slurm_run,
        persist_run_outputs,
        read_stream_lines,
        _execute_docker_run,
        _load_demo_runs,
        _run_local_command,
        _run_local_solver_step,
    )


def docker_cli_executable() -> str:
    docker = shutil.which("docker")
    if docker:
        return docker
    windows_docker = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
    if windows_docker.exists():
        return str(windows_docker)
    return "docker"

app = FastAPI(
    title="SimFEA Studio API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(benchmarks_router)
app.include_router(config_router)
app.include_router(compute_nodes_router)
app.include_router(experiments_router)
app.include_router(knowledge_router)
app.include_router(preflight_router)
app.include_router(runs_router)
app.include_router(toolchain_router)



def kill_process():
    os.kill(os.getpid(), signal.SIGINT)


def start_api_server(**kwargs):
    global server_instance
    port = kwargs.get("port", settings().api_port)
    try:
        if server_instance is None:
            log.info("Starting API server...", port=port)
            config = Config(app, host="0.0.0.0", port=port, log_level="info")
            server_instance = Server(config)
            asyncio.run(server_instance.serve())
        else:
            log.warn("Failed to start new server. Server instance already running.")
    except Exception as e:
        log.error(f"Failed to start API server: {e}")


def stdin_loop():
    log.info("Waiting for commands...")
    while True:
        raw_input = sys.stdin.readline()
        if raw_input == "":
            # When the sidecar is launched without an attached stdin, readline()
            # returns immediately. Avoid flooding the UI log while the API runs.
            threading.Event().wait(0.25)
            continue
        user_input = raw_input.strip()
        match user_input:
            case "sidecar shutdown":
                log.info("Received shutdown command.")
                kill_process()
            case _:
                log.warn(f"Invalid command: {user_input}")


def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True
        input_thread.start()
    except Exception:
        log.error("Failed to start input handler.")


# ── Serve frontend static files ──
# Priority: SIMFEA_FRONTEND env → pip package dir → dev dist/
def _find_frontend_dir() -> Path | None:
    env_path = os.getenv("SIMFEA_FRONTEND")
    if env_path:
        p = Path(env_path)
        if (p / "index.html").exists():
            return p
    # pip install: frontend bundled inside the package
    pkg_dist = Path(__file__).resolve().parent / "frontend"
    if (pkg_dist / "index.html").exists():
        return pkg_dist
    # dev mode: Vite build output at project root
    dev_dist = PROJECT_ROOT / "dist"
    if (dev_dist / "index.html").exists():
        return dev_dist
    return None

_frontend_dir = _find_frontend_dir()
if _frontend_dir:
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="spa")

if __name__ == "__main__":
    try:
        result = cleanup_old_runs(settings())
        if result["removed"]:
            log.info(f"Startup cleanup: removed {result['removed']} old runs, {result['kept']} kept")
    except Exception as e:
        log.warn(f"Startup cleanup skipped: {e}")

    if sys.stdin.isatty():
        # Standalone mode: python main.py 直接启动
        import uvicorn

        port = settings().api_port
        print(f"\n  SimFEA Studio 启动 → http://localhost:{port}\n")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Tauri sidecar 模式：stdin 监听生命周期命令
        start_input_thread()
        start_api_server()
