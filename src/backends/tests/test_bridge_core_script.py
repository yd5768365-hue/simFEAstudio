import importlib.util
import unittest
from pathlib import Path


def load_bridge_core_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "bridge_core.py"
    spec = importlib.util.spec_from_file_location("bridge_core", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BridgeCoreScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge_core = load_bridge_core_module()

    def test_resolve_core_build_prefers_cli_path(self):
        env = {"SIMFEA_CORE_BUILD": "E:/core/from-env"}

        result = self.bridge_core.resolve_core_build("D:/core/from-cli", env)

        self.assertEqual(Path("D:/core/from-cli"), result)

    def test_resolve_core_build_uses_env_path(self):
        env = {"SIMFEA_CORE_BUILD": "E:/core/from-env"}

        result = self.bridge_core.resolve_core_build(None, env)

        self.assertEqual(Path("E:/core/from-env"), result)

    def test_resolve_core_build_returns_none_without_config(self):
        self.assertIsNone(self.bridge_core.resolve_core_build(None, {}))


if __name__ == "__main__":
    unittest.main()
