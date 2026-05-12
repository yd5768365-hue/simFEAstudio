# SimFEA Studio Runner 设计

## 概述

Runner 是 SimFEA Studio 的求解执行抽象层。它将"在何处、以何种方式运行仿真命令"统一为一个接口，让上层（API 路由、运行编排）不感知执行细节。

借鉴来源：
- `sim-main` 的 SSH/Slurm 远程执行模式
- OpenCAEHub 的**文件式求解器集成**模式（`PluginConfig.xml` 的 pre_command / post_command / artifact_patterns）

## Runner 分类

| Runner | 执行位置 | 调度器 | 适用场景 |
|--------|----------|--------|----------|
| `SSHRunner` | 远程节点（SSH） | 无 | 单机远程命令、demo-shell |
| `SlurmRunner` | HPC 集群（sbatch） | Slurm | 作业调度、队列管理 |
| `SolverRunner` | 任意（SSH/Slurm/本地） | 可选 | 真实求解器（CalculiX/OpenFOAM/Elmer） |
| `LocalRunner` | 本地 sidecar 进程 | 无 | 未来本地轻量执行 |

当前已实现：SSHRunner、SlurmRunner、SolverRunner。LocalRunner 待后续。

## 核心概念：文件式求解器集成

参考 OpenCAEHub 的 `PluginConfig.xml` 模式，每次求解运行 = 三段命令链：

```text
pre_commands → solver_command → post_commands
```

这种声明式配置让求解器集成不依赖代码改动，只需在 `.simfea/config.json` 中声明：

```json
{
  "solvers": [{
    "alias": "calculix",
    "executable": "ccx",
    "command_template": "ccx ${case_name}",
    "input_files": { "cantilever.inp": "..." },
    "artifact_patterns": ["*.frd", "*.dat", "result.txt"],
    "pre_commands": ["module load intel-mkl"],
    "post_commands": [
      "grep 'U' cantilever.dat | tail -1 | awk '{print \"max_displacement_mm=\"$NF}'"
    ]
  }]
}
```

### 命令链执行顺序

```
1. 环境检查（solver executable 是否可用）
2. 写入 input_files 到工作目录
3. 依次执行 pre_commands（如加载模块、准备临时文件）
4. 执行 command_template 渲染后的求解命令
5. 依次执行 post_commands（如提取结果指标、转换格式）
6. 写入 result.txt（含退出码、运行节点、结果通配符列表）
```

### 输出通配符收集

OpenCAEHub 的 `APIOutParameterTemlate="filepath=vtk_output/*.vtu|*.pvd"` 用通配符声明收集哪些结果文件。SimFEA Studio 对应为 `artifact_patterns`：

```json
"artifact_patterns": ["*.frd", "*.dat", "*.sta", "postProcessing/**", "result.txt"]
```

运行完成后，`download_remote_artifacts()` 遍历通配符列表，将匹配文件下载到 `.simfea/runs/<run_id>/artifacts/`。

### 工作目录隔离

每次运行有独立的远程工作目录：
- SSHRunner: `$REMOTE_RUNS_ROOT/<run_id>/`
- SlurmRunner: `$REMOTE_RUNS_ROOT/<run_id>/`

对应 OpenCAEHub 的 `temp/%projectId%/%taskId%/` 隔离模式。SimFEA Studio 的 run_id 同时扮演 projectId + taskId 角色。

## SolverDefinition 数据模型

```python
@dataclass
class SolverDefinition:
    alias: str              # 内部标识符，如 "calculix"
    label: str              # 人类可读名称，如 "CalculiX"
    kind: str               # 求解类型: structural / fluid / multiphysics / external
    executable: str         # 可执行文件名或路径，如 "ccx"
    command_template: str   # 命令模板，支持 ${run_id} ${solver_alias} 等变量
    input_files: dict       # 输入文件名 → 内容 映射
    artifact_patterns: list # 输出通配符列表，如 ["*.frd", "result.txt"]
    description: str        # 求解器说明
    pre_commands: list      # 求解前命令链（如加载模块、设置环境变量）
    post_commands: list     # 求解后命令链（如提取指标、格式转换）
```

