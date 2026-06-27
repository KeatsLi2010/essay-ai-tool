"""Score curve and writing-style analysis helpers."""

from __future__ import annotations

import difflib
import html
from collections import Counter
import re
import statistics
from typing import Any

from assignment_service import sorted_submissions
from core import COLORS, trim_text

SCORE_MAX = 60
PUNCTUATION_KEYS = ["，", "。", "；", "、", "：", "！", "？", "“”", "（）", "——", "……"]
STYLE_STOP_TERMS = {
    "我们", "你们", "他们", "她们", "这个", "那个", "一种", "一个", "一些", "自己", "没有", "因为", "所以",
    "但是", "如果", "就是", "可以", "不是", "这样", "那样", "时候", "什么", "然后", "进行", "对于",
}

def group_scores(state: dict[str, Any], students: list[str] | None) -> dict[str, list[dict[str, Any]]]:
    selected = students or sorted(state["students"].keys())
    grouped: dict[str, list[dict[str, Any]]] = {}
    for student in selected:
        subs = []
        for sub in sorted_submissions(state, student):
            if isinstance(sub.get("score"), (int, float)):
                assignment = state["assignments"].get(sub.get("assignment_id"), {})
                subs.append(
                    {
                        "student": student,
                        "score": float(sub["score"]),
                        "assignment": assignment.get("title", sub.get("assignment_id")),
                        "version_no": sub.get("version_no"),
                        "created_at": sub.get("created_at"),
                        "submission_id": sub.get("id"),
                    }
                )
        if subs:
            grouped[student] = subs
    return grouped


def svg_score_chart(grouped: dict[str, list[dict[str, Any]]]) -> str:
    max_len = max((len(items) for items in grouped.values()), default=1)
    width = max(760, 180 + max_len * 95)
    height = 440
    left, right, top, bottom = 64, 160, 36, 70
    plot_w = width - left - right
    plot_h = height - top - bottom

    def x_pos(index: int) -> float:
        if max_len == 1:
            return left + plot_w / 2
        return left + (index / (max_len - 1)) * plot_w

    def y_pos(score: float) -> float:
        clipped = max(0, min(SCORE_MAX, score))
        return top + (SCORE_MAX - clipped) / SCORE_MAX * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-size="18" font-family="Arial, sans-serif" font-weight="700" fill="#111827">学生历次作文得分曲线（60 分制）</text>',
    ]
    for score in range(0, SCORE_MAX + 1, 10):
        y = y_pos(score)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="#6b7280">{score}</text>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#111827"/>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#111827"/>')
    for i in range(max_len):
        x = x_pos(i)
        parts.append(f'<text x="{x:.1f}" y="{height - 34}" text-anchor="middle" font-size="12" fill="#6b7280">第{i + 1}次</text>')

    for idx, (student, items) in enumerate(grouped.items()):
        color = COLORS[idx % len(COLORS)]
        points = []
        for i, item in enumerate(items):
            x, y = x_pos(i), y_pos(float(item["score"]))
            points.append(f"{x:.1f},{y:.1f}")
        if len(points) >= 2:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(points)}"/>')
        for i, item in enumerate(items):
            x, y = x_pos(i), y_pos(float(item["score"]))
            label = f'{item["score"]:.0f}'
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
            parts.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-size="12" fill="{color}">{label}</text>')
        legend_y = top + 22 + idx * 22
        legend_x = left + plot_w + 24
        parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{legend_x + 30}" y="{legend_y + 4}" font-size="13" fill="#111827">{html.escape(student)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def text_metrics(content: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", "", content)
    sentences = [s for s in re.split(r"[。！？!?]", content) if s.strip()]
    paragraphs = [p for p in re.split(r"\n\s*\n", content.strip()) if p.strip()]
    sentence_lengths = [len(re.sub(r"\s+", "", s)) for s in sentences] or [0]
    return {
        "char_count": len(compact),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "avg_sentence_length": round(statistics.mean(sentence_lengths), 1),
        "max_sentence_length": max(sentence_lengths),
        "comma_count": content.count("，") + content.count(","),
        "semicolon_count": content.count("；") + content.count(";"),
        "quote_count": content.count("“") + content.count("”") + content.count('"'),
    }


def build_style_payload(state: dict[str, Any], students: list[str] | None) -> list[dict[str, Any]]:
    selected = students or sorted(state["students"].keys())
    payload: list[dict[str, Any]] = []
    for student in selected:
        subs = sorted_submissions(state, student)
        if not subs:
            continue
        lengths = [text_metrics(sub.get("content", ""))["char_count"] for sub in subs]
        avg_len = statistics.mean(lengths) if lengths else 0
        stdev_len = statistics.pstdev(lengths) if len(lengths) > 1 else 0
        previous_content = ""
        previous_style = ""
        histories = []
        for sub in subs:
            assignment = state["assignments"].get(sub.get("assignment_id"), {})
            analysis = sub.get("analysis", {}) if isinstance(sub.get("analysis"), dict) else {}
            metrics = text_metrics(sub.get("content", ""))
            z_len = 0 if not stdev_len else (metrics["char_count"] - avg_len) / stdev_len
            similarity = None
            if previous_content:
                similarity = round(difflib.SequenceMatcher(None, previous_content[:6000], sub.get("content", "")[:6000]).ratio(), 3)
            style_observation = analysis.get("style_observation")
            language_rhythm = analysis.get("language_rhythm")
            style_similarity = None
            if previous_style and isinstance(style_observation, str):
                style_similarity = round(difflib.SequenceMatcher(None, previous_style, style_observation).ratio(), 3)
            flags = []
            if abs(z_len) >= 2:
                flags.append("篇幅显著偏离个人均值")
            if similarity is not None and similarity < 0.12:
                flags.append("与上一篇文本相似度很低")
            if style_similarity is not None and style_similarity < 0.18:
                flags.append("单篇风格观察与上一篇差异较大")
            histories.append(
                {
                    "submission_id": sub.get("id"),
                    "assignment": assignment.get("title", sub.get("assignment_id")),
                    "created_at": sub.get("created_at"),
                    "version_no": sub.get("version_no"),
                    "score": sub.get("score"),
                    "is_revision": sub.get("is_revision"),
                    "expected_genre": analysis.get("expected_genre"),
                    "detected_genre": analysis.get("detected_genre"),
                    "genre_fit": analysis.get("genre_fit"),
                    "language_rhythm": trim_text(language_rhythm, 700) if language_rhythm else "",
                    "style_observation": trim_text(style_observation, 700) if style_observation else "",
                    "metrics": metrics,
                    "similarity_to_previous": similarity,
                    "style_observation_similarity_to_previous": style_similarity,
                    "heuristic_flags": flags,
                    "excerpt_or_full_text": trim_text(sub.get("content", ""), 5000),
                }
            )
            previous_content = sub.get("content", "")
            if isinstance(style_observation, str) and style_observation.strip():
                previous_style = style_observation
        payload.append({"student": student, "history": histories})
    return payload
