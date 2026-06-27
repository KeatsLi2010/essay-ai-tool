#!/usr/bin/env python3
"""Local web UI for the essay AI tool."""

from __future__ import annotations

import argparse
import copy
import contextlib
import io
import json
import mimetypes
import socket
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import essay_tool as tool
from web_exports import assignment_export_pdf, radar_export_pdf, report_export_pdf, send_pdf_response
from web_state import summarize_state as build_state_payload
from web_summaries import get_or_create_assignment_summary


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
LOG_PATH = ROOT / "web_ui.log"
JOB_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()

def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as f:
        f.write(message.rstrip() + "\n")
    if sys.stdout:
        try:
            print(message, flush=True)
        except Exception:
            pass


def find_free_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 80):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError("找不到可用端口。")


def run_silently(func, args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        func(args)
    return buffer.getvalue().strip()


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def is_safe_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    roots = [ROOT.resolve(), Path.cwd().resolve()]
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def safe_report_path(raw: str) -> Path:
    path = Path(unquote(raw))
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not is_safe_path(path) or not path.exists() or not path.is_file():
        raise tool.ToolError("报告路径不可读取。")
    return path


def materialize_report_pdf(report_path: Path) -> Path:
    if report_path.suffix.lower() == ".pdf":
        return report_path
    _, pdf_bytes = report_export_pdf(report_path)
    pdf_path = report_path.with_suffix(".pdf")
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


def attach_generated_report_pdf(data_dir: Path, report_path: Path, pdf_path: Path) -> None:
    state = tool.load_state(data_dir)
    raw_report = str(report_path.resolve())
    raw_pdf = str(pdf_path.resolve())
    for item in reversed(state.get("generated_reports", [])):
        if item.get("path") == raw_report:
            item["pdf_path"] = raw_pdf
            break
    tool.save_state(data_dir, state)

    stack = tool.load_undo_stack(data_dir)
    if stack:
        created = stack[-1].setdefault("created_paths", [])
        if raw_pdf not in created:
            created.append(raw_pdf)
            tool.save_undo_stack(data_dir, stack)


def jobs_path(data_dir: Path) -> Path:
    return data_dir / "jobs.json"


def load_jobs(data_dir: Path) -> dict:
    tool.ensure_dirs(data_dir)
    path = jobs_path(data_dir)
    if not path.exists():
        return {"jobs": {}}
    try:
        payload = tool.load_json_file(path)
    except json.JSONDecodeError:
        return {"jobs": {}}
    payload.setdefault("jobs", {})
    return payload


def save_jobs(data_dir: Path, payload: dict) -> None:
    tool.ensure_dirs(data_dir)
    tool.save_json_file(jobs_path(data_dir), payload)


def mark_interrupted_jobs(data_dir: Path) -> None:
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        changed = False
        for job in payload.get("jobs", {}).values():
            if job.get("status") not in {"queued", "running"}:
                continue
            job["status"] = "error"
            job["message"] = "网页服务曾重启，这次后台评分已中断；请重新提交该同学本次作文。"
            job["updatedAt"] = tool.now_iso()
            changed = True
        if changed:
            save_jobs(data_dir, payload)


def update_job(data_dir: Path, job_id: str, **updates) -> dict:
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        job = payload["jobs"].setdefault(job_id, {"id": job_id})
        job.update(updates)
        job["updatedAt"] = tool.now_iso()
        save_jobs(data_dir, payload)
        return job


def list_jobs(data_dir: Path) -> list[dict]:
    payload = load_jobs(data_dir)
    jobs = sorted(payload.get("jobs", {}).values(), key=lambda x: x.get("createdAt", ""), reverse=True)
    return jobs[:30]


def newest_submission_for_job(data_dir: Path, assignment_id: str, student: str) -> dict | None:
    state = tool.load_state(data_dir)
    matches = [
        item
        for item in state["submissions"].values()
        if item.get("assignment_id") == assignment_id and item.get("student") == student
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item.get("created_at", ""))[-1]


def submission_for_job(data_dir: Path, submission_id: str) -> dict | None:
    state = tool.load_state(data_dir)
    return state["submissions"].get(submission_id)


def run_submission_job(data_dir: Path, job_id: str, args: SimpleNamespace, assignment_id: str, student: str) -> None:
    update_job(data_dir, job_id, status="running", message="正在调用 DeepSeek 评分，报告完成前不会开放查看。")
    try:
        with STATE_LOCK:
            message = run_silently(tool.command_submission_add, args)
            submission = newest_submission_for_job(data_dir, assignment_id, student)
        updates = {
            "status": "done",
            "message": message or "评分完成。",
        }
        if submission:
            updates.update(
                {
                    "submissionId": submission.get("id"),
                    "score": submission.get("score"),
                    "reportPath": submission.get("report_path"),
                    "detectedGenre": submission.get("analysis", {}).get("detected_genre"),
                    "genreFit": submission.get("analysis", {}).get("genre_fit"),
                }
            )
        update_job(data_dir, job_id, **updates)
    except Exception as exc:  # noqa: BLE001 - background job must surface failures to UI.
        log(traceback.format_exc())
        update_job(data_dir, job_id, status="error", message=str(exc))


def previous_submission_for_rejudge(state: dict, assignment: dict, submission: dict) -> dict | None:
    if not submission.get("is_revision"):
        return None
    previous_id = submission.get("previous_submission_id")
    if previous_id in state.get("submissions", {}):
        return state["submissions"][previous_id]
    student = submission.get("student")
    version_no = submission.get("version_no")
    earlier = [
        item
        for item in state.get("submissions", {}).values()
        if item.get("assignment_id") == assignment.get("id")
        and item.get("student") == student
        and item.get("id") != submission.get("id")
        and (item.get("version_no") or 0) < (version_no or 0)
    ]
    return sorted(earlier, key=lambda item: item.get("version_no") or 0)[-1] if earlier else None


def build_rejudge_analysis(data_dir: Path, args: SimpleNamespace, submission_id: str) -> tuple[dict, str]:
    with STATE_LOCK:
        state = tool.load_state(data_dir)
        submission = tool.resolve_submission(state, submission_id)
        assignment = state["assignments"].get(submission.get("assignment_id"))
        if not assignment:
            raise tool.ToolError("这次提交所属作业已不存在，无法重判。")
        model = args.model or tool.get_config_value("DEEPSEEK_MODEL", tool.DEFAULT_MODEL)
        if args.no_ai:
            return {
                "score": submission.get("score"),
                "overall_comment": "已保留原提交并标记重判；本次未调用 AI。",
                "revision_analysis": None,
            }, model
        previous = previous_submission_for_rejudge(state, assignment, submission)
        content = submission.get("content", "")
        is_revision = bool(submission.get("is_revision"))
    analysis = tool.score_submission_with_ai(assignment, content, previous, is_revision, args)
    return analysis, model


def apply_rejudge_analysis(data_dir: Path, submission_id: str, analysis: dict, model: str) -> tuple[str, dict | None]:
    state = tool.load_state(data_dir)
    previous_state = copy.deepcopy(state)
    submission = tool.resolve_submission(state, submission_id)
    assignment = state["assignments"].get(submission.get("assignment_id"))
    if not assignment:
        raise tool.ToolError("这次提交所属作业已不存在，无法保存重判结果。")

    score = tool.extract_score(analysis)
    if score is None:
        score = submission.get("score")
    submission["analysis"] = analysis
    submission["score"] = score
    submission["model"] = model
    submission["rejudged_at"] = tool.now_iso()
    submission["rejudge_count"] = int(submission.get("rejudge_count") or 0) + 1

    student = submission.get("student")
    version_no = submission.get("version_no")
    report_path = (
        tool.script_dir()
        / "reports"
        / "assignments"
        / assignment["id"]
        / f"{tool.date_prefix()}_{student}_v{version_no}_重判_{tool.stamp()}.md"
    )
    created = [tool.write_text(report_path, tool.format_submission_report(submission, assignment))]
    submission["report_path"] = str(report_path.resolve())
    tool.push_undo(data_dir, previous_state, created, f"重判提交：{student} / {assignment.get('title')} / v{version_no}")
    tool.save_state(data_dir, state)
    message = "\n".join(
        [
            f"已重判提交：{student} v{version_no}",
            f"提交 ID：{submission.get('id')}",
            f"新分数：{score if score is not None else '未提取'} / 60",
            f"新评判报告：{report_path}",
        ]
    )
    return message, submission


def run_rejudge_job(data_dir: Path, job_id: str, args: SimpleNamespace, submission_id: str) -> None:
    update_job(data_dir, job_id, status="running", message="正在重新调用 DeepSeek 完全重判，完成前暂不开放旧报告。")
    try:
        analysis, model = build_rejudge_analysis(data_dir, args, submission_id)
        with STATE_LOCK:
            message, submission = apply_rejudge_analysis(data_dir, submission_id, analysis, model)
        updates = {
            "status": "done",
            "message": message or "重判完成。",
        }
        if submission:
            updates.update(
                {
                    "submissionId": submission.get("id"),
                    "score": submission.get("score"),
                    "reportPath": submission.get("report_path"),
                    "detectedGenre": submission.get("analysis", {}).get("detected_genre"),
                    "genreFit": submission.get("analysis", {}).get("genre_fit"),
                }
            )
        update_job(data_dir, job_id, **updates)
    except Exception as exc:  # noqa: BLE001 - background job must surface failures to UI.
        log(traceback.format_exc())
        update_job(data_dir, job_id, status="error", message=str(exc))


def start_submission_job(data_dir: Path, args: SimpleNamespace, assignment: dict, student: str) -> dict:
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    job = {
        "id": job_id,
        "type": "submission",
        "status": "queued",
        "message": "已加入后台评分队列。",
        "createdAt": tool.now_iso(),
        "updatedAt": tool.now_iso(),
        "assignmentId": assignment.get("id"),
        "assignmentTitle": assignment.get("title"),
        "student": student,
        "isRevision": bool(args.revision),
        "manualScore": args.manual_score,
        "noAi": bool(args.no_ai),
    }
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        payload["jobs"][job_id] = job
        save_jobs(data_dir, payload)
    thread = threading.Thread(
        target=run_submission_job,
        args=(data_dir, job_id, args, assignment.get("id"), student),
        daemon=True,
    )
    thread.start()
    return job


def start_rejudge_job(data_dir: Path, args: SimpleNamespace, submission: dict, assignment: dict) -> dict:
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    job = {
        "id": job_id,
        "type": "rejudge",
        "status": "queued",
        "message": "已加入后台重判队列。",
        "createdAt": tool.now_iso(),
        "updatedAt": tool.now_iso(),
        "assignmentId": assignment.get("id"),
        "assignmentTitle": assignment.get("title"),
        "submissionId": submission.get("id"),
        "student": submission.get("student"),
        "versionNo": submission.get("version_no"),
        "isRevision": bool(submission.get("is_revision")),
        "noAi": bool(args.no_ai),
    }
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        payload["jobs"][job_id] = job
        save_jobs(data_dir, payload)
    thread = threading.Thread(
        target=run_rejudge_job,
        args=(data_dir, job_id, args, submission.get("id")),
        daemon=True,
    )
    thread.start()
    return job


def prune_jobs(data_dir: Path, assignment_id: str | None = None, submission_id: str | None = None) -> None:
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        kept = {}
        for job_id, job in payload.get("jobs", {}).items():
            if assignment_id and job.get("assignmentId") == assignment_id:
                continue
            if submission_id and job.get("submissionId") == submission_id:
                continue
            kept[job_id] = job
        payload["jobs"] = kept
        save_jobs(data_dir, payload)


def has_active_job(data_dir: Path, assignment_id: str | None = None, submission_id: str | None = None) -> bool:
    for job in load_jobs(data_dir).get("jobs", {}).values():
        if job.get("status") not in {"queued", "running"}:
            continue
        if assignment_id and job.get("assignmentId") == assignment_id:
            return True
        if submission_id and job.get("submissionId") == submission_id:
            return True
    return False


def delete_job(data_dir: Path, job_id: str) -> str:
    with JOB_LOCK:
        payload = load_jobs(data_dir)
        job = payload.get("jobs", {}).get(job_id)
        if not job:
            raise tool.ToolError("找不到这条后台任务记录，可能已经删除。")
        if job.get("status") in {"queued", "running"}:
            raise tool.ToolError("后台任务仍在运行，不能删除。")
        del payload["jobs"][job_id]
        save_jobs(data_dir, payload)
    student = job.get("student") or "未知学生"
    assignment = job.get("assignmentTitle") or job.get("assignmentId") or "未知作业"
    return f"已删除 {student} / {assignment} 的后台任务记录。"


def delete_submission(data_dir: Path, submission_id: str) -> str:
    with STATE_LOCK:
        return _delete_submission(data_dir, submission_id)


def _delete_submission(data_dir: Path, submission_id: str) -> str:
    state = tool.load_state(data_dir)
    if submission_id not in state["submissions"]:
        raise tool.ToolError("找不到这次提交，可能已经删除。")
    if has_active_job(data_dir, submission_id=submission_id):
        raise tool.ToolError("这次提交仍有后台评分任务，请等评分结束后再删除。")
    previous_state = json.loads(json.dumps(state, ensure_ascii=False))
    submission = state["submissions"][submission_id]
    assignment = state["assignments"].get(submission.get("assignment_id"), {})
    student = submission.get("student")

    if assignment:
        assignment["submissions"] = [sid for sid in assignment.get("submissions", []) if sid != submission_id]
    if student in state["students"]:
        state["students"][student]["submissions"] = [
            sid for sid in state["students"][student].get("submissions", []) if sid != submission_id
        ]
        if not state["students"][student]["submissions"]:
            del state["students"][student]
    del state["submissions"][submission_id]
    tool.save_state(data_dir, state)
    prune_jobs(data_dir, submission_id=submission_id)
    tool.push_undo(
        data_dir,
        previous_state,
        [],
        f"删除提交：{student} / {assignment.get('title', submission.get('assignment_id'))} / v{submission.get('version_no')}",
    )
    return f"已删除 {student} 的《{assignment.get('title', submission.get('assignment_id'))}》v{submission.get('version_no')}。"


def delete_assignment(data_dir: Path, assignment_id: str) -> str:
    with STATE_LOCK:
        return _delete_assignment(data_dir, assignment_id)


def _delete_assignment(data_dir: Path, assignment_id: str) -> str:
    state = tool.load_state(data_dir)
    if assignment_id not in state["assignments"]:
        raise tool.ToolError("找不到这次作业，可能已经删除。")
    if has_active_job(data_dir, assignment_id=assignment_id):
        raise tool.ToolError("这次作业仍有后台评分任务，请等评分结束后再删除。")
    previous_state = json.loads(json.dumps(state, ensure_ascii=False))
    assignment = state["assignments"][assignment_id]
    sub_ids = set(assignment.get("submissions", []))
    for sid, submission in list(state["submissions"].items()):
        if sid in sub_ids or submission.get("assignment_id") == assignment_id:
            student = submission.get("student")
            if student in state["students"]:
                state["students"][student]["submissions"] = [
                    item for item in state["students"][student].get("submissions", []) if item != sid
                ]
                if not state["students"][student]["submissions"]:
                    del state["students"][student]
            del state["submissions"][sid]
    del state["assignments"][assignment_id]
    tool.save_state(data_dir, state)
    prune_jobs(data_dir, assignment_id=assignment_id)
    tool.push_undo(data_dir, previous_state, [], f"删除作业：{assignment.get('title')}")
    return f"已删除作业《{assignment.get('title')}》及其提交记录。"


def update_assignment(data_dir: Path, body: dict, args: SimpleNamespace) -> tuple[str, dict]:
    assignment_id = body.get("id", "").strip()
    title = body.get("title", "").strip()
    topic = body.get("topic", "")
    writing_type = body.get("writingType") or "auto"
    if not assignment_id:
        raise tool.ToolError("缺少作业 ID。")
    if not title or not topic.strip():
        raise tool.ToolError("请填写作业标题和题目。")
    if has_active_job(data_dir, assignment_id=assignment_id):
        raise tool.ToolError("这次作业仍有后台评分任务，请等任务结束后再修改。")

    state = tool.load_state(data_dir)
    if assignment_id not in state["assignments"]:
        raise tool.ToolError("找不到这次作业，可能已经删除。")
    previous_state = json.loads(json.dumps(state, ensure_ascii=False))
    assignment = state["assignments"][assignment_id]
    model = args.model or tool.get_config_value("DEEPSEEK_MODEL", tool.DEFAULT_MODEL)
    updated_at = tool.now_iso()
    assignment.update(
        {
            "title": title,
            "topic": topic,
            "writing_type_hint": writing_type,
            "model": model,
            "updated_at": updated_at,
            "reanalyzed_at": updated_at,
        }
    )
    topic_path = Path(assignment.get("topic_path") or data_dir / "assignments" / assignment_id / "topic.md")
    report_path = Path(
        assignment.get("analysis_report_path")
        or tool.script_dir() / "reports" / "assignments" / assignment_id / "assignment_analysis.md"
    )
    tool.write_text(topic_path, f"# {title}\n\n{topic}\n")
    assignment["topic_path"] = str(topic_path.resolve())
    assignment["analysis_report_path"] = str(report_path.resolve())
    tool.save_state(data_dir, state)

    reanalysis_error = ""
    try:
        if args.no_ai:
            analysis = {
                "assignment_type": "未调用 AI",
                "core_task": "已保存修改；可关闭离线选项后重新审题。",
            }
        else:
            raw = tool.call_deepseek(tool.assignment_messages(title, topic, writing_type), args, json_mode=True)
            analysis = tool.parse_ai_json(raw)
        assignment["analysis"] = analysis
        assignment.pop("reanalyze_error", None)
    except Exception as exc:  # noqa: BLE001 - save the edited topic even when AI reanalysis fails.
        reanalysis_error = str(exc)
        previous_analysis = assignment.get("analysis") if isinstance(assignment.get("analysis"), dict) else {}
        analysis = dict(previous_analysis)
        analysis["reanalyze_error"] = reanalysis_error
        analysis.setdefault("assignment_type", "审题暂未更新")
        analysis["core_task"] = "作业标题、题目与文体提示已保存，但自动重新审题失败。"
        assignment["analysis"] = analysis
        assignment["reanalyze_error"] = reanalysis_error

    tool.write_text(report_path, tool.format_assignment_report(assignment))
    tool.save_state(data_dir, state)
    tool.push_undo(data_dir, previous_state, [], f"修改作业：{title}")
    sub_count = len([sid for sid in assignment.get("submissions", []) if sid in state["submissions"]])
    if reanalysis_error:
        return f"已保存《{title}》的题目；自动重新审题失败：{reanalysis_error}", {
            "assignment": assignment,
            "submissionCount": sub_count,
            "reanalyzed": False,
        }
    return f"已更新《{title}》并重新生成审题报告。", {
        "assignment": assignment,
        "submissionCount": sub_count,
        "reanalyzed": True,
    }


def summarize_state(data_dir: Path, read_only: bool = False) -> dict:
    return build_state_payload(data_dir, read_only, list_jobs(data_dir))

def make_args(data_dir: Path, body: dict, **extra):
    return SimpleNamespace(
        data_dir=str(data_dir),
        api_key=body.get("apiKey") or None,
        model=body.get("model") or tool.get_config_value("DEEPSEEK_MODEL", tool.DEFAULT_MODEL),
        api_base=body.get("apiBase") or tool.get_config_value("DEEPSEEK_API_BASE", tool.DEFAULT_API_BASE),
        temperature=float(body.get("temperature", 0.25)),
        timeout=int(body.get("timeout", 120)),
        no_ai=bool(body.get("noAi", False)),
        **extra,
    )


class EssayHandler(BaseHTTPRequestHandler):
    data_dir = tool.default_data_dir()
    read_only = False

    def log_message(self, fmt, *args):
        return

    def send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/state":
                self.send_json({"ok": True, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/report":
                query = parse_qs(parsed.query)
                path = safe_report_path(query.get("path", [""])[0])
                self.send_json(
                    {
                        "ok": True,
                        "path": str(path),
                        "name": path.name,
                        "kind": path.suffix.lower().lstrip("."),
                        "content": path.read_text(encoding="utf-8"),
                    }
                )
                return
            if parsed.path == "/api/export/assignment-pdf":
                query = parse_qs(parsed.query)
                filename, pdf_bytes = assignment_export_pdf(self.data_dir, query.get("id", [""])[0])
                send_pdf_response(self, filename, pdf_bytes)
                return
            if parsed.path == "/api/export/radar-pdf":
                query = parse_qs(parsed.query)
                filename, pdf_bytes = radar_export_pdf(self.data_dir, query.get("draft", ["final"])[0])
                send_pdf_response(self, filename, pdf_bytes)
                return
            if parsed.path == "/api/export/report-pdf":
                query = parse_qs(parsed.query)
                path = safe_report_path(query.get("path", [""])[0])
                filename, pdf_bytes = report_export_pdf(path)
                send_pdf_response(self, filename, pdf_bytes)
                return
            self.serve_static(parsed.path)
        except tool.ToolError as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:  # noqa: BLE001 - local UI should report errors to the page.
            self.send_error_json(str(exc), 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if self.read_only:
                self.send_error_json("访客模式为只读，不能执行新增、修改、删除、重判或配置操作。", 403)
                return
            body = read_json_body(self)
            if parsed.path == "/api/config":
                self.handle_config(body)
                return
            if parsed.path == "/api/assignments":
                args = make_args(
                    self.data_dir,
                    body,
                    title=body.get("title", "").strip(),
                    topic=body.get("topic", ""),
                    topic_file=None,
                    writing_type=body.get("writingType") or "auto",
                    id=None,
                )
                if not args.title or not args.topic.strip():
                    raise tool.ToolError("请填写作业标题和题目。")
                with STATE_LOCK:
                    message = run_silently(tool.command_assignment_new, args)
                self.send_json({"ok": True, "message": message, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/assignment-update":
                args = make_args(self.data_dir, body)
                with STATE_LOCK:
                    message, meta = update_assignment(self.data_dir, body, args)
                self.send_json(
                    {
                        "ok": True,
                        "message": message,
                        "assignmentId": body.get("id", ""),
                        "submissionCount": meta.get("submissionCount", 0),
                        "reanalyzed": meta.get("reanalyzed", False),
                        "state": summarize_state(self.data_dir, self.read_only),
                    }
                )
                return
            if parsed.path == "/api/assignment-summary":
                args = make_args(self.data_dir, body)
                with STATE_LOCK:
                    message, report_path, created = get_or_create_assignment_summary(self.data_dir, body, args)
                self.send_json(
                    {
                        "ok": True,
                        "message": message,
                        "path": report_path,
                        "created": created,
                        "state": summarize_state(self.data_dir, self.read_only),
                    }
                )
                return
            if parsed.path == "/api/submissions":
                manual = body.get("manualScore")
                manual_score = None if manual in (None, "") else float(manual)
                if manual_score is not None and not (0 <= manual_score <= 60):
                    raise tool.ToolError("人工分数必须在 0 到 60 之间。")
                assignment_query = body.get("assignment", "")
                student = tool.clean_student(body.get("student", ""))
                content = body.get("content", "")
                if not assignment_query or not student or not content.strip():
                    raise tool.ToolError("请选择作业，并填写学生缩写和作文正文。")
                assignment = tool.resolve_assignment(tool.load_state(self.data_dir), assignment_query)
                args = make_args(
                    self.data_dir,
                    body,
                    assignment=assignment.get("id"),
                    student=student,
                    content=content,
                    content_file=None,
                    revision=bool(body.get("revision", False)),
                    initial=bool(body.get("initial", False)),
                    manual_score=manual_score,
                )
                job = start_submission_job(self.data_dir, args, assignment, student)
                self.send_json({"ok": True, "message": "已开始后台评分。评分完成前不会显示报告。", "job": job, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/rejudge":
                state = tool.load_state(self.data_dir)
                submission = tool.resolve_submission(state, body.get("id", ""))
                if has_active_job(self.data_dir, submission_id=submission.get("id")):
                    raise tool.ToolError("这次提交已有后台任务，请等任务结束后再重判。")
                assignment = state["assignments"].get(submission.get("assignment_id"))
                if not assignment:
                    raise tool.ToolError("这次提交所属作业已不存在，无法重判。")
                args = make_args(self.data_dir, body, submission=submission.get("id"))
                job = start_rejudge_job(self.data_dir, args, submission, assignment)
                self.send_json({"ok": True, "message": "已开始后台重判。完成前不会显示旧报告。", "job": job, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/rejudge-assignment":
                state = tool.load_state(self.data_dir)
                assignment = tool.resolve_assignment(state, body.get("id", ""))
                if has_active_job(self.data_dir, assignment_id=assignment.get("id")):
                    raise tool.ToolError("这次作业已有后台任务，请等任务结束后再批量重判。")
                submissions = [
                    state["submissions"][sid]
                    for sid in assignment.get("submissions", [])
                    if sid in state["submissions"]
                ]
                if not submissions:
                    raise tool.ToolError("这次作业还没有可重判的学生提交。")
                jobs = []
                for submission in submissions:
                    args = make_args(self.data_dir, body, submission=submission.get("id"))
                    jobs.append(start_rejudge_job(self.data_dir, args, submission, assignment))
                self.send_json({"ok": True, "message": f"已开始后台重判 {len(jobs)} 篇提交。完成前不会显示旧报告。", "jobs": jobs, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/curves":
                students = [s.strip() for s in body.get("students", []) if s.strip()]
                args = SimpleNamespace(data_dir=str(self.data_dir), student=students or None, out_dir=None)
                with STATE_LOCK:
                    message = run_silently(tool.command_curves, args)
                self.send_json({"ok": True, "message": message, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/style-report":
                students = [s.strip() for s in body.get("students", []) if s.strip()]
                args = make_args(self.data_dir, {**body, "noAi": True}, student=students or None, out_dir=None)
                with STATE_LOCK:
                    message = run_silently(tool.command_style_report, args)
                state = summarize_state(self.data_dir, self.read_only)
                report_path = ""
                pdf_path = ""
                for item in state.get("generatedReports", []):
                    if item.get("type") == "style_report" and item.get("path"):
                        report_path = item.get("path")
                        report = Path(report_path)
                        pdf = materialize_report_pdf(report)
                        attach_generated_report_pdf(self.data_dir, report, pdf)
                        pdf_path = str(pdf.resolve())
                        state = summarize_state(self.data_dir, self.read_only)
                        break
                self.send_json({"ok": True, "message": message, "path": report_path, "pdfPath": pdf_path, "state": state})
                return
            if parsed.path == "/api/undo":
                args = SimpleNamespace(data_dir=str(self.data_dir))
                with STATE_LOCK:
                    message = run_silently(tool.command_undo, args)
                self.send_json({"ok": True, "message": message, "state": summarize_state(self.data_dir, self.read_only)})
                return
            if parsed.path == "/api/delete":
                kind = body.get("kind")
                if kind == "submission":
                    message = delete_submission(self.data_dir, body.get("id", ""))
                elif kind == "assignment":
                    message = delete_assignment(self.data_dir, body.get("id", ""))
                elif kind == "job":
                    message = delete_job(self.data_dir, body.get("id", ""))
                else:
                    raise tool.ToolError("未知删除类型。")
                self.send_json({"ok": True, "message": message, "state": summarize_state(self.data_dir, self.read_only)})
                return
            self.send_error_json("未知 API。", 404)
        except tool.ToolError as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(str(exc), 500)

    def handle_config(self, body: dict) -> None:
        existing = tool.load_dotenv()
        api_key = body.get("apiKey") or existing.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise tool.ToolError("请填写 DeepSeek API key。")
        model = body.get("model") or existing.get("DEEPSEEK_MODEL") or tool.DEFAULT_MODEL
        api_base = body.get("apiBase") or existing.get("DEEPSEEK_API_BASE") or tool.DEFAULT_API_BASE
        content = "\n".join(
            [
                "# Local secret file. Do not commit.",
                f"DEEPSEEK_API_KEY={api_key}",
                f"DEEPSEEK_MODEL={model}",
                f"DEEPSEEK_API_BASE={api_base}",
                "",
            ]
        )
        tool.write_text(ROOT / ".env", content)
        self.send_json({"ok": True, "message": "配置已保存。", "state": summarize_state(self.data_dir, self.read_only)})

    def serve_static(self, raw_path: str) -> None:
        path = "index.html" if raw_path in ("", "/") else raw_path.lstrip("/")
        target = (STATIC_DIR / path).resolve()
        if not is_safe_path(target) or STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            self.send_error(404)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript"} else mime)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="启动作文 AI 工具网页 UI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="端口，默认管理模式 8765、访客模式 8766；占用时会自动顺延")
    parser.add_argument("--data-dir", default=str(tool.default_data_dir()), help="数据目录")
    parser.add_argument("--guest", action="store_true", help="启动访客只读模式：拒绝所有 POST 修改操作")
    args = parser.parse_args()
    if args.guest and args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("访客模式只能绑定 127.0.0.1、localhost 或 ::1，不能暴露到局域网/公网。")
    requested_port = args.port if args.port is not None else (8766 if args.guest else 8765)
    port = find_free_port(args.host, requested_port)
    EssayHandler.data_dir = Path(args.data_dir).resolve()
    EssayHandler.read_only = bool(args.guest)
    if not args.guest:
        tool.ensure_dirs(EssayHandler.data_dir)
        mark_interrupted_jobs(EssayHandler.data_dir)
    server = ThreadingHTTPServer((args.host, port), EssayHandler)
    mode = "访客只读" if args.guest else "管理"
    log(f"作文 AI 网页 UI 已启动（{mode}）：http://{args.host}:{port}")
    log("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("已停止。")
    except Exception:
        log(traceback.format_exc())
        raise
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
