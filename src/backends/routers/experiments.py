"""Experiment Lab endpoints."""

import os
import subprocess as _sp
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

try:
    from ..simfea_api.config import PROJECT_ROOT
except ImportError:
    from simfea_api.config import PROJECT_ROOT

experiments_router = APIRouter(prefix="/v1")


# ── Learning path resolution ─────────────────────────────

def _resolve_learning_dir(subdir: str) -> Path:
    """Resolve a learning/ subdirectory: env var → package dir → project root."""
    _BENCH_ENV = os.getenv("SIMFEA_BENCHMARKS_DIR")
    if subdir == "benchmarks" and _BENCH_ENV:
        p = Path(_BENCH_ENV)
        if p.is_dir():
            return p
    _LEARNING_ENV = os.getenv("SIMFEA_LEARNING_DIR")
    if _LEARNING_ENV:
        p = Path(_LEARNING_ENV) / subdir if subdir else Path(_LEARNING_ENV)
        if p.is_dir():
            return p
    base = PROJECT_ROOT / "learning"
    if subdir:
        base = base / subdir
    return base


_EXPERIMENT_BASE = _resolve_learning_dir("")
_EXPERIMENT_DIRS = [
    str(_EXPERIMENT_BASE / "experiments"),
    str(_EXPERIMENT_BASE / "benchmarks"),
    str(_EXPERIMENT_BASE / "research"),
]


@experiments_router.get("/experiment/files")
def list_experiment_files():
    """List .py, .ipynb, .md files in experiment directories."""
    files: list[dict] = []
    for rel_dir in _EXPERIMENT_DIRS:
        d = Path(rel_dir) if Path(rel_dir).is_absolute() else PROJECT_ROOT / rel_dir
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".py", ".ipynb", ".md"):
                rel_path = p.relative_to(_EXPERIMENT_BASE)
                parent_dir = p.parent.relative_to(d)
                display_name = str(parent_dir / p.name).replace("\\", "/") if str(parent_dir) != "." else p.name
                files.append({
                    "path": str(rel_path).replace("\\", "/"),
                    "name": display_name,
                    "dir": rel_dir,
                    "size": p.stat().st_size,
                })
    return {"message": f"{len(files)} 个文件。", "data": {"files": files}}


@experiments_router.get("/experiment/files/{file_path:path}")
def read_experiment_file(file_path: str):
    """Read an experiment file."""
    p = (PROJECT_ROOT / file_path).resolve()
    if not str(p).startswith(str(PROJECT_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="路径不在项目目录内。")
    if not p.is_file():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return {
        "message": "文件已读取。",
        "data": {"content": p.read_text(encoding="utf-8"), "path": str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")},
    }


@experiments_router.post("/experiment/files/{file_path:path}")
def save_experiment_file(file_path: str, payload: dict = Body(...)):
    """Save content to an experiment file."""
    content = payload.get("content", "")
    p = (PROJECT_ROOT / file_path).resolve()
    if not str(p).startswith(str(PROJECT_ROOT.resolve())):
        raise HTTPException(status_code=403, detail="路径不在项目目录内。")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"message": "文件已保存。", "data": {"path": str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")}}


@experiments_router.post("/experiment/run")
async def run_experiment_code(payload: dict = Body(...)):
    """Execute Python code (inline or file) and return stdout/stderr."""
    code = payload.get("code", "").strip()
    file_path = payload.get("file_path", "").strip()

    if file_path:
        target = (PROJECT_ROOT / file_path).resolve()
        if not str(target).startswith(str(PROJECT_ROOT.resolve())):
            raise HTTPException(status_code=403, detail="路径不在项目目录内。")
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
        tmp_name = str(target)
        cleanup = False
    elif code:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        try:
            tmp.write(code)
            tmp.close()
            tmp_name = tmp.name
            cleanup = True
        except Exception:
            raise HTTPException(status_code=500, detail="临时文件写入失败。")
    else:
        raise HTTPException(status_code=400, detail="缺少 'code' 或 'file_path' 字段。")

    try:
        r = _sp.run(
            ["python", tmp_name],
            capture_output=True,
            timeout=60,
            cwd=str(target.parent) if file_path else str(PROJECT_ROOT),
        )
        return {
            "message": "代码执行完成。",
            "data": {
                "exit_code": r.returncode,
                "stdout": r.stdout.decode("utf-8", errors="replace"),
                "stderr": r.stderr.decode("utf-8", errors="replace"),
            },
        }
    except _sp.TimeoutExpired:
        return {
            "message": "代码执行超时。",
            "data": {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Execution timed out after 60 seconds.",
            },
        }
    finally:
        if cleanup:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
