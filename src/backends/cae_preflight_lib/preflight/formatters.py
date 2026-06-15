"""求解前验证结果输出格式化。"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cae_preflight_lib.preflight.models import PreflightResult, Severity


def format_json(result: PreflightResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def format_text(result: PreflightResult) -> str:
    lines = [
        "求解前检查摘要",
        "",
        f"输入文件: {result.input_file}",
        f"求解器: {result.solver}",
        f"风险等级: {result.risk_level.value}",
        f"是否通过: {str(result.success).lower()}",
        (
            "问题统计: "
            f"{result.summary['total']} "
            f"(致命={result.summary['fatal']}, "
            f"错误={result.summary['error']}, "
            f"警告={result.summary['warning']}, "
            f"信息={result.summary['info']})"
        ),
        "",
    ]
    if not result.issues:
        lines.append("[通过] 未发现求解前检查问题。")
        return "\n".join(lines)

    for issue in result.issues:
        location = issue.location.file
        if issue.location.line is not None:
            location += f":{issue.location.line}"
        lines.append(f"[{issue.severity.value}] {issue.rule_id} {issue.title}: {issue.message} ({location})")
        for suggestion in issue.suggestions:
            lines.append(f"  - {suggestion}")
    return "\n".join(lines)


def print_rich(result: PreflightResult, console: Console) -> None:
    style = {
        "PASS": "green",
        "LOW": "cyan",
        "MEDIUM": "yellow",
        "HIGH": "red",
    }.get(result.risk_level.value, "white")
    status_style = {
        "PASS": "green",
        "PASS_WITH_INFO": "cyan",
        "PASS_WITH_WARNINGS": "yellow",
        "BLOCKED": "red",
    }.get(result.status, "white")
    console.print()
    console.print(
        Panel.fit(
            f"[bold]cae-preflight[/bold]\n"
            f"输入文件: [cyan]{result.input_file}[/cyan]\n"
            f"求解器: [cyan]{result.solver}[/cyan]\n"
            f"风险等级: [{style}]{result.risk_level.value}[/{style}]  "
            f"状态: [{status_style}]{result.status}[/{status_style}]",
            border_style=style,
        )
    )

    summary = result.summary
    console.print(
        f"  问题数: [bold]{summary['total']}[/bold]  "
        f"致命={summary['fatal']}  "
        f"错误={summary['error']}  "
        f"警告={summary['warning']}  "
        f"信息={summary['info']}"
    )

    check_table = Table(title="检查项")
    check_table.add_column("类别", style="cyan")
    check_table.add_column("状态")
    check_table.add_column("问题数", justify="right")
    for check in result.checks:
        status = "[green]通过[/green]" if check.passed else "[red]未通过[/red]"
        check_table.add_row(check.category, status, str(check.issue_count))
    console.print(check_table)

    pipeline = result.pipeline.get("stages", []) if isinstance(result.pipeline, dict) else []
    configured_unimplemented = [
        stage for stage in pipeline
        if stage.get("enabled") and not stage.get("implemented")
    ]
    if pipeline:
        stage_table = Table(title="流水线阶段")
        stage_table.add_column("阶段", style="cyan")
        stage_table.add_column("启用")
        stage_table.add_column("当前版本实现")
        stage_table.add_column("状态")
        for stage in pipeline:
            enabled = "[green]是[/green]" if stage.get("enabled") else "[dim]否[/dim]"
            implemented = "[green]是[/green]" if stage.get("implemented") else "[yellow]否[/yellow]"
            status = str(stage.get("status", "-"))
            stage_table.add_row(str(stage.get("name", "-")), enabled, implemented, status)
        console.print(stage_table)
    if configured_unimplemented:
        names = ", ".join(str(stage.get("name")) for stage in configured_unimplemented)
        console.print(f"  [yellow]以下阶段已配置但当前版本未实现，已跳过: {names}[/yellow]")

    if not result.issues:
        console.print("  [green]未发现求解前检查问题。[/green]\n")
        return

    issue_table = Table(title="问题")
    issue_table.add_column("级别")
    issue_table.add_column("规则")
    issue_table.add_column("标题")
    issue_table.add_column("说明")
    issue_table.add_column("位置")
    for issue in result.issues:
        severity_style = "red" if issue.severity in {Severity.FATAL, Severity.ERROR} else "yellow"
        location = issue.location.file
        if issue.location.line is not None:
            location += f":{issue.location.line}"
        issue_table.add_row(
            f"[{severity_style}]{issue.severity.value}[/{severity_style}]",
            issue.rule_id,
            issue.title,
            issue.message,
            location,
        )
    console.print(issue_table)

    console.print("  [bold]修复建议[/bold]")
    for issue in result.issues[:10]:
        if issue.suggestions:
            console.print(f"  [cyan]{issue.rule_id}[/cyan]")
            for suggestion in issue.suggestions:
                console.print(f"    - {suggestion}")
    console.print()
