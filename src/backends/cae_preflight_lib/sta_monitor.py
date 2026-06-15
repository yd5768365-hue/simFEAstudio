"""Real-time CalculiX .sta file progress monitor.

Parses CalculiX status (.sta) files during solver execution to extract
step/increment/iteration progress. Useful for live progress reporting
via SSE events.

The .sta file format (CalculiX v2.10+):

    STEP 1

    Displacements
    Increment 1
    Iteration 1
    ...
    Iteration N
    ...
    Increment 2
    ...

Typical usage:

    monitor = StaMonitor(sta_path)
    while solver_running:
        snap = monitor.poll()
        if snap.changed:
            emit_progress(snap)
        await asyncio.sleep(1.0)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StaSnapshot:
    """A point-in-time snapshot of CalculiX progress."""
    step: int = 0
    increment: int = 0
    iteration: int = 0
    converged_increments: int = 0
    step_count: int = 0
    # Whether this snapshot differs from the previous one
    changed: bool = False
    # Raw last meaningful line
    last_line: str = ""


class StaMonitor:
    """Poll-based monitor for CalculiX .sta files.

    Tracks byte offset to only read new content on each poll.
    """

    def __init__(self, sta_path: Path):
        self._path = sta_path
        self._offset: int = 0
        self._prev: StaSnapshot = StaSnapshot()

    def poll(self) -> StaSnapshot:
        """Read new STA content and return current progress snapshot."""
        if not self._path.exists():
            return self._prev

        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return self._prev

        if len(text) <= self._offset:
            unchanged = StaSnapshot(
                step=self._prev.step,
                increment=self._prev.increment,
                iteration=self._prev.iteration,
                converged_increments=self._prev.converged_increments,
                step_count=self._prev.step_count,
                changed=False,
                last_line=self._prev.last_line,
            )
            return unchanged

        new_text = text[self._offset:]
        self._offset = len(text)

        snap = self._parse_new(new_text)
        snap.changed = (
            snap.step != self._prev.step
            or snap.increment != self._prev.increment
            or snap.iteration != self._prev.iteration
            or snap.converged_increments != self._prev.converged_increments
        )
        self._prev = snap
        return snap

    def _parse_new(self, text: str) -> StaSnapshot:
        """Parse new STA text on top of previous state."""
        snap = StaSnapshot(
            step=self._prev.step,
            increment=self._prev.increment,
            iteration=self._prev.iteration,
            converged_increments=self._prev.converged_increments,
            step_count=self._prev.step_count,
        )

        step_re = re.compile(r"^\s*STEP\s+(\d+)", re.IGNORECASE)
        inc_re = re.compile(r"^\s*Increment\s+(\d+)", re.IGNORECASE)
        iter_re = re.compile(r"^\s*Iteration\s+(\d+)", re.IGNORECASE)

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            m = step_re.match(stripped)
            if m:
                snap.step = int(m.group(1))
                snap.step_count = max(snap.step_count, snap.step)
                snap.last_line = stripped
                continue

            m = inc_re.match(stripped)
            if m:
                snap.increment = int(m.group(1))
                snap.iteration = 0
                snap.last_line = stripped
                continue

            m = iter_re.match(stripped)
            if m:
                snap.iteration = int(m.group(1))
                snap.last_line = stripped
                # Assume convergence if iteration completes (simplified)
                if snap.iteration >= 1:
                    snap.converged_increments = max(
                        snap.converged_increments, snap.increment
                    )
                continue

        return snap

    def progress_pct(self, snap: StaSnapshot | None = None) -> float | None:
        """Estimate progress percentage (simplified)."""
        s = snap or self._prev
        if s.step_count < 1 or s.step < 1:
            return None
        return min(99.0, (s.step - 1 + min(s.increment / 10.0, 1.0)) / s.step_count * 100.0)

    def status_line(self, snap: StaSnapshot | None = None) -> str:
        """Human-readable progress line."""
        s = snap or self._prev
        parts = [f"Step {s.step}"]
        if s.increment:
            parts.append(f"Inc {s.increment}")
        if s.iteration:
            parts.append(f"Iter {s.iteration}")
        pct = self.progress_pct(s)
        if pct is not None:
            parts.append(f"({pct:.0f}%)")
        return " ".join(parts)
