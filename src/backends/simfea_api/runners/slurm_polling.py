import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..config import ComputeNode
from ..run_archive import RemoteRun

EmitEventFn = Callable[..., Awaitable[None]]
CancelJobFn = Callable[[RemoteRun, ComputeNode], Awaitable[None]]
QueryStateFn = Callable[[RemoteRun, ComputeNode], Awaitable[tuple[str, str]]]
SyncLogFn = Callable[[RemoteRun, ComputeNode, str, str, str, int], Awaitable[int]]
ReadRemoteTextFn = Callable[[ComputeNode, str, float], Awaitable[str]]
SaveRunMetadataFn = Callable[[RemoteRun], None]


@dataclass
class SlurmPollingResult:
    timed_out: bool
    exit_text: str
    last_stdout_count: int
    last_stderr_count: int


async def poll_slurm_until_done(
    run: RemoteRun,
    node: ComputeNode,
    *,
    emit_event: EmitEventFn,
    cancel_job: CancelJobFn,
    query_state: QueryStateFn,
    sync_log: SyncLogFn,
    read_remote_text: ReadRemoteTextFn,
    save_run_metadata: SaveRunMetadataFn,
    poll_interval_seconds: float = 2.0,
    deadline_seconds: float = 3600.0,
) -> SlurmPollingResult:
    last_stdout_count = 0
    last_stderr_count = 0
    last_state_line = ""
    timed_out = False
    deadline = asyncio.get_running_loop().time() + deadline_seconds

    while True:
        if asyncio.get_running_loop().time() > deadline:
            timed_out = True
            break

        if run.cancel_requested:
            await cancel_job(run, node)
            run.status = "canceling"
            save_run_metadata(run)

        state, node_list = await query_state(run, node)
        if state:
            run.last_scheduler_state = state
            run.status = "running" if state == "RUNNING" else "queued"
            if node_list and not node_list.startswith("("):
                run.allocated_node = node_list
            state_line = f"{state}|{node_list}"
            if state_line != last_state_line:
                await emit_event(
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
            last_stdout_count = await sync_log(
                run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
            )
            last_stderr_count = await sync_log(
                run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
            )

        await asyncio.sleep(poll_interval_seconds)

    if run.job_id:
        last_stdout_count = await sync_log(
            run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
        )
        last_stderr_count = await sync_log(
            run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
        )

    exit_text = ""
    for _ in range(5):
        exit_text = (await read_remote_text(node, f"{run.remote_workdir}/job_exit_code.txt", 20.0)).strip()
        if exit_text:
            break
        await asyncio.sleep(poll_interval_seconds)

    if run.job_id:
        last_stdout_count = await sync_log(
            run, node, f"slurm-{run.job_id}.out", "stdout.log", "stdout", last_stdout_count
        )
        last_stderr_count = await sync_log(
            run, node, f"slurm-{run.job_id}.err", "stderr.log", "stderr", last_stderr_count
        )

    return SlurmPollingResult(
        timed_out=timed_out,
        exit_text=exit_text,
        last_stdout_count=last_stdout_count,
        last_stderr_count=last_stderr_count,
    )


def apply_slurm_completion_status(run: RemoteRun, *, timed_out: bool, exit_text: str):
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

