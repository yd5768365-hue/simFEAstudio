from typing import Optional

from ..config import ComputeNode
from ..run_archive import RemoteRun
from .ssh import build_ssh_command, run_command, sh_quote


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


async def request_slurm_cancel(run: RemoteRun, node: ComputeNode):
    if not run.job_id:
        return
    await run_command(build_ssh_command(node, f"scancel {run.job_id} 2>/dev/null || true"), timeout=20.0)

