from __future__ import annotations

import csv
import re
from pathlib import Path


_TEXT_SUFFIX_ALLOWLIST = {".stderr", ".sta", ".dat", ".cvg", ".log", ".out", ".err"}
_TEXT_NAME_ALLOWLIST = {"history.csv", "solver.log", "message", "listing"}

_INPUT_EXTENSIONS = {".inp", ".cfg", ".comm", ".export", ".sif", ".su2"}
_SU2_FAILURE_PATTERNS = (
    "exit failure",
    "segmentation fault",
    "mpi_abort",
    "received signal",
)
_OPENFOAM_FAILURE_PATTERNS = (
    "foam fatal error",
    "floating point exception",
    "segmentation fault",
)
_CODE_ASTER_FAILURE_PATTERNS = (
    "<f>",
    "diagnostic job : <f>",
    "execution ended (command file #1): failed",
)


def collect_solver_text_sources(results_dir: Path) -> list[Path]:
    if not results_dir.exists() or not results_dir.is_dir():
        return []

    items: list[Path] = []
    seen: set[Path] = set()
    for path in results_dir.rglob("*"):
        if not path.is_file():
            continue
        if not _is_text_source_candidate(path):
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        items.append(path)

    items.sort(key=lambda path: (_text_source_priority(path, results_dir), str(path.relative_to(results_dir))))
    return items[:24]


def extract_solver_convergence_metrics(results_dir: Path) -> list[dict]:
    if not results_dir.exists() or not results_dir.is_dir():
        return []

    metrics: list[dict] = []
    metrics.extend(_extract_calculix_sta_metrics(results_dir))

    history_file = results_dir / "history.csv"
    su2_metric = _extract_su2_history_metric(
        history_file,
        log_file=_pick_matching_log(results_dir, "su2"),
    )
    if su2_metric is not None:
        metrics.append(su2_metric)

    openfoam_log = _pick_matching_log(results_dir, "openfoam")
    openfoam_metric = _extract_openfoam_log_metric(openfoam_log) if openfoam_log else None
    if openfoam_metric is not None:
        metrics.append(openfoam_metric)

    return metrics


