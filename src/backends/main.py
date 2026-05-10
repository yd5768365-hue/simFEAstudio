import asyncio
import json
import os
import re
import signal
import shutil
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from uvicorn import Config, Server

try:
    from .inference import infer_text_api
except ImportError:
    from inference import infer_text_api


def project_root() -> Path:
    def looks_like_project_root(path: Path) -> bool:
        return (path / "package.json").exists() and (path / "src-tauri").exists()

    if getattr(sys, "frozen", False):
        start = Path.cwd().resolve()
    else:
        start = Path(__file__).resolve().parents[2]

    for candidate in [start, *start.parents]:
        if looks_like_project_root(candidate):
            return candidate

    if start.name == "src-tauri" and looks_like_project_root(start.parent):
        return start.parent
    return start


PROJECT_ROOT = project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / ".simfea" / "config.json"
DEFAULT_RUNS_ROOT = PROJECT_ROOT / ".simfea" / "runs"
DEFAULT_WINDOWS_SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
DEFAULT_WINDOWS_SCP = r"C:\Windows\System32\OpenSSH\scp.exe"

DEFAULT_TOOLCHAIN = [
    {
        "name": "FreeCAD",
        "role": "几何建模与 STEP/BREP 来源",
        "status": "后期接入",
    },
    {
        "name": "Salome",
        "role": "复杂网格、网格脚本与前处理来源",
        "status": "后期接入",
    },
    {
        "name": "PrePoMax / CalculiX",
        "role": "结构有限元求解与结果文件来源",
        "status": "后期接入",
    },
    {
        "name": "OpenFOAM / Elmer",
        "role": "流体与多物理场求解入口",
        "status": "后期接入",
    },
    {
        "name": "SSH / WSL / Docker",
        "role": "统一运行器，把本地和远程命令归档为同一种证据",
        "status": "当前验证",
    },
]

server_instance = None
remote_runs = {}

