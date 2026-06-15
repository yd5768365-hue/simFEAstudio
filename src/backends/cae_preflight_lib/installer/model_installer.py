# -*- coding: utf-8 -*-
"""
AI 模型安装器

支持从 Hugging Face / 指定镜像下载 GGUF 模型文件
"""
from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 默认镜像（可配置）
DEFAULT_MIRRORS = [
    "https://huggingface.co",
    "https://hf-mirror.com",
]


@dataclass
class ModelInfo:
    """模型信息"""
    name: str                      # 模型标识（用于 install 命令）
    repo_id: str                   # Hugging Face repo ID
    filename: str                  # GGUF 文件名
    size_gb: float                # 文件大小（GB）
    sha256: str = ""               # SHA256 校验码（可选）
    description: str = ""          # 描述


# 已知模型列表
KNOWN_MODELS: dict[str, ModelInfo] = {
    "deepseek-r1-7b": ModelInfo(
        name="deepseek-r1-7b",
        repo_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        filename="DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        size_gb=4.9,
        description="DeepSeek R1 Distill Qwen 7B (Q4_K_M 量化)",
    ),
    "deepseek-r1-14b": ModelInfo(
        name="deepseek-r1-14b",
        repo_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B-GGUF",
        filename="DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        size_gb=9.0,
        description="DeepSeek R1 Distill Qwen 14B (Q4_K_M 量化)",
    ),
    "qwen2.5-7b": ModelInfo(
        name="qwen2.5-7b",
        repo_id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        size_gb=4.7,
        description="Qwen 2.5 7B Instruct (Q4_K_M 量化)",
    ),
}


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    method: str = ""
    install_path: Optional[Path] = None
    error_message: Optional[str] = None


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool
    file_path: Optional[Path] = None
    file_size_mb: float = 0.0
    error_message: Optional[str] = None


@dataclass
class VerifyResult:
    """校验结果"""
    success: bool
    expected: str = ""
    actual: str = ""
    error: Optional[str] = None


