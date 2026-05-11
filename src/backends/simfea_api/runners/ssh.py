import asyncio
from pathlib import Path

from ..config import ComputeNode, expand_path, settings


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


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def remote_workdir_for(node: ComputeNode, run_id: str) -> str:
    return f"{node.remote_runs_root.rstrip('/')}/{run_id}"


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