app = FastAPI(
    title="SimFEA Studio API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class T_Query(TypedDict):
    prompt: str


class T_Note(TypedDict, total=False):
    note: str
    export: bool
    format: str
    target_dir: str


class T_LearningExport(TypedDict, total=False):
    format: str
    target_dir: str


@dataclass
class ComputeNode:
    alias: str
    label: str
    host: str = ""
    user: str = ""
    port: Optional[int] = None
    identity_file: str = ""
    remote_runs_root: str = "$HOME/simfea-runs"
    connect_timeout_seconds: int = 8
    batch_mode: bool = True
    strict_host_key_checking: str = "accept-new"


@dataclass
class AppSettings:
    api_port: int
    api_public_host: str
    runs_root: Path
    learning_export_root: Path
    learning_formats: list[str]
    learning_default_format: str
    config_path: Path
    ssh_exe: str
    scp_exe: str
    compute_nodes: dict[str, ComputeNode]
    default_compute_node: str
    toolchain: list[dict[str, str]]


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def expand_path(value: str | Path | None, *, relative_to_project: bool = False) -> Path:
    if not value:
        return Path()
    expanded = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if relative_to_project and not expanded.is_absolute():
        return PROJECT_ROOT / expanded
    return expanded


def find_executable(config_value: str, executable_name: str, windows_fallback: str) -> str:
    env_key = f"SIMFEA_{executable_name.upper()}_EXE"
    configured = os.getenv(env_key) or config_value
    if configured:
        return str(expand_path(configured))
    discovered = shutil.which(executable_name)
    if discovered:
        return discovered
    return windows_fallback


def default_config() -> dict:
    return {
        "api": {
            "port": int(os.getenv("SIMFEA_API_PORT", "8008")),
            "public_host": os.getenv("SIMFEA_API_PUBLIC_HOST", "localhost"),
        },
        "paths": {
            "runs_root": os.getenv("SIMFEA_RUNS_ROOT", str(DEFAULT_RUNS_ROOT)),
        },
        "learning": {
            "export_root": os.getenv("SIMFEA_LEARNING_EXPORT_ROOT", str(PROJECT_ROOT / ".simfea" / "learning")),
            "default_format": os.getenv("SIMFEA_LEARNING_DEFAULT_FORMAT", "md"),
            "formats": ["md", "json", "txt"],
        },
        "ssh": {
            "ssh_exe": os.getenv("SIMFEA_SSH_EXE", ""),
            "scp_exe": os.getenv("SIMFEA_SCP_EXE", ""),
        },
        "compute": {
            "default_node": os.getenv("SIMFEA_DEFAULT_COMPUTE_NODE", ""),
            "nodes": [],
        },
        "toolchain": DEFAULT_TOOLCHAIN,
    }


def load_config_file(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> AppSettings:
    config_path = expand_path(
        os.getenv("SIMFEA_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)),
        relative_to_project=True,
    )
    raw_config = deep_merge(default_config(), load_config_file(config_path))

    nodes = {}
    for item in raw_config.get("compute", {}).get("nodes", []):
        node = ComputeNode(
            alias=item["alias"],
            label=item.get("label") or item["alias"],
            host=item.get("host", ""),
            user=item.get("user", ""),
            port=item.get("port"),
            identity_file=item.get("identity_file", ""),
            remote_runs_root=item.get("remote_runs_root", "$HOME/simfea-runs"),
            connect_timeout_seconds=int(item.get("connect_timeout_seconds", 8)),
            batch_mode=bool(item.get("batch_mode", True)),
            strict_host_key_checking=item.get("strict_host_key_checking", "accept-new"),
        )
        nodes[node.alias] = node

    default_node = raw_config.get("compute", {}).get("default_node") or next(iter(nodes), "")
    learning_config = raw_config.get("learning", {})
    learning_formats = [
        normalize_learning_format(item)
        for item in learning_config.get("formats", ["md", "json", "txt"])
    ]
    learning_formats = [item for item in dict.fromkeys(learning_formats) if item in {"md", "json", "txt"}]
    if not learning_formats:
        learning_formats = ["md"]
    learning_default_format = normalize_learning_format(learning_config.get("default_format", learning_formats[0]))
    if learning_default_format not in learning_formats:
        learning_default_format = learning_formats[0]

    return AppSettings(
        api_port=int(raw_config["api"]["port"]),
        api_public_host=raw_config["api"].get("public_host", "localhost"),
        runs_root=expand_path(raw_config["paths"]["runs_root"], relative_to_project=True),
        learning_export_root=expand_path(
            learning_config.get("export_root", str(PROJECT_ROOT / ".simfea" / "learning")),
            relative_to_project=True,
        ),
        learning_formats=learning_formats,
        learning_default_format=learning_default_format,
        config_path=config_path,
        ssh_exe=find_executable(raw_config["ssh"].get("ssh_exe", ""), "ssh", DEFAULT_WINDOWS_SSH),
        scp_exe=find_executable(raw_config["ssh"].get("scp_exe", ""), "scp", DEFAULT_WINDOWS_SCP),
        compute_nodes=nodes,
        default_compute_node=default_node,
        toolchain=raw_config.get("toolchain", DEFAULT_TOOLCHAIN),
    )


def settings() -> AppSettings:
    return load_settings()


def public_compute_node(node: ComputeNode) -> dict:
    return {
        "alias": node.alias,
        "label": node.label,
        "host": node.host,
        "user": node.user,
        "port": node.port,
        "remote_runs_root": node.remote_runs_root,
        "configured": bool(node.host),
    }


def get_compute_node(alias: str | None = None) -> ComputeNode:
    current = settings()
    node_alias = alias or current.default_compute_node
    if not node_alias:
        raise HTTPException(
            status_code=404,
            detail=f"No compute node configured. Create {current.config_path}.",
        )
    node = current.compute_nodes.get(node_alias)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Compute node not found: {node_alias}")
    return node


def ssh_target(node: ComputeNode) -> str:
    if node.host and node.user:
        return f"{node.user}@{node.host}"
    if node.host:
        return node.host
    return node.alias


def common_ssh_options(node: ComputeNode) -> list[str]:
    options = [
        "-o",
        f"BatchMode={'yes' if node.batch_mode else 'no'}",
        "-o",
        f"ConnectTimeout={node.connect_timeout_seconds}",
        "-o",
        f"StrictHostKeyChecking={node.strict_host_key_checking}",
    ]
    if node.identity_file:
        options.extend(["-i", str(expand_path(node.identity_file))])
    return options


def build_ssh_command(node: ComputeNode, remote_command: str) -> list[str]:
    command = [settings().ssh_exe, "-n", *common_ssh_options(node)]
    if node.port:
        command.extend(["-p", str(node.port)])
    command.extend([ssh_target(node), remote_command])
    return command


def build_scp_command(node: ComputeNode, remote_path: str, local_path: Path) -> list[str]:
    command = [settings().scp_exe, *common_ssh_options(node)]
    if node.port:
        command.extend(["-P", str(node.port)])
    command.extend([f"{ssh_target(node)}:{remote_path}", str(local_path)])
    return command


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
    runs_root = settings().runs_root
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
            meta.setdefault("toolchain", settings().toolchain)
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
        return "无"
    return "\n".join(content.splitlines()[-max_lines:])


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


def normalize_learning_format(value: str | None) -> str:
    normalized = (value or "md").strip().lower().lstrip(".")
    aliases = {
        "markdown": "md",
        "md": "md",
        "json": "json",
        "txt": "txt",
        "text": "txt",
    }
    return aliases.get(normalized, normalized)


def sanitize_filename_part(value: str | None, fallback: str = "untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value or "").strip(" ._")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or fallback


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

    solver = meta.get("solver") or parsed.get("solver") or ""
    runner = meta.get("runner") or ""
    case_type = "cantilever_beam" if solver in {"demo-shell", "demo-slurm-shell"} else "unknown"
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
    vtk_artifact = ""
    if case_type == "cantilever_beam":
        vtk_artifact = generate_cantilever_vtk_artifact(
            run_dir,
            displacement_mm=displacement_mm,
            stress_mpa=stress_mpa,
        )

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
        "artifacts": run_artifacts(run_dir, include_summary=False),
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
            "ready": case_type != "unknown",
        },
        "raw_values": parsed,
    }

    summary_path = artifacts_dir / "result_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    meta["result_summary"] = "artifacts/result_summary.json"
    meta["artifacts"] = run_artifacts(run_dir)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def generate_learning_report(run_dir: Path) -> Path:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing run metadata: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    note = read_optional_text(run_dir / "note.md", "尚未填写。").strip() or "尚未填写。"
    stdout_tail = read_tail(run_dir / "stdout.log")
    stderr_tail = read_tail(run_dir / "stderr.log")
    result_text = read_optional_text(run_dir / "artifacts" / "result.txt", "暂无结果文件。").strip()
    toolchain_lines = "\n".join(
        f"- {item['name']}：{item['role']}（{item['status']}）"
        for item in meta.get("toolchain", settings().toolchain)
    )
    scheduler_lines = [
        f"- 调度器：{meta.get('scheduler') or '无'}",
        f"- 作业 ID：{meta.get('job_id') or '无'}",
        f"- 分区：{meta.get('partition') or '无'}",
        f"- 运行节点：{meta.get('allocated_node') or '无'}",
        f"- 申请 CPU：{meta.get('requested_cpus') or '无'}",
        f"- 申请内存：{meta.get('requested_memory') or '无'}",
        f"- 最近调度状态：{meta.get('last_scheduler_state') or '无'}",
    ]
    scheduler_summary = "\n".join(scheduler_lines)

    report = f"""# SimFEA Studio 学习沉淀报告

## 运行身份
- 运行 ID：{meta.get("run_id", "")}
- 算例：{meta.get("case_name", "")}
- 求解器/执行器：{meta.get("solver", "")} / {meta.get("runner", "")}
- 计算节点：{meta.get("compute_node_label", meta.get("compute_node", ""))}
- 状态：{meta.get("status", "")}
- 退出码：{meta.get("exit_code", "")}
- 创建时间：{meta.get("created_at", "")}
- 结束时间：{meta.get("finished_at", "")}
- 本地归档：{meta.get("local_archive", "")}
- 远程目录：{meta.get("remote_workdir", "")}

## 调度信息
{scheduler_summary}

## 工具链位置
{toolchain_lines}

## 执行命令
```bash
{meta.get("command", "").strip()}
```

## 实时日志摘要
```text
{stdout_tail}
```

## 错误输出摘要
```text
{stderr_tail}
```

## 结果文件摘要
```text
{result_text}
```

## 学习笔记
{note}

## 下一步问题
- 这次运行是否证明了远程执行链路可靠？
- 当前输入、命令、日志和结果之间是否能互相解释？
- 下一步要把 demo-shell 替换成 CalculiX、OpenFOAM、Elmer，还是先接 FreeCAD/Salome 的输入文件？
"""

    report_path = run_dir / "learning_report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def learning_export_root(target_dir: str | None = None) -> Path:
    current = settings()
    if target_dir and target_dir.strip():
        return expand_path(target_dir.strip(), relative_to_project=True)
    return current.learning_export_root


def build_plain_learning_record(meta: dict, report: str, note: str, summary: dict | None) -> str:
    metrics = (summary or {}).get("metrics", {})
    lines = [
        "SimFEA Studio 学习记录",
        "",
        f"运行 ID：{meta.get('run_id', '')}",
        f"算例：{meta.get('case_name', '')}",
        f"求解器/执行器：{meta.get('solver', '')} / {meta.get('runner', '')}",
        f"计算节点：{meta.get('compute_node_label', meta.get('compute_node', ''))}",
        f"状态：{meta.get('status', '')}",
        f"退出码：{meta.get('exit_code', '')}",
        f"本地归档：{meta.get('local_archive', '')}",
        f"远程目录：{meta.get('remote_workdir', '')}",
        "",
        "关键结果",
        f"最大位移 mm：{metrics.get('max_displacement_mm', '无')}",
        f"最大 Von Mises MPa：{metrics.get('max_von_mises_mpa', '无')}",
        "",
        "学习笔记",
        note or "尚未填写。",
        "",
        "完整报告",
        report,
    ]
    return "\n".join(str(line) for line in lines)


def export_learning_record(run_dir: Path, export_format: str | None, target_dir: str | None = None) -> dict:
    if not run_dir.exists():
        raise FileNotFoundError(f"Run not found: {run_dir}")

    current = settings()
    normalized_format = normalize_learning_format(export_format or current.learning_default_format)
    if normalized_format not in current.learning_formats:
        raise ValueError(
            f"Unsupported learning export format: {export_format}. "
            f"Allowed formats: {', '.join(current.learning_formats)}"
        )

    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    note = read_optional_text(run_dir / "note.md").strip()

    target_root = learning_export_root(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    date_part = (meta.get("created_at") or utc_now()).split("T", 1)[0]
    filename = "_".join(
        [
            sanitize_filename_part(date_part, "date"),
            sanitize_filename_part(meta.get("run_id"), run_dir.name),
            sanitize_filename_part(meta.get("case_name"), "case"),
        ]
    )
    export_path = target_root / f"{filename}.{normalized_format}"
    record = {
        "schema_version": "simfea.learning-record.v1",
        "exported_at": utc_now(),
        "format": normalized_format,
        "source": {
            "run_archive": str(run_dir),
            "learning_report": str(report_path),
            "note": str(run_dir / "note.md"),
        },
        "run": meta,
        "summary": summary,
        "note": note,
        "report": report,
        "artifacts": run_artifacts(run_dir),
    }

    if normalized_format == "json":
        export_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    elif normalized_format == "txt":
        export_path.write_text(build_plain_learning_record(meta, report, note, summary), encoding="utf-8")
    else:
        export_path.write_text(report, encoding="utf-8")

    export_record = {
        "path": str(export_path),
        "format": normalized_format,
        "exported_at": record["exported_at"],
    }
    exports = meta.get("learning_exports")
    if not isinstance(exports, list):
        exports = []
    exports = [
        item
        for item in exports
        if isinstance(item, dict)
        and not (item.get("path") == export_record["path"] and item.get("format") == export_record["format"])
    ]
    exports.append(export_record)
    meta["learning_export"] = export_record
    meta["learning_exports"] = exports[-20:]
    meta["learning_report"] = "learning_report.md"
    meta["result_summary"] = "artifacts/result_summary.json" if summary else None
    meta["artifacts"] = run_artifacts(run_dir)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "run_id": meta.get("run_id", run_dir.name),
        "export_path": str(export_path),
        "export_root": str(target_root),
        "format": normalized_format,
        "allowed_formats": current.learning_formats,
        "default_format": current.learning_default_format,
        "summary": summary,
        "record": export_record,
    }


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


async def run_command(command: list[str], timeout: float = 20.0):
    started_at = asyncio.get_running_loop().time()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout:.0f}s.",
            "duration_seconds": round(asyncio.get_running_loop().time() - started_at, 3),
        }

    return {
        "exit_code": process.returncode,
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
        "duration_seconds": round(asyncio.get_running_loop().time() - started_at, 3),
    }


