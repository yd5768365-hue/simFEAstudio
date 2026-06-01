"""Docker solver runner — executes solvers inside a long-running container."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from ..config import ComputeNode, SolverDefinition
from ..run_archive import RemoteRun
from ..schemas import emit_remote_event, run_seq
from .solver import render_command_template

CONTAINER_NAME = "simfea-solvers"
WORKSPACE = "/workspace"


def _docker_cmd(args: list[str], timeout: int = 120) -> tuple[int, bytes, bytes]:
    """Run a docker CLI command and return (exit_code, stdout, stderr)."""
    r = subprocess.run(
        ["docker", *args],
        capture_output=True,
        timeout=timeout,
        shell=False,
    )
    return r.returncode, r.stdout, r.stderr


async def docker_exec(cmd: str, run: RemoteRun, timeout: int = 120) -> tuple[int, bytes, bytes]:
    """Execute a command inside the solver container."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _docker_cmd,
        ["exec", "-w", WORKSPACE, CONTAINER_NAME, "bash", "-lc", cmd],
        timeout,
    )


def docker_cp(src: str, dst: str) -> None:
    """Copy files between host and container."""
    _docker_cmd(["cp", src, dst])


async def execute_docker_run(run: RemoteRun, solver: SolverDefinition, node: ComputeNode) -> None:
    """Run a solver inside the Docker container, streaming output via SSE."""
    local_workdir = run.local_dir
    local_workdir.mkdir(parents=True, exist_ok=True)
    container_workdir = f"{WORKSPACE}/{run.run_id}"

    # Ensure container workdir exists
    _docker_cmd(["exec", CONTAINER_NAME, "mkdir", "-p", container_workdir], timeout=10)

    # Set run metadata
    run.status = "running"
    run.runner = "DockerRunner"
    _save_meta(run)

    await emit_remote_event(run, "status", {
        "status": "running",
        "line": f"Docker run started: {solver.label}",
        "remote_workdir": container_workdir,
    })

    try:
        # Write input files locally, then copy to container
        for filename, content in solver.input_files.items():
            local_path = local_workdir / filename
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(content, encoding="utf-8")
            _docker_cmd(["cp", str(local_path), f"{CONTAINER_NAME}:{container_workdir}/{filename}"], timeout=10)

        # Build and run solver command
        solver_cmd = render_command_template(solver.command_template, run, solver)
        exit_code, stdout, stderr = await docker_exec(solver_cmd, run, timeout=solver.timeout_seconds)

        # Stream stdout
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                await emit_remote_event(run, "stdout", {"line": line.strip()})

        # Stream stderr
        for line in stderr.decode("utf-8", errors="replace").splitlines():
            if line.strip():
                await emit_remote_event(run, "stderr", {"line": line.strip()})

        # Copy results back
        _docker_cmd(["cp", f"{CONTAINER_NAME}:{container_workdir}/.", str(local_workdir)], timeout=10)

        # Write result.txt
        result_path = local_workdir / "result.txt"
        result_path.write_text(
            f"runner=DockerRunner\nsolver={solver.alias}\nexit_code={exit_code}\n"
            f"container={CONTAINER_NAME}\nartifact_patterns={','.join(solver.artifact_patterns)}\n",
            encoding="utf-8",
        )

        # Collect artifacts
        _collect_artifacts(run, solver, local_workdir)

        run.exit_code = exit_code
        run.status = "finished" if exit_code == 0 else "failed"

    except Exception as exc:
        run.exit_code = -1
        run.status = "failed"
        await emit_remote_event(run, "stderr", {
            "line": f"Docker execution failed: {exc}",
        })

    finally:
        # Persist metadata
        run.finished_at = run._now_utc()
        _save_meta(run)
        await emit_remote_event(run, "finished", {
            "status": run.status,
            "exit_code": run.exit_code,
            "line": f"DockerRunner finished with exit_code={run.exit_code}.",
        })
        # Signal SSE stream end
        run.queue.put_nowait(None)


def _save_meta(run: RemoteRun) -> None:
    """Save run metadata to meta.json."""
    import json
    meta = {
        "run_id": run.run_id,
        "case_name": run.case_name,
        "solver": run.solver,
        "runner": run.runner,
        "status": run.status,
        "exit_code": run.exit_code,
        "node_alias": run.node_alias,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": getattr(run, "finished_at", ""),
        "remote_workdir": run.remote_workdir,
    }
    meta_path = run.local_dir / "meta.json" if run.local_dir else None
    if meta_path:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _collect_artifacts(run: RemoteRun, solver: SolverDefinition, workdir: Path) -> None:
    """Glob solver artifacts from workdir and copy to artifacts_dir."""
    artifacts_dir = run.artifacts_dir if hasattr(run, "artifacts_dir") else workdir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    import glob as _glob
    for pattern in solver.artifact_patterns:
        for match in _glob.glob(str(workdir / pattern)):
            src = Path(match)
            dst = artifacts_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)


def ensure_docker_container() -> bool:
    """Check if the solver container exists and is running."""
    exit_code, stdout, _ = _docker_cmd(["ps", "-q", "--filter", f"name={CONTAINER_NAME}"], timeout=5)
    return exit_code == 0 and stdout.strip() != b""
