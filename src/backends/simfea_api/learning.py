import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .analytics import analyze_run, render_analysis_section
from .config import expand_path, normalize_learning_format, settings
from .results import generate_result_summary, run_artifacts
from .run_archive import read_optional_text, read_tail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_filename_part(value: str | None, fallback: str = "untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value or "").strip(" ._")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or fallback


# ---------------------------------------------------------------------------
# Structured guided-note system
# ---------------------------------------------------------------------------

_GUIDED_QUESTIONS = {
    "purpose": "这次运行的目的是什么？（验证模型？探索参数？复现结果？）",
    "expectation": "结果和你的预期一致吗？如果不一致，可能的原因是什么？",
    "confusion": "有什么没弄明白的地方？",
    "next": "下次运行会改变什么参数或设置？",
}


def _guided_question_ids(meta: dict) -> list[str]:
    """Return the ordered list of question ids applicable to this run."""
    ids: list[str] = ["purpose", "expectation", "confusion"]
    status = meta.get("status", "")
    exit_code = meta.get("exit_code")
    solver = meta.get("solver", "")

    if status == "failed" or (exit_code is not None and exit_code != 0):
        ids.append("failure_cause")
    elif status == "finished":
        if solver in ("calculix",):
            ids.append("comparison")
        ids.append("next")
    elif status == "canceled":
        ids.append("cancel_reason")
    else:
        ids.append("next")

    return ids


def guided_questions(meta: dict, analysis: dict | None = None) -> list[dict]:
    """Return the guided questions for this run, with empty answers.

    When *analysis* from ``analyze_run()`` is provided, questions are customized
    with actual result values instead of generic prompts.
    """
    extra = {
        "failure_cause": "你判断失败的原因是什么？",
        "comparison": "结果是否符合理论值或经验预期？你是怎么验证的？",
        "cancel_reason": "取消的原因是什么？",
    }

    def _build_question(qid: str) -> str:
        base = _GUIDED_QUESTIONS.get(qid, extra.get(qid, qid))
        if qid != "comparison" or not analysis:
            return base
        analytical = analysis.get("analytical") or {}
        if not analytical:
            return base
        fea_d = analytical.get("fea_delta_mm")
        theory_d = analytical.get("delta_mm")
        err = analytical.get("delta_error_pct")
        if fea_d is not None and theory_d is not None and err is not None:
            return (
                f"理论位移 {theory_d:.2f}mm（Euler-Bernoulli），"
                f"仿真位移 {fea_d:.3f}mm，误差 {err:.1f}%。"
                f"结果是否符合预期？你怎么验证的？"
            )
        return base

    return [
        {"id": qid, "question": _build_question(qid), "answer": ""}
        for qid in _guided_question_ids(meta)
    ]


def parse_note_answers(note_text: str) -> dict[str, str]:
    """Parse a structured note.md into {question_id: answer}.

    Handles both the new Q&A format and legacy free-text notes.
    Legacy notes are returned as a single ``note`` key.
    """
    text = note_text.strip()
    if not text:
        return {}

    # Legacy format: plain text (no ## headings that match our question set)
    known_questions = set(_GUIDED_QUESTIONS.values())
    has_known_heading = any(
        line.strip().startswith("## ") and line.strip().lstrip("# ").strip() in known_questions
        for line in text.splitlines()
    )
    if not has_known_heading:
        return {"note": text}

    # Parse Q&A format
    answers: dict[str, str] = {}
    current_q: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_q is not None:
                answers[_question_id_from_text(current_q)] = "\n".join(current_lines).strip()
            current_q = line[3:].strip()
            current_lines = []
        elif current_q is not None:
            current_lines.append(line)

    if current_q is not None:
        answers[_question_id_from_text(current_q)] = "\n".join(current_lines).strip()

    return answers


def _question_id_from_text(question_text: str) -> str:
    """Reverse-map a question text back to its id."""
    text_to_id = {
        "你判断失败的原因是什么？": "failure_cause",
        "结果是否符合理论值或经验预期？你是怎么验证的？": "comparison",
        "取消的原因是什么？": "cancel_reason",
    }
    for qid, qtext in _GUIDED_QUESTIONS.items():
        text_to_id[qtext] = qid
    return text_to_id.get(question_text, "custom")


def compose_note_md(answers: dict[str, str], meta: dict | None = None) -> str:
    """Render structured answers back to a note.md string."""
    meta = meta or {}
    question_ids = _guided_question_ids(meta)
    extra = {
        "failure_cause": "你判断失败的原因是什么？",
        "comparison": "结果是否符合理论值或经验预期？你是怎么验证的？",
        "cancel_reason": "取消的原因是什么？",
    }

    lines: list[str] = []
    for qid in question_ids:
        question_text = _GUIDED_QUESTIONS.get(qid, extra.get(qid, qid))
        answer = answers.get(qid, "").strip()
        lines.append(f"## {question_text}")
        lines.append("")
        lines.append(answer or "（未填写）")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _render_note_for_report(note_text: str, meta: dict) -> str:
    """Render the note for inclusion in the learning report.

    Structured notes are formatted as a Q&A list.
    Legacy free-text notes are included as-is.
    """
    answers = parse_note_answers(note_text)
    if not answers:
        return (
            "尚未填写。建议从以下几个问题入手：\n\n"
            "- 这次运行的目的是什么？（验证模型？探索参数？复现结果？）\n"
            "- 结果是否符合预期？如果不符合，可能的原因是什么？\n"
            "- 下次运行会改变什么参数或设置？\n"
            "- 这次运行和哪篇文献、哪个理论解或哪个经验值做了对比？"
        )

    # Legacy free-text
    if "note" in answers:
        return answers["note"].strip() or "（空笔记）"

    # Structured Q&A
    question_ids = _guided_question_ids(meta)
    extra = {
        "failure_cause": "你判断失败的原因是什么？",
        "comparison": "结果是否符合理论值或经验预期？你是怎么验证的？",
        "cancel_reason": "取消的原因是什么？",
    }
    lines: list[str] = []
    for qid in question_ids:
        question_text = _GUIDED_QUESTIONS.get(qid, extra.get(qid, qid))
        answer = answers.get(qid, "").strip()
        lines.append(f"- **{question_text}**")
        lines.append(f"  {answer or '（未填写）'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def _next_step_questions(meta: dict, answers: dict[str, str] | None = None) -> str:
    status = meta.get("status", "")
    exit_code = meta.get("exit_code")
    solver = meta.get("solver", "")
    answers = answers or {}
    recorded_next = answers.get("next", "").strip()
    if recorded_next == "（未填写）":
        recorded_next = ""

    questions: list[str] = []
    if recorded_next:
        questions.append(f"已记录的下次调整：{recorded_next}")

    if status == "failed" or (exit_code is not None and exit_code != 0):
        questions.append("stderr 中是否有错误线索能解释失败原因？")
        questions.append("输入文件参数是否合理？求解器是否可用？")
        questions.append("下次会调整什么参数？")
    elif status == "finished":
        if solver in ("calculix",) and exit_code == 0:
            questions.append("结果位移和应力是否符合解析解或经验预期？")
            questions.append("如果加密网格或改变载荷，结果会怎么变化？")
        questions.append("这次运行的物理含义是什么？是验证模型还是探索设计空间？")
        questions.append("输入文件和执行命令之间是否能互相解释？")
    elif status == "canceled":
        questions.append("取消的原因是资源不足、配置错误，还是参数需要调整？")
        questions.append("下次提交前需要修改什么？")
    else:
        questions.append("当前运行尚未结束——是否需要关注运行状态？")

    return "\n".join(f"- {q}" for q in questions) if questions else "- 暂无自动生成的问题。请手动填写。\n"


def _find_related_runs(run_dir: Path, meta: dict, max_results: int = 5) -> list[dict]:
    """Find past runs with the same solver for cross-run comparison."""
    solver = meta.get("solver", "")
    current_id = meta.get("run_id", run_dir.name)
    runs_root = run_dir.parent
    related: list[dict] = []

    for candidate_dir in sorted(runs_root.iterdir(), reverse=True):
        if not candidate_dir.is_dir() or candidate_dir.name == current_id:
            continue
        candidate_meta_path = candidate_dir / "meta.json"
        if not candidate_meta_path.exists():
            continue
        try:
            cm = json.loads(candidate_meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if cm.get("solver") != solver:
            continue

        summary_path = candidate_dir / "artifacts" / "result_summary.json"
        metrics = {}
        if summary_path.exists():
            try:
                sm = json.loads(summary_path.read_text(encoding="utf-8"))
                metrics = sm.get("metrics", {})
            except (json.JSONDecodeError, OSError):
                pass

        related.append({
            "run_id": cm.get("run_id", candidate_dir.name),
            "status": cm.get("status", ""),
            "exit_code": cm.get("exit_code"),
            "created_at": cm.get("created_at", ""),
            "max_displacement_mm": metrics.get("max_displacement_mm"),
            "max_von_mises_mpa": metrics.get("max_von_mises_mpa"),
            "has_note": (candidate_dir / "note.md").exists(),
        })

        if len(related) >= max_results:
            break

    return related


def _render_related_runs(related: list[dict], current_meta: dict) -> str:
    """Render related runs as a markdown comparison section."""
    if not related:
        return ""

    lines = ["## 相关运行", ""]
    lines.append("| 运行 ID | 状态 | 最大位移 (mm) | 最大应力 (MPa) | 笔记 |")
    lines.append("|---------|------|---------------|----------------|------|")

    for r in related:
        sid = r["run_id"][:12] if len(r["run_id"]) > 12 else r["run_id"]
        status = r["status"]
        disp = f"{r['max_displacement_mm']:.3f}" if r["max_displacement_mm"] is not None else "—"
        stress = f"{r['max_von_mises_mpa']:.3f}" if r["max_von_mises_mpa"] is not None else "—"
        note = "有" if r["has_note"] else "无"
        lines.append(f"| {sid} | {status} | {disp} | {stress} | {note} |")

    lines.append("")
    lines.append(f"共找到 {len(related)} 个使用相同求解器的历史运行。")
    lines.append("")

    return "\n".join(lines)


def generate_learning_report(run_dir: Path) -> Path:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing run metadata: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    raw_note = read_optional_text(run_dir / "note.md", "").strip()
    note_answers = parse_note_answers(raw_note)
    note = _render_note_for_report(raw_note, meta)
    stdout_tail = read_tail(run_dir / "stdout.log")
    stderr_tail = read_tail(run_dir / "stderr.log")
    result_text = read_optional_text(run_dir / "artifacts" / "result.txt", "暂无结果文件。").strip()
    solver_label = meta.get("solver_label") or meta.get("solver") or "未知求解器"
    runner_label = meta.get("runner") or "未知执行器"
    toolchain_lines = (
        f"- {solver_label}：{meta.get('solver_kind', '求解器')}（本次实际使用）\n"
        f"- 执行器：{runner_label}"
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

    input_files = meta.get("input_files") or []
    if input_files:
        input_lines: list[str] = []
        for rel_path in input_files:
            input_lines.append(f"### `{rel_path}`")
            abs_path = run_dir / rel_path
            if abs_path.is_file():
                try:
                    content = abs_path.read_text(encoding="utf-8")
                    if content.count("\n") <= 80:
                        input_lines.append(f"```\n{content.strip()}\n```")
                    else:
                        input_lines.append(f"（文件较大，{content.count(chr(10)) + 1} 行，未嵌入。路径：{rel_path}）")
                except Exception:
                    input_lines.append(f"（无法读取文件内容）")
            else:
                input_lines.append(f"（文件不存在：{abs_path}）")
        input_files_section = "\n\n## 输入文件\n\n" + "\n".join(input_lines)
    else:
        input_files_section = ""

    analysis = analyze_run(run_dir)
    analysis_section = render_analysis_section(analysis)
    related = _find_related_runs(run_dir, meta)
    related_section = _render_related_runs(related, meta)
    next_steps = _next_step_questions(meta, note_answers)

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
{input_files_section}

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

{analysis_section}
{related_section}
## 学习笔记
{note}

## 下一步问题
{next_steps}
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
