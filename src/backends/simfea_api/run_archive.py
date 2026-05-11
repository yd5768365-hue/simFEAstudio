import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import settings


@dataclass
class RemoteRun:
    run_id: str
    case_name: str
    solver: str
    node_alias: str
    node_label: str
    remote_workdir: str
    local_dir: Path
    artifacts_dir: Path
    command: str
    created_at: str
    runner: str = "SSHRunner"
    status: str = "created"
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    process: Optional[asyncio.subprocess.Process] = None
    exit_code: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result_downloaded: bool = False
    cancel_requested: bool = False
    toolchain: list[dict[str, str]] = field(default_factory=list)
    scheduler: Optional[str] = None
    job_id: Optional[str] = None
    partition: Optional[str] = None
    allocated_node: Optional[str] = None
    requested_cpus: Optional[int] = None
    requested_memory: Optional[str] = None
    slurm_script: Optional[str] = None
    last_scheduler_state: Optional[str] = None


def run_metadata(run: RemoteRun):
    artifacts = []
    if run.artifacts_dir.exists():
        artifacts = [
            str(path.relative_to(run.local_dir)).replace("\\", "/")
            for path in sorted(run.artifacts_dir.rglob("*"))
            if path.is_file()
        ]
    elif run.result_downloaded:
        artifacts.append("artifacts/result.txt")
    learning_report = "learning_report.md" if (run.local_dir / "learning_report.md").exists() else None
    result_summary = "artifacts/result_summary.json" if (run.local_dir / "artifacts" / "result_summary.json").exists() else None
    return {
        "run_id": run.run_id,
        "case_name": run.case_name,
        "solver": run.solver,
        "runner": run.runner,
        "compute_node": run.node_alias,
        "compute_node_label": run.node_label,
        "status": run.status,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "exit_code": run.exit_code,
        "cancel_requested": run.cancel_requested,
        "remote_workdir": run.remote_workdir,
        "local_archive": str(run.local_dir),
        "command": run.command,
        "artifacts": artifacts,
        "learning_report": learning_report,
        "result_summary": result_summary,
        "toolchain": run.toolchain or settings().toolchain,
        "scheduler": run.scheduler,
        "job_id": run.job_id,
        "partition": run.partition,
        "allocated_node": run.allocated_node,
        "requested_cpus": run.requested_cpus,
        "requested_memory": run.requested_memory,
        "last_scheduler_state": run.last_scheduler_state,
    }


def save_run_metadata(run: RemoteRun):
    run.local_dir.mkdir(parents=True, exist_ok=True)
    (run.local_dir / "meta.json").write_text(
        json.dumps(run_metadata(run), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ensure_run_files(run: RemoteRun):
    run.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (run.local_dir / "note.md").touch(exist_ok=True)
    (run.local_dir / "stdout.log").touch(exist_ok=True)
    (run.local_dir / "stderr.log").touch(exist_ok=True)
    (run.local_dir / "events.jsonl").touch(exist_ok=True)
    (run.local_dir / "command.sh").write_text(run.command, encoding="utf-8")
    if run.slurm_script:
        (run.local_dir / "slurm_job.slurm").write_text(run.slurm_script, encoding="utf-8")
    save_run_metadata(run)


def load_archived_runs(limit: int = 20):
    current = settings()
    runs_root = current.runs_root
    if not runs_root.exists():
        return []

    runs = []
    for meta_path in runs_root.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (meta_path.parent / "learning_report.md").exists():
                meta["learning_report"] = "learning_report.md"
            if (meta_path.parent / "artifacts" / "result_summary.json").exists():
                meta["result_summary"] = "artifacts/result_summary.json"
            meta.setdefault("toolchain", current.toolchain)
            runs.append(meta)
        except (OSError, json.JSONDecodeError):
            continue

    runs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return runs[:limit]


def append_text(path: Path, line: str):
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def read_optional_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def read_tail(path: Path, max_lines: int = 28) -> str:
    content = read_optional_text(path)
    if not content.strip():
        return "暂无"
    return "\n".join(content.splitlines()[-max_lines:])