def parse_key_value_stdout(stdout: str):
    values = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


async def emit_remote_event(run: RemoteRun, event_type: str, **payload):
    message = {
        "run_id": run.run_id,
        "type": event_type,
        "archive_path": str(run.local_dir),
        **payload,
    }
    append_text(run.local_dir / "events.jsonl", json.dumps(message, ensure_ascii=False))
    await run.queue.put(message)


async def read_stream_lines(run: RemoteRun, stream, event_type: str):
    log_name = "stdout.log" if event_type == "stdout" else "stderr.log"
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        append_text(run.local_dir / log_name, text)
        await emit_remote_event(run, event_type, line=text)


def remote_workdir_for(node: ComputeNode, run_id: str) -> str:
    return f"{node.remote_runs_root.rstrip('/')}/{run_id}"


def build_evidence_demo_script(run: RemoteRun):
    return f"""
set -e
RUN_ID={sh_quote(run.run_id)}
REMOTE_WORKDIR={sh_quote(run.remote_workdir)}
mkdir -p "$REMOTE_WORKDIR"
cd "$REMOTE_WORKDIR"
cat > input.txt <<'EOF'
case=悬臂梁远程闭环样例
solver=demo-shell
purpose=验证远程运行、实时日志、结果归档、学习笔记
EOF
echo "SimFEA Studio 远程运行开始"
echo "run_id=$RUN_ID"
echo "hostname=$(hostname)"
echo "user=$(whoami)"
echo "workdir=$(pwd)"
for step in 1 2 3 4 5; do
  echo "step=$step assemble_or_solve"
  sleep 1
done
cat > result.txt <<EOF
SimFEA Studio evidence result
run_id=$RUN_ID
hostname=$(hostname)
status=success
max_displacement_mm=0.421
max_von_mises_mpa=128.6
note=这是一个远程闭环演示结果，后续会替换为真实求解器输出。
EOF
echo "artifact=result.txt"
echo "SimFEA Studio 远程运行结束"
"""


