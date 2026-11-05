"""match → hit 改名的残留检查（只读）：列出指定目录里还剩的 match 字样与中文「匹配」，按拆分总览
「允许保留的用法」分类计数；分不进任何一类的列为「未归类」，那些就是旧义残留或要人工看的地方。

票 06 的改版：在票 05 那份上加了 report 子命令和 --allow-path，分类规则没动。

用法（在仓库根目录）：
    python <本文件> report <路径> [<路径> ...] [--allow <人工判定清单>] [--allow-path <整文件判定清单>]
        全仓终检用：按类别与区域给条数，见下面「report 子命令」一段。退出码：有「未归类」为 1，否则 0。
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

整文件判定清单（--allow-path，票 06 加）：每行 `<路径或前缀>\t<类别>`。用于已关闭的票这类不逐行看的文件，
也用于行里有结果数字、不该把原文抄进证据的文件。

report 子命令（票 06 加）：按类别与区域给条数，再逐行列出范围内留下的行。为了不把行里的数字带进证据，每行只留
第一处 match 字样前后各 24 个字符，数字一律打码成 #；「不在范围的地方」只给条数。

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
# 这里只放全仓通用、不会掩盖旧义的写法；只对应个别行的判定一律进 --allow 清单。
CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("正则与模式匹配", re.compile(
        r"\bre\.(?:match|fullmatch)\b|\.fullmatch\(|\b[A-Za-z_]*_RE\.match\(|\b(?:pat|rx|regex|m_re)\.match\(|"
        r"\bfnmatch\w*|\.match\(/|\bmatchAll\b|\bmatchMedia\b", re.IGNORECASE)),
    ("测试框架", re.compile(
        r"\b(?:raises|warns)\([^)]*\bmatch=|\bmatch=['\"][^'\"]*['\"]|\btoMatch(?:Object|Snapshot|InlineSnapshot)?\b")),
    ("mismatch 一族", re.compile(r"\w*mismatch\w*", re.IGNORECASE)),
    ("「一致 / 等于」的通用说法", re.compile(
        r"\btest_\w*_match(?:es)?_(?:direct|brute(?:_force)?)\w*|\bcheck_study_matches\b|\bledger\.latest\(\*\*match\)")),
    ("统计里的配对", re.compile(
        r"\bmatched_\w+|\w+_matched\w*|\bbaseline_matching\b|\bmatched_difference\b|\bmatched baseline\b")),
    ("web-loop 工作流脚本", re.compile(r"\bmatchesIssueId\b|\bmatchExpect\b|\bbadMatch\b|\bmatchesSubgoal\b")),
    ("新义本身", re.compile(r"\bmatch tag\b|\bunmatched\b")),
]

# 中文「匹配」的分类：只放字面就是泛指的说法；anchor 配对、边关系成立这类要读上下文的，进 --allow 清单
CN_CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("中文「匹配」·泛指（正则、前缀、最左）", re.compile(r"前缀匹配|正则匹配|最左匹配")),
]


def _strip_categories(line: str, cats) -> tuple[str, list[str]]:
    found = []
    for name, rx in cats:
        new = rx.sub(" ", line)
        if new != line:
            found.append(name)
            line = new
    return line, found


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


def load_allow_path(path: str | None) -> list[tuple[str, str]]:
    """读整文件判定清单，返回 (路径或前缀, 类别)。"""
    if not path:
        return []
    rows = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.strip() and not raw.startswith("#"):
            prefix, cat = raw.split("\t")
            rows.append((prefix, cat))
    return rows


REGIONS = [
    ("词表", ("path2/GLOSSARY.md", "path2_web/GLOSSARY.md", "GLOSSARY-MAP.md")),
    ("path2/", ("path2/",)), ("path2_apps/", ("path2_apps/",)), ("path2_web/", ("path2_web/",)),
    ("path2_web_ui/", ("path2_web_ui/",)), ("scripts/", ("scripts/",)), ("tests/", ("tests/",)),
    (".claude/skills/", (".claude/skills/",)), (".claude/ 其他", (".claude/",)),
    ("CLAUDE.md、AGENTS.md", ("CLAUDE.md", "AGENTS.md")),
    ("docs/path2/", ("docs/path2/",)), ("docs/explain/", ("docs/explain/",)),
    ("docs/feature_candidates.md", ("docs/feature_candidates.md",)), ("docs/ 其他", ("docs/",)),
    (".scratch/annotation-path2*", (".scratch/annotation-path2",)),
    (".scratch/match-hit-rename*", (".scratch/match-hit-rename",)), (".scratch/ 其他", (".scratch/",)),
    ("其他", ("",)),
]


def region_of(rel: str) -> str:
    """相对路径属于 REGIONS 的哪个区域，取第一个前缀对上的。"""
    return next(name for name, prefixes in REGIONS if rel.startswith(prefixes))


def masked(loc_rel: str, i: int, line: str) -> str:
    """位置加第一处 match 字样前后各 24 字，数字打码成 #。"""
    m = MATCH_IN_WORD.search(line) or CN_RE.search(line)
    snippet = line[max(0, m.start() - 24):m.end() + 24].strip()
    return f"{loc_rel}:{i}: …{re.sub(r'[0-9]', '#', snippet)}…"


