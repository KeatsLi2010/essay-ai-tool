"""PDF/HTML export helpers for the web UI."""

from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote

import essay_tool as tool
from web_metrics import RADAR_DIMENSIONS, build_radar
from web_summaries import assignment_summary_signature, current_assignment_summary

ROOT = Path(__file__).resolve().parent


def html_escape(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def markdown_to_export_html(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    out: list[str] = []
    table: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def render_inline(text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        rows = [row.strip().strip("|").split("|") for row in table if row.strip()]
        rows = [[cell.strip() for cell in row] for row in rows]
        if len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1]):
            header, body = rows[0], rows[2:]
            out.append("<table><thead><tr>" + "".join(f"<th>{render_inline(c)}</th>" for c in header) + "</tr></thead><tbody>")
            for row in body:
                out.append("<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table>")
        else:
            out.append("<table><tbody>")
            for row in rows:
                out.append("<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table>")
        table = []

    index = 0
    while index < len(lines):
        raw = lines[index]
        if raw.strip() == "<!-- raw-html:start -->":
            close_list()
            flush_table()
            raw_html: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "<!-- raw-html:end -->":
                raw_html.append(lines[index])
                index += 1
            out.append("\n".join(raw_html))
            index += 1
            continue
        line = html_escape(raw).strip()
        if line.startswith("<!--"):
            index += 1
            continue
        if line.startswith("|") and line.endswith("|"):
            close_list()
            table.append(line)
            index += 1
            continue
        flush_table()
        if not line:
            close_list()
            index += 1
            continue
        if line.startswith("# "):
            close_list()
            out.append(f"<h1>{render_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{render_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            close_list()
            out.append(f"<h3>{render_inline(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{render_inline(line[2:])}</li>")
        else:
            close_list()
            out.append(f"<p>{render_inline(line)}</p>")
        index += 1
    flush_table()
    close_list()
    return "\n".join(out)


def export_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html_escape(title)}</title>
<style>
@page {{ size: A4; margin: 0; }}
html, body {{ margin: 0; }}
body {{ box-sizing: border-box; padding: 12mm; font-family: "Microsoft YaHei", "SimSun", sans-serif; color: #1f2b26; line-height: 1.65; font-size: 12px; }}
h1 {{ font-size: 24px; margin: 0 0 18px; page-break-after: avoid; }}
h2 {{ font-size: 18px; margin: 22px 0 10px; padding-bottom: 4px; border-bottom: 1px solid #dbe2dc; page-break-after: avoid; }}
h3 {{ font-size: 14px; margin: 16px 0 8px; page-break-after: avoid; }}
p {{ margin: 6px 0; }}
code {{ background: #f2f5f3; padding: 1px 4px; border-radius: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px; page-break-inside: auto; }}
th, td {{ border: 1px solid #dbe2dc; padding: 6px 7px; vertical-align: top; word-break: break-word; }}
th {{ background: #eef6f2; font-weight: 700; }}
tr {{ page-break-inside: avoid; }}
.style-chart {{ margin: 8px 0 14px; border: 1px solid #dbe2dc; border-radius: 8px; background: #fbfcfa; page-break-inside: avoid; }}
.style-chart svg {{ display: block; width: 100%; height: auto; }}
.section {{ page-break-before: always; }}
.section:first-child {{ page-break-before: auto; }}
.muted {{ color: #66736d; }}
.radar-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
.radar-card {{ border: 1px solid #dbe2dc; border-radius: 8px; padding: 10px; page-break-inside: avoid; }}
.radar-card h3 {{ margin-top: 0; }}
.radar-svg {{ width: 100%; max-width: 260px; display: block; margin: 0 auto; }}
.radar-data {{ font-size: 11px; columns: 2; margin-top: 6px; }}
.radar-ring {{ fill: none; stroke: #dbe2dc; stroke-width: 1; }}
.radar-axis {{ stroke: #e3e9e5; stroke-width: 1; }}
.radar-area {{ fill: rgba(19, 115, 91, .18); }}
.radar-line {{ fill: none; stroke: #13735b; stroke-width: 2.4; }}
.radar-dot {{ fill: #c25545; stroke: #fff; stroke-width: 1.4; }}
.radar-label {{ fill: #3d4944; font-size: 10px; font-weight: 700; }}
.radar-center {{ fill: #13735b; font-size: 18px; font-weight: 800; }}
</style>
</head>
<body>{body}</body>
</html>"""


def find_browser_executable() -> str | None:
    for name in ["msedge", "msedge.exe", "chrome", "chrome.exe", "chromium", "chromium.exe"]:
        found = shutil.which(name)
        if found:
            return found
    for raw in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]:
        if Path(raw).exists():
            return raw
    return None


def html_to_pdf_bytes(page_html: str) -> bytes:
    browser = find_browser_executable()
    if not browser:
        raise tool.ToolError("找不到 Edge/Chrome，无法导出 PDF。")
    tmp_root = ROOT / ".pdf-tmp"
    tmp_root.mkdir(exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="essay_pdf_", dir=str(tmp_root)))
    html_path = tmp_dir / "export.html"
    pdf_path = tmp_dir / "export.pdf"
    profile_path = tmp_dir / "profile"
    html_path.write_text(page_html, encoding="utf-8", newline="\n")
    try:
        common_args = [
            browser,
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_path}",
        ]
        attempts = [
            ["--headless=new", "--no-pdf-header-footer"],
            ["--headless=new", "--print-to-pdf-no-header"],
            ["--headless", "--no-pdf-header-footer"],
            ["--headless", "--print-to-pdf-no-header"],
            ["--headless=new"],
            ["--headless"],
        ]
        last_error: subprocess.CalledProcessError | None = None
        for extra_args in attempts:
            if pdf_path.exists():
                pdf_path.unlink()
            try:
                subprocess.run(
                    [
                        *common_args,
                        *extra_args,
                        f"--print-to-pdf={pdf_path}",
                        str(html_path),
                    ],
                    cwd=str(tmp_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                last_error = exc
                continue
            if pdf_path.exists() and pdf_path.stat().st_size >= 100:
                return pdf_path.read_bytes()
        if last_error:
            raise last_error
        raise tool.ToolError("PDF 生成失败，浏览器没有输出有效文件。")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def send_pdf_response(handler: BaseHTTPRequestHandler, filename: str, pdf_bytes: bytes) -> None:
    raw_name = re.sub(r'[\\/:*?"<>|]+', "_", filename).strip() or "export.pdf"
    if not raw_name.lower().endswith(".pdf"):
        raw_name += ".pdf"
    payload = pdf_bytes
    handler.send_response(200)
    handler.send_header("Content-Type", "application/pdf")
    fallback = raw_name.encode("ascii", "ignore").decode().strip(" ._") or "export.pdf"
    handler.send_header("Content-Disposition", f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(raw_name)}')
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def assignment_export_pdf(data_dir: Path, assignment_id: str) -> tuple[str, bytes]:
    state = tool.load_state(data_dir)
    assignment = tool.resolve_assignment(state, assignment_id)
    sections = [f'<section class="section"><h1>{html_escape(assignment.get("title"))} 作业导出</h1></section>']
    report_paths: list[tuple[str, str | None]] = [
        ("审题报告", assignment.get("analysis_report_path")),
    ]
    submissions = [
        state["submissions"][sid]
        for sid in assignment.get("submissions", [])
        if sid in state["submissions"]
    ]
    for sub in sorted(submissions, key=lambda x: (x.get("student") or "", x.get("version_no") or 0, x.get("created_at") or "")):
        report_paths.append((f"{sub.get('student')} v{sub.get('version_no')} 评判", sub.get("report_path")))
    signature = assignment_summary_signature(assignment, submissions) if submissions else ""
    summary = current_assignment_summary(assignment, signature) if signature else None
    report_paths.append(("作业总结", summary.get("path") if summary else None))
    for title, raw_path in report_paths:
        sections.append(f'<section class="section"><h1>{html_escape(title)}</h1>')
        if raw_path and Path(raw_path).exists():
            sections.append(markdown_to_export_html(Path(raw_path).read_text(encoding="utf-8")))
        else:
            sections.append('<p class="muted">暂无可导出的报告。请先在管理端生成对应报告。</p>')
        sections.append("</section>")
    page = export_page(f"{assignment.get('title')} 作业导出", "\n".join(sections))
    return f"{assignment.get('title')}_作业导出.pdf", html_to_pdf_bytes(page)


def report_export_pdf(report_path: Path) -> tuple[str, bytes]:
    if not report_path.exists() or not report_path.is_file():
        raise tool.ToolError("报告不存在，无法导出 PDF。")
    if report_path.suffix.lower() == ".pdf":
        return report_path.name, report_path.read_bytes()
    title = report_path.stem
    content = report_path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if match:
        title = match.group(1).strip()
    page = export_page(title, markdown_to_export_html(content))
    filename = f"{title}.pdf"
    return filename, html_to_pdf_bytes(page)


def average_radar_from_rows(rows: list[dict]) -> dict:
    buckets = {key: [] for key, _, _ in RADAR_DIMENSIONS}
    for row in rows:
        radar = build_radar(row.get("analysis") or {})
        if not radar.get("available"):
            continue
        for item in radar.get("dimensions") or []:
            if isinstance(item.get("score"), (int, float)):
                buckets[item["key"]].append(float(item["score"]))
    dimensions = []
    for key, label, _ in RADAR_DIMENSIONS:
        values = buckets[key]
        dimensions.append({"key": key, "label": label, "score": round(sum(values) / len(values), 1) if values else None})
    scored = [item["score"] for item in dimensions if isinstance(item.get("score"), (int, float))]
    return {"available": len(scored) >= 4, "dimensions": dimensions, "average": round(sum(scored) / len(scored), 1) if scored else None}


def select_radar_rows(rows: list[dict], draft: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        key = f"{row.get('student')}::{row.get('assignment_id')}"
        current = grouped.get(key)
        version = int(row.get("version_no") or 0)
        current_version = int(current.get("version_no") or 0) if current else None
        newer = current is None or version > current_version or (version == current_version and str(row.get("created_at") or "") > str(current.get("created_at") or ""))
        older = current is None or version < current_version or (version == current_version and str(row.get("created_at") or "") < str(current.get("created_at") or ""))
        if (draft == "final" and newer) or (draft == "initial" and older):
            grouped[key] = row
    return list(grouped.values())


def radar_point(cx: float, cy: float, radius: float, index: int, total: int, value: float = 1.0) -> tuple[float, float]:
    angle = -math.pi / 2 + index * math.pi * 2 / total
    return cx + math.cos(angle) * radius * value, cy + math.sin(angle) * radius * value


def radar_svg(dimensions: list[dict], size: int = 240) -> str:
    count = len(dimensions) or len(RADAR_DIMENSIONS)
    cx = cy = size / 2
    radius = size * 0.3
    label_radius = size * 0.42
    safe = dimensions or [{"label": label, "score": 0} for _, label, _ in RADAR_DIMENSIONS]
    axes = [radar_point(cx, cy, radius, i, count, 1) for i in range(count)]
    polygon = [radar_point(cx, cy, radius, i, count, max(0, min(20, item.get("score") or 0)) / 20) for i, item in enumerate(safe)]
    scored = [item.get("score") for item in safe if isinstance(item.get("score"), (int, float))]
    center = round(sum(scored) / len(scored)) if scored else 0

    def pts(items):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in items)

    labels = []
    for i, item in enumerate(safe):
        x, y = radar_point(cx, cy, label_radius, i, count, 1)
        anchor = "middle" if abs(x - cx) < 8 else ("start" if x > cx else "end")
        labels.append(f'<text class="radar-label" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="middle">{html_escape(item.get("label"))}</text>')
    return f'''<svg class="radar-svg" viewBox="0 0 {size} {size}">
{''.join(f'<polygon class="radar-ring" points="{pts([radar_point(cx, cy, radius, i, count, ring) for i in range(count)])}"></polygon>' for ring in [0.25, 0.5, 0.75, 1])}
{''.join(f'<line class="radar-axis" x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}"></line>' for x, y in axes)}
<polygon class="radar-area" points="{pts(polygon)}"></polygon>
<polyline class="radar-line" points="{pts(polygon + [polygon[0]])}"></polyline>
{''.join(f'<circle class="radar-dot" cx="{x:.1f}" cy="{y:.1f}" r="3"></circle>' for x, y in polygon)}
<text class="radar-center" x="{cx}" y="{cy + 4}" text-anchor="middle">{center}</text>
{''.join(labels)}
</svg>'''


def radar_export_pdf(data_dir: Path, draft: str = "final") -> tuple[str, bytes]:
    state = tool.load_state(data_dir)
    all_subs = list(state["submissions"].values())
    students = sorted(state["students"].keys())
    draft = "initial" if draft == "initial" else "final"
    title = "初稿雷达图" if draft == "initial" else "终稿雷达图"
    sections = [f'<section class="section"><h1>学生总雷达图 - {title}</h1></section>']
    for current_draft, current_title in [(draft, title)]:
        cards = []
        for student in students:
            rows = select_radar_rows([s for s in all_subs if s.get("student") == student], current_draft)
            radar = average_radar_from_rows(rows)
            if not radar["available"]:
                continue
            data = "；".join(f'{d["label"]} {d["score"]}/20' for d in radar["dimensions"] if isinstance(d.get("score"), (int, float)))
            cards.append(f'<div class="radar-card"><h3>{html_escape(student)} <span class="muted">{len(rows)} 篇 · 均值 {radar["average"]}/20</span></h3>{radar_svg(radar["dimensions"])}<div class="radar-data">{html_escape(data)}</div></div>')
        sections.append(f'<section class="section"><h1>{current_title}</h1><div class="radar-grid">{"".join(cards) or "<p>暂无雷达数据。</p>"}</div></section>')
    filename = f"学生总雷达图_{title}.pdf"
    return filename, html_to_pdf_bytes(export_page(f"学生总雷达图 - {title}", "\n".join(sections)))
