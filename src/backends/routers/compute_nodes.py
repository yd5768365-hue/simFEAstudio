"""Compute node endpoints."""

import os

try:
    from ..simfea_api.config import settings
    from ..simfea_api.runners.ssh import build_ssh_command, is_local_node, run_command
    from ..simfea_api.runners.solver import build_solver_probe_command, probe_local_solvers, public_solver
    from ..routers._helpers import get_compute_node, parse_key_value_stdout, public_compute_node
except ImportError:
    from simfea_api.config import settings
    from simfea_api.runners.ssh import build_ssh_command, is_local_node, run_command
    from simfea_api.runners.solver import build_solver_probe_command, probe_local_solvers, public_solver
    from routers._helpers import get_compute_node, parse_key_value_stdout, public_compute_node

from fastapi import APIRouter

compute_nodes_router = APIRouter(prefix="/v1")


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


@compute_nodes_router.get("/compute-nodes")
def list_compute_nodes():
    current = settings()
    return {
        "message": "SimFEA Studio compute nodes loaded.",
        "data": {
            "default_node": current.default_compute_node,
            "nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
        },
    }


@compute_nodes_router.get("/compute-nodes/{alias}/probe")
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


@compute_nodes_router.get("/compute-nodes/{alias}/scheduler-probe")
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


@compute_nodes_router.get("/compute-nodes/{alias}/solvers/probe")
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
