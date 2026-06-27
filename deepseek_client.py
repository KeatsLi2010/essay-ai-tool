"""DeepSeek API client helpers."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core import DEFAULT_API_BASE, DEFAULT_MODEL, ToolError, get_api_key, get_config_value

def make_endpoint(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def post_json(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ToolError(f"DeepSeek API 返回 HTTP {exc.code}：{detail}") from exc
    except URLError as exc:
        raise ToolError(f"无法连接 DeepSeek API：{exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"DeepSeek API 返回了非 JSON 内容：{raw[:500]}") from exc


def call_deepseek(
    messages: list[dict[str, str]],
    args: argparse.Namespace,
    json_mode: bool = True,
) -> str:
    api_key = get_api_key(args)
    model = getattr(args, "model", None) or get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL)
    api_base = getattr(args, "api_base", None) or get_config_value("DEEPSEEK_API_BASE", DEFAULT_API_BASE)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    url = make_endpoint(api_base)
    timeout = int(getattr(args, "timeout", 120))
    try:
        data = post_json(url, payload, api_key, timeout)
    except ToolError as exc:
        if json_mode and "response_format" in str(exc):
            payload.pop("response_format", None)
            data = post_json(url, payload, api_key, timeout)
        else:
            raise
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ToolError(f"DeepSeek API 响应格式异常：{json.dumps(data, ensure_ascii=False)[:800]}") from exc


def parse_ai_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    stripped = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"raw": text}
