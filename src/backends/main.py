import asyncio
import json
import subprocess
import os
import signal
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from uvicorn import Config, Server

try:
    from .inference import infer_text_api
except ImportError:
    from inference import infer_text_api

try:
    from .simfea_api.config import ComputeNode, SolverDefinition, settings
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
        workflow_artifact_patterns,
    )
    from .simfea_api.cleanup import cleanup_old_runs
    from .simfea_api.logger import create_logger
except ImportError:
    from simfea_api.cleanup import cleanup_old_runs
    from simfea_api.config import ComputeNode, SolverDefinition, settings
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
        workflow_artifact_patterns,
    )
    from simfea_api.logger import create_logger

log = create_logger("sidecar")

server_instance = None
remote_runs = {}

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


class T_Query(TypedDict):
    prompt: str


class T_Note(TypedDict, total=False):
    note: str
    answers: dict
    export: bool
    format: str
    target_dir: str


class T_LearningExport(TypedDict, total=False):
    format: str
    target_dir: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_compute_node(node: ComputeNode) -> dict:
    return {
        "alias": node.alias,
        "label": node.label,
        "host": node.host,
        "user": node.user,
        "port": node.port,
        "remote_runs_root": node.remote_runs_root,
        "configured": bool(node.host),
    }


def get_compute_node(alias: str | None = None) -> ComputeNode:
    current = settings()
    node_alias = alias or current.default_compute_node
    if not node_alias:
        raise HTTPException(
            status_code=404,
            detail=f"No compute node configured. Create {current.config_path}.",
        )
    node = current.compute_nodes.get(node_alias)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Compute node not found: {node_alias}")
    return node


def get_solver(solver_alias: str) -> SolverDefinition:
    solver = settings().solvers.get(solver_alias)
    if solver is None:
        raise HTTPException(status_code=404, detail=f"Solver not found: {solver_alias}")
    return solver


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



