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


run_artifacts = service_run_artifacts
generate_result_summary = service_generate_result_summary
generate_learning_report = service_generate_learning_report
export_learning_record = service_export_learning_record
build_scp_command = runner_build_scp_command
build_ssh_command = runner_build_ssh_command
is_local_node = runner_is_local_node
remote_workdir_for = runner_remote_workdir_for
run_command = runner_run_command
sh_quote = runner_sh_quote
build_slurm_job_script = runner_build_slurm_job_script
build_slurm_submit_script = runner_build_slurm_submit_script
parse_sbatch_job_id = runner_parse_sbatch_job_id
query_slurm_state = runner_query_slurm_state
download_remote_file = runner_download_remote_file
download_remote_artifacts = runner_download_remote_artifacts
download_remote_result = runner_download_remote_result
download_slurm_artifacts = runner_download_slurm_artifacts
read_remote_text = runner_read_remote_text
sync_remote_log_file = runner_sync_remote_log_file
poll_slurm_until_done = runner_poll_slurm_until_done
apply_slurm_completion_status = runner_apply_slurm_completion_status
build_solver_probe_command = runner_build_solver_probe_command
probe_local_solvers = runner_probe_local_solvers
build_solver_run_script = runner_build_solver_run_script
public_solver = runner_public_solver
render_command_template = runner_render_command_template


def persist_run_outputs(run: RemoteRun):
    save_run_metadata(run)
    generate_result_summary(run.local_dir)
    save_run_metadata(run)
    # learning_report is deferred until the user writes their note (save_run_note)


async def emit_finished_event(
    run: RemoteRun,
    *,
    status: str,
    exit_code: int,
    line: str,
    include_archive_path: bool = False,
    include_job_fields: bool = False,
):
    payload = {
        "status": status,
        "exit_code": exit_code,
        "line": line,
    }
    if include_archive_path:
        payload["archive_path"] = str(run.local_dir)
    if include_job_fields:
        payload["job_id"] = run.job_id
        payload["allocated_node"] = run.allocated_node
    await emit_remote_event(run, "finished", **payload)


async def emit_remote_event(run: RemoteRun, event_type: str, **payload):
    run._event_seq += 1
    message = {
        "run_id": run.run_id,
        "type": event_type,
        "seq": run._event_seq,
        "archive_path": str(run.local_dir),
        **payload,
    }
    append_text(run.local_dir / "events.jsonl", json.dumps(message, ensure_ascii=False))
    remember_run_event(run, message)
    await run.queue.put(message)


async def read_stream_lines(run: RemoteRun, stream, event_type: str):
    log_name = "stdout.log" if event_type == "stdout" else "stderr.log"
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        append_text(run.local_dir / log_name, text)
        await emit_remote_event(run, event_type, line=text)



def build_evidence_demo_script(run: RemoteRun):
    return f"""
set -e
RUN_ID={sh_quote(run.run_id)}
REMOTE_WORKDIR={sh_quote(run.remote_workdir)}
mkdir -p "$REMOTE_WORKDIR"
cd "$REMOTE_WORKDIR"
cat > input.txt <<'EOF'
case=悬臂梁远程闭环样例
solver=demo-shell
purpose=验证远程运行、实时日志、结果归档、学习笔记
EOF
echo "SimFEA Studio 远程运行开始"
echo "run_id=$RUN_ID"
echo "hostname=$(hostname)"
echo "user=$(whoami)"
echo "workdir=$(pwd)"
for step in 1 2 3 4 5; do
  echo "step=$step assemble_or_solve"
  sleep 1
done
cat > result.txt <<EOF
SimFEA Studio evidence result
run_id=$RUN_ID
hostname=$(hostname)
status=success
max_displacement_mm=0.421
max_von_mises_mpa=128.6
note=这是一个远程闭环演示结果，后续会替换为真实求解器输出。
EOF
echo "artifact=result.txt"
echo "SimFEA Studio 远程运行结束"
"""