## 命令模板变量

`command_template` 支持以下变量替换（由 `render_command_template()` 处理）：

| 变量 | 来源 | 示例值 |
|------|------|--------|
| `$run_id` / `${run_id}` | `RemoteRun.run_id` | `run_abc123` |
| `$remote_workdir` / `${remote_workdir}` | `RemoteRun.remote_workdir` | `/home/user/simfea-runs/run_abc123` |
| `$solver_alias` / `${solver_alias}` | `SolverDefinition.alias` | `calculix` |
| `$solver_executable` / `${solver_executable}` | `SolverDefinition.executable` | `ccx` |

## 运行脚本结构

`build_solver_run_script()` 生成的 bash 脚本结构：

```bash
set -e
# 1. 变量声明
RUN_ID='...'
REMOTE_WORKDIR='...'
SOLVER_ALIAS='calculix'

# 2. 环境准备
mkdir -p "$REMOTE_WORKDIR"
cd "$REMOTE_WORKDIR"

# 3. 求解器可用性检查
command -v "$SOLVER_EXECUTABLE" || exit 127

# 4. 写入输入文件（here-doc）
cat > cantilever.inp <<'SIMFEA_INPUT_EOF'
...input file content...
SIMFEA_INPUT_EOF

# 5. 求解前命令链
echo "pre_command=..."
pre_command_1
pre_command_2

# 6. 求解命令
echo "command=ccx cantilever"
set +e
ccx cantilever
exit_code=$?
set -e

# 7. 求解后命令链
echo "post_command=..."
post_command_1
post_command_2

# 8. 结果摘要
cat > result.txt <<EOF
status=success|failed
exit_code=$exit_code
artifact_patterns=...
EOF

exit $exit_code
```

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/v1/solvers` | 列出所有已配置求解器（不含 input_files） |
| GET | `/v1/compute-nodes/:alias/solvers/probe` | 探测远程节点求解器可用性 |
| POST | `/v1/runs/:alias/solvers/:solver_alias` | 启动求解器运行 |

## SSE 事件流

求解器运行产生与 demo-shell 相同的 SSE 事件类型（`stdout` / `stderr` / `status` / `finished`），`solver` 字段区分运行来源：

- demo-shell: `solver="demo-shell"`
- Slurm demo: `solver="demo-slurm-shell"`
- CalculiX: `solver="calculix"`
- OpenFOAM: `solver="openfoam"`
- Elmer: `solver="elmer"`

## 结果归档

每次求解器运行在 `.simfea/runs/<run_id>/` 下产生：

```text
meta.json              # 运行元数据（solver, kind, runner, status, ...）
command.sh             # 实际执行的命令
stdout.log             # 远程标准输出
stderr.log             # 远程标准错误
events.jsonl           # SSE 事件持久化
inputs/                # 输入文件副本
  cantilever.inp
artifacts/             # 下载的结果文件
  result.txt
  cantilever.frd
  result_summary.json
learning_report.md     # 学习沉淀报告
```

## 与 OpenCAEHub 的对应关系

| OpenCAEHub 概念 | SimFEA Studio 对应 |
|-----------------|-------------------|
| `PluginConfig.xml` | `.simfea/config.json` → `solvers[]` |
| `AppPath` (exe 路径) | `SolverDefinition.executable` |
| `APIParameterTemlate` (输入模板) | `SolverDefinition.input_files` + `command_template` |
| `APIOutParameterTemlate` (输出通配符) | `SolverDefinition.artifact_patterns` |
| `PreCommand` | `SolverDefinition.pre_commands` |
| `PostCommand` | `SolverDefinition.post_commands` |
| `WorkingDir` | `RemoteRun.remote_workdir`（由 `remote_workdir_for()` 生成） |
| `%projectId%/%taskId%/` 隔离 | `.simfea/runs/<run_id>/` 隔离 |
| 无头模式 (`HasUI="false"`) | SSH/Slurm 远程执行 |
