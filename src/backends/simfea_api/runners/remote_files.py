from pathlib import Path
from typing import Awaitable, Callable

from ..config import ComputeNode
from ..run_archive import RemoteRun, append_text
from .ssh import build_scp_command, build_ssh_command, run_command, sh_quote


EmitEventFn = Callable[..., Awaitable[None]]


async def read_remote_text(node: ComputeNode, remote_path: str, timeout: float = 20.0) -> str:
    result = await run_command(
        build_ssh_command(node, f"cat {sh_quote(remote_path)} 2>/dev/null || true"),
        timeout=timeout,
    )
    return result["stdout"] if result["exit_code"] == 0 else ""


async def download_remote_file(
    run: RemoteRun,
    node: ComputeNode,
    remote_name: str,
    local_name: str | None = None,
    *,
    emit_event: EmitEventFn,
) -> bool:
    local_path = run.artifacts_dir / (local_name or remote_name)
    remote_path = f"{run.remote_workdir}/{remote_name}"
    result = await run_command(build_scp_command(node, remote_path, local_path), timeout=30.0)
    if result["exit_code"] == 0:
        if remote_name == "result.txt":
            run.result_downloaded = True
        await emit_event(
            run,
            "artifact",
            line=f"结果物证已归档：{local_path}",
            artifact=str(local_path.relative_to(run.local_dir)).replace("\\", "/"),
        )
        return True

    await emit_event(
        run,
        "stderr",
        line=f"远程文件归档失败 {remote_name}：{result['stderr'] or result['stdout']}",
    )
    return False


async def download_remote_result(run: RemoteRun, node: ComputeNode, *, emit_event: EmitEventFn) -> bool:
    local_result = run.artifacts_dir / "result.txt"
    remote_result = f"{run.remote_workdir}/result.txt"
    result = await run_command(build_scp_command(node, remote_result, local_result), timeout=30.0)
    if result["exit_code"] == 0:
        run.result_downloaded = True
        await emit_event(
            run,
            "artifact",
            line=f"结果文件已归档：{local_result}",
            artifact="artifacts/result.txt",
        )
        return True

    await emit_event(
        run,
        "stderr",
        line=f"结果文件拉取失败：{result['stderr'] or result['stdout']}",
    )
    return False


def build_remote_artifact_list_script(patterns: list[str]) -> str:
    lines = ["shopt -s nullglob globstar"]
    for pattern in patterns:
        lines.append(f"for f in {sh_quote(pattern)}; do")
        lines.append("  for match in $f; do")
        lines.append('    [ -f "$match" ] && printf "%s\\n" "$match"')
        lines.append("  done")
        lines.append("done")
    return "\n".join(lines)


async def list_remote_artifacts(run: RemoteRun, node: ComputeNode, patterns: list[str]) -> list[str]:
    command = (
        f"cd {sh_quote(run.remote_workdir)} && "
        f"bash -lc {sh_quote(build_remote_artifact_list_script(patterns))}"
    )
    result = await run_command(build_ssh_command(node, command), timeout=20.0)
    if result["exit_code"] != 0:
        return []
    return sorted({line.strip() for line in result["stdout"].splitlines() if line.strip()})


async def download_remote_artifacts(
    run: RemoteRun,
    node: ComputeNode,
    patterns: list[str],
    *,
    emit_event: EmitEventFn,
) -> list[str]:
    downloaded = []
    for remote_name in await list_remote_artifacts(run, node, patterns):
        local_path = run.artifacts_dir / remote_name
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote_path = f"{run.remote_workdir}/{remote_name}"
        result = await run_command(build_scp_command(node, remote_path, local_path), timeout=45.0)
        if result["exit_code"] != 0:
            await emit_event(
                run,
                "stderr",
                line=f"Failed to archive solver artifact {remote_name}: {result['stderr'] or result['stdout']}",
            )
            continue
        if remote_name == "result.txt":
            run.result_downloaded = True
        relative = str(local_path.relative_to(run.local_dir)).replace("\\", "/")
        downloaded.append(relative)
        await emit_event(
            run,
            "artifact",
            line=f"Solver artifact archived: {local_path}",
            artifact=relative,
        )
    return downloaded


async def sync_remote_log_file(
    run: RemoteRun,
    node: ComputeNode,
    remote_name: str,
    local_name: str,
    event_type: str,
    already_seen: int,
    *,
    emit_event: EmitEventFn,
) -> int:
    content = await read_remote_text(node, f"{run.remote_workdir}/{remote_name}")
    lines = content.splitlines()
    for text in lines[already_seen:]:
        append_text(run.local_dir / local_name, text)
        await emit_event(run, event_type, line=text)
    return len(lines)


async def download_slurm_artifacts(run: RemoteRun, node: ComputeNode, *, emit_event: EmitEventFn):
    names = ["input.txt", "simfea-demo.slurm", "result.txt", "job_exit_code.txt"]
    if run.job_id:
        names.extend([f"slurm-{run.job_id}.out", f"slurm-{run.job_id}.err"])
    for name in names:
        await download_remote_file(run, node, name, emit_event=emit_event)
