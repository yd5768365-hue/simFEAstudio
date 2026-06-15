"""Shared mutable state for the sidecar API server.

Keeps the in-memory run registry and event queues that need to be
accessible from both main.py (app factory) and routers/runs.py (handlers).
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from .simfea_api.run_archive import RemoteRun
except ImportError:
    from simfea_api.run_archive import RemoteRun

# In-memory run registry — keyed by run_id
remote_runs: dict[str, RemoteRun] = {}
