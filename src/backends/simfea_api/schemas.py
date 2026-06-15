"""
SSE event type contracts for the simfea_api sidecar.

Pattern borrowed from sim-main's execution-events.ts:
- Discriminated union of all event types
- Each event has a known shape, not free-form **kwargs
- Frontend mirrors these as TypeScript types in app/api/contracts.ts
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RunEvent(BaseModel):
    """Base fields present on every SSE event."""
    run_id: str
    type: str
    seq: int
    archive_path: str


class StdoutEvent(RunEvent):
    type: Literal["stdout"] = "stdout"
    line: str


class StderrEvent(RunEvent):
    type: Literal["stderr"] = "stderr"
    line: str


class StatusEvent(RunEvent):
    type: Literal["status"] = "status"
    status: Literal["running", "submitting", "queued", "canceling"]
    line: str
    remote_workdir: str | None = None
    job_id: str | None = None


class ArtifactEvent(RunEvent):
    type: Literal["artifact"] = "artifact"
    line: str
    artifact: str | None = None


class FinishedEvent(RunEvent):
    type: Literal["finished"] = "finished"
    status: str
    exit_code: int
    line: str
    job_id: str | None = None
    allocated_node: str | None = None


class StaProgressEvent(RunEvent):
    """Real-time CalculiX .sta progress snapshot."""
    type: Literal["sta_progress"] = "sta_progress"
    line: str
    step: int = 0
    increment: int = 0
    iteration: int = 0
    progress_pct: float | None = None


# Discriminated union of all event types sent from backend to frontend via SSE
SseEvent = StdoutEvent | StderrEvent | StatusEvent | ArtifactEvent | FinishedEvent | StaProgressEvent
