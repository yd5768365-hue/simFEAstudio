import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from simfea_api.install import start_install, _installs


class TestSolverInstall(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _installs.clear()

    async def test_start_install_rejects_non_calculix(self):
        with self.assertRaises(ValueError):
            await start_install("freecad")

    async def test_start_install_rejects_missing_download_url(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = ""
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            with self.assertRaises(ValueError):
                await start_install("calculix")

    async def test_start_install_returns_install_id(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = "http://example.com/ccx.zip"
            mock_spec.managed_install_root = "%LOCALAPPDATA%\\SimFEA\\solvers"
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            mock_settings.return_value.config_path.parent = MagicMock()
            mock_settings.return_value.config_path.parent.__truediv__ = MagicMock(return_value=MagicMock())

            result = await start_install("calculix")
            self.assertIn("install_id", result)
            self.assertIn("message", result)

    async def test_start_install_rejects_concurrent(self):
        with patch("simfea_api.install.settings") as mock_settings:
            mock_spec = MagicMock()
            mock_spec.download_url = "http://example.com/ccx.zip"
            mock_spec.managed_install_root = "%LOCALAPPDATA%\\SimFEA\\solvers"
            mock_settings.return_value.solver_install_specs = {"calculix": mock_spec}
            mock_settings.return_value.config_path.parent = MagicMock()
            mock_settings.return_value.config_path.parent.__truediv__ = MagicMock(return_value=MagicMock())

            await start_install("calculix")
            with self.assertRaises(RuntimeError):
                await start_install("calculix")


if __name__ == "__main__":
    unittest.main()
