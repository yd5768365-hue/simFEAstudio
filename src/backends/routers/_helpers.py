"""Shared helpers used by multiple routers and main.py."""

from datetime import datetime, timezone

try:
    from ..simfea_api.config import ComputeNode, SolverDefinition, settings
except ImportError:
    from simfea_api.config import ComputeNode, SolverDefinition, settings

from fastapi import HTTPException


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


def parse_key_value_stdout(stdout: str):
    values = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values
