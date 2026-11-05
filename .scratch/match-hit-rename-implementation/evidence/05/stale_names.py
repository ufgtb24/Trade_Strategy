"""列出 docs/path2 里提到、但现行代码里已经找不到的代码名（只读），供另起票修。

在仓库根目录运行。取反引号里和围栏代码块里的标识符：驼峰（KleeneSpec）或带下划线（role_index）的算代码名，
全部小写且不带下划线的普通词不看（噪声太大）。在 path2、path2_apps、path2_web、path2_web_ui/src、scripts/path2 里
按整词 grep，一处也没有就列出来，附提到它的文件与次数。
只说明「代码里没有这个名字」，不判断那段文档是否还对；例子里的局部变量、假想函数也可能落进来，人读时要分。

整词比对有盲区：词在别处还在，这里就漏（hit.event_id：PatternHit 上已没有 event_id，但 path2_web 里还有这个词）。
所以另外两节不靠比对：CLAUDE.md「编码规范」点名退役的身份词一律列；孤立节点「出口过滤」这个说法列出所在行
（path2/dag/engine.py 的 analyze 现在写的是「孤立未消费 node 不求解,hits 直通无出口过滤」）。
"""
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOTS = ["path2", "path2_apps", "path2_web", "path2_web_ui/src", "scripts/path2"]
DOCS = sorted(Path("docs/path2").rglob("*.md"))
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
CODELIKE = re.compile(r"[a-z][A-Z]|[A-Z][a-z].*[A-Z]|_")
FENCE = re.compile(r"^\s*(```|~~~)")
RETIRED = ["event_id", "span_id", "class_id", "source_tag"]

mentions: dict[str, Counter] = defaultdict(Counter)
for f in DOCS:
    in_fence = False
    for line in f.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        parts = [line] if in_fence else re.findall(r"`([^`]+)`", line)
        for part in parts:
            for w in IDENT.findall(part):
                if CODELIKE.search(w) and len(w) > 3:
                    mentions[w][f.as_posix().removeprefix("docs/path2/")] += 1

code_words: set[str] = set()
listed = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "--", *ROOTS], capture_output=True, text=True, check=True).stdout
for rel in listed.splitlines():
    p = Path(rel)
    if p.suffix not in {".py", ".ts", ".vue", ".yaml", ".md", ".json"}:
        continue
    try:
        code_words.update(IDENT.findall(p.read_text(encoding="utf-8")))
    except UnicodeDecodeError:
        pass

stale = {w: c for w, c in mentions.items() if w not in code_words}
print(f"docs/path2 里的代码名 {len(mentions)} 个，代码里找不到 {len(stale)} 个（按提到次数排）\n")
for w, c in sorted(stale.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
    where = ", ".join(f"{k} {v}" for k, v in c.most_common())
    print(f"{sum(c.values()):4d}  {w}  ({where})")

print("\n## CLAUDE.md 点名退役的身份词（docs/path2 全文按整词计，含代码里还有这个词的）\n")
for w in RETIRED:
    rows = Counter()
    for f in DOCS:
        n = len(re.findall(rf"\b{w}\b", f.read_text(encoding="utf-8")))
        if n:
            rows[f.as_posix().removeprefix("docs/path2/")] = n
    print(f"{sum(rows.values()):4d}  {w}  ({', '.join(f'{k} {v}' for k, v in rows.most_common())})")

print("\n## 说法过时：孤立节点靠「出口过滤」丢残缺 hit（现在是孤立未消费 node 不求解，没有出口过滤）\n")
for f in DOCS:
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if "出口" in line:
            print(f"  {f.as_posix().removeprefix('docs/path2/')}:{i}")
