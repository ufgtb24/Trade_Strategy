"""记忆目录改后的检查（只读）。输出不带记忆正文，只有文件名、词和计数。

用法：python check_memory.py <记忆目录>
- 残留：每行的 match / 匹配（不分大小写），抠掉下面 KEEP 的说法后还有剩就算「未归类」；
- 链接：每个 [[name]] 按 frontmatter 的 name 或文件名（不带 .md）找得到文件；MEMORY.md 的 (xxx.md) 指得到文件。
  有些 [[name]] 只差连字符与下划线或多带 .md（记忆里本来就有这种写法），单列「写法不一致」，人能找到文件；
  两种都对不上的才算「指不到文件」；
- frontmatter：除 MEMORY.md 外每个文件都能被 yaml 解析，且有 name。
退出码：未归类、frontmatter 解析失败为 1；断的 [[name]] 只列出来，由调用方和改前比。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

KEEP = [
    ("mismatch 一族", re.compile(r"\w*mismatch\w*", re.IGNORECASE)),
    ("文件名、name（记忆文件名不改）", re.compile(r"feedback[-_]wait[-_]loop[-_]pgrep[-_]self[-_]match(\.md)?")),
    ("中文「匹配」泛指（进程按名字匹配）", re.compile(r"按命令名匹配|会匹配到|都匹配到|还匹配到")),
    ("中文「匹配」泛指（用途、粒度对得上）", re.compile(r"用途匹配|粒度匹配")),
    ("统计里的配对", re.compile(r"层匹配|非匹配|匹配后")),
]
OLD_WORD = re.compile(r"match|匹配", re.IGNORECASE)
LINK = re.compile(r"\[\[([^\]\n]+)\]\]")
MDLINK = re.compile(r"\]\(([^)\s]+\.md)\)")


def norm(name: str) -> str:
    """把 [[name]] 规整成可比的形式：去 .md，连字符当下划线。"""
    return name.removesuffix(".md").replace("-", "_")


def front(path: Path) -> dict | None:
    """解析文件开头的 yaml frontmatter；没有 frontmatter 返回 None，解析失败抛 yaml.YAMLError。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return yaml.safe_load(text[4:end]) if end > 0 else None


def main() -> int:
    """跑三项检查并打印，退出码见模块说明。"""
    mem = Path(sys.argv[1])
    files = sorted(mem.glob("*.md"))
    names = {p.stem for p in files}
    bad_front = []
    for p in files:
        if p.name == "MEMORY.md":
            continue
        try:
            fm = front(p)
        except yaml.YAMLError:
            bad_front.append(p.name)
            continue
        if not fm or not fm.get("name"):
            bad_front.append(p.name)
        else:
            names.add(fm["name"])
    normed = {norm(n) for n in names}
    counts: Counter = Counter()
    left = []
    dead: Counter = Counter()
    loose: Counter = Counter()
    for p in files:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for t in LINK.findall(line):
                if t in names:
                    continue
                if norm(t) in normed:
                    loose[f"{p.name} -> [[{t}]]"] += 1
                else:
                    dead[f"{p.name} -> [[{t}]]"] += 1
            if p.name == "MEMORY.md":
                for t in MDLINK.findall(line):
                    if not (mem / t).is_file():
                        dead[f"MEMORY.md -> ({t})"] += 1
            if not OLD_WORD.search(line):
                continue
            rest = line
            for cat, rx in KEEP:
                rest, n = rx.subn(" ", rest)
                counts[cat] += n
            if OLD_WORD.search(rest):
                left.append(f"{p.name}:{i}")
    print(f"文件 {len(files)} 个；frontmatter 解析失败或缺 name：{len(bad_front)}", bad_front or "")
    print("残留按类（次）：")
    for k, v in sorted(counts.items()):
        if v:
            print(f"  {v:3d}  {k}")
    print(f"未归类（行）：{len(left)}", left or "")
    print(f"写法不一致的链接：{sum(loose.values())}")
    for k, v in sorted(loose.items()):
        print(f"  {v:3d}  {k}")
    print(f"指不到文件的链接：{sum(dead.values())}")
    for k, v in sorted(dead.items()):
        print(f"  {v:3d}  {k}")
    return 1 if left or bad_front else 0


if __name__ == "__main__":
    sys.exit(main())
