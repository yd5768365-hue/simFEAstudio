"""
Check that simfea_api modules do not violate layer boundaries.

Rules:
  1. No file under simfea_api/ may import from main (the API route layer).
  2. No file under simfea_api/runners/ may import fastapi.
  3. No file under simfea_api/runners/ may import EventSourceResponse.

Usage:
  python scripts/check_backend_boundaries.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "backends" / "simfea_api"
MAIN = ROOT / "src" / "backends" / "main.py"

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(\S+)", re.MULTILINE)

violations: list[str] = []

for py_file in sorted(SRC.rglob("*.py")):
    text = py_file.read_text(encoding="utf-8", errors="replace")
    imports = IMPORT_RE.findall(text)

    relative = py_file.relative_to(ROOT)

    # Rule 1: no simfea_api module imports from main
    for imp in imports:
        if imp in ("main", ".main", "..main"):
            violations.append(f"[rule-1] {relative}: imports '{imp}' (main.py is the API route layer)")

    # Rule 2: runners/ must not import fastapi
    if "runners" in py_file.parts:
        for imp in imports:
            if imp.startswith("fastapi"):
                violations.append(f"[rule-2] {relative}: imports '{imp}' (runners must not depend on FastAPI)")

    # Rule 3: runners/ must not import SSE response helpers
    if "runners" in py_file.parts:
        for imp in imports:
            if "sse_starlette" in imp or "EventSourceResponse" in imp:
                violations.append(f"[rule-3] {relative}: imports '{imp}' (runners must not depend on SSE layer)")

if violations:
    print(f"{len(violations)} boundary violation(s) found:\n")
    for v in violations:
        print(f"  {v}")
    print("\nFix: runner modules should accept an emit_event callback parameter instead of importing SSE/API layers.")
    sys.exit(1)

print(f"OK: {sum(1 for _ in SRC.rglob('*.py'))} simfea_api modules, no boundary violations.")
sys.exit(0)
