"""
CalculiX 官方测试集 (ccx_2.23.test) 批量测试

测试路径: ccx_2.23.test/CalculiX/ccx_2.23/test/*.inp
"""
from __future__ import annotations

import subprocess
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# 配置
TEST_DIR = Path("ccx_2.23.test/CalculiX/ccx_2.23/test")
MAIN = "cae/main.py"

# 优先使用项目内置 Python
PYTHON = sys.executable


@dataclass
class PhaseResult:
    """单个测试阶段的结果"""
    name: str
    total: int
    ok: int
    failed: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.ok / self.total * 100) if self.total > 0 else 0


@dataclass
class OfficialTestResult:
    """官方测试集的完整结果"""
    phase1: PhaseResult
    phase2: PhaseResult
    phase3: PhaseResult

    @property
    def total_pass(self) -> bool:
        return (
            self.phase1.ok == self.phase1.total and
            self.phase2.ok == self.phase2.total and
            self.phase3.ok == self.phase3.total
        )

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CalculiX 官方测试集 (ccx_2.23.test) 测试报告",
            "=" * 60,
            f"Phase 1 (inp info):  {self.phase1.ok}/{self.phase1.total} OK ({self.phase1.pass_rate:.1f}%)",
            f"Phase 2 (solve):     {self.phase2.ok}/{self.phase2.total} OK ({self.phase2.pass_rate:.1f}%)",
            f"Phase 3 (convert):   {self.phase3.ok}/{self.phase3.total} OK ({self.phase3.pass_rate:.1f}%)",
            "=" * 60,
        ]
        if self.phase1.failed:
            lines.append(f"\nPhase 1 失败文件 ({len(self.phase1.failed)}):")
            for f in self.phase1.failed[:10]:
                lines.append(f"  - {f}")
        if self.phase2.failed:
            lines.append(f"\nPhase 2 失败文件 ({len(self.phase2.failed)}):")
            for f in self.phase2.failed[:10]:
                lines.append(f"  - {f}")
        if self.phase3.failed:
            lines.append(f"\nPhase 3 失败文件 ({len(self.phase3.failed)}):")
            for f in self.phase3.failed[:10]:
                lines.append(f"  - {f}")
        return "\n".join(lines)


