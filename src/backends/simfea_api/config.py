import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def project_root() -> Path:
    def looks_like_project_root(path: Path) -> bool:
        return (path / "package.json").exists() and (path / "src-tauri").exists()

    if getattr(sys, "frozen", False):
        start = Path.cwd().resolve()
    else:
        start = Path(__file__).resolve().parents[3]

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

