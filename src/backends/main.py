import os
import signal
import sys
import asyncio
import threading
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional, TypedDict
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from uvicorn import Config, Server

try:
    from .inference import infer_text_api
except ImportError:
    from inference import infer_text_api

PORT_API = 8008
SHH1_HOST = "cloud.dghpc.com"
SHH1_PORT = "1014"
SHH1_USER = "dg001767"
SHH1_KEY_PATH = os.path.expanduser(r"~\.ssh\shh1_rsa")
SSH_EXE = r"C:\Windows\System32\OpenSSH\ssh.exe"

server_instance = None  # Global reference to the Uvicorn server instance
remote_runs = {}

app = FastAPI(
    title="API server",
    version="0.1.0",
)

# Configure CORS settings
origins = [
    "*",  # to whitelist any url, REMOVE THIS FOR PRODUCTION!!!
    # "http://localhost:3000", # for dev
    # "https://your-web-ui.com", # for prod
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Tell client we are ready to accept requests.
# This is a mock func, modify to your needs.
@app.get("/v1/connect")
def connect_to_api_server():
    print("[server] Connecting to server...", flush=True)
    host = f"http://localhost:{PORT_API}"
    return {
        "message": f"Connected to api server on port {PORT_API}. Refer to '{host}/docs' for api docs.",
        "data": {
            "port": PORT_API,
            "pid": os.getpid(),
            "host": host,
        },
    }


class T_Query(TypedDict):
    prompt: str


@dataclass
class RemoteRun:
    run_id: str
    status: str = "created"
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    process: Optional[asyncio.subprocess.Process] = None
    exit_code: Optional[int] = None


def build_shh1_command(remote_command: str):
    return [
        SSH_EXE,
        "-n",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        SHH1_KEY_PATH,
        "-p",
        SHH1_PORT,
        f"{SHH1_USER}@{SHH1_HOST}",
        remote_command,
    ]


# Mock text inference endpoint, here for inspiration.
@app.post("/v1/completions")
def llm_completion(payload: T_Query = Body(...)):
    return infer_text_api.completions(payload)


async def run_command(command: list[str], timeout: float = 20.0):
    started_at = asyncio.get_running_loop().time()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
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


@app.get("/v1/compute-nodes/shh1/probe")
async def probe_shh1_compute_node():
    remote_command = (
        "printf 'hostname='; hostname; "
        "printf 'user='; whoami; "
        "printf 'cpu_cores='; nproc 2>/dev/null || getconf _NPROCESSORS_ONLN; "
        "printf 'workdir='; pwd"
    )
    ssh_command = build_shh1_command(remote_command)
    result = await run_command(ssh_command, timeout=20.0)
    ok = result["exit_code"] == 0
    details = parse_key_value_stdout(result["stdout"]) if ok else {}
    return {
        "message": "shh1 remote compute node probe completed." if ok else "shh1 remote compute node probe failed.",
        "data": {
            "alias": "shh1",
            "connected": ok,
            "details": details,
            **result,
        },
    }


async def emit_remote_event(run: RemoteRun, event_type: str, **payload):
    message = {
        "run_id": run.run_id,
        "type": event_type,
        **payload,
    }
    await run.queue.put(message)


async def read_stream_lines(run: RemoteRun, stream, event_type: str):
    while True:
        line = await stream.readline()
        if not line:
            break
        await emit_remote_event(
            run,
            event_type,
            line=line.decode("utf-8", errors="replace").rstrip(),
        )


async def execute_remote_run(run: RemoteRun, remote_command: str):
    run.status = "running"
    await emit_remote_event(run, "status", status="running", line="远程终端已连接，任务开始执行。")
    try:
        run.process = await asyncio.create_subprocess_exec(
            *build_shh1_command(remote_command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.gather(
            read_stream_lines(run, run.process.stdout, "stdout"),
            read_stream_lines(run, run.process.stderr, "stderr"),
        )
        run.exit_code = await run.process.wait()
        run.status = "finished" if run.exit_code == 0 else "failed"
        await emit_remote_event(
            run,
            "finished",
            status=run.status,
            exit_code=run.exit_code,
            line=f"远程任务结束，退出码 {run.exit_code}。",
        )
    except Exception as exc:
        run.status = "failed"
        run.exit_code = -1
        await emit_remote_event(
            run,
            "finished",
            status="failed",
            exit_code=-1,
            line=f"远程任务失败：{exc}",
        )
    finally:
        await run.queue.put(None)


@app.post("/v1/runs/shh1/demo")
async def start_shh1_demo_run():
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run = RemoteRun(run_id=run_id)
    remote_runs[run_id] = run
    remote_command = (
        "bash -lc \""
        "echo 'SimFEA remote terminal demo'; "
        "echo hostname=$(hostname); "
        "echo user=$(whoami); "
        "for i in 1 2 3 4 5; do echo remote_step=\\$i; sleep 1; done; "
        "echo done"
        "\""
    )
    asyncio.create_task(execute_remote_run(run, remote_command))
    return {
        "message": "shh1 remote demo run started.",
        "data": {
            "run_id": run_id,
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
                        "line": "未找到运行任务。",
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


# Programmatically force shutdown this sidecar.
def kill_process():
    os.kill(os.getpid(), signal.SIGINT)  # This force closes this script.


# Programmatically startup the api server
def start_api_server(**kwargs):
    global server_instance
    port = kwargs.get("port", PORT_API)
    try:
        if server_instance is None:
            print("[sidecar] Starting API server...", flush=True)
            config = Config(app, host="0.0.0.0", port=port, log_level="info")
            server_instance = Server(config)
            # Start the ASGI server
            asyncio.run(server_instance.serve())
        else:
            print(
                "[sidecar] Failed to start new server. Server instance already running.",
                flush=True,
            )
    except Exception as e:
        print(f"[sidecar] Error, failed to start API server {e}", flush=True)


# Handle the stdin event loop. This can be used like a CLI.
def stdin_loop():
    print("[sidecar] Waiting for commands...", flush=True)
    while True:
        # Read input from stdin.
        user_input = sys.stdin.readline().strip()

        # Check if the input matches one of the available functions
        match user_input:
            case "sidecar shutdown":
                print("[sidecar] Received 'sidecar shutdown' command.", flush=True)
                kill_process()
            case _:
                print(
                    f"[sidecar] Invalid command [{user_input}]. Try again.", flush=True
                )


# Start the input loop in a separate thread
def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True  # so it exits when the main program exits
        input_thread.start()
    except:
        print("[sidecar] Failed to start input handler.", flush=True)


if __name__ == "__main__":
    # You can spawn sub-processes here before the main process.
    # new_command = ["python", "-m", "some_script", "--arg", "argValue"]
    # subprocess.Popen(new_command)

    # Listen for stdin from parent process
    start_input_thread()

    # Starts API server, blocks further code from execution.
    start_api_server()
