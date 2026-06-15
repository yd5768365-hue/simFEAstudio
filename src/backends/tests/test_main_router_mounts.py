"""Verify main.py mounts routers via include_router (not inline routes)."""

import ast
import sys
import unittest
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parent.parent / "main.py"


def _parse() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _find_include_router_calls(tree) -> dict[str, int]:
    """Return {router_var_name: count} for all app.include_router(...) calls."""
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "app"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name):
                found[arg.id] = found.get(arg.id, 0) + 1
    return found


def _find_inline_routes(tree) -> list[tuple[str, str]]:
    """Return [(http_method, path)] for all @app.get/post/delete(...) in main.py."""
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            method = dec.func.attr
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            if not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"):
                continue
            for arg in dec.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    routes.append((method, arg.value))
    return routes


class TestMainRouterMounts(unittest.TestCase):
    """AST-level checks that endpoints are mounted via router, not inline."""

    # (router_var, required_include_count)
    REQUIRED_ROUTERS = {
        "benchmarks_router": 1,
        "preflight_router": 1,
        "experiments_router": 1,
        "config_router": 1,
        "toolchain_router": 1,
        "knowledge_router": 1,
        "compute_nodes_router": 1,
    }

    # (method, path) that must NOT appear as inline @app.xxx routes
    FORBIDDEN_INLINE_ROUTES = [
        ("get", "/v1/benchmarks"),
        ("get", "/v1/benchmarks/{case_name}"),
        ("post", "/v1/preflight"),
        ("get", "/v1/experiment/files"),
        ("get", "/v1/experiment/files/{file_path:path}"),
        ("post", "/v1/experiment/files/{file_path:path}"),
        ("post", "/v1/experiment/run"),
        ("get", "/v1/config"),
        ("get", "/v1/connect"),
        ("post", "/v1/completions"),
        ("post", "/v1/completions/translate-task"),
        ("get", "/v1/solvers"),
        ("get", "/v1/toolchain/solvers"),
        ("post", "/v1/toolchain/solvers/{alias}/scan"),
        ("post", "/v1/toolchain/solvers/{alias}/path"),
        ("post", "/v1/toolchain/solvers/{alias}/verify"),
        ("post", "/v1/toolchain/solvers/{alias}/install"),
        ("get", "/v1/toolchain/solvers/{alias}/install/{install_id}/events"),
        ("post", "/v1/knowledge/documents"),
        ("post", "/v1/knowledge/documents/by-path"),
        ("get", "/v1/knowledge/documents"),
        ("delete", "/v1/knowledge/documents/{doc_id}"),
        ("post", "/v1/knowledge/ask"),
        ("get", "/v1/compute-nodes"),
        ("get", "/v1/compute-nodes/{alias}/probe"),
        ("get", "/v1/compute-nodes/{alias}/scheduler-probe"),
        ("get", "/v1/compute-nodes/{alias}/solvers/probe"),
    ]

    def test_required_routers_mounted(self):
        tree = _parse()
        mounted = _find_include_router_calls(tree)
        for router_var, expected_count in self.REQUIRED_ROUTERS.items():
            actual = mounted.get(router_var, 0)
            self.assertEqual(
                actual,
                expected_count,
                f"Expected {expected_count} app.include_router({router_var}), found {actual}",
            )

    def test_no_forbidden_inline_routes(self):
        tree = _parse()
        inline = _find_inline_routes(tree)
        for method, path in self.FORBIDDEN_INLINE_ROUTES:
            if (method, path) in inline:
                self.fail(f"Found inline @app.{method}('{path}') in main.py — should be in a router")


class TestMainPathsAtRuntime(unittest.TestCase):
    """Runtime checks that expected paths exist in the mounted app."""

    EXPECTED_PATHS = [
        "/v1/benchmarks",
        "/v1/config",
        "/v1/connect",
        "/v1/preflight",
        "/v1/experiment/files",
        "/v1/knowledge/documents",
        "/v1/compute-nodes",
        "/v1/solvers",
        "/v1/toolchain/solvers",
        "/v1/runs",
    ]

    @classmethod
    def setUpClass(cls):
        # main.py uses relative imports that need src/backends on sys.path
        cls._backends_dir = Path(__file__).resolve().parent.parent
        if str(cls._backends_dir) not in sys.path:
            sys.path.insert(0, str(cls._backends_dir))
        try:
            from main import app as _app
        except Exception as exc:
            raise unittest.SkipTest(f"Cannot import app from main.py: {exc}")
        cls.app = _app

    def test_expected_paths_exist(self):
        paths = self.app.openapi().get("paths", {})
        for expected in self.EXPECTED_PATHS:
            with self.subTest(path=expected):
                self.assertIn(
                    expected,
                    paths,
                    f"Expected path '{expected}' not found in app routes",
                )


if __name__ == "__main__":
    unittest.main()
