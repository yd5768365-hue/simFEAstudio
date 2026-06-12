"""Build frontend and prepare for pip packaging.

Run before `python -m build` to ensure the frontend is built
and placed where the Python package can find it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "dist"
PKG_FRONTEND = PROJECT / "src" / "backends" / "frontend"


def main():
    # 1. Build frontend
    print("[1/3] Installing frontend dependencies...")
    subprocess.run(["pnpm", "install"], cwd=str(PROJECT), check=True)

    print("[2/3] Building frontend (Vite)...")
    subprocess.run(["pnpm", "build"], cwd=str(PROJECT), check=True)

    if not (DIST / "index.html").exists():
        print("ERROR: Frontend build failed — dist/index.html not found.")
        sys.exit(1)

    # 2. Copy dist → src/backends/frontend (for inclusion in pip package)
    print("[3/3] Copying frontend into package directory...")
    if PKG_FRONTEND.exists():
        shutil.rmtree(PKG_FRONTEND)
    shutil.copytree(DIST, PKG_FRONTEND)

    # Add .gitignore inside frontend to prevent it being tracked
    (PKG_FRONTEND / ".gitignore").write_text("*\n")

    print("Done. Frontend is ready for pip packaging.")
    print("Run: python -m build")
    print("Then: twine upload dist/*.tar.gz")


if __name__ == "__main__":
    main()