def _run_cmd(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """执行命令并返回 (返回码, stdout, stderr)"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(
            [PYTHON] + args,
            capture_output=True, text=True, timeout=timeout,
            env=env, encoding="utf-8", errors="replace"
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -2, "", str(e)


def _test_inp_info(inp_file: Path) -> tuple[bool, str]:
    """测试 inp info 命令"""
    code, out, err = _run_cmd([MAIN, "inp", "info", str(inp_file)], timeout=10)
    if code == 0 and "关键词统计" in out:
        return True, out
    return False, err[:200] if err else out[:200]


def _test_solve(inp_file: Path, out_dir: Path) -> tuple[bool, str]:
    """测试 solve 命令"""
    code, out, err = _run_cmd([MAIN, "solve", str(inp_file), "-o", str(out_dir)], timeout=60)
    if code == 0 and "求解完成" in out:
        return True, out
    return False, err[:200] if err else out[:200]


def _test_convert(frd_file: Path) -> tuple[bool, str]:
    """测试 convert 命令"""
    code, out, err = _run_cmd([MAIN, "convert", str(frd_file)], timeout=30)
    if code == 0 and "转换完成" in out:
        return True, out
    return False, err[:200] if err else out[:200]


def run_official_tests(
    test_dir: Optional[Path] = None,
    sample_size: int = 10,
    verbose: bool = True,
) -> OfficialTestResult:
    """
    运行 CalculiX 官方测试集

    Args:
        test_dir: 测试文件目录，默认使用 ccx_2.23.test/CalculiX/ccx_2.23/test
        sample_size: Phase 2/3 采样测试的文件数量
        verbose: 是否打印详细进度

    Returns:
        OfficialTestResult: 测试结果
    """
    test_path = test_dir or TEST_DIR

    # 查找所有 .inp 文件
    if not test_path.exists():
        raise FileNotFoundError(f"测试目录不存在: {test_path}")

    inp_files = sorted(test_path.glob("*.inp"))
    if not inp_files:
        raise FileNotFoundError(f"在 {test_path} 中未找到 .inp 文件")

    if verbose:
        print(f"找到 {len(inp_files)} 个 .inp 文件")

    # ========== Phase 1: inp info ==========
    if verbose:
        print("\n" + "=" * 60)
        print("Phase 1: Testing inp info on all files...")
        print("=" * 60)

    phase1_ok = []
    phase1_fail = []

    for i, f in enumerate(inp_files):
        success, msg = _test_inp_info(f)
        if success:
            phase1_ok.append(f.name)
        else:
            phase1_fail.append(f.name)
        if verbose and (i + 1) % 100 == 0:
            print(f"  进度: {i + 1}/{len(inp_files)}")

    phase1 = PhaseResult(
        name="inp info",
        total=len(inp_files),
        ok=len(phase1_ok),
        failed=phase1_fail,
    )

    if verbose:
        print(f"\nPhase 1 结果: OK={phase1.ok}, FAIL={phase1.fail}")

    # ========== Phase 2: solve (采样) ==========
    if verbose:
        print("\n" + "=" * 60)
        print(f"Phase 2: Testing solve on sample files ({sample_size})...")
        print("=" * 60)

    sample = phase1_ok[:sample_size]
    phase2_ok = []
    phase2_fail = []

    for i, name in enumerate(sample):
        f = test_path / name
        out_dir = Path("results_test") / f.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        success, msg = _test_solve(f, out_dir)
        if success:
            phase2_ok.append(name)
        else:
            phase2_fail.append(name)

        if verbose:
            status = "OK" if success else "FAIL"
            print(f"  [{i + 1}/{sample_size}] {name}: {status}")

        # 清理
        if success:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    phase2 = PhaseResult(
        name="solve",
        total=len(sample),
        ok=len(phase2_ok),
        failed=phase2_fail,
    )

    if verbose:
        print(f"\nPhase 2 结果: OK={phase2.ok}, FAIL={phase2.fail}")

    # ========== Phase 3: convert (采样) ==========
    if verbose:
        print("\n" + "=" * 60)
        print(f"Phase 3: Testing convert on solved files ({sample_size})...")
        print("=" * 60)

    phase3_ok = []
    phase3_fail = []

    for i, name in enumerate(sample):
        f = test_path / name
        out_dir = Path("results_test") / f.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        # 求解
        success, _ = _test_solve(f, out_dir)
        if not success:
            phase3_fail.append(name)
            if verbose:
                print(f"  [{i + 1}/{sample_size}] {name}: SKIP (solve failed)")
            continue

        # 查找 frd
        frd_files = list(out_dir.glob("*.frd"))
        if not frd_files:
            phase3_fail.append(name)
            if verbose:
                print(f"  [{i + 1}/{sample_size}] {name}: SKIP (no frd)")
            continue

        # 转换
        success, msg = _test_convert(frd_files[0])
        if success:
            phase3_ok.append(name)
        else:
            phase3_fail.append(name)

        if verbose:
            status = "OK" if success else "FAIL"
            print(f"  [{i + 1}/{sample_size}] {name}: {status}")

        # 清理
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)

    phase3 = PhaseResult(
        name="convert",
        total=len(sample),
        ok=len(phase3_ok),
        failed=phase3_fail,
    )

    if verbose:
        print(f"\nPhase 3 结果: OK={phase3.ok}, FAIL={phase3.fail}")

    return OfficialTestResult(phase1=phase1, phase2=phase2, phase3=phase3)


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="CalculiX 官方测试集批量测试")
    parser.add_argument("--test-dir", type=Path, help="测试文件目录")
    parser.add_argument("--sample", type=int, default=10, help="采样数量 (默认: 10)")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    try:
        result = run_official_tests(
            test_dir=args.test_dir,
            sample_size=args.sample,
            verbose=not args.quiet,
        )
        print("\n" + result.summary())

        # 返回退出码
        sys.exit(0 if result.total_pass else 1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
