#!/usr/bin/env python3
"""Core paths, storage, config, and file utilities for the essay tool."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "deepseek-v4-pro"


DEFAULT_API_BASE = "https://api.deepseek.com"


STATE_VERSION = 1


COLORS = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
]


class ToolError(Exception):
    """A user-facing error."""


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def default_data_dir() -> Path:
    return script_dir() / "data"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def date_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def undo_path(data_dir: Path) -> Path:
    return data_dir / "undo_stack.json"


def ensure_dirs(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for child in ["assignments", "submissions", "reports"]:
        (data_dir / child).mkdir(parents=True, exist_ok=True)
    for child in ["assignments", "score_curves", "style"]:
        (script_dir() / "reports" / child).mkdir(parents=True, exist_ok=True)


def default_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "created_at": now_iso(),
        "assignments": {},
        "students": {},
        "submissions": {},
        "generated_reports": [],
    }


def load_json_file(path: Path, attempts: int = 5) -> Any:
    last_error: json.JSONDecodeError | None = None
    for attempt in range(attempts):
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(0.05 * (attempt + 1))
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    if last_error:
        raise last_error
    raise ToolError(f"无法读取 JSON 文件：{path}")


def save_json_file(path: Path, payload: Any, attempts: int = 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        for attempt in range(attempts):
            try:
                os.replace(temp_path, path)
                break
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def load_state(data_dir: Path) -> dict[str, Any]:
    ensure_dirs(data_dir)
    path = state_path(data_dir)
    if not path.exists():
        return default_state()
    state = load_json_file(path)
    state.setdefault("version", STATE_VERSION)
    state.setdefault("assignments", {})
    state.setdefault("students", {})
    state.setdefault("submissions", {})
    state.setdefault("generated_reports", [])
    return state


def save_state(data_dir: Path, state: dict[str, Any]) -> None:
    ensure_dirs(data_dir)
    save_json_file(state_path(data_dir), state)


def load_undo_stack(data_dir: Path) -> list[dict[str, Any]]:
    ensure_dirs(data_dir)
    path = undo_path(data_dir)
    if not path.exists():
        return []
    return load_json_file(path)


def save_undo_stack(data_dir: Path, stack: list[dict[str, Any]]) -> None:
    ensure_dirs(data_dir)
    save_json_file(undo_path(data_dir), stack)


def push_undo(
    data_dir: Path,
    previous_state: dict[str, Any],
    created_paths: list[Path],
    description: str,
) -> None:
    stack = load_undo_stack(data_dir)
    stack.append(
        {
            "timestamp": now_iso(),
            "description": description,
            "previous_state": previous_state,
            "created_paths": [str(path.resolve()) for path in created_paths],
        }
    )
    save_undo_stack(data_dir, stack)


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def safe_delete_created_path(path: Path) -> None:
    path = path.resolve()
    allowed_roots = [script_dir().resolve(), Path.cwd().resolve()]
    if not any(is_relative_to(path, root) for root in allowed_roots):
        print(f"跳过删除不在工具目录或当前目录内的路径：{path}", file=sys.stderr)
        return
    if path.is_file():
        path.unlink()
        return
    if path.is_dir():
        try:
            path.rmdir()
        except OSError:
            pass


def clean_student(value: str) -> str:
    value = value.strip()
    if not value:
        raise ToolError("学生姓名缩写不能为空。")
    return re.sub(r"\s+", "_", value)


def safe_filename(value: str, max_len: int = 50) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip())
    value = re.sub(r"\s+", "-", value)
    value = value.strip(".- ")
    if not value:
        value = "untitled"
    return value[:max_len]


def make_id(title: str) -> str:
    return f"{stamp()}_{safe_filename(title, 28)}_{uuid.uuid4().hex[:6]}"


def read_text_arg(text: str | None, file_path: str | None, label: str) -> str:
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    if text:
        return text.strip()
    if not sys.stdin.isatty():
        value = sys.stdin.read().strip()
        if value:
            return value
    raise ToolError(f"请通过 --{label} 或 --{label}-file 提供文本。")


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def trim_text(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    head = value[: limit // 2]
    tail = value[-limit // 2 :]
    return f"{head}\n\n...[中间省略 {len(value) - limit} 字]...\n\n{tail}"


def load_dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    path = script_dir() / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_config_value(name: str, fallback: str | None = None) -> str | None:
    dotenv = load_dotenv()
    return os.environ.get(name) or dotenv.get(name) or fallback


def get_api_key(args: argparse.Namespace) -> str:
    key = getattr(args, "api_key", None) or get_config_value("DEEPSEEK_API_KEY")
    if not key:
        raise ToolError(
            "未找到 DeepSeek API key。可以先运行 `python essay_tool.py config-key`，"
            "或设置环境变量 DEEPSEEK_API_KEY。"
        )
    return key
