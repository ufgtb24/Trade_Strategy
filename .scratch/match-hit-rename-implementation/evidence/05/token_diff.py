"""按词列出两份文本的改动：每处一行 `文件:行: …前文[-旧-]{+新+}后文…`，并校验「只换词」（只读）。

用法：
    python token_diff.py dirs <改前目录> <改后目录> [--context N] [--mask-digits] [--summary]
    python token_diff.py git <改前提交> <路径...> [--context N] [--mask-digits]（改后取工作区，git mv 用 <旧路径>=<新路径> 写）

--context N      每处改动前后各留 N 个字符（默认 30），记忆和登记簿的行很长，整行放进证据没有必要。
--mask-digits    前后文里的数字一律换成 #。记忆里有含 2026 年窗口的结果，证据只留换词所需的上下文，
                 不转述数字；改动本身（旧词、新词）不打码。
--summary        不列改动，只输出统计与校验：行数是否相同、没改的行是否逐字相同、每条「旧→新」的次数。

校验「只换词」的办法：逐行比，行数必须相同（否则 FAIL、退出码 1），没改的行逐字相同；--summary 列出全部「旧→新」及次数，
人读这张表确认里面只有换词。
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

WORDISH = re.compile(r"[A-Za-z0-9_]")


def changes(old: str, new: str) -> list[tuple[int, int, int, int]]:
    """字符级差异，返回 (旧起, 旧止, 新起, 新止)；把落在标识符中间的差异扩到整个单词，方便读。"""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    out = []
    for tag, a, b, c, d in sm.get_opcodes():
        if tag == "equal":
            continue
        while a > 0 and c > 0 and old[a - 1] == new[c - 1] and WORDISH.match(old[a - 1]):
            a -= 1
            c -= 1
        while b < len(old) and d < len(new) and old[b] == new[d] and WORDISH.match(old[b]):
            b += 1
            d += 1
        if out and a <= out[-1][1]:
            pa, _, pc, _ = out.pop()
            a, c = pa, pc
        out.append((a, b, c, d))
    return out


def mask(s: str, on: bool) -> str:
    return re.sub(r"\d+", "#", s) if on else s


def compare(label: str, before: str, after: str, args, stats: Counter, rows: list[str]) -> bool:
    b_lines, a_lines = before.split("\n"), after.split("\n")
    if len(b_lines) != len(a_lines):
        print(f"FAIL 行数变了 {label}: {len(b_lines)} → {len(a_lines)}")
        return False
    ok = True
    for i, (x, y) in enumerate(zip(b_lines, a_lines), 1):
        if x == y:
            continue
        for a, b, c, d in changes(x, y):
            old, new = x[a:b], y[c:d]
            stats[f"{old} → {new}"] += 1
            pre = mask(x[max(0, a - args.context):a], args.mask_digits)
            post = mask(x[b:b + args.context], args.mask_digits)
            rows.append(f"{label}:{i}: …{pre}[-{old}-]{{+{new}+}}{post}…")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dirs", "git"])
    ap.add_argument("a")
    ap.add_argument("rest", nargs="+")
    ap.add_argument("--context", type=int, default=30)
    ap.add_argument("--mask-digits", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    stats: Counter = Counter()
    rows: list[str] = []
    ok = True
    n_files = n_changed = 0
    if args.mode == "dirs":
        ra, rb = Path(args.a), Path(args.rest[0])
        names = sorted({p.relative_to(ra).as_posix() for p in ra.rglob("*") if p.is_file()}
                       | {p.relative_to(rb).as_posix() for p in rb.rglob("*") if p.is_file()})
        for name in names:
            pa, pb = ra / name, rb / name
            if not pa.exists() or not pb.exists():
                print(f"FAIL 文件集合变了 {name}")
                ok = False
                continue
            x, y = pa.read_text(encoding="utf-8"), pb.read_text(encoding="utf-8")
            n_files += 1
            if x != y:
                n_changed += 1
                ok = compare(name, x, y, args, stats, rows) and ok
    else:
        for spec in args.rest:
            old_path, _, new_path = spec.partition("=")
            new_path = new_path or old_path
            x = subprocess.run(["git", "show", f"{args.a}:{old_path}"], capture_output=True, text=True, check=True).stdout
            y = Path(new_path).read_text(encoding="utf-8")
            n_files += 1
            if x != y:
                n_changed += 1
                ok = compare(new_path, x, y, args, stats, rows) and ok

    if args.summary:
        print(f"文件 {n_files} 个，改动 {n_changed} 个，改动处 {sum(stats.values())}；行数与未改行逐字校验：{'通过' if ok else '不通过'}")
        for k, v in sorted(stats.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {v:4d}  {k}")
    else:
        print("\n".join(rows))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
