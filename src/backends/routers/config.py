"""Config, connect, and completions endpoints."""

import os
from typing import TypedDict

from fastapi import APIRouter, Body, HTTPException

try:
    from ..simfea_api.config import settings
    from ..simfea_api.runners.solver import public_solver
    from ..routers._helpers import public_compute_node
    from ..inference import infer_text_api
except ImportError:
    from simfea_api.config import settings
    from simfea_api.runners.solver import public_solver
    from routers._helpers import public_compute_node
    from inference import infer_text_api

try:
    from ..simfea_api.logger import create_logger
except ImportError:
    from simfea_api.logger import create_logger

config_router = APIRouter(prefix="/v1")
log = create_logger("config")


class T_Query(TypedDict):
    prompt: str


class T_TranslateTask(TypedDict):
    description: str


@config_router.get("/config")
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


@config_router.get("/connect")
def connect_to_api_server():
    log.info("Connecting to server...")
    try:
        try:
            from ..simfea_api.toolchain import auto_discover_all
        except ImportError:
            from simfea_api.toolchain import auto_discover_all
        auto_discover_all()
    except Exception:
        pass
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


@config_router.post("/completions")
def llm_completion(payload: T_Query = Body(...)):
    return infer_text_api.completions(payload)


@config_router.post("/completions/translate-task")
def translate_task(payload: T_TranslateTask = Body(...)):
    """Translate a natural-language task description into a solver config."""
    description = payload.get("description", "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="缺少 'description' 字段。")

    current = settings()
    available_solvers = [
        {"alias": s.alias, "label": s.label, "kind": s.kind}
        for s in current.solvers.values()
    ]

    try:
        result = infer_text_api.translate_task_to_run(description, available_solvers)
    except (ConnectionError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "message": "任务分析完成。",
        "data": result,
    }
