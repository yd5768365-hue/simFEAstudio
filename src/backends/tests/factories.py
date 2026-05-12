"""
Test factories for simfea_api domain objects.

Pattern borrowed from @sim/testing in sim-main:
- Each factory returns a fully-valid object with sensible defaults.
- Every field can be overridden via keyword arguments.
- Convenience wrappers for common variants.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from simfea_api.config import ComputeNode
from simfea_api.run_archive import RemoteRun


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def create_node(**overrides) -> ComputeNode:
    """Create a ComputeNode with sensible defaults."""
    defaults = {
        "alias": "test-node",
        "label": "Test Node",
        "host": "192.168.1.100",
        "user": "testuser",
        "port": 22,
        "identity_file": "~/.ssh/id_rsa",
        "remote_runs_root": "/home/testuser/simfea-runs",
        "connect_timeout_seconds": 8,
        "batch_mode": True,
        "strict_host_key_checking": "accept-new",
    }
    return ComputeNode(**(defaults | overrides))


def create_hpc_node(**overrides) -> ComputeNode:
    """Create a ComputeNode with Slurm/HPC defaults."""
    defaults = {
        "alias": "hpc-node",
        "label": "HPC Cluster",
        "host": "login.hpc.example.com",
        "user": "hpcuser",
        "port": 22,
        "identity_file": "~/.ssh/hpc_rsa",
        "remote_runs_root": "/scratch/hpcuser/simfea-runs",
        "connect_timeout_seconds": 15,
        "batch_mode": True,
        "strict_host_key_checking": "accept-new",
    }
    return create_node(**(defaults | overrides))


def create_run(**overrides) -> RemoteRun:
    """Create a RemoteRun with sensible defaults.

    The returned object is a real dataclass instance suitable for:
    - Testing archive read/write logic.
    - Testing event emission.
    - Testing result parsing and learning export.
    """
    run_id = overrides.get("run_id", f"run_{_short_id()}")
    local_dir = overrides.get("local_dir", Path(f"/tmp/simfea-test/{run_id}"))
    defaults = {
        "run_id": run_id,
        "case_name": "test-cantilever",
        "solver": "demo-shell",
        "node_alias": "test-node",
        "node_label": "Test Node",
        "remote_workdir": f"/tmp/remote/{run_id}",
        "local_dir": local_dir,
        "artifacts_dir": local_dir / "artifacts",
        "command": "echo 'hello simfea'",
        "created_at": _utc_now(),
        "runner": "SSHRunner",
        "status": "created",
        "toolchain": [{"name": "demo-shell", "role": "solver", "status": "ready"}],
    }
    return RemoteRun(**(defaults | overrides))


def create_slurm_run(**overrides) -> RemoteRun:
    """Create a RemoteRun pre-configured for Slurm."""
    run_id = overrides.get("run_id", f"run_{_short_id()}")
    defaults = {
        "run_id": run_id,
        "runner": "SlurmRunner",
        "scheduler": "slurm",
        "partition": "compute",
        "requested_cpus": 4,
        "requested_memory": "8G",
        "job_id": None,
        "allocated_node": None,
    }
    return create_run(**(defaults | overrides))


def create_finished_run(**overrides) -> RemoteRun:
    """Create a RemoteRun that has already completed successfully."""
    defaults = {
        "status": "finished",
        "exit_code": 0,
        "started_at": _utc_now(),
        "finished_at": _utc_now(),
        "result_downloaded": True,
    }
    return create_run(**(defaults | overrides))
