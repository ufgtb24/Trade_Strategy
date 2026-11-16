"""两轮之间把用户认可的 pattern 定义写进标注（references/between-rounds.md 第 4 步）。

用法：
    uv run python .claude/skills/annotation-round/scripts/write_definition.py <pattern> <文本文件> [--write]

文本文件是新定义的全文（UTF-8，末尾空行会去掉）。不带 --write 只打印现在的定义和要写成的定义；
带 --write 才写：经 path2_web/annotation/store.py 的 append_batch 新写一个批次文件（与网页保存同一个
写入函数，先校验、不改已有文件），base 取读出的最后一次修改。pattern 的其它键（flags）原样保留。
有冲突或未同步的修改时不写，先报出来。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from path2_web.annotation.store import append_batch, read_annotations
from path2_web.config import load_config

REREAD = "规则：上下文压缩过或记不清时，重读 .claude/skills/annotation-round/SKILL.md 与 references/between-rounds.md"


def main() -> int:
    try:
        return _run()
    finally:
        print(REREAD)   # 压缩后最近的工具输出里仍有这句指针


def _run() -> int:
    ap = argparse.ArgumentParser(description="把新的 pattern 定义写进标注（默认只预览）")
    ap.add_argument("pattern")
    ap.add_argument("text_file")
    ap.add_argument("--write", action="store_true", help="真的写入；不带只预览")
    a = ap.parse_args()

    cfg = load_config()
    r = read_annotations(cfg)
    found = [p for p in r["state"]["patterns"] if p["name"] == a.pattern]
    if not found:
        print(f"标注里没有叫 {a.pattern!r} 的 pattern", file=sys.stderr)
        return 1
    cur = found[0]
    old = cur.get("definition") or ""
    new = Path(a.text_file).read_text(encoding="utf-8").rstrip("\n")

    print("== 现在的定义 ==")
    print(old or "（空）")
    print("== 要写成 ==")
    print(new)
    if not new.strip():
        print("新定义是空的，不写", file=sys.stderr)
        return 1
    if new == old:
        print("没有变化，不写")
        return 0
    if not a.write:
        print("（只是预览；确认后加 --write 写入）")
        return 0
    pending = [c for c in r["conflicts"] if c["kind"] == "pattern" and c["id"] == a.pattern]
    pending += [u for u in r["unsynced"] if u["kind"] == "pattern" and u["id"] == a.pattern]
    if pending:
        print(f"这个 pattern 有冲突或还没同步到的修改，不写：{pending}", file=sys.stderr)
        return 1
    value = {**cur, "definition": new}
    name = append_batch(cfg, [{"kind": "pattern", "id": a.pattern,
                               "base": r["revs"]["pattern"].get(a.pattern), "value": value}])
    print(f"已写入批次文件 {name}；请刷新页面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