def summarize_solver_run(results_dir: Path) -> dict:
    summary = {
        "solver": "unknown",
        "status": "unknown",
        "primary_log": None,
        "status_reason": None,
        "text_sources": [],
        "artifacts": {
            "input_files": [],
            "log_files": [],
            "result_files": [],
        },
    }
    if not results_dir.exists() or not results_dir.is_dir():
        return summary

    text_sources = collect_solver_text_sources(results_dir)
    solver = _detect_solver_family(results_dir, text_sources)
    primary_log = _pick_matching_log(results_dir, solver)
    status, reason = _detect_solver_status(results_dir, solver, primary_log)

    log_files = _iter_runtime_logs(results_dir)
    input_files = sorted(
        path
        for path in results_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _INPUT_EXTENSIONS
    )
    excluded = {path.resolve() for path in log_files + input_files}
    result_files: list[Path] = []
    for path in sorted(results_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in excluded:
            continue
        if path.suffix.lower() == ".md":
            continue
        result_files.append(path)

    summary["solver"] = solver
    summary["status"] = status
    summary["primary_log"] = primary_log.name if primary_log else None
    summary["status_reason"] = reason
    summary["text_sources"] = [
        {
            "path": str(path.relative_to(results_dir)).replace("\\", "/"),
            "kind": _text_source_kind(path),
        }
        for path in text_sources
    ]
    summary["artifacts"] = {
        "input_files": _limit_relpaths(input_files, results_dir),
        "log_files": _limit_relpaths(log_files, results_dir),
        "result_files": _limit_relpaths(result_files, results_dir),
    }
    return summary


def _extract_calculix_sta_metrics(results_dir: Path) -> list[dict]:
    metrics: list[dict] = []
    float_pattern = r"(-?[\d.]+(?:[eE][+-]?\d+)?)"

    for sta_file in sorted(results_dir.glob("*.sta")):
        try:
            lines = sta_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            continue

        max_iterations = 0
        final_residual = None
        final_force_ratio = None
        final_increment = None
        converged = None
        residual_series: list[float] = []
        increment_series: list[float] = []

        for line in lines[-200:]:
            upper = line.upper()
            if converged is None:
                if "NOT CONVERGED" in upper or "DID NOT CONVERGE" in upper or "FAILED" in upper:
                    converged = "NOT CONVERGED"
                elif "CONVERGED" in upper:
                    converged = "CONVERGED"

            iter_match = re.search(r"iter[=\s]+(\d+)", line, re.IGNORECASE)
            if iter_match:
                max_iterations = max(max_iterations, int(iter_match.group(1)))

            resid_match = re.search(rf"resid[.=\s]+{float_pattern}", line, re.IGNORECASE)
            if resid_match:
                final_residual = float(resid_match.group(1))
                residual_series.append(final_residual)

            force_match = re.search(rf"force%?\s*=\s*{float_pattern}", line, re.IGNORECASE)
            if force_match:
                final_force_ratio = float(force_match.group(1))

            inc_match = re.search(rf"increment\s+size\s*=\s*{float_pattern}", line, re.IGNORECASE)
            if inc_match:
                final_increment = float(inc_match.group(1))
                increment_series.append(final_increment)

        if (
            converged is not None
            or max_iterations > 0
            or final_residual is not None
            or final_increment is not None
        ):
            residual_trend = _classify_series_trend(residual_series)
            increment_trend = _classify_series_trend(
                increment_series,
                direction_words=("shrinking", "growing", "steady"),
            )
            metrics.append(
                {
                    "file": sta_file.name,
                    "solver": "calculix",
                    "source": "sta",
                    "status": converged,
                    "max_iter": max_iterations if max_iterations > 0 else None,
                    "final_residual": final_residual,
                    "final_force_ratio": final_force_ratio,
                    "final_increment": final_increment,
                    "residual_trend": residual_trend if residual_trend != "insufficient" else None,
                    "residual_span": _format_series_bounds(residual_series) if residual_series else None,
                    "increment_trend": increment_trend if increment_trend != "insufficient" else None,
                    "increment_span": _format_series_bounds(increment_series) if increment_series else None,
                }
            )

    return metrics


def _extract_su2_history_metric(history_file: Path, *, log_file: Path | None = None) -> dict | None:
    if not history_file.is_file():
        return None

    try:
        with history_file.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            if not fieldnames:
                return None

            residual_keys = [
                key
                for key in fieldnames
                if "rms[" in _normalize_header(key).lower()
            ]
            if not residual_keys:
                return None

            inner_iter_key = _find_header(fieldnames, "inner_iter")
            outer_iter_key = _find_header(fieldnames, "outer_iter")
            time_iter_key = _find_header(fieldnames, "time_iter")

            residual_series: list[float] = []
            max_iterations = 0
            last_outer_iter = None
            last_time_iter = None

            for row in reader:
                residual_values = [
                    _normalize_su2_residual(_float_or_none(row.get(key)))
                    for key in residual_keys
                ]
                filtered = [value for value in residual_values if value is not None]
                if filtered:
                    residual_series.append(max(filtered))

                inner_iter = _int_or_none(row.get(inner_iter_key)) if inner_iter_key else None
                outer_iter = _int_or_none(row.get(outer_iter_key)) if outer_iter_key else None
                time_iter = _int_or_none(row.get(time_iter_key)) if time_iter_key else None
                if inner_iter is not None:
                    max_iterations = max(max_iterations, inner_iter)
                elif outer_iter is not None:
                    max_iterations = max(max_iterations, outer_iter)
                elif time_iter is not None:
                    max_iterations = max(max_iterations, time_iter)
                last_outer_iter = outer_iter if outer_iter is not None else last_outer_iter
                last_time_iter = time_iter if time_iter is not None else last_time_iter
    except (OSError, ValueError, csv.Error):
        return None

    if not residual_series:
        return None

    log_text = _read_text(log_file) if log_file else ""
    status = None
    if "maximum number of iterations reached" in log_text.lower() or "before convergence" in log_text.lower():
        status = "NOT CONVERGED"
    elif "exit success (su2_cfd)" in log_text.lower():
        status = "COMPLETED"
    elif residual_series[-1] <= 1e-8:
        status = "CONVERGED"

    metric = {
        "file": history_file.name,
        "solver": "su2",
        "source": "history.csv",
        "status": status,
        "max_iter": max_iterations if max_iterations > 0 else None,
        "final_residual": residual_series[-1],
        "final_force_ratio": None,
        "final_increment": None,
        "residual_trend": _classify_series_trend(residual_series),
        "residual_span": _format_series_bounds(residual_series),
        "increment_trend": None,
        "increment_span": None,
    }
    if last_outer_iter is not None:
        metric["final_outer_iter"] = last_outer_iter
    if last_time_iter is not None:
        metric["final_time_iter"] = last_time_iter
    return metric


def _extract_openfoam_log_metric(log_file: Path) -> dict | None:
    if not log_file.is_file():
        return None

    text = _read_text(log_file)
    lowered = text.lower()
    if "openfoam" not in lowered and "courant number mean" not in lowered:
        return None

    time_values: list[float] = []
    residual_series: list[float] = []
    max_courant = None
    max_solver_iterations = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        time_match = re.search(r"^Time\s*=\s*([0-9eE.+-]+)s?$", line)
        if time_match:
            time_value = _float_or_none(time_match.group(1))
            if time_value is not None:
                time_values.append(time_value)

        courant_match = re.search(
            r"Courant Number mean:\s*([0-9eE.+-]+)\s+max:\s*([0-9eE.+-]+)",
            line,
        )
        if courant_match:
            current_max = _float_or_none(courant_match.group(2))
            if current_max is not None:
                max_courant = current_max if max_courant is None else max(max_courant, current_max)

        residual_match = re.search(
            r"Final residual =\s*([0-9eE.+-]+),\s*No Iterations\s+(\d+)",
            line,
        )
        if residual_match:
            residual = _float_or_none(residual_match.group(1))
            iterations = _int_or_none(residual_match.group(2))
            if residual is not None:
                residual_series.append(residual)
            if iterations is not None:
                max_solver_iterations = max(max_solver_iterations, iterations)

    if not residual_series and not time_values:
        return None

    time_increments = [
        round(time_values[idx] - time_values[idx - 1], 12)
        for idx in range(1, len(time_values))
    ]
    final_increment = None
    if time_increments:
        final_increment = time_increments[-1]

    status = None
    if any(pattern in lowered for pattern in _OPENFOAM_FAILURE_PATTERNS):
        status = "FAILED"
    elif re.search(r"(?m)^End\s*$", text):
        status = "COMPLETED"

    metric = {
        "file": log_file.name,
        "solver": "openfoam",
        "source": "docker-log",
        "status": status,
        "max_iter": len(time_values) if time_values else None,
        "final_residual": residual_series[-1] if residual_series else None,
        "final_force_ratio": None,
        "final_increment": final_increment,
        "residual_trend": _classify_series_trend(residual_series),
        "residual_span": _format_series_bounds(residual_series) if residual_series else None,
        "increment_trend": _classify_series_trend(
            time_increments,
            direction_words=("shrinking", "growing", "steady"),
        ) if len(time_increments) >= 2 else None,
        "increment_span": _format_series_bounds(time_increments) if time_increments else None,
    }
    if time_values:
        metric["final_time"] = time_values[-1]
    if max_courant is not None:
        metric["max_courant"] = max_courant
    if max_solver_iterations > 0:
        metric["max_solver_iterations"] = max_solver_iterations
    return metric


def _detect_solver_family(results_dir: Path, text_sources: list[Path]) -> str:
    history_file = results_dir / "history.csv"
    if history_file.is_file():
        su2_log = _pick_matching_log(results_dir, "su2")
        if su2_log or any(path.suffix.lower() == ".cfg" for path in results_dir.iterdir() if path.is_file()):
            return "su2"

    openfoam_log = _pick_matching_log(results_dir, "openfoam", allow_fallback=False)
    if openfoam_log:
        return "openfoam"
    if (results_dir / "system" / "controlDict").exists() and (results_dir / "constant").exists():
        return "openfoam"

    code_aster_log = _pick_matching_log(results_dir, "code_aster", allow_fallback=False)
    if code_aster_log:
        return "code_aster"
    if any(path.suffix.lower() in {".comm", ".export"} for path in results_dir.iterdir() if path.is_file()):
        return "code_aster"

    if any(path.suffix.lower() == ".sif" for path in results_dir.iterdir() if path.is_file()):
        return "elmer"
    if (results_dir / "mesh").is_dir():
        return "elmer"

    if any(path.suffix.lower() in {".frd", ".sta", ".stderr"} for path in results_dir.iterdir() if path.is_file()):
        return "calculix"

    if text_sources:
        first_name = text_sources[0].name.lower()
        if "su2" in first_name:
            return "su2"
        if "openfoam" in first_name:
            return "openfoam"
        if "code_aster" in first_name:
            return "code_aster"

    return "unknown"


def _detect_solver_status(
    results_dir: Path,
    solver: str,
    primary_log: Path | None,
) -> tuple[str, str | None]:
    if solver == "su2":
        return _detect_su2_status(results_dir, primary_log)
    if solver == "openfoam":
        return _detect_openfoam_status(primary_log)
    if solver == "code_aster":
        return _detect_code_aster_status(primary_log)
    if solver == "elmer":
        return _detect_elmer_status(results_dir, primary_log)
    if solver == "calculix":
        return _detect_calculix_status(results_dir)
    return "unknown", None


def _detect_su2_status(results_dir: Path, log_file: Path | None) -> tuple[str, str | None]:
    text = _read_text(log_file) if log_file else ""
    lowered = text.lower()
    if "maximum number of iterations reached" in lowered or "before convergence" in lowered:
        return "not_converged", _first_matching_line(
            text,
            ("maximum number of iterations reached", "before convergence"),
        )
    if any(pattern in lowered for pattern in _SU2_FAILURE_PATTERNS):
        return "failed", _first_matching_line(text, _SU2_FAILURE_PATTERNS)
    if "exit success (su2_cfd)" in lowered:
        return "success", _first_matching_line(text, ("exit success",))

    history_metric = _extract_su2_history_metric(results_dir / "history.csv", log_file=log_file)
    if history_metric and history_metric.get("final_residual") is not None:
        if float(history_metric["final_residual"]) <= 1e-8:
            return "success", "SU2 residual history reached a low final residual."
    return "unknown", None


def _detect_openfoam_status(log_file: Path | None) -> tuple[str, str | None]:
    text = _read_text(log_file) if log_file else ""
    lowered = text.lower()
    if any(pattern in lowered for pattern in _OPENFOAM_FAILURE_PATTERNS):
        return "failed", _first_matching_line(text, _OPENFOAM_FAILURE_PATTERNS)
    if re.search(r"(?m)^End\s*$", text):
        return "success", "OpenFOAM log reached End."
    return "unknown", None


def _detect_code_aster_status(log_file: Path | None) -> tuple[str, str | None]:
    text = _read_text(log_file) if log_file else ""
    lowered = text.lower()
    if any(pattern in lowered for pattern in _CODE_ASTER_FAILURE_PATTERNS):
        return "failed", _first_matching_line(text, _CODE_ASTER_FAILURE_PATTERNS)
    if "diagnostic job : ok" in lowered:
        return "success", _first_matching_line(text, ("diagnostic job : ok",))
    if "arret normal" in lowered or "exits normally" in lowered:
        return "success", _first_matching_line(text, ("arret normal", "exits normally"))
    return "unknown", None


def _detect_elmer_status(results_dir: Path, log_file: Path | None) -> tuple[str, str | None]:
    text = _read_text(log_file) if log_file else ""
    lowered = text.lower()
    if "error" in lowered and "solver" in lowered:
        return "failed", _first_matching_line(text, ("error",))
    if list(results_dir.glob("*.vtu")) or list(results_dir.glob("*.ep")):
        return "success", "Elmer output files were generated."
    return "unknown", None


def _detect_calculix_status(results_dir: Path) -> tuple[str, str | None]:
    if list(results_dir.glob("*.frd")):
        return "success", "CalculiX FRD result file detected."

    for stderr_file in sorted(results_dir.glob("*.stderr")):
        text = _read_text(stderr_file)
        lowered = text.lower()
        if "not converged" in lowered or "did not converge" in lowered:
            return "not_converged", _first_matching_line(text, ("not converged", "did not converge"))
        if "fatal error" in lowered:
            return "failed", _first_matching_line(text, ("fatal error",))

    return "unknown", None


def _pick_matching_log(
    results_dir: Path,
    solver: str,
    *,
    allow_fallback: bool = True,
) -> Path | None:
    log_files = _iter_runtime_logs(results_dir)
    if not log_files:
        return None

    solver_token = solver.replace("_", "")
    for path in log_files:
        lowered = path.name.lower().replace("_", "")
        if solver_token and solver_token in lowered:
            return path

    for path in log_files:
        text = _read_text(path)
        lowered = text.lower()
        if solver == "openfoam" and ("openfoam" in lowered or "courant number mean" in lowered):
            return path
        if solver == "su2" and ("su2" in lowered or "exit success (su2_cfd)" in lowered):
            return path
        if solver == "code_aster" and ("code_aster" in lowered or "diagnostic job" in lowered):
            return path
        if solver == "elmer" and "elmersolver" in lowered:
            return path

    return log_files[0] if allow_fallback else None


def _iter_runtime_logs(results_dir: Path) -> list[Path]:
    logs: list[Path] = []
    seen: set[Path] = set()
    for path in results_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if path.suffix.lower() == ".log" or name.startswith("log."):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            logs.append(path)
    logs.sort(key=lambda path: (len(path.relative_to(results_dir).parts), str(path.relative_to(results_dir))))
    return logs[:24]


def _text_source_kind(path: Path) -> str:
    if path.suffix.lower() == ".stderr":
        return "stderr"
    if path.suffix.lower() == ".sta":
        return "convergence_log"
    if path.suffix.lower() in {".out", ".err"}:
        return "runtime_log"
    if path.suffix.lower() == ".log":
        return "runtime_log"
    if path.name.lower() == "history.csv":
        return "solver_history"
    return "auxiliary_text"


def _is_text_source_candidate(path: Path) -> bool:
    name = path.name.lower()
    if name in _TEXT_NAME_ALLOWLIST:
        return True
    if name.startswith("docker-") and name.endswith(".log"):
        return True
    if name.startswith("log."):
        return True
    return path.suffix.lower() in _TEXT_SUFFIX_ALLOWLIST


def _text_source_priority(path: Path, root: Path) -> tuple[int, int]:
    name = path.name.lower()
    depth = len(path.relative_to(root).parts)
    if name.startswith("docker-") and name.endswith(".log"):
        return (0, depth)
    if name == "history.csv":
        return (1, depth)
    if path.suffix.lower() == ".stderr":
        return (2, depth)
    if path.suffix.lower() == ".sta":
        return (3, depth)
    if name == "solver.log":
        return (4, depth)
    if path.suffix.lower() == ".log" or name.startswith("log."):
        return (5, depth)
    if path.suffix.lower() in {".dat", ".cvg"}:
        return (6, depth)
    if path.suffix.lower() in {".out", ".err"}:
        return (7, depth)
    return (8, depth)


def _limit_relpaths(paths: list[Path], root: Path, limit: int = 12) -> list[str]:
    return [
        str(path.relative_to(root)).replace("\\", "/")
        for path in paths[:limit]
    ]


def _classify_series_trend(
    values: list[float],
    *,
    neutral_ratio: float = 0.15,
    direction_words: tuple[str, str, str] = ("decreasing", "increasing", "steady"),
) -> str:
    if len(values) < 2:
        return "insufficient"

    first = values[0]
    last = values[-1]
    if first == 0:
        if last == 0:
            return direction_words[2]
        return direction_words[1] if last > 0 else direction_words[0]

    ratio = (last - first) / abs(first)
    if ratio <= -neutral_ratio:
        return direction_words[0]
    if ratio >= neutral_ratio:
        return direction_words[1]
    return direction_words[2]


def _format_series_bounds(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{values[0]:.3e}->{values[-1]:.3e}"


def _find_header(fieldnames: list[str], normalized_target: str) -> str | None:
    for name in fieldnames:
        if _normalize_header(name).lower() == normalized_target.lower():
            return name
    return None


def _normalize_header(value: str) -> str:
    return value.strip().strip('"').replace(" ", "")


def _normalize_su2_residual(value: float | None) -> float | None:
    if value is None:
        return None
    if -100.0 <= value <= 20.0:
        return 10.0 ** value
    return abs(value)


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().strip('"'))
    except ValueError:
        return None


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip().strip('"')))
    except ValueError:
        return None


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first_matching_line(text: str, needles: tuple[str, ...]) -> str | None:
    lowered_needles = tuple(needle.lower() for needle in needles)
    for line in text.splitlines():
        lowered = line.lower()
        if any(needle in lowered for needle in lowered_needles):
            return line.strip()
    return None
