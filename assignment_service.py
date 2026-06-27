"""Assignment and submission lookup helpers."""

from __future__ import annotations

from typing import Any

from core import ToolError

def resolve_assignment(state: dict[str, Any], query: str) -> dict[str, Any]:
    assignments = state["assignments"]
    if query in assignments:
        return assignments[query]
    title_matches = [item for item in assignments.values() if item.get("title") == query]
    if len(title_matches) == 1:
        return title_matches[0]
    prefix_matches = [item for key, item in assignments.items() if key.startswith(query)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if not title_matches and not prefix_matches:
        raise ToolError(f"找不到作业：{query}")
    raise ToolError(f"作业标识不唯一，请使用完整 ID：{query}")


def resolve_submission(state: dict[str, Any], query: str) -> dict[str, Any]:
    submissions = state["submissions"]
    if query in submissions:
        return submissions[query]
    prefix_matches = [item for key, item in submissions.items() if key.startswith(query)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if not prefix_matches:
        raise ToolError(f"找不到提交：{query}")
    raise ToolError(f"提交标识不唯一，请使用完整提交 ID：{query}")


def sorted_submissions(state: dict[str, Any], student: str | None = None) -> list[dict[str, Any]]:
    submissions = list(state["submissions"].values())
    if student:
        submissions = [s for s in submissions if s.get("student") == student]
    return sorted(submissions, key=lambda item: item.get("created_at", ""))


def latest_submission(
    state: dict[str, Any],
    assignment_id: str,
    student: str,
) -> dict[str, Any] | None:
    matches = [
        s
        for s in state["submissions"].values()
        if s.get("assignment_id") == assignment_id and s.get("student") == student
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item.get("created_at", ""))[-1]