class ModelInstaller:
    """AI 模型安装器"""

    def __init__(self, mirror: Optional[str] = None):
        self.platform_name = platform.system().lower()
        # 模型安装到 ~/.cae-cli/models/
        self.cae_home = Path.home() / ".cae-cli"
        self.models_dir = self.cae_home / "models"
        # 下载镜像
        self.mirror = mirror or os.environ.get("HF_HUB_MIRROR", DEFAULT_MIRRORS[0])

    def is_installed(self, model_name: str) -> bool:
        """检查模型是否已安装"""
        info = self._find_model(model_name)
        if info:
            model_path = self.models_dir / info.filename
            return model_path.exists()
        # 未知模型，按文件名检查
        model_path = self.models_dir / model_name
        if not model_path.name.endswith(".gguf"):
            model_path = model_path.with_suffix(".gguf")
        return model_path.exists()

    def _find_model(self, model_name: str) -> Optional[ModelInfo]:
        """查找匹配的模型信息"""
        search = model_name.lower().replace("-", "_").replace(".gguf", "")
        for info in KNOWN_MODELS.values():
            if (search in info.name.replace("-", "_") or
                info.name.replace("-", "_") in search):
                return info
        return None

    def get_install_path(self, model_name: str) -> Path:
        """获取模型的安装路径"""
        info = self._find_model(model_name)
        if info:
            return self.models_dir / info.filename
        path = self.models_dir / model_name
        if not path.suffix:
            path = path.with_suffix(".gguf")
        return path

    def activate(self, model_name: str) -> None:
        """激活模型（设置默认模型）"""
        from cae_preflight_lib.config import settings
        settings.active_model = model_name

    def list_models(self) -> list[dict]:
        """列出所有已知模型"""
        return [
            {
                "name": info.name,
                "size_gb": info.size_gb,
                "description": info.description,
                "installed": self.is_installed(info.name),
            }
            for info in KNOWN_MODELS.values()
        ]

    def list_installed(self) -> list[Path]:
        """列出已安装的模型文件"""
        if not self.models_dir.exists():
            return []
        return list(self.models_dir.glob("*.gguf"))

    def install(
        self,
        model_name: str,
        progress_callback: Optional[callable] = None,
        mirror: Optional[str] = None,
    ) -> InstallResult:
        """
        安装模型（下载 + 校验）

        Args:
            model_name: 模型名称（支持简写，如 deepseek-r1-7b）
            progress_callback: 进度回调函数 (percent: float, message: str)
            mirror: 下载镜像（覆盖默认）

        Returns:
            InstallResult
        """
        # 查找模型
        info = self._find_model(model_name)
        if info is None:
            # 未知模型，尝试作为 Hugging Face repo/filename
            if "/" in model_name:
                parts = model_name.split("/")
                repo_id = model_name
                filename = parts[-1] if parts[-1].endswith(".gguf") else "model.gguf"
                info = ModelInfo(
                    name=model_name,
                    repo_id=repo_id,
                    filename=filename,
                    size_gb=0,
                    description=f"自定义模型: {model_name}",
                )
            else:
                return InstallResult(success=False, error_message=f"未知模型: {model_name}")

        model_path = self.models_dir / info.filename
        use_mirror = mirror or self.mirror

        # 检查是否已安装
        if model_path.exists():
            # 校验已有文件
            if progress_callback:
                progress_callback(0.5, "文件已存在，正在校验...")
            verify = self.verify_file(model_path, info.sha256)
            if verify.success:
                if progress_callback:
                    progress_callback(1.0, "校验通过")
                return InstallResult(success=True, method="already_installed", install_path=model_path)
            else:
                # 校验失败，删除并重新下载
                if progress_callback:
                    progress_callback(0.0, "文件校验失败，将重新下载...")
                model_path.unlink()

        # 确保目录存在
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # 构建下载 URL
        download_url = f"{use_mirror.rstrip('/')}/{info.repo_id}/resolve/main/{info.filename}"

        try:
            if progress_callback:
                progress_callback(0.05, "准备下载...")

            # 下载文件
            result = self._download_file(download_url, model_path, progress_callback)
            if not result.success:
                return InstallResult(success=False, error_message=result.error_message)

            # 校验
            if info.sha256:
                if progress_callback:
                    progress_callback(0.95, "正在校验 SHA256...")
                verify = self.verify_file(model_path, info.sha256)
                if not verify.success:
                    model_path.unlink()
                    return InstallResult(
                        success=False,
                        error_message=f"SHA256 校验失败: 期望 {info.sha256[:16]}... 实际 {verify.actual[:16]}...",
                    )

            if progress_callback:
                progress_callback(1.0, "安装完成")
            return InstallResult(
                success=True,
                method="downloaded",
                install_path=model_path,
            )

        except Exception as e:
            if model_path.exists():
                model_path.unlink()
            return InstallResult(success=False, error_message=str(e))

    def verify_file(self, file_path: Path, expected_sha256: str = "") -> VerifyResult:
        """校验文件 SHA256"""
        if not file_path.exists():
            return VerifyResult(success=False, error="文件不存在")

        if not expected_sha256:
            # 只检查文件存在
            return VerifyResult(success=True, expected="(未校验)", actual="(未校验)")

        # 计算 SHA256
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192 * 1024), b""):
                sha256_hash.update(chunk)

        actual = sha256_hash.hexdigest()
        success = actual.lower() == expected_sha256.lower()

        return VerifyResult(
            success=success,
            expected=expected_sha256,
            actual=actual,
        )

    def _download_file(
        self,
        url: str,
        dest: Path,
        progress_callback: Optional[callable] = None,
    ) -> DownloadResult:
        """下载文件（使用 curl，支持进度回调）"""
        import threading
        import re

        def _parse_progress(line: str, callback: callable, size_mb: float) -> None:
            """解析进度行并回调"""
            # curl --progress-bar 输出: "  100.0%"
            # 或普通进度: "  % Total    100   5.0M    0:00:12   --:--:--"
            if "%" in line:
                match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                if match:
                    pct = float(match.group(1)) / 100.0
                    downloaded = pct * size_mb
                    callback(min(pct, 0.99), f"下载中... {downloaded:.1f} / {size_mb:.1f} MB")

        def _run_with_progress(cmd: list[str], cb: callable) -> tuple[int, str, float]:
            """运行命令并实时更新进度，返回 (returncode, stderr, size_mb)"""
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stderr_lines = []
            total_size_mb = 0.0

            def _read_stderr():
                nonlocal total_size_mb
                for line in process.stderr:
                    stderr_lines.append(line)
                    # 尝试从 "  % Total" 行提取总大小
                    if "Total" in line and total_size_mb == 0.0:
                        # 格式: "  % Total    100   5.0M    0:00:12   --:--:--"
                        size_match = re.search(r'(\d+\.?\d*)\s*[KMG]?B?\s*$', line)
                        if size_match:
                            size_str = size_match.group(1)
                            if "G" in line.upper():
                                total_size_mb = float(size_str) * 1024
                            elif "M" in line.upper():
                                total_size_mb = float(size_str)
                            elif "K" in line.upper():
                                total_size_mb = float(size_str) / 1024
                            else:
                                total_size_mb = float(size_str) / (1024 * 1024)
                    if cb:
                        _parse_progress(line, cb, total_size_mb if total_size_mb > 0 else 5000.0)

            thread = threading.Thread(target=_read_stderr, daemon=True)
            thread.start()
            process.wait()
            thread.join(timeout=1)
            return process.returncode, "".join(stderr_lines), total_size_mb

        try:
            if progress_callback:
                progress_callback(0.0, "正在连接...")

            cmd = ["curl", "-L", "-C", "-", "-o", str(dest), "--progress-bar", url]

            if progress_callback:
                progress_callback(0.05, "下载中...")

            returncode, stderr, size_mb = _run_with_progress(cmd, progress_callback)

            if returncode == 0:
                if dest.exists() and dest.stat().st_size > 1024 * 1024:
                    if progress_callback:
                        progress_callback(1.0, "下载完成")
                    return DownloadResult(
                        success=True,
                        file_path=dest,
                        file_size_mb=dest.stat().st_size / (1024 * 1024),
                    )
                return DownloadResult(success=False, error_message="下载失败或文件无效")
            else:
                error = stderr.strip() if stderr else "curl 下载失败"
                if "404" in error:
                    return DownloadResult(success=False, error_message="文件不存在")
                return DownloadResult(success=False, error_message=error)

        except FileNotFoundError:
            return DownloadResult(success=False, error_message="未找到 curl，请安装")
        except subprocess.TimeoutExpired:
            if dest.exists():
                dest.unlink()
            return DownloadResult(success=False, error_message="下载超时")
        except Exception as e:
            if dest.exists():
                dest.unlink()
            return DownloadResult(success=False, error_message=str(e))

    def uninstall(self, model_name: str) -> bool:
        """卸载模型"""
        model_path = self.get_install_path(model_name)
        try:
            if model_path.exists():
                model_path.unlink()
            return True
        except Exception:
            return False


# 兼容旧接口
def _get_legacy_download_url(filename: str) -> str:
    """获取旧版 GitHub Release 下载链接"""
    from cae_preflight_lib.installer.model_installer_legacy import REPO_OWNER, REPO_NAME, RELEASE_VERSION
    return f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_VERSION}/{filename}"
