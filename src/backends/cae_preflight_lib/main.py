# CLI 入口
"""cae-preflight：CAE 输入文件求解前验证流水线。"""

from __future__ import annotations

import json
import os
import shutil
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cae_preflight_lib.preflight.models import Severity

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="cae",
    help="[bold]cae-preflight[/bold] — CAE 输入文件求解前验证流水线",
    no_args_is_help=True,
    add_completion=False,
)


def _emit_preflight_result(result, output_format: str, out: Optional[Path] = None) -> None:
    from cae_preflight_lib.preflight.formatters import format_json, format_text, print_rich

    fmt = output_format.lower().strip()
    if fmt == "json":
        rendered = format_json(result)
    else:
        rendered = format_text(result)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
        if fmt == "rich":
            print_rich(result, console)
            console.print(f"  [green]报告已写出:[/green] [cyan]{out}[/cyan]")
        return

    if fmt == "rich":
        print_rich(result, console)
    else:
        typer.echo(rendered)


@app.command(name="preflight")
def preflight_command(
    inp_file: Optional[Path] = typer.Argument(None, help="Abaqus/CalculiX .inp 输入文件"),
    solver: Optional[str] = typer.Option(None, "--solver", help="求解器风格: calculix / abaqus"),
    output_format: Optional[str] = typer.Option(None, "--format", help="输出格式: rich / text / json"),
    out: Optional[Path] = typer.Option(None, "--out", help="写出报告路径"),
    strict: Optional[bool] = typer.Option(None, "--strict/--no-strict", help="发现 ERROR/FATAL 时返回 exit 1"),
    strict_static: Optional[bool] = typer.Option(
        None,
        "--strict-static/--no-strict-static",
        help="缺少 *BOUNDARY 升级为 ERROR（静力分析）",
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help="只运行指定类别检查: structure/material/section/set/boundary/load/step",
    ),
    explain: Optional[str] = typer.Option(
        None,
        "--explain",
        help="解释规则编号，例如 CAE-SEC-002",
        metavar="RULE_ID",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="cae.toml 配置文件路径"),
) -> None:
    """CAE 求解前完整验证。

    \b
    示例：
      cae preflight model.inp
      cae preflight model.inp --format json
      cae preflight model.inp --strict
      cae preflight model.inp --category material
      cae preflight --explain CAE-SEC-002
      cae preflight model.inp --config my.toml
    """
    from cae_preflight_lib.preflight import explain_rule, run_preflight
    from cae_preflight_lib.preflight.config import load_config

    # --explain 模式：不需要 inp_file 实际解析
    if explain is not None:
        explanation = explain_rule(explain)
        if explanation is None:
            err_console.print(f"\n  未知规则编号: {explain}\n")
            raise typer.Exit(1)
        typer.echo(explanation)
        return

    if inp_file is None:
        err_console.print("\n  请提供 .inp 输入文件，或使用 --explain RULE_ID 查看规则说明。\n")
        raise typer.Exit(2)

    cfg = load_config(config)
    effective_solver = solver or cfg.solver
    effective_strict = strict if strict is not None else cfg.strict
    effective_strict_static = strict_static if strict_static is not None else cfg.strict_static
    effective_format = output_format or cfg.output_format

    try:
        result = run_preflight(
            inp_file,
            solver=effective_solver,
            category=category,
            strict_static=effective_strict_static,
            pipeline=cfg.pipeline,
        )
    except FileNotFoundError:
        err_console.print(f"\n  文件不存在: {inp_file}\n")
        raise typer.Exit(1)
    except ValueError as exc:
        err_console.print(f"\n  {exc}\n")
        raise typer.Exit(2)
    except Exception as exc:
        err_console.print(f"\n  Preflight 解析失败: {exc}\n")
        raise typer.Exit(1)

    _emit_preflight_result(result, effective_format, out)
    if effective_strict and any(
        issue.severity in {Severity.FATAL, Severity.ERROR, Severity.WARNING}
        for issue in result.issues
    ):
        raise typer.Exit(1)


