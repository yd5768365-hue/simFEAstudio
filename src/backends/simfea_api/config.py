import json
import os
import shutil
import sys
from dataclasses import dataclass, field
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
class SolverDefinition:
    alias: str
    label: str
    kind: str
    executable: str
    command_template: str
    input_files: dict[str, str]
    artifact_patterns: list[str]
    description: str = ""
    pre_commands: list[str] = field(default_factory=list)
    post_commands: list[str] = field(default_factory=list)
    timeout_seconds: int = 120


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
    solvers: dict[str, SolverDefinition]
    toolchain: list[dict[str, str]]
    run_retention_days: int = 90
    max_runs: int = 100


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
        "cleanup": {
            "run_retention_days": int(os.getenv("SIMFEA_RUN_RETENTION_DAYS", "90")),
            "max_runs": int(os.getenv("SIMFEA_MAX_RUNS", "100")),
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
            "default_node": os.getenv("SIMFEA_DEFAULT_COMPUTE_NODE", "local"),
            "nodes": [
                {
                    "alias": "local",
                    "label": "Local Machine",
                    "host": "localhost",
                    "user": "",
                    "remote_runs_root": ".simfea/runs",
                },
            ],
        },
        "solvers": [
            {
                "alias": "calculix",
                "label": "CalculiX",
                "kind": "structural",
                "executable": "ccx",
                "description": "Structural finite element solver adapter.",
                "command_template": "ccx cantilever",
                "artifact_patterns": ["*.frd", "*.dat", "*.sta", "result.txt"],
                "pre_commands": [],
                "post_commands": [
                    "printf 'max_displacement_mm=' && grep -o 'U[[:space:]]*[0-9.]*' cantilever.dat 2>/dev/null | tail -1 | awk '{print $NF}' || true",
                    "printf 'max_von_mises_mpa=' && grep -o 'S[[:space:]]*[0-9.]*' cantilever.dat 2>/dev/null | tail -1 | awk '{print $NF}' || true",
                ],
                "input_files": {
                    "cantilever.inp": """*HEADING
SimFEA Studio CalculiX adapter smoke case (N, mm, MPa)
*NODE
1, 0., 0., 0.
2, 1000., 0., 0.
*ELEMENT, TYPE=B31, ELSET=beam
1, 1, 2
*MATERIAL, NAME=steel
*ELASTIC
210000., 0.3
*BEAM SECTION, ELSET=beam, MATERIAL=steel, SECTION=RECT
20., 20.
0., 0., 1.
*BOUNDARY
1, 1, 6
*STEP
*STATIC
*CLOAD
2, 2, -100.
*NODE FILE
U
*EL FILE, ELSET=beam
S
*END STEP
""",
                },
            },
            {
                "alias": "freecad",
                "label": "FreeCAD",
                "kind": "preprocessor",
                "executable": "python",
                "description": "FreeCAD Python API adapter. Run with a Python environment that can import FreeCAD and Part.",
                "command_template": "${solver_executable} freecad_smoke.py",
                "artifact_patterns": ["*.FCStd", "*.step", "*.stp", "result.txt"],
                "pre_commands": [],
                "post_commands": [],
                "input_files": {
                    "freecad_smoke.py": """import FreeCAD as App
import Part

doc = App.newDocument("SimFEA_FreeCAD_Smoke")
box = Part.makeBox(10, 10, 10)
Part.show(box)
doc.recompute()
doc.saveAs("freecad_smoke.FCStd")
Part.export([box], "freecad_smoke.step")
print("freecad_artifact=freecad_smoke.step")
""",
                },
            },
            {
                "alias": "prepomax",
                "label": "PrePoMax",
                "kind": "structural-prepost",
                "executable": "PrePoMax",
                "description": "PrePoMax command-line adapter placeholder. Use -f to import geometry or -r with -g No for regeneration workflows.",
                "command_template": "\"${solver_executable}\" --help",
                "artifact_patterns": ["*.pmx", "*.inp", "*.frd", "*.dat", "*.vtk", "*.vtu", "prepomax_adapter.txt", "result.txt"],
                "pre_commands": [],
                "post_commands": [],
                "input_files": {
                    "README.prepomax.txt": "PrePoMax CLI smoke run. For geometry import use: PrePoMax -f model.step -u MM_TON_S_C. For automation use: PrePoMax -r model.pmx -g No -w workdir.\n",
                },
            },
            {
                "alias": "prepomax-regenerate",
                "label": "PrePoMax Regenerate",
                "kind": "structural-prepost",
                "executable": "PrePoMax",
                "description": "Headless PrePoMax regeneration workflow. Provide model.pmx and related geometry files in the run workdir.",
                "command_template": "\"${solver_executable}\" -r model.pmx -g No -w .",
                "artifact_patterns": ["*.pmx", "*.STEP", "*.step", "*.inp", "*.frd", "*.dat", "*.sta", "*.cvg", "*.csv", "_output_*.txt", "_error_*.txt", "result.txt"],
                "pre_commands": [],
                "post_commands": [],
                "input_files": {
                    "README.prepomax-regenerate.txt": "PrePoMax regeneration template. Add model.pmx and required geometry files to this workdir, then run: PrePoMax -r model.pmx -g No -w .\n",
                },
            },
            {
                "alias": "openfoam",
                "label": "OpenFOAM",
                "kind": "fluid",
                "executable": "icoFoam",
                "description": "OpenFOAM case adapter. Provide a real case through config for production runs.",
                "command_template": "foamDictionary -help >/dev/null 2>&1 || true; echo 'OpenFOAM adapter ready: provide case files in solvers.openfoam.input_files'; touch result.txt",
                "artifact_patterns": ["log.*", "postProcessing/**", "result.txt"],
                "pre_commands": [],
                "post_commands": [],
                "input_files": {
                    "README.simfea.txt": "OpenFOAM adapter placeholder. Replace input_files with a real OpenFOAM case in .simfea/config.json.\n",
                },
            },
            {
                "alias": "elmer",
                "label": "Elmer",
                "kind": "multiphysics",
                "executable": "ElmerSolver",
                "description": "Elmer multiphysics solver adapter.",
                "command_template": "ElmerSolver case.sif",
                "artifact_patterns": ["case.result", "*.ep", "*.vtu", "result.txt"],
                "pre_commands": [],
                "post_commands": [],
                "input_files": {
                    "case.sif": """Header
  CHECK KEYWORDS Warn
End
Simulation
  Max Output Level = 3
  Coordinate System = Cartesian
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output File = case.result
End
""",
                },
            },
        ],
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

    # Merge solvers by alias: default solvers provide the base (including
    # input_files templates); user config solvers with the same alias override
    # individual fields.  This lets the user set e.g. the calculix executable
    # without losing the openfoam / elmer defaults.
    default_solver_items = {s["alias"]: s for s in default_config().get("solvers", [])}
    raw_config.setdefault("solvers", [])
    for item in raw_config["solvers"]:
        alias = item["alias"]
        if alias in default_solver_items:
            merged = dict(default_solver_items[alias])
            merged.update(item)
            default_solver_items[alias] = merged
        else:
            default_solver_items[alias] = item
    # Put merged result back
    raw_config["solvers"] = list(default_solver_items.values())

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

    solvers = {}
    for item in raw_config.get("solvers", []):
        solver = SolverDefinition(
            alias=item["alias"],
            label=item.get("label") or item["alias"],
            kind=item.get("kind", "external"),
            executable=item.get("executable", item["alias"]),
            command_template=item.get("command_template", ""),
            input_files=dict(item.get("input_files", {})),
            artifact_patterns=list(item.get("artifact_patterns", ["result.txt"])),
            description=item.get("description", ""),
            pre_commands=list(item.get("pre_commands", [])),
            post_commands=list(item.get("post_commands", [])),
        )
        solvers[solver.alias] = solver

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
        solvers=solvers,
        toolchain=raw_config.get("toolchain", DEFAULT_TOOLCHAIN),
        run_retention_days=int(raw_config.get("cleanup", {}).get("run_retention_days", 90)),
        max_runs=int(raw_config.get("cleanup", {}).get("max_runs", 100)),
    )


def settings() -> AppSettings:
    return load_settings()
