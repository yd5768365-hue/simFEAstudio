import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .run_archive import append_text, read_optional_text


def post_process_solver_artifacts(run_dir: Path) -> dict:
    """Convert solver-native result files to VTK/VTU and extract metrics.

    Finds .frd files in artifacts/, converts first one via frd_convert
    (generates VTU + PVD for multi-step, legacy VTK for compat),
    and appends extracted metrics to result.txt.

    Also processes .dat files if present (integration-point statistics).
    """
    artifacts_dir = run_dir / "artifacts"
    frd_files = sorted(artifacts_dir.glob("*.frd"))
    dat_files = sorted(artifacts_dir.glob("*.dat"))

    metrics: dict = {}

    # ── FRD → VTK/VTU conversion ──
    if frd_files:
        from .frd_to_vtk import frd_convert

        try:
            metrics = frd_convert(frd_files[0], artifacts_dir, "solver_result")
        except (ValueError, OSError) as exc:
            return {"error": str(exc)}

    # ── DAT → integration-point summary ──
    if dat_files:
        try:
            from .frd_dat_reader import write_dat_summary
            dat_metrics = write_dat_summary(dat_files[0], artifacts_dir / "dat_summary.txt")
            metrics.update(dat_metrics)
        except Exception:
            pass  # DAT parsing is best-effort

    # ── Write result.txt ──
    result_path = artifacts_dir / "result.txt"
    lines = []
    if result_path.exists():
        lines.append(result_path.read_text(encoding="utf-8").rstrip())
    if "max_displacement_mm" in metrics:
        lines.append(f"max_displacement_mm={metrics['max_displacement_mm']:.6f}")
    if "max_von_mises_mpa" in metrics:
        lines.append(f"max_von_mises_mpa={metrics['max_von_mises_mpa']:.6f}")
    if lines:
        result_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return metrics


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_key_value_text(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_optional_float(value: str | int | float | None) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_int(value: str | int | float | None) -> Optional[int]:
    number = parse_optional_float(value)
    return int(number) if number is not None else None


def run_artifacts(run_dir: Path, *, include_summary: bool = True) -> list[str]:
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.exists():
        return []
    artifacts = []
    for path in sorted(artifacts_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(run_dir)).replace("\\", "/")
        if not include_summary and relative == "artifacts/result_summary.json":
            continue
        artifacts.append(relative)
    return artifacts


def primary_vtk_artifact(artifacts: list[str]) -> str:
    for suffix in (".vtu", ".vtk"):
        for artifact in artifacts:
            if artifact.lower().endswith(suffix):
                return artifact
    return ""


def generate_cantilever_vtk_artifact(
    run_dir: Path,
    *,
    displacement_mm: Optional[float],
    stress_mpa: Optional[float],
) -> str:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    vtk_path = artifacts_dir / "cantilever_result.vtk"

    length = 100.0
    half_width = 4.0
    half_height = 4.0
    max_disp = displacement_mm if displacement_mm is not None else 0.12
    max_stress = stress_mpa if stress_mpa is not None else 25.0
    stations = 9

    points = []
    displacements = []
    stresses = []
    for index in range(stations):
        t = index / (stations - 1)
        x = length * t
        deflection = -max_disp * (t**2) * 28.0
        axial_stress = max_stress * (1.0 - 0.72 * t)
        section_points = [
            (x, -half_width, deflection - half_height),
            (x, half_width, deflection - half_height),
            (x, half_width, deflection + half_height),
            (x, -half_width, deflection + half_height),
        ]
        points.extend(section_points)
        displacements.extend([(0.0, 0.0, deflection)] * 4)
        stresses.extend([max(axial_stress, max_stress * 0.18)] * 4)

    polygons = []
    for index in range(stations - 1):
        a = index * 4
        b = (index + 1) * 4
        polygons.extend(
            [
                (a, b, b + 1, a + 1),
                (a + 1, b + 1, b + 2, a + 2),
                (a + 2, b + 2, b + 3, a + 3),
                (a + 3, b + 3, b, a),
            ]
        )
    polygons.extend([(0, 1, 2, 3)])
    last = (stations - 1) * 4
    polygons.extend([(last, last + 3, last + 2, last + 1)])

    lines = [
        "# vtk DataFile Version 3.0",
        "SimFEA Studio cantilever demo result",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(points)} float",
    ]
    lines.extend(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in points)
    lines.append(f"POLYGONS {len(polygons)} {len(polygons) * 5}")
    lines.extend(f"4 {a} {b} {c} {d}" for a, b, c, d in polygons)
    lines.extend(
        [
            f"POINT_DATA {len(points)}",
            "SCALARS von_mises_mpa float 1",
            "LOOKUP_TABLE default",
        ]
    )
    lines.extend(f"{value:.6f}" for value in stresses)
    lines.append("VECTORS displacement_mm float")
    lines.extend(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in displacements)
    vtk_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(vtk_path.relative_to(run_dir)).replace("\\", "/")