def cmd_report(paths: list[str], line_allow_file: str | None, path_allow_file: str | None) -> int:
    """全仓终检：line_allow_file 是逐行判定（--allow），path_allow_file 是整文件判定（--allow-path）。有「未归类」返回 1。"""
    allow = load_allow(line_allow_file)
    allow_paths = load_allow_path(path_allow_file)
    by_cat: dict[str, Counter] = defaultdict(Counter)
    rows: dict[str, list[str]] = defaultdict(list)
    n_lines = 0
    for f in iter_files(paths):
        rel = f.as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if not (MATCH_IN_WORD.search(line) or CN_RE.search(line)):
                continue
            n_lines += 1
            region = region_of(rel)
            scope = scope_of(rel)
            if scope:
                by_cat[scope][region] += 1
                continue
            whole = next((cat for prefix, cat in allow_paths if rel.startswith(prefix)), None)
            if whole:
                by_cat[whole][region] += 1
                rows[whole].append(masked(rel, i, line))
                continue
            cats, left = classify(line)
            if (rel, line.strip()) in allow:
                cats, left = [allow[(rel, line.strip())]], False
            for c in (["未归类"] if left else cats):
                by_cat[c][region] += 1
                rows[c].append(masked(rel, i, line))
    print(f"全部受管文本文件里含 match / 匹配 字样的行：{n_lines}（一行可算进几类，下面的条数加起来会多于它）")
    print("\n## 按类别与区域的条数")
    for cat in sorted(by_cat, key=lambda c: (c != "未归类", not c.startswith("不在范围"), c)):
        detail = "、".join(f"{r} {n}" for r, n in sorted(by_cat[cat].items(), key=lambda kv: -kv[1]))
        print(f"{cat}：{sum(by_cat[cat].values())}（{detail}）")
    if not by_cat.get("未归类"):
        print("未归类：0")
    print("\n## 逐行（范围内；每行只留前后各 24 字，数字打码）")
    for cat in sorted(rows, key=lambda c: (c != "未归类", c)):
        print(f"\n### {cat}")
        for r in rows[cat]:
            print("  " + r)
    return 1 if by_cat.get("未归类") else 0


def iter_files(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        q = Path(p)
        if q.is_file():
            out.append(q)
            continue
        # 票 05 改：-c core.quotepath=off。原版 git 把中文文件名转义成带引号的八进制，is_file() 为假，这些文件被静默跳过
        res = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "--", str(q)], capture_output=True, text=True, check=True)
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
            if (rel, line.strip()) in allow:   # 票 05 改：读过上下文的判定优先，正则把「unmatched satisfy」认成新义就是这样纠正
                cats, left = [allow[(rel, line.strip())]], False
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
    r = sub.add_parser("report")
    r.add_argument("paths", nargs="+")
    r.add_argument("--allow")
    r.add_argument("--allow-path")
    args = ap.parse_args()
    if args.cmd == "report":
        return cmd_report(args.paths, args.allow, args.allow_path)
    if args.cmd == "area":
        return cmd_area(args.paths, args.allow, args.detail, args.exclude)
    return cmd_api(args.root)


if __name__ == "__main__":
    sys.exit(main())