def parse_key_value_stdout(stdout: str):
    values = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


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
    cause the parent to hang.  stdin is pointed at NUL.

    Uses Popen + polling so the sidecar terminal shows solver output
    as it is written, while still collecting full output for SSE events.

    If *on_output(stream, line)* is provided it is called (from the
    executor thread) for every line as it arrives.
    """
    import time as _time

    cwd.mkdir(parents=True, exist_ok=True)
    stdout_path = cwd / "stdout.log"
    stderr_path = cwd / "stderr.log"
    wrapped = f'{cmd} < NUL > "{stdout_path}" 2> "{stderr_path}"'

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
    """Kill a process and all its children on Windows."""
    if sys.platform != 'win32':
        return
    try:
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
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


def _local_probe_info():
    """Return (exit_code, stdout_bytes, stderr_bytes) for local compute-node probe.

    Uses Python stdlib instead of shell commands so the probe works on Windows
    where bash builtins (printf, nproc, pwd) are unavailable.
    """
    import getpass
    import platform
    lines = [
        f"hostname={platform.node()}",
        f"user={getpass.getuser()}",
        f"cpu_cores={os.cpu_count() or 1}",
        f"workdir={os.getcwd()}",
    ]
    return 0, "\n".join(lines).encode("utf-8"), b""


def _local_scheduler_probe_info():
    """Return (exit_code, stdout_bytes, stderr_bytes) for local scheduler probe."""
    import getpass
    import platform
    lines = [
        f"hostname={platform.node()}",
        f"user={getpass.getuser()}",
        "scheduler=none",
        "sbatch=",
        "srun=",
        "squeue=",
        "qsub=",
        "bsub=",
        f"cpu_cores={os.cpu_count() or 1}",
        "memory=N/A",
        f"workdir={os.getcwd()}",
    ]
    return 0, "\n".join(lines).encode("utf-8"), b""


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
    loop = asyncio.get_running_loop()
    def _on_output(stream, line):
        asyncio.run_coroutine_threadsafe(
            emit_remote_event(run, stream, line=line), loop
        )
    exit_code, stdout, stderr = await _run_local_command(
        run.command, workdir, timeout=solver.timeout_seconds, on_output=_on_output,
    )
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


@app.get("/v1/config")
def get_app_config():
    current = settings()
    return {
        "message": "SimFEA Studio config loaded.",
        "data": {
            "api": {
                "port": current.api_port,
                "public_host": current.api_public_host,
            },
            "paths": {
                "runs_root": str(current.runs_root),
                "config_path": str(current.config_path),
            },
            "learning": {
                "export_root": str(current.learning_export_root),
                "formats": current.learning_formats,
                "default_format": current.learning_default_format,
            },
            "compute": {
                "default_node": current.default_compute_node,
                "nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
            },
            "solvers": [public_solver(solver) for solver in current.solvers.values()],
            "toolchain": current.toolchain,
        },
    }


@app.get("/v1/connect")
def connect_to_api_server():
    log.info("Connecting to server...")
    current = settings()
    host = f"http://{current.api_public_host}:{current.api_port}"
    return {
        "message": f"Connected to SimFEA Studio API server on port {current.api_port}.",
        "data": {
            "port": current.api_port,
            "pid": os.getpid(),
            "host": host,
            "runs_root": str(current.runs_root),
            "config_path": str(current.config_path),
            "learning_export_root": str(current.learning_export_root),
            "learning_formats": current.learning_formats,
            "learning_default_format": current.learning_default_format,
            "default_compute_node": current.default_compute_node,
            "compute_nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
            "solvers": [public_solver(solver) for solver in current.solvers.values()],
            "toolchain": current.toolchain,
        },
    }


@app.post("/v1/completions")
def llm_completion(payload: T_Query = Body(...)):
    return infer_text_api.completions(payload)


@app.get("/v1/compute-nodes")
def list_compute_nodes():
    current = settings()
    return {
        "message": "SimFEA Studio compute nodes loaded.",
        "data": {
            "default_node": current.default_compute_node,
            "nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
        },
    }


@app.get("/v1/compute-nodes/{alias}/probe")
async def probe_compute_node(alias: str):
    node = get_compute_node(alias)
    remote_command = (
        "printf 'hostname='; hostname; "
        "printf 'user='; whoami; "
        "printf 'cpu_cores='; nproc 2>/dev/null || getconf _NPROCESSORS_ONLN; "
        "printf 'workdir='; pwd"
    )
    if is_local_node(node):
        exit_code, stdout_bytes, stderr_bytes = _local_probe_info()
        result = {
            "exit_code": exit_code,
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "duration_seconds": 0,
        }
    else:
        result = await run_command(build_ssh_command(node, remote_command), timeout=20.0)
    ok = result["exit_code"] == 0
    details = parse_key_value_stdout(result["stdout"]) if ok else {}
    return {
        "message": f"{alias} compute node probe {'completed' if ok else 'failed'}.",
        "data": {
            "alias": node.alias,
            "label": node.label,
            "connected": ok,
            "details": details,
            **result,
        },
    }


@app.get("/v1/compute-nodes/{alias}/scheduler-probe")
async def probe_compute_node_scheduler(alias: str):
    node = get_compute_node(alias)
    remote_command = (
        "printf 'hostname='; hostname; "
        "printf 'user='; whoami; "
        "printf 'scheduler='; "
        "if command -v sbatch >/dev/null 2>&1; then echo slurm; "
        "elif command -v qsub >/dev/null 2>&1; then echo pbs; "
        "elif command -v bsub >/dev/null 2>&1; then echo lsf; "
        "else echo none; fi; "
        "printf 'sbatch='; command -v sbatch 2>/dev/null || true; "
        "printf 'srun='; command -v srun 2>/dev/null || true; "
        "printf 'squeue='; command -v squeue 2>/dev/null || true; "
        "printf 'qsub='; command -v qsub 2>/dev/null || true; "
        "printf 'bsub='; command -v bsub 2>/dev/null || true; "
        "printf 'cpu_cores='; nproc 2>/dev/null || getconf _NPROCESSORS_ONLN; "
        "printf 'memory='; free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || true; "
        "printf 'workdir='; pwd"
    )
    if is_local_node(node):
        exit_code, stdout_bytes, stderr_bytes = _local_scheduler_probe_info()
        result = {
            "exit_code": exit_code,
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "duration_seconds": 0,
        }
    else:
        result = await run_command(build_ssh_command(node, remote_command), timeout=25.0)
    ok = result["exit_code"] == 0
    details = parse_key_value_stdout(result["stdout"]) if ok else {}
    return {
        "message": f"{alias} scheduler probe {'completed' if ok else 'failed'}.",
        "data": {
            "alias": node.alias,
            "label": node.label,
            "connected": ok,
            "details": details,
            **result,
        },
    }


@app.get("/v1/solvers")
def list_solvers():
    current = settings()
    return {
        "message": "SimFEA Studio solvers loaded.",
        "data": {
            "solvers": [public_solver(solver) for solver in current.solvers.values()],
        },
    }


@app.get("/v1/compute-nodes/{alias}/solvers/probe")
async def probe_compute_node_solvers(alias: str):
    node = get_compute_node(alias)
    current = settings()
    solvers = list(current.solvers.values())
    if is_local_node(node):
        local_results = probe_local_solvers(solvers)
        result = {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0}
        ok = True
        values = local_results
    else:
        result = await run_command(build_ssh_command(node, build_solver_probe_command(solvers)), timeout=25.0)
        ok = result["exit_code"] == 0
        values = parse_key_value_stdout(result["stdout"]) if ok else {}
    solver_statuses = [
        {
            **public_solver(solver),
            "available": bool(values.get(solver.alias)),
            "path": values.get(solver.alias, ""),
        }
        for solver in solvers
    ]
    return {
        "message": f"{alias} solver probe {'completed' if ok else 'failed'}.",
        "data": {
            "alias": node.alias,
            "label": node.label,
            "connected": ok,
            "solvers": solver_statuses,
            **result,
        },
    }


@app.get("/v1/runs")
def list_runs():
    current = settings()
    return {
        "message": "SimFEA Studio archived runs loaded.",
        "data": {
            "runs_root": str(current.runs_root),
            "learning_export_root": str(current.learning_export_root),
            "learning_formats": current.learning_formats,
            "learning_default_format": current.learning_default_format,
            "runs": load_archived_runs(),
        },
    }


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str):
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


@app.get("/v1/runs/{run_id}/result-summary")
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


@app.get("/v1/runs/{run_id}/artifacts/{artifact_path:path}")
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


@app.get("/v1/runs/{run_id}/report")
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


@app.post("/v1/runs/{run_id}/learning-export")
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


@app.post("/v1/runs/{alias}/demo")
async def start_demo_run(alias: str):
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


@app.post("/v1/runs/{alias}/slurm-demo")
async def start_slurm_demo_run(alias: str):
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


@app.post("/v1/runs/{alias}/solvers/{solver_alias}")
async def start_solver_run(alias: str, solver_alias: str):
    node = get_compute_node(alias)
    solver = get_solver(solver_alias)
    current = settings()
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
    if is_local_node(node):
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
        },
    }


@app.post("/v1/runs/{alias}/workflows/freecad-prepomax")
async def start_freecad_prepomax_workflow(alias: str):
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


@app.post("/v1/runs/{run_id}/note")
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


@app.get("/v1/runs/{run_id}/guided-questions")
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


@app.post("/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
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


@app.get("/v1/runs/{run_id}/events")
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


if __name__ == "__main__":
    try:
        result = cleanup_old_runs(settings())
        if result["removed"]:
            log.info(f"Startup cleanup: removed {result['removed']} old runs, {result['kept']} kept")
    except Exception as e:
        log.warn(f"Startup cleanup skipped: {e}")
    start_input_thread()
    start_api_server()