def build_slurm_job_script(run: RemoteRun) -> str:
    partition = run.partition or "dg83"
    cpus = run.requested_cpus or 4
    memory = run.requested_memory or "8G"
    return f"""#!/bin/bash
#SBATCH -J simfea-demo
#SBATCH -p {partition}
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory}
#SBATCH -o slurm-%j.out
#SBATCH -e slurm-%j.err

set -e
trap 'code=$?; echo "exit_code=$code" > job_exit_code.txt' EXIT

RUN_ID="{run.run_id}"
echo "SimFEA Studio Slurm 运行开始"
echo "run_id=$RUN_ID"
echo "job_id=$SLURM_JOB_ID"
echo "submit_host=$SLURM_SUBMIT_HOST"
echo "run_node=$(hostname)"
echo "user=$(whoami)"
echo "workdir=$(pwd)"
echo "partition={partition}"
echo "cpus=$SLURM_CPUS_PER_TASK"
echo "memory_request={memory}"
nproc
free -h
for step in 1 2 3 4 5; do
  echo "slurm_step=$step assemble_or_solve"
  sleep 2
done
cat > result.txt <<EOF
SimFEA Studio Slurm evidence result
run_id=$RUN_ID
job_id=$SLURM_JOB_ID
submit_host=$SLURM_SUBMIT_HOST
run_node=$(hostname)
status=success
requested_cpus=$SLURM_CPUS_PER_TASK
requested_memory={memory}
max_displacement_mm=0.421
max_von_mises_mpa=128.6
note=这是一个 Slurm 闭环演示结果，证明任务进入真实计算节点。
EOF
echo "artifact=result.txt"
echo "SimFEA Studio Slurm 运行结束"
"""


def build_slurm_submit_script(run: RemoteRun) -> str:
    if not run.slurm_script:
        raise ValueError("Missing Slurm script.")
    return f"""
set -e
RUN_ID={sh_quote(run.run_id)}
REMOTE_WORKDIR={sh_quote(run.remote_workdir)}
mkdir -p "$REMOTE_WORKDIR"
cd "$REMOTE_WORKDIR"
cat > input.txt <<'EOF'
case=Slurm 远程闭环样例
solver=demo-slurm-shell
purpose=验证 sbatch 提交、squeue 轮询、日志回传、结果归档、学习笔记
EOF
cat > simfea-demo.slurm <<'EOF'
{run.slurm_script.rstrip()}
EOF
sbatch simfea-demo.slurm
"""


async def download_remote_result(run: RemoteRun, node: ComputeNode):
    local_result = run.artifacts_dir / "result.txt"
    remote_result = f"{run.remote_workdir}/result.txt"
    result = await run_command(build_scp_command(node, remote_result, local_result), timeout=30.0)
    if result["exit_code"] == 0:
        run.result_downloaded = True
        await emit_remote_event(
            run,
            "artifact",
            line=f"结果文件已归档：{local_result}",
            artifact="artifacts/result.txt",
        )
    else:
        await emit_remote_event(
            run,
            "stderr",
            line=f"结果文件拉取失败：{result['stderr'] or result['stdout']}",
        )


async def download_remote_file(run: RemoteRun, node: ComputeNode, remote_name: str, local_name: str | None = None):
    local_path = run.artifacts_dir / (local_name or remote_name)
    remote_path = f"{run.remote_workdir}/{remote_name}"
    result = await run_command(build_scp_command(node, remote_path, local_path), timeout=30.0)
    if result["exit_code"] == 0:
        if remote_name == "result.txt":
            run.result_downloaded = True
        await emit_remote_event(
            run,
            "artifact",
            line=f"结果物证已归档：{local_path}",
            artifact=str(local_path.relative_to(run.local_dir)).replace("\\", "/"),
        )
    else:
        await emit_remote_event(
            run,
            "stderr",
            line=f"远程文件归档失败 {remote_name}：{result['stderr'] or result['stdout']}",
        )


