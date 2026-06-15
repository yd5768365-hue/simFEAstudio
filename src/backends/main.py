import asyncio
import os
import signal
import sys
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uvicorn import Config, Server

try:
    from .routers.benchmarks import benchmarks_router
    from .routers.config import config_router
    from .routers.compute_nodes import compute_nodes_router
    from .routers.experiments import experiments_router
    from .routers.knowledge import knowledge_router
    from .routers.preflight import preflight_router
    from .routers.runs import runs_router
    from .routers.toolchain import toolchain_router
except ImportError:
    from routers.benchmarks import benchmarks_router
    from routers.config import config_router
    from routers.compute_nodes import compute_nodes_router
    from routers.experiments import experiments_router
    from routers.knowledge import knowledge_router
    from routers.preflight import preflight_router
    from routers.runs import runs_router
    from routers.toolchain import toolchain_router

try:
    from .simfea_api.config import PROJECT_ROOT, settings
    from .simfea_api.cleanup import cleanup_old_runs
    from .simfea_api.logger import create_logger
except ImportError:
    from simfea_api.config import PROJECT_ROOT, settings
    from simfea_api.cleanup import cleanup_old_runs
    from simfea_api.logger import create_logger

log = create_logger("sidecar")

server_instance = None


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

app.include_router(benchmarks_router)
app.include_router(config_router)
app.include_router(compute_nodes_router)
app.include_router(experiments_router)
app.include_router(knowledge_router)
app.include_router(preflight_router)
app.include_router(runs_router)
app.include_router(toolchain_router)



def kill_process():
    os.kill(os.getpid(), signal.SIGINT)


def start_api_server(**kwargs):
    global server_instance
    port = kwargs.get("port", settings().api_port)
    try:
        if server_instance is None:
            log.info("Starting API server...", port=port)
            config = Config(app, host="0.0.0.0", port=port, log_level="info")
            server_instance = Server(config)
            asyncio.run(server_instance.serve())
        else:
            log.warn("Failed to start new server. Server instance already running.")
    except Exception as e:
        log.error(f"Failed to start API server: {e}")


def stdin_loop():
    log.info("Waiting for commands...")
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
                log.info("Received shutdown command.")
                kill_process()
            case _:
                log.warn(f"Invalid command: {user_input}")


def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True
        input_thread.start()
    except Exception:
        log.error("Failed to start input handler.")


# ── Serve frontend static files ──
# Priority: SIMFEA_FRONTEND env → pip package dir → dev dist/
def _find_frontend_dir() -> Path | None:
    env_path = os.getenv("SIMFEA_FRONTEND")
    if env_path:
        p = Path(env_path)
        if (p / "index.html").exists():
            return p
    # pip install: frontend bundled inside the package
    pkg_dist = Path(__file__).resolve().parent / "frontend"
    if (pkg_dist / "index.html").exists():
        return pkg_dist
    # dev mode: Vite build output at project root
    dev_dist = PROJECT_ROOT / "dist"
    if (dev_dist / "index.html").exists():
        return dev_dist
    return None

_frontend_dir = _find_frontend_dir()
if _frontend_dir:
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="spa")

if __name__ == "__main__":
    try:
        result = cleanup_old_runs(settings())
        if result["removed"]:
            log.info(f"Startup cleanup: removed {result['removed']} old runs, {result['kept']} kept")
    except Exception as e:
        log.warn(f"Startup cleanup skipped: {e}")

    if sys.stdin.isatty():
        # Standalone mode: python main.py 直接启动
        import uvicorn

        port = settings().api_port
        print(f"\n  SimFEA Studio 启动 → http://localhost:{port}\n")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Tauri sidecar 模式：stdin 监听生命周期命令
        start_input_thread()
        start_api_server()
