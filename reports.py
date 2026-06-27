"""Markdown and SVG report formatting helpers."""

from __future__ import annotations

import re
import statistics
import html
from pathlib import Path
from typing import Any

from core import now_iso

def render_any(value: Any, level: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                title = item.get("title") or item.get("name") or item.get("point") or item.get("维度")
                if title:
                    lines.append(f"- **{title}**：{render_any({k: v for k, v in item.items() if k not in {'title', 'name', 'point', '维度'}}, level + 1)}")
                else:
                    lines.append(f"- {render_any(item, level + 1)}")
            else:
                lines.append(f"- {render_any(item, level + 1)}")
        return "\n".join(line for line in lines if line.strip())
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            lines.append(f"- **{key}**：{render_any(item, level + 1)}")
        return "\n".join(lines)
    return str(value)


REPORT_FIELD_LABELS = {
    "content_band": "内容档次",
    "expression_band": "表达档次",
    "development_band": "发展档次",
    "initial_total_band": "初定档位/分数",
    "hard_caps": "硬性上限",
    "penalties": "扣分项",
    "final_total_60": "最终 60 分",
    "final_band_reason": "最终定档理由",
}


def table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(v).replace("\n", "<br>").replace("|", "\\|") for v in values) + " |"


def short_cell(value: Any, limit: int = 80) -> str:
    text = render_any(value) if not isinstance(value, str) else value
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_thesis_options(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return render_any(value)
    lines = [
        table_row(["关键词", "角度", "主旨", "文体", "风险"]),
        table_row(["---", "---", "---", "---", "---"]),
    ]
    for item in value[:6]:
        if not isinstance(item, dict):
            lines.append(table_row(["", short_cell(item, 24), "", "", ""]))
            continue
        lines.append(
            table_row(
                [
                    short_cell(item.get("keyword") or item.get("关键词") or "", 8),
                    short_cell(item.get("angle") or item.get("角度") or "", 24),
                    short_cell(item.get("main_idea") or item.get("主旨") or "", 56),
                    short_cell(item.get("genre") or item.get("suitable_genre") or item.get("文体") or "", 16),
                    short_cell(item.get("risk") or item.get("风险") or "", 32),
                ]
            )
        )
    return "\n".join(lines)


def compact_list(value: Any, limit: int = 5) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return value[:limit]
    return [value]


def format_genre_candidates(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return render_any(value)
    lines = [
        table_row(["文体", "适配度", "理由"]),
        table_row(["---", "---", "---"]),
    ]
    for item in value[:4]:
        if not isinstance(item, dict):
            lines.append(table_row([short_cell(item, 16), "", ""]))
            continue
        lines.append(
            table_row(
                [
                    short_cell(item.get("genre") or item.get("文体") or "", 16),
                    short_cell(item.get("suitability") or item.get("适配度") or "", 10),
                    short_cell(item.get("reason") or item.get("理由") or "", 36),
                ]
            )
        )
    return "\n".join(lines)


def format_constraints(value: Any) -> str:
    if not isinstance(value, dict):
        return render_any(value)
    lines = [
        table_row(["类型", "限制"]),
        table_row(["---", "---"]),
    ]
    for key, label in (("explicit", "显性"), ("implicit", "隐性")):
        for item in compact_list(value.get(key), 5):
            lines.append(table_row([label, short_cell(item, 42)]))
    return "\n".join(lines) if len(lines) > 2 else render_any(value)


def format_best_thesis(value: Any) -> str:
    if not isinstance(value, dict):
        return render_any(value)
    return "\n".join(
        [
            table_row(["关键词", "角度/主旨", "推荐理由"]),
            table_row(["---", "---", "---"]),
            table_row(
                [
                    short_cell(value.get("keyword") or value.get("关键词") or "", 10),
                    short_cell(value.get("angle") or value.get("main_idea") or value.get("主旨") or "", 44),
                    short_cell(value.get("reason") or value.get("理由") or "", 56),
                ]
            ),
        ]
    )


def format_assignment_value(key: str, value: Any) -> str:
    if key == "genre_candidates":
        return format_genre_candidates(value)
    if key == "constraints":
        return format_constraints(value)
    if key == "thesis_options":
        return format_thesis_options(value)
    if key == "best_thesis":
        return format_best_thesis(value)
    return render_any(value)


def format_assignment_report(assignment: dict[str, Any]) -> str:
    analysis = assignment.get("analysis", {})
    lines = [
        f"# 《{assignment.get('title')}》审题分析",
        "",
        f"- 作业 ID：`{assignment.get('id')}`",
        f"- 创建时间：{assignment.get('created_at')}",
        f"- 模型：`{assignment.get('model')}`",
        "",
        "## 题目",
        "",
        assignment.get("topic", "").strip(),
        "",
        "## AI 审题",
        "",
    ]
    if "raw" in analysis:
        lines.append(analysis["raw"])
    else:
        ordered = [
            ("assignment_type", "任务类型"),
            ("genre_candidates", "可能文体"),
            ("core_task", "核心任务"),
            ("constraints", "题目限制"),
            ("thesis_options", "可能立意"),
            ("best_thesis", "推荐主旨"),
            ("scoring_focus", "评分关注"),
            ("pitfalls", "常见风险"),
            ("teaching_notes", "教学提醒"),
            ("student_brief", "学生提示"),
        ]
        for key, title in ordered:
            if key in analysis and analysis[key] not in (None, "", [], {}):
                rendered = format_assignment_value(key, analysis[key])
                lines.extend([f"### {title}", "", rendered, ""])
        rest = {k: v for k, v in analysis.items() if k not in {key for key, _ in ordered}}
        if rest:
            lines.extend(["### 其他信息", "", render_any(rest), ""])
    return "\n".join(lines).rstrip() + "\n"


def _extract_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _normalize_score_60(value: Any) -> float | None:
    score = _extract_number(value)
    if score is None:
        return None
    if 60 < score <= 100:
        score = round(score / 100 * 60)
    if 0 <= score <= 60:
        return float(score)
    return None


def extract_score(analysis: dict[str, Any]) -> float | None:
    strict = analysis.get("strict_gaokao_banding")
    if isinstance(strict, dict):
        score = _normalize_score_60(strict.get("final_total_60"))
        if score is not None:
            return score
    gaokao_ref = analysis.get("gaokao_60_reference")
    if isinstance(gaokao_ref, dict):
        score = _normalize_score_60(gaokao_ref.get("total_60"))
        if score is not None:
            return score
    score = _normalize_score_60(analysis.get("score"))
    if score is not None:
        return score
    raw = analysis.get("raw")
    if isinstance(raw, str):
        match_60 = re.search(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*/\s*60", raw)
        if match_60:
            return _normalize_score_60(match_60.group(1))
        match_100 = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*/\s*100", raw)
        if match_100:
            return _normalize_score_60(match_100.group(1))
        match = re.search(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*分", raw)
        if match:
            return _normalize_score_60(match.group(1))
    return None


def format_breakdown(breakdown: Any) -> str:
    if not isinstance(breakdown, dict) or not breakdown:
        return ""
    lines = [table_row(["维度", "分数 / 说明"]), table_row(["---", "---"])]
    for key, value in breakdown.items():
        lines.append(table_row([key, render_any(value)]))
    return "\n".join(lines)


def format_strict_banding(value: Any) -> str:
    if not isinstance(value, dict):
        return render_any(value)
    ordered = [
        "content_band",
        "expression_band",
        "development_band",
        "initial_total_band",
        "hard_caps",
        "penalties",
        "final_total_60",
        "final_band_reason",
    ]
    lines = []
    for key in ordered:
        item = value.get(key)
        if item in (None, "", [], {}):
            continue
        lines.append(f"- **{REPORT_FIELD_LABELS.get(key, key)}**：{render_any(item)}")
    for key, item in value.items():
        if key in ordered or key in {"consistency_check", "converted_score_100"} or item in (None, "", [], {}):
            continue
        lines.append(f"- **{REPORT_FIELD_LABELS.get(key, key)}**：{render_any(item)}")
    return "\n".join(lines)


def format_revision_analysis(value: Any) -> str:
    if not isinstance(value, dict):
        return render_any(value)
    lines: list[str] = []
    for key in ("overall", "score_change_reason", "previous_review_response"):
        item = value.get(key)
        if item not in (None, "", [], {}):
            lines.append(f"- **{key}**：{render_any(item)}")
    changes = value.get("changes")
    if isinstance(changes, list) and changes:
        if lines:
            lines.append("")
        for change in changes:
            if not isinstance(change, dict):
                lines.append(f"- {render_any(change)}")
                continue
            for key in ("change_type", "review_basis", "before", "after", "what_changed", "effect", "evidence", "remaining_issue"):
                item = change.get(key)
                if item not in (None, "", [], {}):
                    lines.append(f"- **{key}**：{render_any(item)}")
    tail: list[str] = []
    for key in ("new_problems", "keep_next_time"):
        item = value.get(key)
        if item not in (None, "", [], {}):
            tail.append(f"- **{key}**：{render_any(item)}")
    if tail:
        if lines:
            lines.append("")
        lines.extend(tail)
    return "\n".join(lines)


def format_submission_report(submission: dict[str, Any], assignment: dict[str, Any]) -> str:
    analysis = submission.get("analysis", {})
    title = assignment.get("title", submission.get("assignment_id"))
    score = submission.get("score")
    metadata = [
        f"# {submission.get('student')}《{title}》第 {submission.get('version_no')} 次提交评判",
        "",
        f"- 作业 ID：`{submission.get('assignment_id')}`",
        f"- 提交 ID：`{submission.get('id')}`",
        f"- 学生：{submission.get('student')}",
        f"- 是否修改稿：{'是' if submission.get('is_revision') else '否'}",
        f"- 创建时间：{submission.get('created_at')}",
        f"- 模型：`{submission.get('model')}`",
    ]
    if submission.get("rejudged_at"):
        metadata.extend(
            [
                f"- 重判时间：{submission.get('rejudged_at')}",
                f"- 重判次数：{submission.get('rejudge_count')}",
            ]
        )
    lines = [
        *metadata,
        "",
        "## 原文",
        "",
        submission.get("content", "").strip(),
        "",
        "## 评分",
        "",
        f"**总分：{score if score is not None else '未提取'} / 60**",
        "",
    ]
    if "raw" in analysis:
        lines.extend(["## AI 评判", "", analysis["raw"], ""])
        return "\n".join(lines).rstrip() + "\n"
    breakdown = format_breakdown(analysis.get("score_breakdown"))
    if breakdown:
        lines.extend([breakdown, ""])
    ordered = [
        ("detected_task_type", "任务类型判断"),
        ("expected_genre", "题目期待文体"),
        ("detected_genre", "实际文体"),
        ("genre_evidence", "文体判断依据"),
        ("genre_fit", "文体匹配"),
        ("genre_specific_assessment", "文体专项评价"),
        ("genre_score_cap", "文体分数上限提示"),
        ("grade_band", "档次判断"),
        ("strict_gaokao_banding", "严格定档依据"),
        ("overall_comment", "总评"),
        ("gaokao_60_reference", "60 分制参考"),
        ("radar_scores", "八方面雷达数据"),
        ("strengths", "亮点分析"),
        ("issues", "问题诊断"),
        ("revision_analysis", "修改分析"),
        ("language_rhythm", "语言与韵律"),
        ("revision_plan", "修改建议"),
        ("score_raise_path", "提分路径"),
        ("style_observation", "风格观察"),
        ("teacher_note", "教师备注"),
    ]
    for key, heading in ordered:
        value = analysis.get(key)
        if value in (None, "", [], {}):
            continue
        if key == "strict_gaokao_banding":
            rendered = format_strict_banding(value)
        elif key == "revision_analysis":
            rendered = format_revision_analysis(value)
        else:
            rendered = render_any(value)
        lines.extend([f"## {heading}", "", rendered, ""])
    rest = {k: v for k, v in analysis.items() if k not in {key for key, _ in ordered} and k not in {"score", "score_breakdown"}}
    if rest:
        lines.extend(["## 其他信息", "", render_any(rest), ""])
    return "\n".join(lines).rstrip() + "\n"


def format_curve_report(grouped: dict[str, list[dict[str, Any]]], svg_path: Path) -> str:
    lines = [
        "# 学生历次作文得分分析",
        "",
        f"生成时间：{now_iso()}",
        "",
        f"![得分曲线]({svg_path.resolve()})",
        "",
    ]
    for student, items in grouped.items():
        scores = [float(item["score"]) for item in items]
        delta = scores[-1] - scores[0] if len(scores) >= 2 else 0
        lines.extend(
            [
                f"## {student}",
                "",
                f"- 提交篇数：{len(items)}",
                f"- 平均分：{statistics.mean(scores):.1f}",
                f"- 最高分：{max(scores):.1f}",
                f"- 最低分：{min(scores):.1f}",
                f"- 首末变化：{delta:+.1f}",
                "",
                table_row(["序号", "作业", "版本", "分数", "时间", "提交 ID"]),
                table_row(["---", "---", "---", "---:", "---", "---"]),
            ]
        )
        for i, item in enumerate(items, start=1):
            lines.append(
                table_row(
                    [
                        i,
                        item["assignment"],
                        item.get("version_no", ""),
                        f'{item["score"]:.1f}',
                        item.get("created_at", ""),
                        f"`{item.get('submission_id')}`",
                    ]
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _style_text(history: dict[str, Any]) -> str:
    return str(history.get("excerpt_or_full_text") or "")


def _style_top_chars(histories: list[dict[str, Any]], limit: int = 5) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for history in histories:
        for char in re.findall(r"[\u4e00-\u9fff]", _style_text(history)):
            counts[char] = counts.get(char, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


_STYLE_PUNCTUATION_MARKS = [
    ("，", ["，", ","]),
    ("。", ["。"]),
    ("、", ["、"]),
    ("；", ["；", ";"]),
    ("：", ["：", ":"]),
    ("！", ["！", "!"]),
    ("？", ["？", "?"]),
    ("引号", ["“", "”", '"']),
    ("括号", ["（", "）", "(", ")"]),
    ("破折号", ["——"]),
    ("省略号", ["……"]),
]


def _style_char_total(history: dict[str, Any]) -> int:
    metrics = history.get("metrics") or {}
    value = metrics.get("char_count")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return max(1, len(re.sub(r"\s+", "", _style_text(history))))


def _count_punctuation(text: str, tokens: list[str]) -> int:
    return sum(text.count(token) for token in tokens)


def _style_top_punctuation(histories: list[dict[str, Any]], limit: int = 5) -> list[tuple[str, int, list[str]]]:
    totals: list[tuple[str, int, list[str]]] = []
    for label, tokens in _STYLE_PUNCTUATION_MARKS:
        count = sum(_count_punctuation(_style_text(history), tokens) for history in histories)
        if count:
            totals.append((label, count, tokens))
    return sorted(totals, key=lambda item: (-item[1], item[0]))[:limit]


def _style_line_chart(histories: list[dict[str, Any]], metric_key: str, title: str, unit: str = "") -> str:
    values: list[float] = []
    labels: list[str] = []
    for index, history in enumerate(histories):
        metrics = history.get("metrics") or {}
        value = metrics.get(metric_key)
        if isinstance(value, (int, float)):
            values.append(float(value))
            labels.append(f"第{index + 1}篇")
    if not values:
        return '<p class="muted">暂无可绘制数据。</p>'
    return _style_multi_line_chart([{"label": title, "values": values, "unit": unit}], labels, title)


def _style_multi_line_chart(series: list[dict[str, Any]], labels: list[str], title: str) -> str:
    if not series or not labels:
        return '<p class="muted">暂无可绘制数据。</p>'
    palette = ["#13735b", "#c25545", "#5b63b7", "#b7791f", "#2f7f9f", "#7a4b9f"]
    values = [float(value) for item in series for value in item.get("values", []) if isinstance(value, (int, float))]
    if not values:
        return '<p class="muted">暂无可绘制数据。</p>'
    width = max(660, 190 + len(labels) * 86)
    height = 300
    left, right, top, bottom = 58, 148, 38, 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        max_v += 1
        min_v = max(0, min_v - 1)
    pad = max(0.5, (max_v - min_v) * 0.12)
    min_v = max(0, min_v - pad)
    max_v += pad

    def x_pos(index: int) -> float:
        return left + (plot_w / 2 if len(labels) == 1 else index / (len(labels) - 1) * plot_w)

    def y_pos(value: float) -> float:
        return top + (max_v - value) / (max_v - min_v) * plot_h

    parts = [
        '<div class="style-chart">',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        '<rect width="100%" height="100%" rx="12" fill="#fbfcfa"/>',
        f'<text x="{left}" y="23" font-size="16" font-family="Microsoft YaHei, Arial, sans-serif" font-weight="700" fill="#1f2b26">{html.escape(title)}</text>',
    ]
    for step in range(4):
        value = min_v + (max_v - min_v) * step / 3
        y = y_pos(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#dbe2dc" stroke-width="1"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#66736d">{value:.1f}</text>')
    for index, label in enumerate(labels):
        x = x_pos(index)
        parts.append(f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" font-size="11" fill="#66736d">{html.escape(label)}</text>')
    for s_index, item in enumerate(series):
        color = palette[s_index % len(palette)]
        raw_values = [float(value) for value in item.get("values", [])]
        points = [(x_pos(i), y_pos(value), value) for i, value in enumerate(raw_values)]
        point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round" points="{point_attr}"/>')
        for x, y, value in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="#fff" stroke-width="1.4"/>')
        legend_y = top + 18 + s_index * 22
        legend_x = left + plot_w + 24
        parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{legend_x + 30}" y="{legend_y + 4}" font-size="12" fill="#1f2b26">{html.escape(str(item.get("label", "")))}</text>')
    parts.extend(["</svg>", "</div>"])
    return "\n".join(parts)


def _style_char_density_chart(histories: list[dict[str, Any]], chars: list[tuple[str, int]]) -> str:
    labels = [f"第{index + 1}篇" for index in range(len(histories))]
    series = []
    for char, _total in chars:
        values = []
        for history in histories:
            total = _style_char_total(history)
            values.append(round(_style_text(history).count(char) / total * 100, 2))
        series.append({"label": char, "values": values})
    return _style_multi_line_chart(series, labels, "高频单字密度（每百字）")


def _style_punctuation_density_chart(histories: list[dict[str, Any]], marks: list[tuple[str, int, list[str]]]) -> str:
    labels = [f"第{index + 1}篇" for index in range(len(histories))]
    series = []
    for label, _total, tokens in marks:
        values = []
        for history in histories:
            total = _style_char_total(history)
            values.append(round(_count_punctuation(_style_text(history), tokens) / total * 100, 2))
        series.append({"label": label, "values": values})
    return _style_multi_line_chart(series, labels, "标点密度（每百字）")


def format_style_report(analysis: dict[str, Any], payload: list[dict[str, Any]]) -> str:
    lines = ["# 学生语言风格数据报告", "", f"生成时间：{now_iso()}", ""]
    for item in payload:
        histories = item.get("history") or []
        if not histories:
            continue
        lines.append(f"## {item['student']}")
        lines.append("")
        lines.extend(["<!-- raw-html:start -->", _style_line_chart(histories, "avg_sentence_length", "均句长变化", "字"), "<!-- raw-html:end -->", ""])
        top_chars = _style_top_chars(histories)
        if top_chars:
            lines.append("### 高频单字")
            lines.append("")
            lines.extend(["<!-- raw-html:start -->", _style_char_density_chart(histories, top_chars), "<!-- raw-html:end -->", ""])
            lines.append(table_row(["单字", "总次数", "平均每百字次数"]))
            lines.append(table_row(["---", "---:", "---:"]))
            total_chars = sum(_style_char_total(history) for history in histories) or 1
            for char, count in top_chars:
                lines.append(table_row([char, count, round(count / total_chars * 100, 2)]))
            lines.append("")
        top_marks = _style_top_punctuation(histories)
        if top_marks:
            lines.append("### 标点密度")
            lines.append("")
            lines.extend(["<!-- raw-html:start -->", _style_punctuation_density_chart(histories, top_marks), "<!-- raw-html:end -->", ""])
            lines.append(table_row(["标点", "总次数", "平均每百字次数"]))
            lines.append(table_row(["---", "---:", "---:"]))
            total_chars = sum(_style_char_total(history) for history in histories) or 1
            for label, count, _tokens in top_marks:
                lines.append(table_row([label, count, round(count / total_chars * 100, 2)]))
            lines.append("")
        lines.append("### 篇目基础数据")
        lines.append("")
        lines.append(table_row(["提交 ID", "作业", "文体", "匹配", "分数", "字数", "句数", "最长句"]))
        lines.append(table_row(["---", "---", "---", "---", "---:", "---:", "---:", "---:"]))
        for history in histories:
            metrics = history.get("metrics") or {}
            lines.append(
                table_row(
                    [
                        f"`{history['submission_id']}`",
                        history["assignment"],
                        history.get("detected_genre", ""),
                        history.get("genre_fit", ""),
                        history.get("score", ""),
                        metrics.get("char_count", ""),
                        metrics.get("sentence_count", ""),
                        metrics.get("max_sentence_length", ""),
                    ]
                )
            )
        lines.append("")
        flagged = [history for history in histories if history.get("heuristic_flags")]
        if flagged:
            lines.append("### 异常提示")
            lines.append("")
            lines.append(table_row(["提交 ID", "提示", "与上一篇文本相似度"]))
            lines.append(table_row(["---", "---", "---:"]))
            for history in flagged:
                lines.append(
                    table_row(
                        [
                            f"`{history.get('submission_id')}`",
                            "；".join(history.get("heuristic_flags") or []),
                            "" if history.get("similarity_to_previous") is None else history.get("similarity_to_previous"),
                        ]
                    )
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def format_assignment_summary_report(assignment: dict[str, Any], analysis: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = [
        f"# 《{assignment.get('title')}》作业总结",
        "<!-- assignment-summary-render:v3 -->",
        "",
        f"生成时间：{now_iso()}",
        f"作业 ID：`{assignment.get('id')}`",
        f"提交数量：{len(payload.get('submissions') or [])}",
        "",
    ]
    if "raw" in analysis:
        lines.extend([analysis["raw"], ""])
    else:
        ordered = [
            ("overall", "整体情况"),
            ("score_distribution", "分数与档位"),
            ("task_understanding", "任务理解"),
            ("common_strengths", "共性亮点"),
            ("common_issues", "共性问题"),
            ("student_notes", "学生简表"),
            ("revision_observations", "修改稿观察"),
            ("radar_observations", "雷达观察"),
            ("teaching_actions", "讲评与训练建议"),
            ("next_assignment_suggestions", "后续作业建议"),
        ]
        for key, title in ordered:
            value = analysis.get(key)
            if value in (None, "", [], {}):
                continue
            lines.extend([f"## {title}", "", render_summary_value(key, value), ""])
        rest = {k: v for k, v in analysis.items() if k not in {key for key, _ in ordered}}
        if rest:
            lines.extend(["## 其他信息", "", render_any(rest), ""])

    submissions = payload.get("submissions") or []
    if submissions:
        lines.extend(["## 本次总结覆盖的提交", ""])
        lines.append(table_row(["学生", "版本", "分数", "文体", "匹配", "提交 ID"]))
        lines.append(table_row(["---", "---:", "---:", "---", "---", "---"]))
        for item in submissions:
            lines.append(
                table_row(
                    [
                        item.get("student", ""),
                        item.get("version_no", ""),
                        item.get("score", ""),
                        item.get("detected_genre", ""),
                        item.get("genre_fit", ""),
                        f"`{item.get('submission_id')}`",
                    ]
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summary_join(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return "、".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def render_summary_value(key: str, value: Any) -> str:
    if key in {"common_strengths", "common_issues", "student_notes"} and isinstance(value, list):
        rows: list[str] = []
        if key == "common_strengths":
            rows.append(table_row(["亮点", "证据", "学生"]))
            rows.append(table_row(["---", "---", "---"]))
            for item in value:
                if isinstance(item, dict):
                    rows.append(table_row([item.get("point", ""), item.get("evidence", ""), summary_join(item.get("students"))]))
        elif key == "common_issues":
            rows.append(table_row(["问题", "原因", "典型学生", "讲评修正"]))
            rows.append(table_row(["---", "---", "---", "---"]))
            for item in value:
                if isinstance(item, dict):
                    rows.append(
                        table_row(
                            [
                                item.get("issue", ""),
                                item.get("reason", ""),
                                summary_join(item.get("typical_students")),
                                item.get("teaching_fix", ""),
                            ]
                        )
                    )
        else:
            rows.append(table_row(["学生", "版本", "分数", "主要亮点", "主要问题", "下一步"]))
            rows.append(table_row(["---", "---", "---:", "---", "---", "---"]))
            for item in value:
                if isinstance(item, dict):
                    versions = item.get("versions")
                    rows.append(
                        table_row(
                            [
                                item.get("student", ""),
                                summary_join(versions),
                                item.get("score", ""),
                                item.get("main_strength", ""),
                                item.get("main_issue", ""),
                                item.get("next_step", ""),
                            ]
                        )
                    )
        return "\n".join(rows) if len(rows) > 2 else render_any(value)
    return render_any(value)