async def read_remote_text(node: ComputeNode, remote_path: str, timeout: float = 20.0) -> str:
    result = await run_command(
        build_ssh_command(node, f"cat {sh_quote(remote_path)} 2>/dev/null || true"),
        timeout=timeout,
    )
    return result["stdout"] if result["exit_code"] == 0 else ""


async def sync_remote_log_file(
    run: RemoteRun,
    node: ComputeNode,
    remote_name: str,
    local_name: str,
    event_type: str,
    already_seen: int,
) -> int:
    content = await read_remote_text(node, f"{run.remote_workdir}/{remote_name}")
    lines = content.splitlines()
    for text in lines[already_seen:]:
        append_text(run.local_dir / local_name, text)
        await emit_remote_event(run, event_type, line=text)
    return len(lines)


def parse_sbatch_job_id(stdout: str) -> Optional[str]:
    for token in stdout.split():
        if token.isdigit():
            return token
    return None


async def query_slurm_state(run: RemoteRun, node: ComputeNode) -> tuple[str, str]:
    if not run.job_id:
        return "", ""
    result = await run_command(
        build_ssh_command(node, f"squeue -h -j {run.job_id} -o '%T|%N' 2>/dev/null || true"),
        timeout=20.0,
    )
    line = result["stdout"].strip().splitlines()[0] if result["stdout"].strip() else ""
    if "|" not in line:
        return "", ""
    state, node_list = line.split("|", 1)
    return state.strip(), node_list.strip()


async def cancel_slurm_job(run: RemoteRun, node: ComputeNode):
    if not run.job_id:
        return
    await run_command(build_ssh_command(node, f"scancel {run.job_id} 2>/dev/null || true"), timeout=20.0)
    await emit_remote_event(run, "status", status="canceling", line=f"已向 Slurm 发送 scancel：{run.job_id}")


async def download_slurm_artifacts(run: RemoteRun, node: ComputeNode):
    names = ["input.txt", "simfea-demo.slurm", "result.txt", "job_exit_code.txt"]
    if run.job_id:
        names.extend([f"slurm-{run.job_id}.out", f"slurm-{run.job_id}.err"])
    for name in names:
        await download_remote_file(run, node, name)


