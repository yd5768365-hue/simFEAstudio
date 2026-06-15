"""Preflight INP validation endpoint."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

preflight_router = APIRouter(prefix="/v1")


@preflight_router.post("/preflight")
def run_preflight_check(payload: dict = Body(...)):
    """Validate an .inp file before solver submission."""
    content = payload.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="缺少 'content' 字段。")

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()
        from cae_preflight_lib.preflight import run_preflight as _run_preflight
        result = _run_preflight(Path(tmp.name))
        return {"message": "预检查完成。", "data": result.to_dict()}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
