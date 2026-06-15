"""Solvers and toolchain management endpoints."""

from typing import TypedDict

from fastapi import APIRouter, Body, HTTPException
from sse_starlette.sse import EventSourceResponse

try:
    from ..simfea_api.config import settings
    from ..simfea_api.runners.solver import public_solver
    from ..simfea_api.toolchain import _scan_solver_install, update_solver_executable, verify_solver_install
    from ..simfea_api.install import start_install, event_generator
except ImportError:
    from simfea_api.config import settings
    from simfea_api.runners.solver import public_solver
    from simfea_api.toolchain import _scan_solver_install, update_solver_executable, verify_solver_install
    from simfea_api.install import start_install, event_generator

toolchain_router = APIRouter(prefix="/v1")


class T_SolverExecutable(TypedDict, total=False):
    executable: str


@toolchain_router.get("/solvers")
def list_solvers():
    current = settings()
    return {
        "message": "SimFEA Studio solvers loaded.",
        "data": {
            "solvers": [public_solver(solver) for solver in current.solvers.values()],
        },
    }


@toolchain_router.get("/toolchain/solvers")
def list_solver_installations():
    current = settings()
    return {
        "message": "SimFEA Studio toolchain installations loaded.",
        "data": {
            "solvers": [_scan_solver_install(alias) for alias in current.solver_install_specs],
        },
    }


@toolchain_router.post("/toolchain/solvers/{alias}/scan")
def scan_solver_installation(alias: str):
    return {
        "message": f"{alias} installation scan completed.",
        "data": _scan_solver_install(alias),
    }


@toolchain_router.post("/toolchain/solvers/{alias}/path")
def configure_solver_executable(alias: str, payload: T_SolverExecutable = Body(...)):
    executable = payload.get("executable", "").strip()
    if not executable:
        raise HTTPException(status_code=400, detail="Executable path is required.")
    return {
        "message": f"{alias} executable path saved.",
        "data": update_solver_executable(alias, executable),
    }


@toolchain_router.post("/toolchain/solvers/{alias}/verify")
async def verify_solver_installation(alias: str, payload: T_SolverExecutable = Body(default={})):
    return {
        "message": f"{alias} verification completed.",
        "data": await verify_solver_install(alias, payload.get("executable")),
    }


@toolchain_router.post("/toolchain/solvers/{alias}/install")
async def install_solver_pack(alias: str):
    if alias != "calculix":
        raise HTTPException(status_code=400, detail="Solver pack currently only supports calculix.")
    try:
        result = await start_install(alias)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@toolchain_router.get("/toolchain/solvers/{alias}/install/{install_id}/events")
async def stream_install_events(alias: str, install_id: str):
    return EventSourceResponse(event_generator(install_id))