async def execute_remote_run(run: RemoteRun, node: ComputeNode):
    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        await emit_remote_event(
            run,
            "finished",
            status="canceled",
            exit_code=-1,
            line="远程任务已在启动前取消。",
            archive_path=str(run.local_dir),
        )
        await run.queue.put(None)
        return

    run.status = "running"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="running",
        line="远程终端已连接，任务开始执行。",
        remote_workdir=run.remote_workdir,
    )
    try:
        run.process = await asyncio.create_subprocess_exec(
            *build_ssh_command(node, run.command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.gather(
            read_stream_lines(run, run.process.stdout, "stdout"),
            read_stream_lines(run, run.process.stderr, "stderr"),
        )
        run.exit_code = await run.process.wait()
        if run.cancel_requested:
            run.status = "canceled"
        elif run.exit_code == 0:
            await download_remote_result(run, node)
            run.status = "finished"
        else:
            run.status = "failed"
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        final_line = "远程任务已取消。" if run.status == "canceled" else f"远程任务结束，退出码 {run.exit_code}。"
        await emit_remote_event(
            run,
            "finished",
            status=run.status,
            exit_code=run.exit_code,
            line=final_line,
            archive_path=str(run.local_dir),
        )
    except Exception as exc:
        run.status = "failed"
        run.exit_code = -1
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        await emit_remote_event(
            run,
            "finished",
            status="failed",
            exit_code=-1,
            line=f"远程任务异常：{exc}",
        )
    finally:
        await run.queue.put(None)


async def execute_slurm_run(run: RemoteRun, node: ComputeNode):
    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        await emit_remote_event(
            run,
            "finished",
            status="canceled",
            exit_code=-1,
            line="Slurm 任务已在提交前取消。",
            archive_path=str(run.local_dir),
        )
        await run.queue.put(None)
        return

    run.status = "submitting"
    run.started_at = utc_now()
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="submitting",
        line="正在通过 SSH 写入 Slurm 脚本并提交 sbatch。",
        remote_workdir=run.remote_workdir,
    )

    submit_stdout = ""
    submit_stderr = ""
    try:
        run.process = await asyncio.create_subprocess_exec(
            *build_ssh_command(node, run.command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(run.process.communicate(), timeout=45.0)
        submit_stdout = stdout_bytes.decode("utf-8", errors="replace")
        submit_stderr = stderr_bytes.decode("utf-8", errors="replace")
        for line in submit_stdout.splitlines():
            append_text(run.local_dir / "stdout.log", line)
            await emit_remote_event(run, "stdout", line=line)
        for line in submit_stderr.splitlines():
            append_text(run.local_dir / "stderr.log", line)
            await emit_remote_event(run, "stderr", line=line)
        submit_exit = await run.process.wait()
    except asyncio.TimeoutError:
        if run.process and run.process.returncode is None:
            run.process.kill()
            await run.process.wait()
        submit_exit = -1
        submit_stderr = "sbatch submit command timed out."
    except Exception as exc:
        submit_exit = -1
        submit_stderr = str(exc)

    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        await emit_remote_event(run, "finished", status="canceled", exit_code=-1, line="Slurm 提交已取消。")
        await run.queue.put(None)
        return

    run.job_id = parse_sbatch_job_id(submit_stdout)
    if submit_exit != 0 or not run.job_id:
        run.status = "failed"
        run.exit_code = submit_exit if submit_exit != 0 else -1
        run.finished_at = utc_now()
        save_run_metadata(run)
        generate_result_summary(run.local_dir)
        generate_learning_report(run.local_dir)
        save_run_metadata(run)
        await emit_remote_event(
            run,
            "finished",
            status="failed",
            exit_code=run.exit_code,
            line=f"Slurm 提交失败：{submit_stderr or submit_stdout or '未解析到 JobID'}",
        )
        await run.queue.put(None)
        return

    run.status = "queued"
    run.last_scheduler_state = "SUBMITTED"
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="queued",
        job_id=run.job_id,
        line=f"Slurm 作业已提交：{run.job_id}",
    )

    last_stdout_count = 0
    last_stderr_count = 0
    last_state_line = ""
    timed_out = False
    deadline = asyncio.get_running_loop().time() + 3600

    while True:
        if asyncio.get_running_loop().time() > deadline:
            timed_out = True
            break

        if run.cancel_requested:
            await cancel_slurm_job(run, node)
            run.status = "canceling"
            save_run_metadata(run)

        state, node_list = await query_slurm_state(run, node)
        if state:
            run.last_scheduler_state = state
            run.status = "running" if state == "RUNNING" else "queued"
            if node_list and not node_list.startswith("("):
                run.allocated_node = node_list
            state_line = f"{state}|{node_list}"
            if state_line != last_state_line:
                await emit_remote_event(
                    run,
                    "status",
                    status=run.status,
                    scheduler_state=state,
                    allocated_node=run.allocated_node,
                    line=f"Slurm 状态：{state} {node_list}".strip(),
                )
                last_state_line = state_line
            save_run_metadata(run)
        else:
            break

        if run.job_id:
            last_stdout_count = await sync_remote_log_file(
                run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
            )
            last_stderr_count = await sync_remote_log_file(
                run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
            )

        await asyncio.sleep(2)

    if run.job_id:
        last_stdout_count = await sync_remote_log_file(
            run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
        )
        last_stderr_count = await sync_remote_log_file(
            run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
        )

    exit_text = ""
    for _ in range(5):
        exit_text = (await read_remote_text(node, f"{run.remote_workdir}/job_exit_code.txt", timeout=20.0)).strip()
        if exit_text:
            break
        await asyncio.sleep(2)

    if run.job_id:
        last_stdout_count = await sync_remote_log_file(
            run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
        )
        last_stderr_count = await sync_remote_log_file(
            run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
        )
    if run.cancel_requested:
        run.status = "canceled"
        run.exit_code = -1
        run.last_scheduler_state = "CANCELED"
    elif timed_out:
        run.status = "failed"
        run.exit_code = -1
        run.last_scheduler_state = "TIMEOUT"
    elif exit_text.isdigit():
        run.exit_code = int(exit_text)
        run.status = "finished" if run.exit_code == 0 else "failed"
        run.last_scheduler_state = "COMPLETED" if run.exit_code == 0 else "FAILED"
    else:
        run.status = "failed"
        run.exit_code = -1
        run.last_scheduler_state = "UNKNOWN"

    run.finished_at = utc_now()
    save_run_metadata(run)
    await download_slurm_artifacts(run, node)
    save_run_metadata(run)
    generate_result_summary(run.local_dir)
    generate_learning_report(run.local_dir)
    save_run_metadata(run)

    final_line = (
        "Slurm 任务已取消。"
        if run.status == "canceled"
        else f"Slurm 任务结束，状态 {run.status}，退出码 {run.exit_code}。"
    )
    await emit_remote_event(
        run,
        "finished",
        status=run.status,
        exit_code=run.exit_code,
        job_id=run.job_id,
        allocated_node=run.allocated_node,
        line=final_line,
        archive_path=str(run.local_dir),
    )
    await run.queue.put(None)


@app.get("/v1/config")
def get_app_config():
    current = settings()
    return {
        "message": "SimFEA Studio config loaded.",
        "data": {
            "api": {
                "port": current.api_port,
                "public_host": current.api_public_host,
            },
            "paths": {
                "runs_root": str(current.runs_root),
                "config_path": str(current.config_path),
            },
            "learning": {
                "export_root": str(current.learning_export_root),
                "formats": current.learning_formats,
                "default_format": current.learning_default_format,
            },
            "compute": {
                "default_node": current.default_compute_node,
                "nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
            },
            "toolchain": current.toolchain,
        },
    }


@app.get("/v1/connect")
def connect_to_api_server():
    print("[server] Connecting to server...", flush=True)
    current = settings()
    host = f"http://{current.api_public_host}:{current.api_port}"
    return {
        "message": f"Connected to SimFEA Studio API server on port {current.api_port}.",
        "data": {
            "port": current.api_port,
            "pid": os.getpid(),
            "host": host,
            "runs_root": str(current.runs_root),
            "config_path": str(current.config_path),
            "learning_export_root": str(current.learning_export_root),
            "learning_formats": current.learning_formats,
            "learning_default_format": current.learning_default_format,
            "default_compute_node": current.default_compute_node,
            "compute_nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
            "toolchain": current.toolchain,
        },
    }


@app.post("/v1/completions")
def llm_completion(payload: T_Query = Body(...)):
    return infer_text_api.completions(payload)


@app.get("/v1/compute-nodes")
def list_compute_nodes():
    current = settings()
    return {
        "message": "SimFEA Studio compute nodes loaded.",
        "data": {
            "default_node": current.default_compute_node,
            "nodes": [public_compute_node(node) for node in current.compute_nodes.values()],
        },
    }


@app.get("/v1/compute-nodes/{alias}/probe")
async def probe_compute_node(alias: str):
    node = get_compute_node(alias)
    remote_command = (
        "printf 'hostname='; hostname; "
        "printf 'user='; whoami; "
        "printf 'cpu_cores='; nproc 2>/dev/null || getconf _NPROCESSORS_ONLN; "
        "printf 'workdir='; pwd"
    )
    result = await run_command(build_ssh_command(node, remote_command), timeout=20.0)
    ok = result["exit_code"] == 0
    details = parse_key_value_stdout(result["stdout"]) if ok else {}
    return {
        "message": f"{alias} remote compute node probe completed." if ok else f"{alias} remote compute node probe failed.",
        "data": {
            "alias": node.alias,
            "label": node.label,
            "connected": ok,
            "details": details,
            **result,
        },
    }


@app.get("/v1/compute-nodes/{alias}/scheduler-probe")
async def probe_compute_node_scheduler(alias: str):
    node = get_compute_node(alias)
    remote_command = (
        "printf 'hostname='; hostname; "
        "printf 'user='; whoami; "
        "printf 'scheduler='; "
        "if command -v sbatch >/dev/null 2>&1; then echo slurm; "
        "elif command -v qsub >/dev/null 2>&1; then echo pbs; "
        "elif command -v bsub >/dev/null 2>&1; then echo lsf; "
        "else echo none; fi; "
        "printf 'sbatch='; command -v sbatch 2>/dev/null || true; "
        "printf 'srun='; command -v srun 2>/dev/null || true; "
        "printf 'squeue='; command -v squeue 2>/dev/null || true; "
        "printf 'qsub='; command -v qsub 2>/dev/null || true; "
        "printf 'bsub='; command -v bsub 2>/dev/null || true; "
        "printf 'cpu_cores='; nproc 2>/dev/null || getconf _NPROCESSORS_ONLN; "
        "printf 'memory='; free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || true; "
        "printf 'workdir='; pwd"
    )
    result = await run_command(build_ssh_command(node, remote_command), timeout=25.0)
    ok = result["exit_code"] == 0
    details = parse_key_value_stdout(result["stdout"]) if ok else {}
    return {
        "message": f"{alias} scheduler probe completed." if ok else f"{alias} scheduler probe failed.",
        "data": {
            "alias": node.alias,
            "label": node.label,
            "connected": ok,
            "details": details,
            **result,
        },
    }


@app.get("/v1/runs")
def list_runs():
    current = settings()
    return {
        "message": "SimFEA Studio archived runs loaded.",
        "data": {
            "runs_root": str(current.runs_root),
            "learning_export_root": str(current.learning_export_root),
            "learning_formats": current.learning_formats,
            "learning_default_format": current.learning_default_format,
            "runs": load_archived_runs(),
        },
    }


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str):
    run = remote_runs.get(run_id)
    if run is not None:
        summary = generate_result_summary(run.local_dir)
        note = (run.local_dir / "note.md").read_text(encoding="utf-8")
        report = read_optional_text(run.local_dir / "learning_report.md")
        data = run_metadata(run)
        meta_path = run.local_dir / "meta.json"
        if meta_path.exists():
            archived_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for key in ("learning_export", "learning_exports"):
                if key in archived_meta:
                    data[key] = archived_meta[key]
        return {
            "message": "SimFEA Studio run loaded.",
            "data": {
                **data,
                "note": note,
                "report": report,
                "summary": summary,
            },
        }

    runs_root = settings().runs_root
    run_dir = runs_root / run_id
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    note_path = runs_root / run_id / "note.md"
    report_path = runs_root / run_id / "learning_report.md"
    meta.setdefault("toolchain", settings().toolchain)
    meta["note"] = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    meta["report"] = read_optional_text(report_path)
    meta["summary"] = summary
    if report_path.exists():
        meta["learning_report"] = "learning_report.md"
    return {
        "message": "SimFEA Studio archived run loaded.",
        "data": meta,
    }


@app.get("/v1/runs/{run_id}/result-summary")
def get_run_result_summary(run_id: str):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    return {
        "message": "SimFEA Studio result summary generated.",
        "data": {
            "run_id": run_id,
            "summary_path": str(run_dir / "artifacts" / "result_summary.json"),
            "summary": summary,
        },
    }


@app.get("/v1/runs/{run_id}/artifacts/{artifact_path:path}")
def get_run_artifact(run_id: str, artifact_path: str):
    run_dir = (settings().runs_root / run_id).resolve()
    artifact = (run_dir / artifact_path).resolve()

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        artifact.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")

    media_type = "text/plain"
    if artifact.suffix.lower() == ".json":
        media_type = "application/json"
    elif artifact.suffix.lower() in {".vtk", ".vtu"}:
        media_type = "model/vnd.vtk"

    return FileResponse(artifact, media_type=media_type, filename=artifact.name)


@app.get("/v1/runs/{run_id}/report")
def get_run_report(run_id: str):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": None,
        }

    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["learning_report"] = "learning_report.md"
        meta["result_summary"] = "artifacts/result_summary.json" if summary else None
        meta.setdefault("toolchain", settings().toolchain)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "message": "SimFEA Studio learning report generated.",
        "data": {
            "run_id": run_id,
            "report_path": str(report_path),
            "report": report_path.read_text(encoding="utf-8"),
            "summary": summary,
        },
    }


