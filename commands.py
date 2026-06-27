"""Business command implementations."""

from __future__ import annotations

import argparse
import copy
import getpass
import statistics
import uuid
from pathlib import Path

from analytics import build_style_payload, group_scores, svg_score_chart
from assignment_service import latest_submission, resolve_assignment, resolve_submission
from core import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL,
    ToolError,
    clean_student,
    date_prefix,
    get_config_value,
    load_state,
    load_undo_stack,
    make_id,
    now_iso,
    push_undo,
    read_text_arg,
    safe_delete_created_path,
    save_state,
    save_undo_stack,
    script_dir,
    stamp,
    write_text,
)
from deepseek_client import call_deepseek, parse_ai_json
from prompts import assignment_messages, revision_analysis_messages, style_messages, submission_messages
from reports import (
    extract_score,
    format_assignment_report,
    format_curve_report,
    format_style_report,
    format_submission_report,
)


def score_submission_with_ai(
    assignment: dict,
    content: str,
    previous: dict | None,
    is_revision: bool,
    args: argparse.Namespace,
) -> dict:
    """Score independently, then optionally ask for revision analysis."""
    raw = call_deepseek(
        submission_messages(assignment, content, None, False),
        args,
        json_mode=True,
    )
    analysis = parse_ai_json(raw)
    analysis["revision_analysis"] = None
    if previous and is_revision:
        revision_raw = call_deepseek(
            revision_analysis_messages(assignment, content, previous, analysis),
            args,
            json_mode=True,
        )
        revision_payload = parse_ai_json(revision_raw)
        revision_analysis = revision_payload.get("revision_analysis")
        analysis["revision_analysis"] = revision_analysis if isinstance(revision_analysis, dict) else revision_payload
    return analysis


def command_config_key(args: argparse.Namespace) -> None:
    key = args.api_key or getpass.getpass("DeepSeek API key: ").strip()
    if not key:
        raise ToolError("API key 不能为空。")
    model = args.model or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    api_base = args.api_base or get_config_value("DEEPSEEK_API_BASE", DEFAULT_API_BASE)
    path = script_dir() / ".env"
    lines = [
        "# Local secret file. Do not commit.",
        f"DEEPSEEK_API_KEY={key}",
        f"DEEPSEEK_MODEL={model}",
        f"DEEPSEEK_API_BASE={api_base}",
    ]
    write_text(path, "\n".join(lines) + "\n")
    print(f"已保存到 {path}")


