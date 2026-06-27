"""Assignment summary cache/build helpers for the web UI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import essay_tool as tool
from web_metrics import build_radar


def assignment_summary_signature(assignment: dict, submissions: list[dict]) -> str:
    payload = {
        "assignment": {
            "id": assignment.get("id"),
            "title": assignment.get("title"),
            "topic": assignment.get("topic"),
            "writing_type_hint": assignment.get("writing_type_hint"),
            "updated_at": assignment.get("updated_at"),
            "reanalyzed_at": assignment.get("reanalyzed_at"),
        },
        "submissions": [
            {
                "id": item.get("id"),
                "student": item.get("student"),
                "version_no": item.get("version_no"),
                "score": item.get("score"),
                "report_path": item.get("report_path"),
                "created_at": item.get("created_at"),
                "rejudged_at": item.get("rejudged_at"),
                "rejudge_count": item.get("rejudge_count"),
            }
            for item in sorted(submissions, key=lambda x: (x.get("student") or "", x.get("version_no") or 0, x.get("id") or ""))
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def current_assignment_summary(assignment: dict, signature: str) -> dict | None:
    for item in reversed(assignment.get("summary_reports") or []):
        if item.get("signature") != signature or not item.get("path"):
            continue
        path = Path(item["path"])
        if not path.exists():
            continue
        try:
            if "assignment-summary-render:v3" not in path.read_text(encoding="utf-8", errors="ignore"):
                continue
        except OSError:
            continue
        return item
    return None


def build_assignment_summary_payload(assignment: dict, submissions: list[dict]) -> dict:
    rows = []
    for sub in sorted(submissions, key=lambda x: (x.get("student") or "", x.get("version_no") or 0, x.get("created_at") or "")):
        analysis = sub.get("analysis") or {}
        strict = analysis.get("strict_gaokao_banding") if isinstance(analysis.get("strict_gaokao_banding"), dict) else {}
        radar = build_radar(analysis)
        rows.append(
            {
                "submission_id": sub.get("id"),
                "student": sub.get("student"),
                "version_no": sub.get("version_no"),
                "is_revision": sub.get("is_revision"),
                "score": sub.get("score"),
                "created_at": sub.get("created_at"),
                "detected_task_type": analysis.get("detected_task_type"),
                "expected_genre": analysis.get("expected_genre"),
                "detected_genre": analysis.get("detected_genre"),
                "genre_fit": analysis.get("genre_fit"),
                "grade_band": analysis.get("grade_band"),
                "final_band_reason": strict.get("final_band_reason"),
                "overall_comment": analysis.get("overall_comment"),
                "strengths": analysis.get("strengths"),
                "issues": analysis.get("issues"),
                "revision_analysis": analysis.get("revision_analysis"),
                "language_rhythm": analysis.get("language_rhythm"),
                "style_observation": analysis.get("style_observation"),
                "radar": radar,
                "content_excerpt": tool.trim_text(sub.get("content", ""), 1200),
            }
        )
    return {
        "assignment": {
            "id": assignment.get("id"),
            "title": assignment.get("title"),
            "topic": assignment.get("topic"),
            "writing_type_hint": assignment.get("writing_type_hint"),
            "analysis": assignment.get("analysis"),
        },
        "submissions": rows,
    }


def get_or_create_assignment_summary(data_dir: Path, body: dict, args: SimpleNamespace) -> tuple[str, str, bool]:
    state = tool.load_state(data_dir)
    previous_state = json.loads(json.dumps(state, ensure_ascii=False))
    assignment = tool.resolve_assignment(state, body.get("id", ""))
    submissions = [
        state["submissions"][sid]
        for sid in assignment.get("submissions", [])
        if sid in state["submissions"]
    ]
    if not submissions:
        raise tool.ToolError("这次作业还没有可总结的提交。")
    signature = assignment_summary_signature(assignment, submissions)
    cached = current_assignment_summary(assignment, signature)
    if cached:
        return "已打开当前提交集合的作业总结。", cached["path"], False

    model = args.model or tool.get_config_value("DEEPSEEK_MODEL", tool.DEFAULT_MODEL)
    payload = build_assignment_summary_payload(assignment, submissions)
    if args.no_ai:
        analysis = {
            "overall": "未调用 AI；本报告仅列出当前作业提交清单。",
            "teaching_actions": ["关闭离线选项后可重新生成 AI 作业总结。"],
        }
    else:
        raw = tool.call_deepseek(tool.assignment_summary_messages(payload), args, json_mode=True)
        analysis = tool.parse_ai_json(raw)

    report_path = (
        tool.script_dir()
        / "reports"
        / "assignments"
        / assignment["id"]
        / f"assignment_summary_{tool.stamp()}.md"
    )
    created = [tool.write_text(report_path, tool.format_assignment_summary_report(assignment, analysis, payload))]
    record = {
        "signature": signature,
        "created_at": tool.now_iso(),
        "model": model,
        "path": str(report_path.resolve()),
        "submission_ids": [sub.get("id") for sub in submissions],
    }
    assignment.setdefault("summary_reports", []).append(record)
    state.setdefault("generated_reports", []).append(
        {
            "type": "assignment_summary",
            "created_at": record["created_at"],
            "model": model,
            "assignment_id": assignment.get("id"),
            "path": record["path"],
        }
    )
    tool.save_state(data_dir, state)
    tool.push_undo(data_dir, previous_state, created, f"生成作业总结：{assignment.get('title')}")
    return "已生成作业总结。", record["path"], True