@app.post("/v1/runs/{run_id}/learning-export")
def export_run_learning_record(run_id: str, payload: T_LearningExport = Body(default={})):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "exported": False,
                "run_id": run_id,
            },
        }

    try:
        export_result = export_learning_record(
            run_dir,
            payload.get("format"),
            payload.get("target_dir"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "SimFEA Studio learning record exported.",
        "data": {
            "exported": True,
            **export_result,
        },
    }


@app.post("/v1/runs/{alias}/demo")
async def start_demo_run(alias: str):
    node = get_compute_node(alias)
    current = settings()
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    remote_workdir = remote_workdir_for(node, run_id)
    local_dir = current.runs_root / run_id
    run = RemoteRun(
        run_id=run_id,
        case_name="远程闭环样例",
        solver="demo-shell",
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=remote_workdir,
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="",
        created_at=utc_now(),
        toolchain=current.toolchain,
    )
    run.command = f"bash -lc {sh_quote(build_evidence_demo_script(run))}"
    ensure_run_files(run)
    remote_runs[run_id] = run
    asyncio.create_task(execute_remote_run(run, node))
    return {
        "message": f"{node.alias} remote evidence run started.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
        },
    }


@app.post("/v1/runs/{alias}/slurm-demo")
async def start_slurm_demo_run(alias: str):
    node = get_compute_node(alias)
    current = settings()
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    remote_workdir = remote_workdir_for(node, run_id)
    local_dir = current.runs_root / run_id
    run = RemoteRun(
        run_id=run_id,
        case_name="Slurm 远程闭环样例",
        solver="demo-slurm-shell",
        node_alias=node.alias,
        node_label=node.label,
        remote_workdir=remote_workdir,
        local_dir=local_dir,
        artifacts_dir=local_dir / "artifacts",
        command="",
        created_at=utc_now(),
        runner="SlurmRunner",
        toolchain=current.toolchain,
        scheduler="slurm",
        partition="dg83",
        requested_cpus=4,
        requested_memory="8G",
    )
    run.slurm_script = build_slurm_job_script(run)
    run.command = f"bash -lc {sh_quote(build_slurm_submit_script(run))}"
    ensure_run_files(run)
    remote_runs[run_id] = run
    asyncio.create_task(execute_slurm_run(run, node))
    return {
        "message": f"{node.alias} Slurm evidence run submitted.",
        "data": {
            "run_id": run_id,
            "status": run.status,
            "archive_path": str(run.local_dir),
            "remote_workdir": run.remote_workdir,
            "compute_node": node.alias,
            "scheduler": run.scheduler,
            "partition": run.partition,
            "requested_cpus": run.requested_cpus,
            "requested_memory": run.requested_memory,
        },
    }


