import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import AppSettings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_created_at(meta_path: Path) -> datetime:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created = meta.get("created_at", "")
        if created:
            return datetime.fromisoformat(created)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return datetime.fromtimestamp(meta_path.parent.stat().st_mtime, tz=timezone.utc)


def cleanup_old_runs(settings: AppSettings, *, now: datetime | None = None) -> dict:
    """Remove runs exceeding retention days or max count. Returns summary dict."""
    now = now or utc_now()
    runs_root = settings.runs_root
    retention = settings.run_retention_days
    max_runs = settings.max_runs

    if not runs_root.exists():
        return {"removed": 0, "kept": 0, "reason": "no runs root"}

    entries: list[tuple[datetime, Path]] = []
    for meta_path in runs_root.glob("*/meta.json"):
        entries.append((_parse_created_at(meta_path), meta_path.parent))

    if not entries:
        return {"removed": 0, "kept": 0, "reason": "no runs found"}

    entries.sort(key=lambda item: item[0])

    cutoff = now - timedelta(days=retention)
    to_remove: set[Path] = set()

    for created, run_dir in entries:
        if created < cutoff:
            to_remove.add(run_dir)

    # Remove oldest remaining entries until within max_runs limit
    remaining = [e for e in entries if e[1] not in to_remove]
    for entry in remaining[: len(remaining) - max_runs]:
        to_remove.add(entry[1])

    for run_dir in to_remove:
        shutil.rmtree(run_dir, ignore_errors=True)

    kept = len(entries) - len(to_remove)
    return {"removed": len(to_remove), "kept": kept}
