"""Shared scoring/radar helpers for the web UI."""

from __future__ import annotations

import re

RADAR_DIMENSIONS = [
    ("topic", "审题立意", ["审题立意", "审题立意与内容", "立意"]),
    ("genre", "文体适配", ["文体适配", "文体适配与结构", "文体"]),
    ("material", "内容材料", ["内容材料", "内容", "材料"]),
    ("structure", "结构层次", ["结构层次", "结构"]),
    ("language", "语言表达", ["语言表达", "语言"]),
    ("rhythm", "韵律节奏", ["韵律节奏", "节奏", "语言与韵律"]),
    ("development", "发展亮点", ["发展亮点", "发展"]),
    ("norm", "规范表现", ["规范表现", "规范风险", "规范"]),
]


def avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _extract_number(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    ratio = re.search(r"(\d+(?:\.\d+)?)\s*/\s*20", text)
    if ratio:
        return float(ratio.group(1))
    number = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", text)
    return float(number.group(1)) if number else None


def _has_explicit_20_scale(value) -> bool:
    return bool(re.search(r"/\s*20|满分\s*20|20\s*分制", str(value or "")))


def _text_says_no_risk(value) -> bool:
    text = str(value or "")
    if any(token in text for token in ["扣", "不足", "风险", "瑕疵", "错别字", "语病"]):
        return False
    return any(token in text for token in ["无明显", "无错别字", "无格式", "无。", "无风险", "无"])


def _radar_source_value(source: dict, label: str, aliases: list[str]):
    for key in [label, *aliases]:
        if key in source:
            return source.get(key)
    for key, value in source.items():
        if any(alias in str(key) for alias in [label, *aliases]):
            return value
    return None


def _normalize_radar_score(label: str, value, source_name: str | None = None) -> float | None:
    if value in (None, "", [], {}):
        return None
    if label == "规范表现":
        if isinstance(value, str) and _text_says_no_risk(value):
            return 20.0
        number = _extract_number(value)
        if number is None:
            return 14.0 if str(value).strip() else None
        if number <= 10:
            return max(0.0, min(20.0, 20.0 - number))
        return max(0.0, min(20.0, number))
    number = _extract_number(value)
    if number is None:
        return None
    if (
        source_name == "score_breakdown"
        and label in {"文体适配", "韵律节奏", "发展亮点"}
        and number <= 10
        and not _has_explicit_20_scale(value)
    ):
        number *= 2
    return max(0.0, min(20.0, number))


def build_radar(analysis: dict) -> dict:
    sources: list[tuple[str, dict]] = []
    radar_scores = analysis.get("radar_scores")
    if isinstance(radar_scores, dict):
        sources.append(("radar_scores", radar_scores))
    breakdown = analysis.get("score_breakdown")
    if isinstance(breakdown, dict):
        sources.append(("score_breakdown", breakdown))
    values = []
    for key, label, aliases in RADAR_DIMENSIONS:
        raw = None
        source_name = None
        for candidate_name, source in sources:
            raw = _radar_source_value(source, label, aliases)
            if raw not in (None, "", [], {}):
                source_name = candidate_name
                break
        score = _normalize_radar_score(label, raw, source_name)
        values.append(
            {
                "key": key,
                "label": label,
                "score": round(score, 1) if score is not None else None,
                "max": 20,
                "source": source_name,
                "raw": str(raw) if raw not in (None, "", [], {}) else "",
            }
        )
    available_scores = [item["score"] for item in values if isinstance(item.get("score"), (int, float))]
    return {
        "available": len(available_scores) >= 4,
        "dimensions": values,
        "average": avg(available_scores),
        "source": "radar_scores" if isinstance(radar_scores, dict) else ("score_breakdown" if isinstance(breakdown, dict) else None),
    }