@app.post("/v1/runs/{run_id}/note")
def save_run_note(run_id: str, payload: T_Note = Body(...)):
    run_dir = settings().runs_root / run_id
    if not run_dir.exists():
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "saved": False,
                "run_id": run_id,
            },
        }

    note = payload.get("note", "")
    note_path = run_dir / "note.md"
    note_path.write_text(note, encoding="utf-8")
    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    export_result = None
    if payload.get("export"):
        export_result = export_learning_record(
            run_dir,
            payload.get("format"),
            payload.get("target_dir"),
        )
    return {
        "message": "SimFEA Studio learning note saved.",
        "data": {
            "saved": True,
            "run_id": run_id,
            "note_path": str(note_path),
            "report_path": str(report_path),
            "summary_path": str(run_dir / "artifacts" / "result_summary.json") if summary else "",
            "learning_export": export_result,
        },
    }


@app.post("/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    run = remote_runs.get(run_id)
    if run is None:
        return {
            "message": "SimFEA Studio run not found.",
            "data": {
                "run_id": run_id,
                "cancel_requested": False,
                "status": "missing",
            },
        }

    if run.status not in {"created", "submitting", "queued", "running", "canceling"}:
        return {
            "message": "SimFEA Studio run is already finished.",
            "data": {
                "run_id": run_id,
                "cancel_requested": False,
                "status": run.status,
                "exit_code": run.exit_code,
            },
        }

    run.cancel_requested = True
    run.status = "canceling"
    save_run_metadata(run)
    await emit_remote_event(
        run,
        "status",
        status="canceling",
        line="已请求取消远程任务，正在终止 SSH 通道。",
    )

    if run.runner == "SlurmRunner" and run.job_id:
        try:
            await cancel_slurm_job(run, get_compute_node(run.node_alias))
        except Exception as exc:
            await emit_remote_event(run, "stderr", line=f"Slurm 取消请求失败：{exc}")
    elif run.process is not None and run.process.returncode is None:
        try:
            run.process.terminate()
        except ProcessLookupError:
            pass

    return {
        "message": "SimFEA Studio cancel request sent.",
        "data": {
            "run_id": run_id,
            "cancel_requested": True,
            "status": run.status,
        },
    }


@app.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    run = remote_runs.get(run_id)
    if run is None:
        async def missing_run_events():
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "run_id": run_id,
                        "type": "finished",
                        "status": "failed",
                        "exit_code": -1,
                        "line": "没有找到这个运行任务。",
                    },
                    ensure_ascii=False,
                ),
            }

        return EventSourceResponse(missing_run_events())

    async def event_generator():
        while True:
            event = await run.queue.get()
            if event is None:
                break
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


def kill_process():
    os.kill(os.getpid(), signal.SIGINT)


def start_api_server(**kwargs):
    global server_instance
    port = kwargs.get("port", settings().api_port)
    try:
        if server_instance is None:
            print("[sidecar] Starting API server...", flush=True)
            config = Config(app, host="0.0.0.0", port=port, log_level="info")
            server_instance = Server(config)
            asyncio.run(server_instance.serve())
        else:
            print(
                "[sidecar] Failed to start new server. Server instance already running.",
                flush=True,
            )
    except Exception as e:
        print(f"[sidecar] Error, failed to start API server {e}", flush=True)


def stdin_loop():
    print("[sidecar] Waiting for commands...", flush=True)
    while True:
        raw_input = sys.stdin.readline()
        if raw_input == "":
            # When the sidecar is launched without an attached stdin, readline()
            # returns immediately. Avoid flooding the UI log while the API runs.
            threading.Event().wait(0.25)
            continue
        user_input = raw_input.strip()
        match user_input:
            case "sidecar shutdown":
                print("[sidecar] Received 'sidecar shutdown' command.", flush=True)
                kill_process()
            case _:
                print(
                    f"[sidecar] Invalid command [{user_input}]. Try again.",
                    flush=True,
                )


def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True
        input_thread.start()
    except Exception:
        print("[sidecar] Failed to start input handler.", flush=True)


if __name__ == "__main__":
    start_input_thread()
    start_api_server()
