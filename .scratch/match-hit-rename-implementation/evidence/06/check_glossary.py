"""票 06 的词表检查（只读）。在仓库根目录运行，不读行情。

做两件事：
1. 行号引用：票面清单里每个文档对两份词表的行号引用（`path2/GLOSSARY.md:NNN`、同一行后面的 `:NNN`，
   以及 spec 里没写文件名、由上下文指向 path2 词表的 `:NNN`），改前改后那一行所属词条的规范词（词头第一个）
   必须相同；词头其余部分变了的（票面要求的别名移走）单独列出。同时比较 :103 之后逐行是否原样。
2. 词条：hit、match、matching 三个词条存在；两份词表每个词条的词头与自己的 _Avoid_ 不相交；
   hit 的 _Avoid_ 里有 match；三档词条是 detected、qualified、in_hit；三个文件里剩下的 match 字样逐行列出；
   CLAUDE.md 写的词头数等于实际词头数。

用法：python check_glossary.py <改前提交> [--path2-new <文件>]
    --path2-new 用另一份文件代替现行 path2/GLOSSARY.md，用来确认检查拦得住移了行的词表。
退出码：有任何一项不通过为 1，否则 0。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

P2, WEB, MAP = "path2/GLOSSARY.md", "path2_web/GLOSSARY.md", "GLOSSARY-MAP.md"
SOURCES = [
    ".claude/skills/tune-gates-v3/SKILL.md",
    ".claude/skills/tune-gates-v3/references/method.md",
    ".claude/skills/write-user-doc/SKILL.md",   # 票面清单之外，也有一处引用，一并查
    "docs/explain/tune-gates_v3_通俗解释.md",
    ".scratch/annotation-path2/spec.md",
    ".scratch/annotation-path2/manual.md",
    ".scratch/annotation-path2-implementation/v-s1-notes.md",
]
FULL_REF = re.compile(r"(path2(?:_web)?/GLOSSARY\.md):(\d+)")
BARE_REF = re.compile(r"(?<![\w./\-:])`?:(\d{1,3})\b")
HEAD_RE = re.compile(r"^\*\*(.+?)\*\*：\s*$")
# spec.md 里这几行没写文件名，行上的 `:NNN` 由上下文指向 path2 词表（读过上下文定的）
BARE_ONLY_LINES = {".scratch/annotation-path2/spec.md": {57, 58, 968}}
# 票面要求就地改名的词条：同一行、同一个词条，只是名字变了
RENAMED = {"detected、qualified、matched": "detected、qualified、in_hit"}


def show(base: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, check=True).stdout
    return out.decode("utf-8").splitlines()


def owner(lines: list[str], n: int) -> str:
    """第 n 行（从 1 起）所属的词条词头；词条之外返回最近的标题行。"""
    if not 1 <= n <= len(lines):
        return "（超出文件）"
    for i in range(n - 1, -1, -1):
        m = HEAD_RE.match(lines[i])
        if m:
            return m.group(1)
        if lines[i].startswith("#"):
            return lines[i].lstrip("# ")
    return "（文件头）"


def canonical(head: str) -> str:
    return head.split(" / ")[0].strip()


def collect_refs(read_lines) -> list[tuple[str, int, str, int]]:
    refs = []
    for src in SOURCES:
        for ln, line in enumerate(read_lines(src), 1):
            full = list(FULL_REF.finditer(line))
            for m in full:
                refs.append((src, ln, m.group(1), int(m.group(2))))
            if not full and ln not in BARE_ONLY_LINES.get(src, set()):
                continue
            # 同一行里裸的 :NNN 算前面最近一个文件名；没写文件名的行算 path2 词表
            for m in BARE_REF.finditer(line):
                before = [f for f in full if f.start() < m.start()]
                target = before[-1].group(1) if before else P2
                refs.append((src, ln, target, int(m.group(1))))
    return refs


def check_refs(base: str, new_p2: list[str], new_web: list[str]) -> int:
    old = {P2: show(base, P2), WEB: show(base, WEB)}
    new = {P2: new_p2, WEB: new_web}
    refs = collect_refs(lambda src: show(base, src))   # 「改前所指」：引用取自改前的文档
    now = collect_refs(lambda src: Path(src).read_text(encoding="utf-8").splitlines())
    bad = 0
    print(f"## 行号引用（共 {len(refs)} 处）")
    print("来源\t引用\t改前词头\t改后词头\t结论")
    for src, ln, target, n in refs:
        a, b = owner(old[target], n), owner(new[target], n)
        if RENAMED.get(a) == b:
            verdict = "词条按票面改名"
        elif canonical(a) != canonical(b):
            verdict = "错位"
            bad += 1
        elif a != b:
            verdict = "规范词相同，词头有变"
        else:
            verdict = "相同"
        print(f"{src}:{ln}\t{target}:{n}\t{a}\t{b}\t{verdict}")
    print("\n按来源计：")
    for src, c in sorted(Counter(r[0] for r in refs).items()):
        print(f"  {src}: {c}")
    moved_band = [r for r in refs if r[2] == P2 and 95 <= r[3] <= 102]
    print(f"指向 path2 词表 :95～:102（这段内部的行动了）的引用：{len(moved_band)}")
    bad += len(moved_band)

    print("\n本票在文档里改过的引用（改前有、现在没有的 / 现在有、改前没有的，都是词条有了自己的行，或删掉了过时的说明）：")
    for r in sorted(set(refs) - set(now)):
        print(f"  去掉 {r[0]}:{r[1]} → {r[2]}:{r[3]}")
    for r in sorted(set(now) - set(refs)):
        print(f"  新增 {r[0]}:{r[1]} → {r[2]}:{r[3]}（{owner(new[r[2]], r[3])}）")

    print("\n## 逐行比较：改前改后不同的行")
    for path in (P2, WEB):
        o, w = old[path], new[path]
        n_old, n_new = len(o), len(w)
        diff = [i + 1 for i in range(min(n_old, n_new)) if o[i] != w[i]]
        print(f"{path}: 改前 {n_old} 行，改后 {n_new} 行；前 {min(n_old, n_new)} 行里不同的行号 {diff}")
    p2_allowed = {95, 96, 97, 98, 99, 100, 101, 102, 114, 116}
    web_allowed = {5, 26, 28, 29, 46, 62}
    for path, allowed in ((P2, p2_allowed), (WEB, web_allowed)):
        o, w = old[path], new[path]
        extra = [i + 1 for i in range(min(len(o), len(w))) if o[i] != w[i] and i + 1 not in allowed]
        if extra:
            print(f"不通过：{path} 有票面之外的行变了：{extra}")
            bad += 1
    print(f"结论：错位或行变动 {bad} 处")
    return bad


def parse_entries(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """返回 (词头行号, 词头, 这个词条 _Avoid_ 里被避免的词)。"""
    out = []
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if not m:
            continue
        avoid: list[str] = []
        for j in range(i + 1, len(lines)):
            s = lines[j]
            if not s.strip() or HEAD_RE.match(s) or s.startswith("#"):
                break
            if s.startswith("_Avoid_:"):
                avoid = avoid_words(s[len("_Avoid_:"):].strip())
        out.append((i + 1, m.group(1), avoid))
    return out


def avoid_words(text: str) -> list[str]:
    """按「被避免的词打头，理由跟后面」取词：`词、词 —— 理由；词 —— 理由`，没有 —— 的整段按顿号分。"""
    segs = re.split(r"[；;]", text)
    has_dash = any(" —— " in s for s in segs)
    words = []
    for s in segs:
        if has_dash and " —— " not in s:
            continue   # 理由里的分号后半段
        left = s.split(" —— ")[0]
        left = re.sub(r"（.*", "", left)
        words += [w.strip(" `。") for w in left.split("、") if w.strip(" `。")]
    return words


def check_entries(new_p2: list[str], new_web: list[str]) -> int:
    bad = 0
    print("\n## 词条")
    entries = {P2: parse_entries(new_p2), WEB: parse_entries(new_web)}
    for path, es in entries.items():
        print(f"{path}: {len(es)} 个词头")
        for ln, head, avoid in es:
            heads = {h.strip() for h in re.split(r" / |、", head)}
            common = heads & set(avoid)
            if common:
                print(f"  不通过：:{ln} {head} 词头与 _Avoid_ 相交：{sorted(common)}")
                bad += 1
    print("词头与 _Avoid_ 相交的检查覆盖两份词表全部词条")
    by_canon = {canonical(h): (ln, h, a) for ln, h, a in entries[P2]}
    for name in ("hit", "match", "matching"):
        if name not in by_canon:
            print(f"不通过：path2 词表缺词条 {name}")
            bad += 1
        else:
            ln, h, a = by_canon[name]
            print(f"  :{ln} 词头 {h}；_Avoid_ {a}")
    if "match" not in by_canon.get("hit", (0, "", []))[2]:
        print("不通过：hit 的 _Avoid_ 里没有 match")
        bad += 1
    tiers = [h for _, h, _ in entries[WEB] if "qualified" in h and "detected" in h]
    print(f"  三档词条：{tiers}")
    if tiers != ["detected、qualified、in_hit"]:
        print("不通过：三档词条不是 detected、qualified、in_hit")
        bad += 1

    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    m = re.search(r"`path2/GLOSSARY\.md` 共 (\d+) 个词头", claude)
    print(f"  CLAUDE.md 写 {m.group(1) if m else '（没写）'} 个词头，实际 {len(entries[P2])}")
    if not m or int(m.group(1)) != len(entries[P2]):
        print("不通过：CLAUDE.md 的词头数与实际不符")
        bad += 1

    print("\n## 三个文件里剩下的 match 字样（逐行）")
    for path, lines in ((P2, new_p2), (WEB, new_web), (MAP, Path(MAP).read_text(encoding="utf-8").splitlines())):
        for i, line in enumerate(lines, 1):
            if re.search(r"match|匹配", line, re.IGNORECASE):
                print(f"{path}:{i}: {owner(lines, i)} | {line[:100]}")
    print(f"结论：词条不通过 {bad} 处")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--path2-new")
    a = ap.parse_args()
    p2 = Path(a.path2_new or P2).read_text(encoding="utf-8").splitlines()
    web = Path(WEB).read_text(encoding="utf-8").splitlines()
    bad = check_refs(a.base, p2, web) + check_entries(p2, web)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
