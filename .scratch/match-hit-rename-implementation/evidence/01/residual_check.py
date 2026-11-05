"""match → hit 改名的残留检查（只读）：列出指定目录里还剩的 match 字样与中文「匹配」，按拆分总览
「允许保留的用法」分类计数；分不进任何一类的列为「未归类」，那些就是旧义残留或要人工看的地方。

用法（在仓库根目录）：
    python <本文件> area <路径> [<路径> ...] [--allow <人工判定清单>] [--exclude <路径前缀>] [--detail]
        对给定的文件或目录逐行查 match / matches / matched / matching（不分大小写、含在标识符里的）
        与中文「匹配」，输出各类计数；--detail 再逐行列出每一类。退出码：有「未归类」为 1，否则 0。
    python <本文件> api [--root <目录>]
        全仓 Python 里查 01 改掉的 Python 接口名是否还在：PatternMatch、match_forward_returns、
        match_forward_drawdowns、match_first_passage、`.matches` 属性访问（含 app 的 matches() 调用）、
        `.match_id` 属性访问、从 path2 / path2_apps 导入函数 matches。
        JSON 键字面量 "matches" / "match_id"（含 `["matches"]`、`.get("matches")`）单列，留给 02。
        「不在范围的地方」（历史与别的系统）单列，不算残留。退出码：有残留为 1。

人工判定清单（--allow）：每行 `<相对路径>\t<该行去掉首尾空白后的原文>\t<类别>`，# 开头为注释。
用来登记正则分不出来、读上下文判为可留的行（例如边关系「成立」意义上的「匹配」）。行原文变了就不再命中，
会重新落回「未归类」，由当时的执行者再看一次。各票可以复制一份、追加自己区域的条目，存进自己的 evidence。

分类规则见下面 CATEGORIES；顺序即优先级，一行里只要有一处没被任何一类认领，就整行进「未归类」。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)
MATCH_IN_WORD = re.compile(r"match", re.IGNORECASE)
CN_RE = re.compile(r"匹配")

# 不在范围的地方（拆分总览「允许保留的用法」最后第二行）：路径前缀
OUT_OF_SCOPE = (
    "BreakoutStrategy/", "tests/mining/", "tests/news_sentiment/", "scripts/experiments/",
    "scripts/implementation_board.py", "scripts/wayfinder_board.py", "docs/research/", "docs/tmp/",
    "docs/legacy/", "docs/superpowers/", "docs/agents/", ".scratch-archive/", "configs/security_names.csv",
)
EVIDENCE_RE = re.compile(r"^\.scratch/[^/]+/evidence/")   # 各 effort 的 evidence（含本批各票自己的检查脚本）
# 拿不准、单列：不属于允许列表任何一类，也不硬改，由完成记录单独交代
UNSURE = {
    ".scratch/annotation-path2/scripts/01-dump-proto-data.py":
        "已 resolved 的决定票 01 的原型取数脚本（历史资产，依赖已不在的 chart_workflow）",
}


def scope_of(rel: str) -> str | None:
    """不在范围的路径返回类别名，范围内返回 None。"""
    if rel in UNSURE:
        return f"拿不准、单列（{UNSURE[rel]}）"
    if rel.startswith(OUT_OF_SCOPE) or EVIDENCE_RE.match(rel):
        return "不在范围的地方"
    return None

# 英文 match 字样的分类：(类别名, 作用于整行的正则)。命中的片段从行里抠掉，抠完还剩 match 字样才算没认领。
CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("正则与模式匹配", re.compile(
        r"\bre\.(?:match|fullmatch)\b|\.fullmatch\(|\b[A-Za-z_]*_RE\.match\(|\b(?:pat|rx|regex|m_re)\.match\(|"
        r"\bfnmatch\w*|\.match\(/|\bmatchAll\b|\bmatchMedia\b|\bno pkl matched\b", re.IGNORECASE)),
    ("测试框架", re.compile(
        r"\b(?:raises|warns)\([^)]*\bmatch=|\bmatch=['\"][^'\"]*['\"]|\btoMatch(?:Object|Snapshot|InlineSnapshot)?\b")),
    ("mismatch 一族", re.compile(r"\w*mismatch\w*", re.IGNORECASE)),
    ("「一致 / 等于」的通用说法", re.compile(
        r"\btest_\w*_match(?:es)?_(?:direct|brute(?:_force)?|reference|scalar_formula|instance|derived|end_anchor_kind|"
        r"v1_signature|detector_signature)\w*|\b_pass_when_declaration_matches_instance\b|"
        r"\btest_\w*_must_match_derived\b|\btest_negation_matches_brute\b|\bcheck_study_matches\b|"
        r"\bledger\.latest\(\*\*match\)|\btest_build_writes_matching_manifest\b|"
        r"既有测试只 match 字段名")),
    ("统计里的配对", re.compile(
        r"\bmatched_\w+|\w+_matched\w*|\bbaseline_matching\b|\bmatched_difference\b|\bmatched baseline\b")),
    ("web-loop 工作流脚本", re.compile(r"\bmatchesIssueId\b|\bmatchExpect\b|\bbadMatch\b|\bmatchesSubgoal\b")),
    ("新义本身", re.compile(r"\bmatch tag\b|\bunmatched\b")),
]

# 中文「匹配」的分类：泛指的说法（正则 / 前缀 / 名字 / 签名 / anchor 配对 / 边关系成立）
CN_CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("中文「匹配」·泛指（模式、前缀、名字、签名）", re.compile(
        r"前缀匹配|正则匹配|最左匹配|grep 找到匹配|精确匹配\s*\w+\s*签名|名字?匹配|名匹配|误匹配|无匹配 → KeyError|"
        r"帧匹配|anchor_kind 匹配|匹配 anchor_kind|anchor_kind 不匹配|只匹配 anchor_kind")),
    ("中文「匹配」·泛指（anchor 配对）", re.compile(r"anchor 匹配|形态不匹配|src_10#0 不匹配|与它匹配的伙伴")),
]


def _strip_categories(line: str, cats) -> tuple[str, list[str]]:
    hit_cats = []
    for name, rx in cats:
        new = rx.sub(" ", line)
        if new != line:
            hit_cats.append(name)
            line = new
    return line, hit_cats


def classify(line: str) -> tuple[list[str], bool]:
    """返回 (认领到的类别, 是否还有没认领的 match / 匹配)。"""
    rest, cats = _strip_categories(line, CATEGORIES)
    rest, cn_cats = _strip_categories(rest, CN_CATEGORIES)
    left = bool(MATCH_IN_WORD.search(rest)) or bool(CN_RE.search(rest))
    return cats + cn_cats, left


def load_allow(path: str | None) -> dict[tuple[str, str], str]:
    if not path:
        return {}
    out = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        rel, text, cat = raw.split("\t")
        out[(rel, text)] = cat
    return out


def iter_files(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        q = Path(p)
        if q.is_file():
            out.append(q)
            continue
        res = subprocess.run(["git", "ls-files", "--", str(q)], capture_output=True, text=True, check=True)
        out += [Path(x) for x in res.stdout.splitlines()]
    return sorted(set(f for f in out if f.is_file() and f.suffix not in {".png", ".pkl", ".jpg", ".ico"}))


def cmd_area(paths: list[str], allow_path: str | None, detail: bool, exclude: list[str]) -> int:
    allow = load_allow(allow_path)
    counts: Counter = Counter()
    rows: dict[str, list[str]] = defaultdict(list)
    for f in iter_files(paths):
        rel = f.as_posix()
        if any(rel.startswith(e) for e in exclude):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if not (MATCH_IN_WORD.search(line) or CN_RE.search(line)):
                continue
            loc = f"{rel}:{i}: {line.strip()}"
            scope = scope_of(rel)
            if scope:
                counts[scope] += 1
                rows[scope].append(loc)
                continue
            cats, left = classify(line)
            if left and (rel, line.strip()) in allow:
                cats, left = cats + [allow[(rel, line.strip())]], False
            if left:
                counts["未归类"] += 1
                rows["未归类"].append(loc)
            else:
                for c in cats:
                    counts[c] += 1
                    rows[c].append(loc)
    print("按行计（一行可能同时算进几类）：")
    for c, n in sorted(counts.items(), key=lambda kv: (kv[0] != "未归类", kv[0])):
        print(f"  {c}: {n}")
    if not counts:
        print("  （没有 match 字样）")
    shown = rows.keys() if detail else (["未归类"] if "未归类" in rows else [])
    for c in shown:
        print(f"\n## {c}")
        for r in rows[c]:
            print("  " + r)
    return 1 if counts.get("未归类") else 0


API_PATTERNS = [
    ("PatternMatch", re.compile(r"\bPatternMatch\b")),
    ("match_forward_returns", re.compile(r"\bmatch_forward_returns\b")),
    ("match_forward_drawdowns", re.compile(r"\bmatch_forward_drawdowns\b")),
    ("match_first_passage", re.compile(r"\bmatch_first_passage\b")),
    (".matches 属性访问", re.compile(r"\.matches\b(?!\?)")),   # 含 app.matches(...) 调用；JS 的 el.matches?.( 不算
    (".match_id 属性访问", re.compile(r"\.match_id\b")),
    ("导入函数 matches", re.compile(r"\bfrom\s+path2(?:_apps)?[\w.]*\s+import\b.*\bmatches\b")),
]
JSON_KEY_RE = re.compile(r"[\"']match(?:es|_id)[\"']")


def cmd_api(root: str) -> int:
    res = subprocess.run(["git", "-C", root, "ls-files", "*.py"], capture_output=True, text=True, check=True)
    bad: list[str] = []
    out_scope: list[str] = []
    unsure: list[str] = []
    json_keys: list[str] = []
    for rel in res.stdout.splitlines():
        f = Path(root) / rel
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            loc = f"{rel}:{i}: {line.strip()}"
            names = [n for n, rx in API_PATTERNS if rx.search(line)]
            # JSON 路径写法（summary.matches、analysis.matches 之类）出现在注释里时是 JSON 键，不是属性访问
            if ".matches 属性访问" in names and re.search(r"\b(?:summary|analysis)\.matches\b", line) \
                    and not re.search(r"(?<!summary)(?<!analysis)\.matches\b", line):
                names.remove(".matches 属性访问")
            scope = scope_of(rel)
            if names:
                row = f"{loc}  [{', '.join(names)}]"
                (bad if scope is None else unsure if rel in UNSURE else out_scope).append(row)
            if JSON_KEY_RE.search(line) and scope is None:
                json_keys.append(loc)
    print(f"旧接口名残留（范围内）：{len(bad)}")
    for r in bad:
        print("  " + r)
    print(f"\n拿不准、单列（不改，完成记录交代）：{len(unsure)}")
    for r in unsure:
        print("  " + r)
    print(f"\n不在范围的地方（历史与别的系统，不改）：{len(out_scope)}")
    for r in out_scope:
        print("  " + r)
    print(f"\nJSON 键字面量 \"matches\" / \"match_id\"（留给 02）：{len(json_keys)}")
    for r in json_keys:
        print("  " + r)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("area")
    a.add_argument("paths", nargs="+")
    a.add_argument("--allow")
    a.add_argument("--detail", action="store_true")
    a.add_argument("--exclude", action="append", default=[], help="跳过的路径前缀（如 path2/GLOSSARY.md）")
    b = sub.add_parser("api")
    b.add_argument("--root", default=".")
    args = ap.parse_args()
    if args.cmd == "area":
        return cmd_area(args.paths, args.allow, args.detail, args.exclude)
    return cmd_api(args.root)


if __name__ == "__main__":
    sys.exit(main())
