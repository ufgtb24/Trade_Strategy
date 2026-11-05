"""检查 Markdown 相对链接与页内锚点（只读）。

用法（在仓库根目录）：python check_links.py <目录或文件> [...]
对每个 Markdown 文件里的 `[文字](目标)`（跳过围栏代码块、外部链接）：
- 目标路径相对当前文件解析，文件不存在算断链；
- 带 `#锚点` 的，按 GitHub 规则从目标文件的标题算出锚点集合（小写、去标点、空格变连字符、重名加 -1），不在集合里算断锚。
退出码：有断链或断锚为 1。
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

LINK_RE = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def body_lines(path: Path):
    """逐行给出 (行号, 文本)，跳过围栏代码块。"""
    in_fence = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield i, line


def slug(text: str) -> str:
    """按 GitHub 规则把标题文字转成锚点：去 Markdown 记号、小写、去标点、空格变连字符。"""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text).strip().lower()
    out = []
    for ch in text:
        if ch in "-_" or ch == " ":
            out.append("-" if ch == " " else ch)
        elif unicodedata.category(ch)[0] in "LN" or unicodedata.category(ch) == "Mn":
            out.append(ch)
    return "".join(out)


def anchors(path: Path) -> set[str]:
    """目标文件全部标题的锚点集合，重名的依次加 -1、-2。"""
    seen: dict[str, int] = {}
    found = set()
    for _, line in body_lines(path):
        m = HEAD_RE.match(line)
        if not m:
            continue
        s = slug(m.group(2))
        n = seen.get(s, 0)
        seen[s] = n + 1
        found.add(s if n == 0 else f"{s}-{n}")
    return found


def main(args: list[str]) -> int:
    """检查给定文件或目录下的全部 Markdown，打印断链断锚，返回退出码。"""
    files: list[Path] = []
    for a in args:
        p = Path(a)
        files += sorted(p.rglob("*.md")) if p.is_dir() else [p]
    total = bad = 0
    for f in files:
        for i, line in body_lines(f):
            for target in LINK_RE.findall(line):
                if re.match(r"[a-z]+:", target):
                    continue
                total += 1
                path_part, _, frag = target.partition("#")
                dest = (f.parent / path_part).resolve() if path_part else f.resolve()
                if not dest.exists():
                    bad += 1
                    print(f"断链 {f}:{i}: {target}")
                    continue
                if frag and dest.suffix == ".md" and frag.lower() not in anchors(dest):
                    bad += 1
                    print(f"断锚 {f}:{i}: {target}")
    print(f"相对链接 {total} 条，断 {bad} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
