"""State payload builders for the web UI."""

from __future__ import annotations

from pathlib import Path

import essay_tool as tool
from web_metrics import avg, build_radar
from web_summaries import assignment_summary_signature, current_assignment_summary


def filter_superseded_jobs(jobs: list[dict]) -> list[dict]:
    latest_done_by_submission: dict[str, str] = {}
    for job in jobs:
        if job.get("status") != "done":
            continue
        submission_id = job.get("submissionId")
        if not submission_id:
            continue
        updated = str(job.get("updatedAt") or "")
        if updated > latest_done_by_submission.get(submission_id, ""):
            latest_done_by_submission[submission_id] = updated

    visible: list[dict] = []
    for job in jobs:
        if job.get("status") == "error":
            submission_id = job.get("submissionId")
            if submission_id and latest_done_by_submission.get(submission_id, "") > str(job.get("updatedAt") or ""):
                continue
        visible.append(job)
    return visible


def summarize_state(data_dir: Path, read_only: bool, jobs: list[dict]) -> dict:
    jobs = filter_superseded_jobs(jobs)
    state = tool.load_state(data_dir)
    assignments = []
    for item in sorted(state["assignments"].values(), key=lambda x: x.get("created_at", ""), reverse=True):
        sub_ids = [sid for sid in item.get("submissions", []) if sid in state["submissions"]]
        scores = [
            float(state["submissions"][sid]["score"])
            for sid in sub_ids
            if isinstance(state["submissions"][sid].get("score"), (int, float))
        ]
        sub_items = [state["submissions"][sid] for sid in sub_ids]
        summary_signature = assignment_summary_signature(item, sub_items) if sub_items else ""
        summary = current_assignment_summary(item, summary_signature) if summary_signature else None
        assignments.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "topic": item.get("topic", ""),
                "createdAt": item.get("created_at"),
                "writingType": item.get("writing_type_hint"),
                "submissionCount": len(sub_ids),
                "avgScore": avg(scores),
                "reportPath": item.get("analysis_report_path"),
                "summaryReportPath": summary.get("path") if summary else None,
            }
        )

    students = []
    for name, item in sorted(state["students"].items()):
        subs = [state["submissions"][sid] for sid in item.get("submissions", []) if sid in state["submissions"]]
        subs = sorted(subs, key=lambda x: x.get("created_at", ""))
        scores = [float(s["score"]) for s in subs if isinstance(s.get("score"), (int, float))]
        latest = subs[-1] if subs else {}
        students.append(
            {
                "student": name,
                "submissionCount": len(subs),
                "avgScore": avg(scores),
                "latestScore": scores[-1] if scores else None,
                "trend": round(scores[-1] - scores[0], 1) if len(scores) > 1 else 0,
                "latestGenre": latest.get("analysis", {}).get("detected_genre"),
            }
        )

    submissions = []
    for sub in sorted(state["submissions"].values(), key=lambda x: x.get("created_at", ""), reverse=True):
        assignment = state["assignments"].get(sub.get("assignment_id"), {})
        analysis = sub.get("analysis", {})
        submissions.append(
            {
                "id": sub.get("id"),
                "assignmentId": sub.get("assignment_id"),
                "assignmentTitle": assignment.get("title", sub.get("assignment_id")),
                "student": sub.get("student"),
                "versionNo": sub.get("version_no"),
                "score": sub.get("score"),
                "isRevision": sub.get("is_revision"),
                "createdAt": sub.get("created_at"),
                "expectedGenre": analysis.get("expected_genre"),
                "detectedGenre": analysis.get("detected_genre"),
                "genreFit": analysis.get("genre_fit"),
                "reportPath": sub.get("report_path"),
                "radar": build_radar(analysis),
            }
        )
    recent = submissions[:20]

    reports = []
    for item in reversed(state.get("generated_reports", [])[-20:]):
        reports.append(
            {
                "type": item.get("type"),
                "createdAt": item.get("created_at"),
                "model": item.get("model"),
                "path": item.get("path"),
                "pdfPath": item.get("pdf_path"),
            }
        )

    stack = tool.load_undo_stack(data_dir)
    return {
        "assignments": assignments,
        "students": students,
        "submissions": submissions,
        "recentSubmissions": recent,
        "generatedReports": reports,
        "jobs": jobs,
        "config": {
            "hasApiKey": bool(tool.get_config_value("DEEPSEEK_API_KEY")),
            "model": tool.get_config_value("DEEPSEEK_MODEL", tool.DEFAULT_MODEL),
            "apiBase": tool.get_config_value("DEEPSEEK_API_BASE", tool.DEFAULT_API_BASE),
            "readOnly": read_only,
        },
        "undo": {
            "count": len(stack),
            "last": stack[-1]["description"] if stack else None,
        },
    }
