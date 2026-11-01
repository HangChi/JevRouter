#!/usr/bin/env python3
"""检查仓库内 Markdown 的相对链接与锚点是否指向真实存在的位置。

只用标准库：文档检查不该引入依赖，也不该需要装好整个项目才能跑。
外部链接（http/https/mailto）不探测——网络不可达不等于链接失效。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".workbuddy",
    ".venv",
    "node_modules",
    ".next",
    ".pytest_tmp",
    ".mypy_cache",
    ".ruff_cache",
}

# [文字](目标) 或 [文字](目标 "标题")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def anchor_of(heading: str) -> str:
    """按 GitHub 的规则把标题转成锚点。

    粗体标记、行内代码与标点都会被丢掉，空格变连字符，中文原样保留。
    """
    text = heading.strip().lower()
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"[*_~]", "", text)
    kept = []
    for char in text:
        if char.isalnum() or char in "-_" or "\u4e00" <= char <= "\u9fff":
            kept.append(char)
        elif char == " ":
            kept.append("-")
    return "".join(kept)


def markdown_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.md")
        if not SKIP_DIRS & set(path.relative_to(root).parts)
    ]


def anchors(path: Path) -> set[str]:
    return {
        anchor_of(match.group(2))
        for match in (HEADING.match(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if match
    }


def check(root: Path) -> list[str]:
    files = markdown_files(root)
    known = {path.resolve(): anchors(path) for path in files}
    problems: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            location, _, anchor = target.partition("#")
            destination = (path.parent / location).resolve() if location else path.resolve()
            if location and not destination.exists():
                problems.append(f"{path.relative_to(root)}: {target} —— 文件不存在")
                continue
            if anchor and anchor not in known.get(destination, set()):
                problems.append(f"{path.relative_to(root)}: {target} —— 锚点不存在")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems = check(root)
    if not problems:
        print(f"文档链接检查通过（{len(markdown_files(root))} 个文件）")
        return 0
    print(f"发现 {len(problems)} 处失效链接：", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