async def cancel_slurm_job(run: RemoteRun, node: ComputeNode):
    if not run.job_id:
        return
    await runner_request_slurm_cancel(run, node)
    await emit_remote_event(run, "status", status="canceling", line=f"已向 Slurm 发送 scancel：{run.job_id}")


def _find_local_shell() -> str | None:
    """Find an available shell for local command execution."""
    import shutil
    for shell in ["bash", "sh", "zsh"]:
        if shutil.which(shell):
            return shell
    return None


async def _run_local_command(cmd: str, cwd: Path, timeout: int = 120, on_output=None):
    """Run a command locally via the platform shell (cmd.exe on Windows).

    Uses a thread-pool executor to avoid event-loop deadlocks that can occur
    with asyncio.create_subprocess_shell on Windows when the child process
    spawns grandchildren that inherit pipe handles.

    If *on_output(stream, line)* is provided it is called for every
    stdout/stderr line as it is written (from the executor thread).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_local_sync, cmd, cwd, timeout, on_output)


def _run_local_sync(cmd: str, cwd: Path, timeout: int = 120, on_output=None):
    """Run a command synchronously with real-time log streaming.

    Redirect stdout/stderr to files (not OS pipes) so that child
    processes spawned by .bat wrappers don't inherit pipe handles and
    cause the parent to hang.  stdin is pointed at the platform null device.

    Uses Popen + polling so the sidecar terminal shows solver output
    as it is written, while still collecting full output for SSE events.

    If *on_output(stream, line)* is provided it is called (from the
    executor thread) for every line as it arrives.
    """
    import time as _time

    cwd.mkdir(parents=True, exist_ok=True)
    stdout_path = cwd / "stdout.log"
    stderr_path = cwd / "stderr.log"
    null_device = "NUL" if sys.platform == "win32" else "/dev/null"
    wrapped = f'{cmd} < {null_device} > "{stdout_path}" 2> "{stderr_path}"'

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    proc = subprocess.Popen(
        wrapped, cwd=str(cwd), shell=True,
        creationflags=creationflags,
    )

    stdout_offset = 0
    stderr_offset = 0
    deadline = _time.monotonic() + timeout

    while True:
        try:
            proc.wait(timeout=0.4)
            break
        except subprocess.TimeoutExpired:
            if _time.monotonic() > deadline:
                _kill_process_tree(proc.pid)
                proc.wait()
                print(f"[solver] KILLED after {timeout}s timeout", flush=True)
                break

        _tail_log(stdout_path, stdout_offset, "[solver] ", on_output=on_output, stream="stdout")
        stdout_offset = stdout_path.stat().st_size if stdout_path.exists() else 0

        _tail_log(stderr_path, stderr_offset, "[solver:err] ", on_output=on_output, stream="stderr")
        stderr_offset = stderr_path.stat().st_size if stderr_path.exists() else 0

    # Drain remaining output
    _tail_log(stdout_path, stdout_offset, "[solver] ", on_output=on_output, stream="stdout")
    _tail_log(stderr_path, stderr_offset, "[solver:err] ", on_output=on_output, stream="stderr")

    stdout = stdout_path.read_bytes() if stdout_path.exists() else b""
    stderr = stderr_path.read_bytes() if stderr_path.exists() else b""
    return proc.returncode, stdout, stderr


def _kill_process_tree(pid: int):
    """Kill a process and all its children."""
    if sys.platform == 'win32':
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    else:
        try:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                subprocess.run(['pkill', '-P', str(pid)], capture_output=True)
            except Exception:
                pass


def _tail_log(path: Path, offset: int, prefix: str, on_output=None, stream=None):
    """Print new lines from a log file since the given byte offset.

    If *on_output(stream, line)* is provided it is called for every line.
    """
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        if size <= offset:
            return
        with open(path, 'rb') as fh:
            fh.seek(offset)
            chunk = fh.read(size - offset)
        for raw_line in chunk.splitlines():
            line = raw_line.decode('utf-8', errors='replace').strip()
            if line:
                print(f"{prefix}{line}", flush=True)
                if on_output and stream:
                    on_output(stream, line)
    except Exception:
        pass


def _extract_frd_metrics(frd_path: Path) -> dict[str, float]:
    """Extract max displacement and stress from a CalculiX FRD file."""
    text = frd_path.read_text(encoding="utf-8", errors="replace")
    metrics: dict[str, float] = {}

    def _section_values(label: str) -> list[float]:
        in_section = False
        values: list[float] = []
        for line in text.splitlines():
            if line.startswith("-4") and label in line:
                in_section = True
                continue
            if in_section and line.startswith("-4"):
                break
            if in_section and line.startswith("-1"):
                for token in line.split()[1:]:
                    try:
                        values.append(float(token))
                    except ValueError:
                        pass
        return values

    disp_vals = _section_values("DISP")
    if disp_vals:
        metrics["max_displacement_mm"] = max(abs(v) for v in disp_vals)

    stress_vals = _section_values("STRESS")
    if stress_vals:
        metrics["max_von_mises_mpa"] = max(stress_vals)

    return metrics


async def execute_local_run(run: RemoteRun, solver_definition=None):
    """Execute a solver run locally without SSH.

    Does what build_solver_run_script() does for remote runs, but
    natively in Python — write inputs, run pre_commands, solver,
    post_commands, collect artifacts, and post-process results.
    """
    run.status = "running"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run, "status", status="running",
        line="本地求解器启动。",
        remote_workdir=str(run.local_dir),
    )

    workdir = run.local_dir
    solver = solver_definition

    # Write input files
    for name, content in run.input_files.items():
        input_path = workdir / name
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(content, encoding="utf-8")
        await emit_remote_event(run, "stdout", line=f"写入输入文件: {name}")

    # Pre-commands
    for cmd in (solver.pre_commands if solver else []):
        await emit_remote_event(run, "stdout", line=f"pre_command={cmd}")
        _, stdout, stderr = await _run_local_command(cmd, workdir, timeout=solver.timeout_seconds)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            await emit_remote_event(run, "stdout", line=line)
        for line in stderr.decode("utf-8", errors="replace").splitlines():
            await emit_remote_event(run, "stderr", line=line)

    # Solver command
    run.command = run.command or (
        render_command_template(solver.command_template, run, solver) if solver else ""
    )
    await emit_remote_event(run, "stdout", line=f"command={run.command}")

    # ── STA progress monitor (background) ──
    _sta_stop = False
    _sta_task: asyncio.Task | None = None

    async def _poll_sta(sta_path: Path):
        """Poll CalculiX .sta file every 2s for progress events."""
        monitor = StaMonitor(sta_path)
        while not _sta_stop:
            try:
                snap = monitor.poll()
                if snap.changed and snap.step > 0:
                    await emit_remote_event(
                        run, "sta_progress",
                        line=monitor.status_line(snap),
                        step=snap.step,
                        increment=snap.increment,
                        iteration=snap.iteration,
                        progress_pct=monitor.progress_pct(snap),
                    )
            except Exception:
                pass
            await asyncio.sleep(2.0)

    # Determine expected STA path from input files or solver command
    _sta_path: Path | None = None
    inp_names = [k for k in run.input_files if k.lower().endswith(".inp")]
    if inp_names:
        _sta_path = workdir / (Path(inp_names[0]).stem + ".sta")
    else:
        # Try to extract from solver command (-i <jobname>)
        import re as _re
        m = _re.search(r"-i\s+(\S+)", run.command)
        if m:
            _sta_path = workdir / (m.group(1) + ".sta")

    if _sta_path:
        _sta_task = asyncio.create_task(_poll_sta(_sta_path))

    # ── Execute solver ──
    loop = asyncio.get_running_loop()
    def _on_output(stream, line):
        asyncio.run_coroutine_threadsafe(
            emit_remote_event(run, stream, line=line), loop
        )
    exit_code, stdout, stderr = await _run_local_command(
        run.command, workdir, timeout=solver.timeout_seconds, on_output=_on_output,
    )

    # Stop STA monitor
    _sta_stop = True
    if _sta_task:
        _sta_task.cancel()
        try:
            await _sta_task
        except asyncio.CancelledError:
            pass
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        append_text(run.local_dir / "stdout.log", line)
    for line in stderr.decode("utf-8", errors="replace").splitlines():
        append_text(run.local_dir / "stderr.log", line)

    # Post-commands (shell commands; may be no-ops on some platforms)
    for cmd in (solver.post_commands if solver else []):
        await emit_remote_event(run, "stdout", line=f"post_command={cmd}")
        _, stdout, stderr = await _run_local_command(cmd, workdir, timeout=solver.timeout_seconds)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            await emit_remote_event(run, "stdout", line=line)

    # Extract metrics natively from FRD when post_commands are absent or
    # the shell commands are not meaningful on this platform.
    if not (solver and solver.post_commands):
        for frd_path in sorted(workdir.glob("*.frd")):
            frd_metrics = _extract_frd_metrics(frd_path)
            for key, value in frd_metrics.items():
                await emit_remote_event(run, "stdout", line=f"{key}={value:.6f}")

    # Write result.txt
    result_lines = [
        "SimFEA Studio local solver result",
        f"run_id={run.run_id}",
        f"solver={run.solver}",
        f"solver_executable={solver.executable if solver else ''}",
        "hostname=localhost",
        f"status={'success' if exit_code == 0 else 'failed'}",
        f"exit_code={exit_code}",
        f"artifact_patterns={' '.join(run.artifact_patterns)}",
    ]
    (workdir / "result.txt").write_text("\n".join(result_lines) + "\n", encoding="utf-8")

    # Collect artifacts locally
    artifacts_dir = run.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for pattern in run.artifact_patterns:
        for match in sorted(workdir.glob(pattern)):
            if not match.is_file():
                continue
            dest = artifacts_dir / match.relative_to(workdir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(match.read_bytes())
            if match.name == "result.txt":
                run.result_downloaded = True

    # Post-process solver artifacts (FRD→VTK)
    if run.solver_kind and run.solver_kind not in ("", "cantilever_beam"):
        post_process_solver_artifacts(run.local_dir)

    run.exit_code = exit_code
    substantive = any(
        f.name not in ("result.txt", "result_summary.json")
        for f in artifacts_dir.iterdir()
    ) if artifacts_dir.exists() else False
    if run.cancel_requested:
        run.status = "canceled"
    elif exit_code == 0 or substantive:
        run.status = "finished"
    else:
        run.status = "failed"
    run.finished_at = utc_now()
    persist_run_outputs(run)
    final_line = "本地任务已取消。" if run.status == "canceled" else f"本地任务结束，退出码 {exit_code}。"
    await emit_finished_event(
        run, status=run.status,
        exit_code=exit_code if exit_code is not None else -1,
        line=final_line, include_archive_path=True,
    )
    await run.queue.put(None)


async def _run_local_solver_step(run: RemoteRun, solver: SolverDefinition, workdir: Path) -> int:
    await emit_remote_event(run, "status", status="running", line=f"Workflow step started: {solver.label}")

    for name, content in solver.input_files.items():
        input_path = workdir / name
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(content, encoding="utf-8")
        await emit_remote_event(run, "stdout", line=f"write input: {name}")

    for cmd in solver.pre_commands:
        await emit_remote_event(run, "stdout", line=f"pre_command={cmd}")
        _, stdout, stderr = await _run_local_command(cmd, workdir, timeout=solver.timeout_seconds)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            append_text(run.local_dir / "stdout.log", line)
            await emit_remote_event(run, "stdout", line=line)
        for line in stderr.decode("utf-8", errors="replace").splitlines():
            append_text(run.local_dir / "stderr.log", line)
            await emit_remote_event(run, "stderr", line=line)

    command = render_command_template(solver.command_template, run, solver)
    await emit_remote_event(run, "stdout", line=f"command={command}")
    loop = asyncio.get_running_loop()
    def _on_output(stream, line):
        asyncio.run_coroutine_threadsafe(
            emit_remote_event(run, stream, line=line), loop
        )
    exit_code, stdout, stderr = await _run_local_command(
        command, workdir, timeout=solver.timeout_seconds, on_output=_on_output,
    )
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        append_text(run.local_dir / "stdout.log", line)
    for line in stderr.decode("utf-8", errors="replace").splitlines():
        append_text(run.local_dir / "stderr.log", line)

    for cmd in solver.post_commands:
        await emit_remote_event(run, "stdout", line=f"post_command={cmd}")
        _, stdout, stderr = await _run_local_command(cmd, workdir, timeout=solver.timeout_seconds)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            append_text(run.local_dir / "stdout.log", line)
            await emit_remote_event(run, "stdout", line=line)
        for line in stderr.decode("utf-8", errors="replace").splitlines():
            append_text(run.local_dir / "stderr.log", line)
            await emit_remote_event(run, "stderr", line=line)

    await emit_remote_event(run, "status", status="running", line=f"Workflow step finished: {solver.label}, exit_code={exit_code}")
    return exit_code


async def _execute_docker_run(run: RemoteRun, solver: SolverDefinition):
    import subprocess as _sp
    CONTAINER_NAME = "simfea-solvers"

    def _docker(args: list[str], timeout: int = 120) -> tuple[int, bytes, bytes]:
        r = _sp.run([docker_cli_executable(), *args], capture_output=True, timeout=timeout, shell=False)
        return r.returncode, r.stdout, r.stderr

    async def _docker_exec(cmd: str, timeout: int = 120) -> tuple[int, bytes, bytes]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _docker, ["exec", "-w", "/workspace", CONTAINER_NAME, "bash", "-lc", cmd], timeout)

    run.status = "running"
    run.runner = "DockerRunner"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(run, "status", status="running", line=f"Docker run: {solver.label}", remote_workdir=run.remote_workdir)

    workdir = run.local_dir
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        # Write input files
        for filename, content in solver.input_files.items():
            path = workdir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        # Copy input files to container
        _docker(["exec", CONTAINER_NAME, "mkdir", "-p", "/workspace"], timeout=10)
        for filename in solver.input_files:
            src = str(workdir / filename)
            _docker(["cp", src, f"{CONTAINER_NAME}:/workspace/{filename}"], timeout=10)

        # Render and run solver command
        cmd = runner_render_command_template(solver.command_template, run, solver)
        exit_code, stdout, stderr = await _docker_exec(cmd, timeout=solver.timeout_seconds)

        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                await emit_remote_event(run, "stdout", line=line.strip())
        for line in stderr.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                await emit_remote_event(run, "stderr", line=line.strip())

        # Copy results back
        _docker(["cp", f"{CONTAINER_NAME}:/workspace/.", str(workdir)], timeout=10)

        # Write result.txt
        (workdir / "result.txt").write_text(
            f"runner=DockerRunner\nsolver={solver.alias}\nexit_code={exit_code}\n",
            encoding="utf-8")

        # Collect artifacts
        for pattern in solver.artifact_patterns:
            for match in workdir.glob(pattern):
                dst = run.artifacts_dir / match.name
                run.artifacts_dir.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    match.replace(dst)

        run.exit_code = exit_code
        run.status = "finished" if exit_code == 0 else "failed"
    except Exception as exc:
        run.exit_code = -1
        run.status = "failed"
        await emit_remote_event(run, "stderr", line=f"Docker error: {exc}")
    finally:
        run.finished_at = utc_now()
        save_run_metadata(run)
        await emit_finished_event(run, status=run.status, exit_code=run.exit_code,
                                  line=f"DockerRunner finished with exit_code={run.exit_code}.")
        run.queue.put_nowait(None)


async def execute_local_workflow_run(run: RemoteRun, solvers: list[SolverDefinition]):
    run.status = "running"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run, "status", status="running",
        line="WorkflowRunner started.",
        remote_workdir=str(run.local_dir),
    )

    workdir = run.local_dir
    exit_code = 0
    for solver in solvers:
        exit_code = await _run_local_solver_step(run, solver, workdir)
        if exit_code != 0:
            break

    result_lines = [
        "SimFEA Studio local workflow result",
        f"run_id={run.run_id}",
        f"solver={run.solver}",
        "runner=WorkflowRunner",
        "steps=" + ",".join(solver.alias for solver in solvers),
        f"status={'success' if exit_code == 0 else 'failed'}",
        f"exit_code={exit_code}",
        f"artifact_patterns={' '.join(run.artifact_patterns)}",
    ]
    (workdir / "result.txt").write_text("\n".join(result_lines) + "\n", encoding="utf-8")

    run.artifacts_dir.mkdir(parents=True, exist_ok=True)
    for pattern in run.artifact_patterns:
        for match in sorted(workdir.glob(pattern)):
            if not match.is_file():
                continue
            dest = run.artifacts_dir / match.relative_to(workdir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(match.read_bytes())
            if match.name == "result.txt":
                run.result_downloaded = True

    post_process_solver_artifacts(run.local_dir)
    run.exit_code = exit_code
    any_artifacts = any(run.artifacts_dir.iterdir()) if run.artifacts_dir.exists() else False
    if run.cancel_requested:
        run.status = "canceled"
    elif exit_code == 0 or any_artifacts:
        run.status = "finished"
    else:
        run.status = "failed"
    run.finished_at = utc_now()
    persist_run_outputs(run)
    await emit_finished_event(
        run, status=run.status,
        exit_code=exit_code,
        line=f"WorkflowRunner finished with exit_code={exit_code}.",
        include_archive_path=True,
    )
    await run.queue.put(None)


async def execute_remote_run(run: RemoteRun, node: ComputeNode):
    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        persist_run_outputs(run)
        await emit_finished_event(
            run,
            status="canceled",
            exit_code=-1,
            line="远程任务已在启动前取消。",
            include_archive_path=True,
        )
        await run.queue.put(None)
        return

    run.status = "running"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="running",
        line="远程终端已连接，任务开始执行。",
        remote_workdir=run.remote_workdir,
    )
    try:
        run.process = await asyncio.create_subprocess_exec(
            *build_ssh_command(node, run.command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.gather(
            read_stream_lines(run, run.process.stdout, "stdout"),
            read_stream_lines(run, run.process.stderr, "stderr"),
        )
        run.exit_code = await run.process.wait()
        if run.cancel_requested:
            run.status = "canceled"
        elif run.exit_code == 0:
            await download_remote_artifacts(run, node, run.artifact_patterns, emit_event=emit_remote_event)
            if not run.result_downloaded:
                await download_remote_result(run, node, emit_event=emit_remote_event)
            run.status = "finished"
        else:
            await download_remote_artifacts(run, node, run.artifact_patterns, emit_event=emit_remote_event)
            run.status = "failed"
        if run.solver_kind and run.solver_kind not in ("", "cantilever_beam"):
            post_process_solver_artifacts(run.local_dir)
        run.finished_at = utc_now()
        persist_run_outputs(run)
        final_line = "远程任务已取消。" if run.status == "canceled" else f"远程任务结束，退出码 {run.exit_code}。"
        await emit_finished_event(
            run,
            status=run.status,
            exit_code=run.exit_code if run.exit_code is not None else -1,
            line=final_line,
            include_archive_path=True,
        )
    except Exception as exc:
        run.status = "failed"
        run.exit_code = -1
        run.finished_at = utc_now()
        persist_run_outputs(run)
        await emit_finished_event(
            run,
            status="failed",
            exit_code=-1,
            line=f"远程任务异常：{exc}",
        )
    finally:
        await run.queue.put(None)


async def execute_slurm_run(run: RemoteRun, node: ComputeNode):
    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        persist_run_outputs(run)
        await emit_finished_event(
            run,
            status="canceled",
            exit_code=-1,
            line="Slurm 任务已在提交前取消。",
            include_archive_path=True,
        )
        await run.queue.put(None)
        return

    run.status = "submitting"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="submitting",
        line="正在通过 SSH 写入 Slurm 脚本并提交 sbatch。",
        remote_workdir=run.remote_workdir,
    )

    submit_stdout = ""
    submit_stderr = ""
    try:
        run.process = await asyncio.create_subprocess_exec(
            *build_ssh_command(node, run.command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(run.process.communicate(), timeout=45.0)
        submit_stdout = stdout_bytes.decode("utf-8", errors="replace")
        submit_stderr = stderr_bytes.decode("utf-8", errors="replace")
        for line in submit_stdout.splitlines():
            append_text(run.local_dir / "stdout.log", line)
            await emit_remote_event(run, "stdout", line=line)
        for line in submit_stderr.splitlines():
            append_text(run.local_dir / "stderr.log", line)
            await emit_remote_event(run, "stderr", line=line)
        submit_exit = await run.process.wait()
    except asyncio.TimeoutError:
        if run.process and run.process.returncode is None:
            run.process.kill()
            await run.process.wait()
        submit_exit = -1
        submit_stderr = "sbatch submit command timed out."
    except Exception as exc:
        submit_exit = -1
        submit_stderr = str(exc)

    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        persist_run_outputs(run)
        await emit_finished_event(
            run,
            status="canceled",
            exit_code=-1,
            line="Slurm 提交已取消。",
        )
        await run.queue.put(None)
        return

    run.job_id = parse_sbatch_job_id(submit_stdout)
    if submit_exit != 0 or not run.job_id:
        run.status = "failed"
        run.exit_code = submit_exit if submit_exit != 0 else -1
        run.finished_at = utc_now()
        persist_run_outputs(run)
        await emit_finished_event(
            run,
            status="failed",
            exit_code=run.exit_code if run.exit_code is not None else -1,
            line=f"Slurm 提交失败：{submit_stderr or submit_stdout or '未解析到 JobID'}",
        )
        await run.queue.put(None)
        return

    run.status = "queued"
    run.last_scheduler_state = "SUBMITTED"
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="queued",
        job_id=run.job_id,
        line=f"Slurm 作业已提交：{run.job_id}",
    )

    polling = await poll_slurm_until_done(
        run,
        node,
        emit_event=emit_remote_event,
        cancel_job=cancel_slurm_job,
        query_state=query_slurm_state,
        sync_log=lambda current_run, current_node, remote_name, local_name, event_type, seen: sync_remote_log_file(
            current_run,
            current_node,
            remote_name,
            local_name,
            event_type,
            seen,
            emit_event=emit_remote_event,
        ),
        read_remote_text=lambda current_node, remote_path, timeout: read_remote_text(
            current_node,
            remote_path,
            timeout=timeout,
        ),
        save_run_metadata=save_run_metadata,
    )
    apply_slurm_completion_status(run, timed_out=polling.timed_out, exit_text=polling.exit_text)

    run.finished_at = utc_now()
    save_run_metadata(run)
    await download_slurm_artifacts(run, node, emit_event=emit_remote_event)
    persist_run_outputs(run)

    final_line = (
        "Slurm 任务已取消。"
        if run.status == "canceled"
        else f"Slurm 任务结束，状态 {run.status}，退出码 {run.exit_code}。"
    )
    await emit_finished_event(
        run,
        status=run.status,
        exit_code=run.exit_code if run.exit_code is not None else -1,
        line=final_line,
        include_archive_path=True,
        include_job_fields=True,
    )
    await run.queue.put(None)


_DEMO_RUNS_DIR = Path(__file__).resolve().parent / "demo_runs"


def _load_demo_runs():
    """Load demo run archives shipped with the package, for first-launch UX."""
    if not _DEMO_RUNS_DIR.is_dir():
        return []
    runs = []
    for meta_path in sorted(_DEMO_RUNS_DIR.glob("**/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (meta_path.parent / "learning_report.md").exists():
                meta["learning_report"] = "learning_report.md"
            if (meta_path.parent / "artifacts" / "result_summary.json").exists():
                meta["result_summary"] = "artifacts/result_summary.json"
                try:
                    meta["summary"] = json.loads(
                        (meta_path.parent / "artifacts" / "result_summary.json").read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass
            runs.append(meta)
        except (OSError, json.JSONDecodeError):
            continue
    return runs


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
