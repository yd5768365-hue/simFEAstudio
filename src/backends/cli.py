"""SimFEA Studio — 仿真学习桌面工作台。

Usage:
    simfea-studio              # Start on default port 8008
    simfea-studio --port 3000  # Start on custom port
"""

import os
import sys
import threading
import time
import webbrowser


def main():
    port = int(os.environ.get("SIMFEA_PORT", "8008"))

    # Parse --port / -p from command line
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("--port", "-p") and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] in ("--help", "-h"):
            print(__doc__)
            return
        else:
            i += 1

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    # Import and start the FastAPI server
    from main import start_api_server

    print(f"\n  SimFEA Studio starting on http://localhost:{port}\n")
    start_api_server(port=port)


if __name__ == "__main__":
    main()
