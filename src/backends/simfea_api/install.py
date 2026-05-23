import asyncio
import json
import os
import uuid
import zipfile
from pathlib import Path

import httpx

from .config import settings
from .logger import create_logger

log = create_logger("install")

_installs: dict[str, dict] = {}


def _expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value)))


async def start_install(alias: str) -> dict:
    current = settings()
    spec = current.solver_install_specs.get(alias)
    if spec is None:
        raise ValueError(f"Solver install spec not found: {alias}")
    if not spec.download_url:
        raise ValueError(f"Solver {alias} does not support managed install.")

    for install_id, state in _installs.items():
        if state.get("alias") == alias and state.get("status") == "running":
            raise RuntimeError("install already in progress")

    install_id = f"install_{uuid.uuid4().hex[:10]}"
    queue: asyncio.Queue = asyncio.Queue()
    _installs[install_id] = {
        "alias": alias,
        "status": "running",
        "queue": queue,
    }
    asyncio.create_task(_run_install(install_id, alias, spec))
    return {"install_id": install_id, "message": "install started"}


async def _run_install(install_id: str, alias: str, spec):
    state = _installs.get(install_id)
    if state is None:
        return
    queue = state["queue"]

    async def emit(event_type: str, **payload):
        await queue.put({"type": event_type, **payload})

    # Download (0% -> 40%)
    await emit("install_progress", step="download", progress_pct=0, message="Downloading CalculiX...")
    tmp_dir = settings().config_path.parent / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"calculix_{install_id}.zip"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0), follow_redirects=True) as client:
            async with client.stream("GET", spec.download_url) as response:
                if response.status_code != 200:
                    await emit("install_error", message=f"Download failed: HTTP {response.status_code}")
                    state["status"] = "error"
                    return
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 40)
                            await emit("install_progress", step="download", progress_pct=pct, message=f"Downloading CalculiX... {downloaded // 1024}/{total // 1024} KB")
    except Exception as exc:
        await emit("install_error", message=f"Download failed: {exc}")
        state["status"] = "error"
        return

    # Extract (40% -> 80%)
    await emit("install_progress", step="extract", progress_pct=40, message="Extracting...")
    install_root = _expand_path(spec.managed_install_root)
    extract_dir = install_root / "calculix"
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            total_files = len(names)
            for i, name in enumerate(names):
                zf.extract(name, extract_dir)
                if total_files > 0:
                    pct = 40 + int(i / total_files * 40)
                    await emit("install_progress", step="extract", progress_pct=pct, message=f"Extracting... {i + 1}/{total_files}")
    except Exception as exc:
        await emit("install_error", message=f"Extract failed: {exc}")
        state["status"] = "error"
        return
    finally:
        if zip_path.exists():
            zip_path.unlink()

    # Scan (80% -> 90%)
    await emit("install_progress", step="scan", progress_pct=80, message="Scanning for executable...")
    found_exe = ""
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.lower() in ("ccx.bat", "ccx.exe"):
                found_exe = str(Path(root) / f)
                break
        if found_exe:
            break

    if not found_exe:
        extracted = []
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                extracted.append(str(Path(root) / f))
                if len(extracted) >= 20:
                    break
            if len(extracted) >= 20:
                break
        await emit("install_error", message=f"ccx.bat or ccx.exe not found after extraction. Contents: {extracted}")
        state["status"] = "error"
        return

    await emit("install_progress", step="scan", progress_pct=90, message=f"Found executable: {found_exe}")

    # Verify (90% -> 100%) - reuse _verify_solver_install from main
    await emit("install_progress", step="verify", progress_pct=90, message="Verifying...")
    try:
        from main import _verify_solver_install, _update_solver_executable
        result = await _verify_solver_install(alias, found_exe)
        if not result.get("verified"):
            await emit("install_error", message=f"Verification failed: {result.get('stderr', 'unknown error')}")
            state["status"] = "error"
            return

        _update_solver_executable(alias, found_exe)
        await emit("install_progress", step="verify", progress_pct=100, message="Install complete")
        await emit("install_complete", data=result)
        state["status"] = "done"
    except Exception as exc:
        await emit("install_error", message=f"Verification failed: {exc}")
        state["status"] = "error"


async def event_generator(install_id: str):
    state = _installs.get(install_id)
    if state is None:
        yield {
            "event": "message",
            "data": json.dumps({"type": "install_error", "message": "Install task not found"}, ensure_ascii=False),
        }
        return

    queue = state["queue"]
    while True:
        event = await queue.get()
        yield {
            "event": "message",
            "data": json.dumps(event, ensure_ascii=False),
        }
        if event["type"] in ("install_complete", "install_error"):
            break