def generate_result_summary(run_dir: Path) -> Optional[dict]:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result_text = read_optional_text(artifacts_dir / "result.txt")
    stdout_text = read_optional_text(run_dir / "stdout.log")
    parsed = {
        **parse_key_value_text(stdout_text),
        **parse_key_value_text(result_text),
    }

    artifacts = run_artifacts(run_dir, include_summary=False)
    solver = meta.get("solver") or parsed.get("solver") or ""
    runner = meta.get("runner") or ""
    solver_kind = meta.get("solver_kind") or ""
    case_type = "cantilever_beam" if solver in {"demo-shell", "demo-slurm-shell"} else solver_kind or "unknown"
    run_node = (
        meta.get("allocated_node")
        or parsed.get("run_node")
        or parsed.get("hostname")
        or ""
    )
    job_id = meta.get("job_id") or parsed.get("job_id") or ""
    partition = meta.get("partition") or parsed.get("partition") or ""
    requested_cpus = meta.get("requested_cpus") or parse_optional_int(parsed.get("requested_cpus") or parsed.get("cpus"))
    requested_memory = meta.get("requested_memory") or parsed.get("requested_memory") or parsed.get("memory_request") or ""
    displacement_mm = parse_optional_float(parsed.get("max_displacement_mm"))
    stress_mpa = parse_optional_float(parsed.get("max_von_mises_mpa"))
    vtk_artifact = primary_vtk_artifact(artifacts)
    if case_type == "cantilever_beam":
        vtk_artifact = generate_cantilever_vtk_artifact(
            run_dir,
            displacement_mm=displacement_mm,
            stress_mpa=stress_mpa,
        )
        artifacts = run_artifacts(run_dir, include_summary=False)
    visualization_ready = bool(vtk_artifact) or case_type == "cantilever_beam"

    summary = {
        "schema_version": "simfea.result-summary.v1",
        "generated_at": utc_now(),
        "run_id": meta.get("run_id", run_dir.name),
        "case_name": meta.get("case_name", ""),
        "case_type": case_type,
        "solver": solver,
        "runner": runner,
        "status": meta.get("status", ""),
        "exit_code": meta.get("exit_code"),
        "execution": {
            "compute_node": meta.get("compute_node", ""),
            "compute_node_label": meta.get("compute_node_label", meta.get("compute_node", "")),
            "remote_workdir": meta.get("remote_workdir", ""),
            "local_archive": meta.get("local_archive", str(run_dir)),
            "created_at": meta.get("created_at", ""),
            "started_at": meta.get("started_at", ""),
            "finished_at": meta.get("finished_at", ""),
        },
        "scheduler": {
            "name": meta.get("scheduler") or "",
            "job_id": job_id,
            "partition": partition,
            "allocated_node": run_node,
            "requested_cpus": requested_cpus,
            "requested_memory": requested_memory,
            "last_state": meta.get("last_scheduler_state") or "",
        },
        "metrics": {
            "max_displacement_mm": displacement_mm,
            "max_von_mises_mpa": stress_mpa,
        },
        "units": {
            "max_displacement_mm": "mm",
            "max_von_mises_mpa": "MPa",
        },
        "artifacts": artifacts,
        "sources": {
            "result_text": "artifacts/result.txt" if (artifacts_dir / "result.txt").exists() else "",
            "stdout_log": "stdout.log" if (run_dir / "stdout.log").exists() else "",
            "stderr_log": "stderr.log" if (run_dir / "stderr.log").exists() else "",
        },
        "visualization": {
            "kind": case_type,
            "primary_metric": "max_displacement_mm",
            "stress_metric": "max_von_mises_mpa",
            "vtk_artifact": vtk_artifact,
            "ready": visualization_ready,
        },
        "raw_values": parsed,
    }

    summary_path = artifacts_dir / "result_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    meta["result_summary"] = "artifacts/result_summary.json"
    meta["artifacts"] = run_artifacts(run_dir)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
