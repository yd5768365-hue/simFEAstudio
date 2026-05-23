import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException

from .config import settings


def _normalize_executable(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value.strip().strip('"')))


def _existing_executable(value: str) -> str:
    if not value:
        return ""
    normalized = _normalize_executable(value)
    path = Path(normalized)
    if path.is_file():
        return str(path)
    found = shutil.which(normalized)
    return found or ""


def _solver_install_candidates(alias: str) -> list[str]:
    current = settings()
    spec = current.solver_install_specs.get(alias)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Solver install spec not found: {alias}")

    candidates = []
    solver = current.solvers.get(alias)
    if solver:
        candidates.append(solver.executable)
    candidates.extend(spec.common_paths)
    candidates.extend(spec.executable_candidates)

    unique = []
    for candidate in candidates:
        normalized = _normalize_executable(candidate)
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _scan_solver_install(alias: str) -> dict:
    current = settings()
    spec = current.solver_install_specs.get(alias)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Solver install spec not found: {alias}")
    solver = current.solvers.get(alias)

    discovered_path = ""
    searched_paths = []
    for candidate in _solver_install_candidates(alias):
        found = _existing_executable(candidate)
        searched_paths.append(candidate)
        if found and not discovered_path:
            discovered_path = found

    return {
        "alias": spec.alias,
        "label": spec.label,
        "install_mode": spec.install_mode,
        "status": "found" if discovered_path else "missing",
        "configured_executable": solver.executable if solver else "",
        "discovered_path": discovered_path,
        "executable_candidates": spec.executable_candidates,
        "common_paths": spec.common_paths,
        "searched_paths": searched_paths,
        "verify_command": spec.verify_command,
        "install_hint": spec.install_hint,
        "install_guide_url": spec.install_guide_url,
        "input_extensions": spec.input_extensions,
    }


def update_solver_executable(alias: str, executable: str) -> dict:
    current = settings()
    existing_config = {}
    if current.config_path.exists():
        existing_config = json.loads(current.config_path.read_text(encoding="utf-8"))

    solver_items = existing_config.setdefault("solvers", [])
    target_aliases = [alias]
    if alias == "prepomax":
        target_aliases.append("prepomax-regenerate")

    for target_alias in target_aliases:
        for item in solver_items:
            if item.get("alias") == target_alias:
                previous = item.get("executable", "")
                item["executable"] = executable
                if previous and previous in item.get("command_template", ""):
                    item["command_template"] = item["command_template"].replace(previous, executable)
                break
        else:
            solver_items.append({"alias": target_alias, "executable": executable})

    current.config_path.parent.mkdir(parents=True, exist_ok=True)
    current.config_path.write_text(json.dumps(existing_config, ensure_ascii=False, indent=2), encoding="utf-8")
    return _scan_solver_install(alias)


async def _run_verify_command(cmd: str, cwd: Path, timeout: int = 20):
    """Run a short verification command via subprocess in a thread executor."""
    loop = asyncio.get_running_loop()

    def _run():
        cwd.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            cmd, cwd=str(cwd), shell=True,
            capture_output=True, timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr

    return await loop.run_in_executor(None, _run)


async def verify_solver_install(alias: str, executable: str | None = None) -> dict:
    current = settings()
    spec = current.solver_install_specs.get(alias)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Solver install spec not found: {alias}")

    scan = _scan_solver_install(alias)
    resolved = _existing_executable(executable or scan["discovered_path"] or scan["configured_executable"])
    if not resolved:
        return {
            **scan,
            "status": "missing",
            "verified": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Executable not found.",
            "duration_seconds": 0,
        }

    command = spec.verify_command.replace("${executable}", resolved)
    workdir = current.runs_root / "_toolchain_probe" / alias
    exit_code, stdout_bytes, stderr_bytes = await _run_verify_command(command, workdir, timeout=20)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    output = f"{stdout}\n{stderr}".lower()
    verified = exit_code == 0 or (
        spec.label.lower() in output and ("--help" in output or "version" in output or "usage:" in output)
    )
    return {
        **scan,
        "status": "verified" if verified else "found",
        "verified": verified,
        "discovered_path": resolved,
        "configured_executable": resolved,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": 0,
    }