def command_assignment_new(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    previous_state = copy.deepcopy(state)
    title = args.title.strip()
    topic = read_text_arg(args.topic, args.topic_file, "topic")
    assignment_id = args.id or make_id(title)
    if assignment_id in state["assignments"]:
        raise ToolError(f"作业 ID 已存在：{assignment_id}")
    model = args.model or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    if args.no_ai:
        analysis = {
            "assignment_type": "未调用 AI",
            "core_task": "已保存题目；之后可重新创建或手动补充审题分析。",
        }
    else:
        raw = call_deepseek(assignment_messages(title, topic, args.writing_type), args, json_mode=True)
        analysis = parse_ai_json(raw)
    assignment = {
        "id": assignment_id,
        "title": title,
        "topic": topic,
        "writing_type_hint": args.writing_type,
        "created_at": now_iso(),
        "model": model,
        "analysis": analysis,
        "submissions": [],
    }
    state["assignments"][assignment_id] = assignment
    created: list[Path] = []
    topic_path = data_dir / "assignments" / assignment_id / "topic.md"
    report_path = script_dir() / "reports" / "assignments" / assignment_id / "assignment_analysis.md"
    created.append(write_text(topic_path, f"# {title}\n\n{topic}\n"))
    created.append(write_text(report_path, format_assignment_report(assignment)))
    assignment["topic_path"] = str(topic_path.resolve())
    assignment["analysis_report_path"] = str(report_path.resolve())
    save_state(data_dir, state)
    push_undo(data_dir, previous_state, created, f"新建作业：{title}")
    print(f"已新建作业：{title}")
    print(f"作业 ID：{assignment_id}")
    print(f"审题报告：{report_path}")


def command_submission_add(args: argparse.Namespace) -> None:
    if args.revision and args.initial:
        raise ToolError("--revision 和 --initial 不能同时使用。")
    if args.manual_score is not None and not (0 <= args.manual_score <= 60):
        raise ToolError("--manual-score 必须在 0 到 60 之间。")
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    previous_state = copy.deepcopy(state)
    assignment = resolve_assignment(state, args.assignment)
    student = clean_student(args.student)
    content = read_text_arg(args.content, args.content_file, "content")
    existing = [
        s
        for s in state["submissions"].values()
        if s.get("assignment_id") == assignment["id"] and s.get("student") == student
    ]
    version_no = len(existing) + 1
    previous = latest_submission(state, assignment["id"], student)
    if args.revision is True:
        is_revision = True
    elif args.initial is True:
        is_revision = False
    else:
        is_revision = previous is not None
    model = args.model or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    if args.no_ai:
        analysis = {
            "score": None,
            "overall_comment": "已保存作文；本次未调用 AI 评分。",
            "revision_analysis": None,
        }
    else:
        analysis = score_submission_with_ai(assignment, content, previous, is_revision, args)
    score = float(args.manual_score) if args.manual_score is not None else extract_score(analysis)
    if args.manual_score is not None:
        analysis["manual_score"] = args.manual_score
    submission_id = f"{assignment['id']}_{student}_v{version_no}_{uuid.uuid4().hex[:6]}"
    submission = {
        "id": submission_id,
        "assignment_id": assignment["id"],
        "student": student,
        "version_no": version_no,
        "is_revision": is_revision,
        "previous_submission_id": previous.get("id") if previous and is_revision else None,
        "created_at": now_iso(),
        "model": model,
        "content": content,
        "analysis": analysis,
        "score": score,
    }
    created: list[Path] = []
    content_path = data_dir / "submissions" / assignment["id"] / f"{date_prefix()}_{student}_v{version_no}.md"
    report_path = (
        script_dir()
        / "reports"
        / "assignments"
        / assignment["id"]
        / f"{date_prefix()}_{student}_v{version_no}_评判.md"
    )
    created.append(write_text(content_path, f"# {student} 第 {version_no} 次提交\n\n{content}\n"))
    submission["content_path"] = str(content_path.resolve())
    state["submissions"][submission_id] = submission
    state["students"].setdefault(student, {"student": student, "submissions": []})
    state["students"][student]["submissions"].append(submission_id)
    state["assignments"][assignment["id"]].setdefault("submissions", []).append(submission_id)
    created.append(write_text(report_path, format_submission_report(submission, assignment)))
    submission["report_path"] = str(report_path.resolve())
    save_state(data_dir, state)
    push_undo(data_dir, previous_state, created, f"新增提交：{student} / {assignment.get('title')} / v{version_no}")
    print(f"已保存提交：{student} v{version_no}")
    print(f"提交 ID：{submission_id}")
    print(f"分数：{score if score is not None else '未提取'} / 60")
    print(f"评判报告：{report_path}")


def command_submission_rejudge(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    previous_state = copy.deepcopy(state)
    submission = resolve_submission(state, args.submission)
    assignment = state["assignments"].get(submission.get("assignment_id"))
    if not assignment:
        raise ToolError("这次提交所属作业已不存在，无法重判。")

    student = submission.get("student")
    version_no = submission.get("version_no")
    is_revision = bool(submission.get("is_revision"))
    previous = None
    previous_id = submission.get("previous_submission_id")
    if is_revision and previous_id in state["submissions"]:
        previous = state["submissions"][previous_id]
    elif is_revision:
        earlier = [
            item
            for item in state["submissions"].values()
            if item.get("assignment_id") == assignment.get("id")
            and item.get("student") == student
            and item.get("id") != submission.get("id")
            and (item.get("version_no") or 0) < (version_no or 0)
        ]
        previous = sorted(earlier, key=lambda item: item.get("version_no") or 0)[-1] if earlier else None

    model = args.model or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    if args.no_ai:
        analysis = {
            "score": submission.get("score"),
            "overall_comment": "已保留原提交并标记重判；本次未调用 AI。",
            "revision_analysis": None,
        }
    else:
        analysis = score_submission_with_ai(assignment, submission.get("content", ""), previous, is_revision, args)

    score = extract_score(analysis)
    if score is None:
        score = submission.get("score")
    submission["analysis"] = analysis
    submission["score"] = score
    submission["model"] = model
    submission["rejudged_at"] = now_iso()
    submission["rejudge_count"] = int(submission.get("rejudge_count") or 0) + 1

    report_path = (
        script_dir()
        / "reports"
        / "assignments"
        / assignment["id"]
        / f"{date_prefix()}_{student}_v{version_no}_重判_{stamp()}.md"
    )
    created = [write_text(report_path, format_submission_report(submission, assignment))]
    submission["report_path"] = str(report_path.resolve())
    save_state(data_dir, state)
    push_undo(data_dir, previous_state, created, f"重判提交：{student} / {assignment.get('title')} / v{version_no}")
    print(f"已重判提交：{student} v{version_no}")
    print(f"提交 ID：{submission.get('id')}")
    print(f"新分数：{score if score is not None else '未提取'} / 60")
    print(f"新评判报告：{report_path}")


def command_assignment_rejudge(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    assignment = resolve_assignment(state, args.assignment)
    sub_ids = [sid for sid in assignment.get("submissions", []) if sid in state["submissions"]]
    if not sub_ids:
        raise ToolError("这次作业还没有可重判的学生提交。")
    for sid in sub_ids:
        child_args = copy.copy(args)
        child_args.submission = sid
        command_submission_rejudge(child_args)
        print("")


def command_list(args: argparse.Namespace) -> None:
    state = load_state(Path(args.data_dir).resolve())
    if args.kind == "assignments":
        print("作业列表：")
        for item in sorted(state["assignments"].values(), key=lambda x: x.get("created_at", "")):
            print(f"- {item.get('id')} | {item.get('title')} | 提交 {len(item.get('submissions', []))} 篇")
        return
    print("学生列表：")
    for student, payload in sorted(state["students"].items()):
        subs = [state["submissions"][sid] for sid in payload.get("submissions", []) if sid in state["submissions"]]
        scores = [s.get("score") for s in subs if isinstance(s.get("score"), (int, float))]
        avg = f"{statistics.mean(scores):.1f}" if scores else "无"
        print(f"- {student} | 提交 {len(subs)} 篇 | 平均分 {avg}")


def command_curves(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    previous_state = copy.deepcopy(state)
    students = args.student if args.student else None
    grouped = group_scores(state, students)
    if not grouped:
        raise ToolError("没有可用于生成曲线的分数。请先添加 AI 评分后的提交。")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else script_dir() / "reports" / "score_curves"
    base = f"score_curves_{stamp()}"
    svg_path = out_dir / f"{base}.svg"
    report_path = out_dir / f"{base}.md"
    created = [
        write_text(svg_path, svg_score_chart(grouped)),
        write_text(report_path, format_curve_report(grouped, svg_path)),
    ]
    state["generated_reports"].append({"type": "score_curves", "created_at": now_iso(), "path": str(report_path.resolve())})
    save_state(data_dir, state)
    push_undo(data_dir, previous_state, created, "生成得分曲线")
    print(f"已生成得分曲线：{svg_path}")
    print(f"分析报告：{report_path}")


def command_style_report(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    state = load_state(data_dir)
    previous_state = copy.deepcopy(state)
    payload = build_style_payload(state, args.student if args.student else None)
    if not payload:
        raise ToolError("没有可分析的学生提交。")
    model = args.model or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    if args.no_ai:
        analysis = {
            "students": [
                {
                    "student": item["student"],
                    "style_profile": "未调用 AI，仅保留逐篇风格记录与启发式提示。",
                    "per_assignment_styles": [
                        {
                            "submission_id": history.get("submission_id"),
                            "assignment": history.get("assignment"),
                            "version_no": history.get("version_no"),
                            "style_summary": history.get("style_observation") or "暂无单篇风格观察。",
                            "language_rhythm_summary": history.get("language_rhythm") or "暂无语言韵律记录。",
                            "genre_style": f"{history.get('detected_genre') or '未判断'} / {history.get('genre_fit') or '未判断'}",
                            "stable_features": "离线模式不归纳稳定特征。",
                            "new_or_changed_features": "；".join(history.get("heuristic_flags") or []) or "暂无明显启发式偏离。",
                            "evidence": {
                                "metrics": history.get("metrics"),
                                "similarity_to_previous": history.get("similarity_to_previous"),
                                "style_observation_similarity_to_previous": history.get("style_observation_similarity_to_previous"),
                            },
                        }
                        for history in item["history"]
                    ],
                    "style_baseline": (
                        f"样本数 {len(item['history'])}。离线模式只展示逐篇风格，不建立 AI 归纳基线。"
                        if len(item["history"]) > 1
                        else "样本不足，暂不建立稳定基线。"
                    ),
                    "possible_anomalies": [
                        {
                            "submission_id": history.get("submission_id"),
                            "anomaly_level": "需复核",
                            "compared_with": "同一学生上一篇作文与个人文本指标",
                            "deviation_points": history.get("heuristic_flags"),
                            "evidence": {
                                "similarity_to_previous": history.get("similarity_to_previous"),
                                "style_observation_similarity_to_previous": history.get("style_observation_similarity_to_previous"),
                                "metrics": history.get("metrics"),
                            },
                            "alternative_explanation": "可能由题材、文体、修改目标或教师指导造成。",
                            "confidence": "低；离线启发式只能提醒人工复核。",
                        }
                        for history in item["history"]
                        if history.get("heuristic_flags")
                    ],
                    "next_training": "建议积累更多同一学生作文后再做稳定风格判断。",
                }
                for item in payload
            ],
            "caution": "启发式提示只能作为人工复核线索。",
        }
    else:
        raw = call_deepseek(style_messages(payload), args, json_mode=True)
        analysis = parse_ai_json(raw)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else script_dir() / "reports" / "style"
    report_path = out_dir / f"style_report_{stamp()}.md"
    created = [write_text(report_path, format_style_report(analysis, payload))]
    state["generated_reports"].append(
        {
            "type": "style_report",
            "created_at": now_iso(),
            "model": model,
            "path": str(report_path.resolve()),
        }
    )
    save_state(data_dir, state)
    push_undo(data_dir, previous_state, created, "生成语言风格与异常分析")
    print(f"已生成风格分析报告：{report_path}")


def command_undo(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    stack = load_undo_stack(data_dir)
    if not stack:
        raise ToolError("没有可撤销的操作。")
    entry = stack.pop()
    for raw_path in reversed(entry.get("created_paths", [])):
        safe_delete_created_path(Path(raw_path))
    save_state(data_dir, entry["previous_state"])
    save_undo_stack(data_dir, stack)
    print(f"已撤销：{entry.get('description')}")
