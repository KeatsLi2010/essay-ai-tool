#!/usr/bin/env python3
"""Compatibility facade for the modular essay AI tool."""

from __future__ import annotations

from analytics import *  # noqa: F403
from assignment_service import *  # noqa: F403
from cli import add_common_ai_args, build_parser, main
from commands import *  # noqa: F403
from core import *  # noqa: F403
from deepseek_client import *  # noqa: F403
from prompts import *  # noqa: F403
from reports import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(main())