@app.command(name="doctor")
def doctor_command(
    json_output: bool = typer.Option(False, "--json", help="输出结构化 JSON。"),
) -> None:
    """检查本机 CAE 环境、依赖和配置状态。

    \b
    示例：
      cae doctor
    """
    from cae_preflight_lib.preflight.config import load_config

    checks: list[tuple[str, str, str, str]] = []

    # Python 版本
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    ok_ver = v >= (3, 10)
    checks.append(("Python 版本", ver_str, "ok" if ok_ver else "error", "" if ok_ver else "需要 Python >= 3.10"))

    # CalculiX
    ccx = shutil.which("ccx")
    checks.append(("CalculiX (ccx)", ccx or "未找到", "warning" if not ccx else "ok", "" if ccx else "当前 V0.1 默认不运行求解器，可稍后安装 ccx"))

    # cae 包
    try:
        import cae as _cae_pkg
        cae_ver = getattr(_cae_pkg, "__version__", "已安装")
        checks.append(("cae 包", cae_ver, "ok", ""))
    except ImportError:
        checks.append(("cae 包", "未安装", "error", "pip install -e ."))

    # TOML 支持
    if sys.version_info >= (3, 11):
        checks.append(("TOML 支持 (tomllib)", "内置", "ok", ""))
    else:
        try:
            import tomli as _  # noqa: F401
            checks.append(("TOML 支持 (tomli)", "已安装", "ok", ""))
        except ImportError:
            checks.append(("TOML 支持 (tomli)", "未安装", "error", "pip install tomli"))

    # cae.toml
    cfg = load_config()
    if cfg.config_path is not None:
        checks.append(("cae.toml", str(cfg.config_path.resolve()), "info", ""))
        if cfg.parse_error:
            checks.append(("cae.toml 解析", "失败", "error", cfg.parse_error))
        else:
            checks.append(("cae.toml 解析", "通过", "ok", ""))
    else:
        checks.append(("cae.toml", "未找到（使用默认配置）", "info", ""))

    for stage_name in cfg.pipeline.unknown_stages:
        checks.append(("未知 stage", stage_name, "warning", "该 stages 配置会被当前版本忽略"))
    for stage_name in cfg.pipeline.enabled_unimplemented_stages():
        checks.append(("未实现 stage", stage_name, "warning", "已配置但当前版本不会执行"))

    # AI 支持（可选）
    try:
        import requests as _  # noqa: F401
        checks.append(("AI 支持 (requests)", "已安装", "ok", ""))
    except ImportError:
        checks.append(("AI 支持 (requests)", "未安装（可选）", "info", "pip install requests"))

    payload = {
        "success": not any(level == "error" for _, _, level, _ in checks),
        "checks": [
            {
                "name": name,
                "status": status,
                "level": level,
                "hint": hint,
            }
            for name, status, level, hint in checks
        ],
        "warnings": [
            {
                "name": name,
                "status": status,
                "hint": hint,
            }
            for name, status, level, hint in checks
            if level == "warning"
        ],
        "meta": {
            "python": ver_str,
            "cwd": str(Path.cwd()),
        },
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload["success"]:
            raise typer.Exit(1)
        return

    table = Table(title="cae doctor — 环境检查", show_header=True)
    table.add_column("检查项", style="cyan", min_width=24)
    table.add_column("状态", min_width=28)
    table.add_column("备注", style="dim")

    all_ok = True
    for name, status, level, hint in checks:
        if level == "ok":
            s = f"[green]{status}[/green]"
        elif level == "error":
            s = f"[red]{status}[/red]"
            all_ok = False
        elif level == "warning":
            s = f"[yellow]{status}[/yellow]"
        else:
            s = f"[dim]{status}[/dim]"
        table.add_row(name, s, hint)

    console.print()
    console.print(table)
    console.print()
    if all_ok:
        console.print("  [green]环境检查通过。[/green]\n")
    else:
        console.print("  [yellow]部分检查未通过，请参考上方备注修复。[/yellow]\n")


if __name__ == "__main__":
    app()
