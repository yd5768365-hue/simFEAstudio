import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import expand_path, normalize_learning_format, settings
from .results import generate_result_summary, run_artifacts
from .run_archive import read_optional_text, read_tail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_filename_part(value: str | None, fallback: str = "untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value or "").strip(" ._")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or fallback


def generate_learning_report(run_dir: Path) -> Path:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing run metadata: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    note = read_optional_text(run_dir / "note.md", "尚未填写。").strip() or "尚未填写。"
    stdout_tail = read_tail(run_dir / "stdout.log")
    stderr_tail = read_tail(run_dir / "stderr.log")
    result_text = read_optional_text(run_dir / "artifacts" / "result.txt", "暂无结果文件。").strip()
    toolchain_lines = "\n".join(
        f"- {item['name']}：{item['role']}（{item['status']}）"
        for item in meta.get("toolchain", settings().toolchain)
    )
    scheduler_lines = [
        f"- 调度器：{meta.get('scheduler') or '无'}",
        f"- 作业 ID：{meta.get('job_id') or '无'}",
        f"- 分区：{meta.get('partition') or '无'}",
        f"- 运行节点：{meta.get('allocated_node') or '无'}",
        f"- 申请 CPU：{meta.get('requested_cpus') or '无'}",
        f"- 申请内存：{meta.get('requested_memory') or '无'}",
        f"- 最近调度状态：{meta.get('last_scheduler_state') or '无'}",
    ]
    scheduler_summary = "\n".join(scheduler_lines)

    report = f"""# SimFEA Studio 学习沉淀报告

## 运行身份
- 运行 ID：{meta.get("run_id", "")}
- 算例：{meta.get("case_name", "")}
- 求解器/执行器：{meta.get("solver", "")} / {meta.get("runner", "")}
- 计算节点：{meta.get("compute_node_label", meta.get("compute_node", ""))}
- 状态：{meta.get("status", "")}
- 退出码：{meta.get("exit_code", "")}
- 创建时间：{meta.get("created_at", "")}
- 结束时间：{meta.get("finished_at", "")}
- 本地归档：{meta.get("local_archive", "")}
- 远程目录：{meta.get("remote_workdir", "")}

## 调度信息
{scheduler_summary}

## 工具链位置
{toolchain_lines}

## 执行命令
```bash
{meta.get("command", "").strip()}
```

## 实时日志摘要
```text
{stdout_tail}
```

## 错误输出摘要
```text
{stderr_tail}
```

## 结果文件摘要
```text
{result_text}
```

## 学习笔记
{note}

## 下一步问题
- 这次运行是否证明了远程执行链路可靠？
- 当前输入、命令、日志和结果之间是否能互相解释？
- 下一步要把 demo-shell 替换成 CalculiX、OpenFOAM、Elmer，还是先接 FreeCAD/Salome 的输入文件？
"""

    report_path = run_dir / "learning_report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def learning_export_root(target_dir: str | None = None) -> Path:
    current = settings()
    if target_dir and target_dir.strip():
        return expand_path(target_dir.strip(), relative_to_project=True)
    return current.learning_export_root


def build_plain_learning_record(meta: dict, report: str, note: str, summary: dict | None) -> str:
    metrics = (summary or {}).get("metrics", {})
    lines = [
        "SimFEA Studio 学习记录",
        "",
        f"运行 ID：{meta.get('run_id', '')}",
        f"算例：{meta.get('case_name', '')}",
        f"求解器/执行器：{meta.get('solver', '')} / {meta.get('runner', '')}",
        f"计算节点：{meta.get('compute_node_label', meta.get('compute_node', ''))}",
        f"状态：{meta.get('status', '')}",
        f"退出码：{meta.get('exit_code', '')}",
        f"本地归档：{meta.get('local_archive', '')}",
        f"远程目录：{meta.get('remote_workdir', '')}",
        "",
        "关键结果",
        f"最大位移 mm：{metrics.get('max_displacement_mm', '无')}",
        f"最大 Von Mises MPa：{metrics.get('max_von_mises_mpa', '无')}",
        "",
        "学习笔记",
        note or "尚未填写。",
        "",
        "完整报告",
        report,
    ]
    return "\n".join(str(line) for line in lines)


def export_learning_record(run_dir: Path, export_format: str | None, target_dir: str | None = None) -> dict:
    if not run_dir.exists():
        raise FileNotFoundError(f"Run not found: {run_dir}")

    current = settings()
    normalized_format = normalize_learning_format(export_format or current.learning_default_format)
    if normalized_format not in current.learning_formats:
        raise ValueError(
            f"Unsupported learning export format: {export_format}. "
            f"Allowed formats: {', '.join(current.learning_formats)}"
        )

    summary = generate_result_summary(run_dir)
    report_path = generate_learning_report(run_dir)
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    note = read_optional_text(run_dir / "note.md").strip()

    target_root = learning_export_root(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    date_part = (meta.get("created_at") or utc_now()).split("T", 1)[0]
    filename = "_".join(
        [
            sanitize_filename_part(date_part, "date"),
            sanitize_filename_part(meta.get("run_id"), run_dir.name),
            sanitize_filename_part(meta.get("case_name"), "case"),
        ]
    )
    export_path = target_root / f"{filename}.{normalized_format}"
    record = {
        "schema_version": "simfea.learning-record.v1",
        "exported_at": utc_now(),
        "format": normalized_format,
        "source": {
            "run_archive": str(run_dir),
            "learning_report": str(report_path),
            "note": str(run_dir / "note.md"),
        },
        "run": meta,
        "summary": summary,
        "note": note,
        "report": report,
        "artifacts": run_artifacts(run_dir),
    }

    if normalized_format == "json":
        export_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    elif normalized_format == "txt":
        export_path.write_text(build_plain_learning_record(meta, report, note, summary), encoding="utf-8")
    else:
        export_path.write_text(report, encoding="utf-8")

    export_record = {
        "path": str(export_path),
        "format": normalized_format,
        "exported_at": record["exported_at"],
    }
    exports = meta.get("learning_exports")
    if not isinstance(exports, list):
        exports = []
    exports = [
        item
        for item in exports
        if isinstance(item, dict)
        and not (item.get("path") == export_record["path"] and item.get("format") == export_record["format"])
    ]
    exports.append(export_record)
    meta["learning_export"] = export_record
    meta["learning_exports"] = exports[-20:]
    meta["learning_report"] = "learning_report.md"
    meta["result_summary"] = "artifacts/result_summary.json" if summary else None
    meta["artifacts"] = run_artifacts(run_dir)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "run_id": meta.get("run_id", run_dir.name),
        "export_path": str(export_path),
        "export_root": str(target_root),
        "format": normalized_format,
        "allowed_formats": current.learning_formats,
        "default_format": current.learning_default_format,
        "summary": summary,
        "record": export_record,
    }

