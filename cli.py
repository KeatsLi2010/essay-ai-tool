"""Command-line interface for the essay tool."""

from __future__ import annotations

import argparse
import sys

from commands import (
    command_assignment_rejudge,
    command_assignment_new,
    command_config_key,
    command_curves,
    command_list,
    command_submission_rejudge,
    command_style_report,
    command_submission_add,
    command_undo,
)
from core import DEFAULT_API_BASE, DEFAULT_MODEL, ToolError, default_data_dir, get_config_value

def add_common_ai_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-key", help="DeepSeek API key；也可用 DEEPSEEK_API_KEY 或 .env")
    parser.add_argument("--model", default=get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL), help=f"DeepSeek 模型名，默认 {DEFAULT_MODEL}")
    parser.add_argument("--api-base", default=get_config_value("DEEPSEEK_API_BASE", DEFAULT_API_BASE), help=f"API base，默认 {DEFAULT_API_BASE}")
    parser.add_argument("--temperature", type=float, default=0.25, help="保留参数；DeepSeek thinking 模式下不会使用温度")
    parser.add_argument("--timeout", type=int, default=120, help="API 超时秒数，默认 120")
    parser.add_argument("--no-ai", action="store_true", help="仅保存数据，不调用 DeepSeek；用于离线测试")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepSeek 高考作文作业、评分、曲线和风格分析工具")
    parser.add_argument("--data-dir", default=str(default_data_dir()), help="数据目录，默认 essay_ai_tool/data")
    sub = parser.add_subparsers(dest="command", required=True)

    p_key = sub.add_parser("config-key", help="保存 DeepSeek API key 到本地 .env")
    p_key.add_argument("--api-key", help="不推荐在共享终端中使用；省略则安全提示输入")
    p_key.add_argument("--model", default=get_config_value("DEEPSEEK_MODEL", DEFAULT_MODEL), help=f"模型名，默认 {DEFAULT_MODEL}")
    p_key.add_argument("--api-base", default=get_config_value("DEEPSEEK_API_BASE", DEFAULT_API_BASE), help=f"API base，默认 {DEFAULT_API_BASE}")
    p_key.set_defaults(func=command_config_key)

    p_assignment = sub.add_parser("assignment-new", help="新建一次作文作业并生成审题分析")
    p_assignment.add_argument("--title", required=True, help="作业标题")
    p_assignment.add_argument("--topic", help="作文题目全文")
    p_assignment.add_argument("--topic-file", help="作文题目文件，UTF-8")
    p_assignment.add_argument("--writing-type", default="auto", help="用户标注文体，如 auto、微写作、大作文、议论文、记叙文")
    p_assignment.add_argument("--id", help="自定义作业 ID")
    add_common_ai_args(p_assignment)
    p_assignment.set_defaults(func=command_assignment_new)

    p_submission = sub.add_parser("submission-add", help="新增学生提交，保存原文并生成评分报告")
    p_submission.add_argument("--assignment", required=True, help="作业 ID、ID 前缀或完整标题")
    p_submission.add_argument("--student", required=True, help="学生姓名缩写")
    p_submission.add_argument("--content", help="作文正文")
    p_submission.add_argument("--content-file", help="作文正文文件，UTF-8")
    p_submission.add_argument("--revision", action="store_true", help="明确按修改稿处理")
    p_submission.add_argument("--initial", action="store_true", help="明确按初稿处理，即使已有历史提交")
    p_submission.add_argument("--manual-score", type=float, help="手动录入 0-60 分；可用于离线导入或覆盖 AI 分数")
    add_common_ai_args(p_submission)
    p_submission.set_defaults(func=command_submission_add)

    p_rejudge = sub.add_parser("rejudge-submission", help="完全重判某一次学生提交，覆盖原分数和报告")
    p_rejudge.add_argument("--submission", required=True, help="提交 ID 或唯一前缀")
    add_common_ai_args(p_rejudge)
    p_rejudge.set_defaults(func=command_submission_rejudge)

    p_rejudge_assignment = sub.add_parser("rejudge-assignment", help="完全重判某次作业下的全部提交")
    p_rejudge_assignment.add_argument("--assignment", required=True, help="作业 ID、ID 前缀或完整标题")
    add_common_ai_args(p_rejudge_assignment)
    p_rejudge_assignment.set_defaults(func=command_assignment_rejudge)

    p_list = sub.add_parser("list", help="查看已有作业或学生")
    p_list.add_argument("kind", choices=["assignments", "students"], help="列表类型")
    p_list.set_defaults(func=command_list)

    p_curves = sub.add_parser("curves", help="分析历次提交与得分，并生成 SVG 得分曲线")
    p_curves.add_argument("--student", action="append", help="只分析指定学生；可重复")
    p_curves.add_argument("--out-dir", help="报告输出目录，默认 reports/score_curves")
    p_curves.set_defaults(func=command_curves)

    p_style = sub.add_parser("style-report", help="分析学生语言风格，并提示可能异常作业")
    p_style.add_argument("--student", action="append", help="只分析指定学生；可重复")
    p_style.add_argument("--out-dir", help="报告输出目录，默认 reports/style")
    add_common_ai_args(p_style)
    p_style.set_defaults(func=command_style_report)

    p_undo = sub.add_parser("undo", help="撤销上一次新增作业、提交或报告生成")
    p_undo.set_defaults(func=command_undo)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
