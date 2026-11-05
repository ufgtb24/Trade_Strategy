"""把残留检查的「未归类」行按读过上下文定下的规则写成 allow_05.tsv（格式见 residual_check.py）。分不进去的行报错。

在仓库根目录运行。只收 CLAUDE.md、docs/path2、docs/explain、docs/feature_candidates.md。
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STALE = "docs/path2 过时旧名（代码里已没有，单列）"
GENERIC = "中文「匹配」泛指"
PAIRING = "统计里的配对"
PATHS = "路径（研究目录、归档里的文件名，路径不动）"

# (路径前缀, 该行正则, 类别)：读过上下文定的，按优先级
RULES = [
    ("docs/path2/", re.compile(r"MatchContext"), STALE),
    ("docs/path2/guide/hits-and-results.md", re.compile(r'"图匹配"理论'), GENERIC + "（图匹配这门理论的名字）"),
    ("CLAUDE.md", re.compile(r"用途匹配"), GENERIC + "（评估用途对得上）"),
    ("CLAUDE.md", re.compile(r"当匹配词"), GENERIC + "（skill 触发词）"),
    ("docs/explain/next_mode_ptr_advance_通俗解释.md", re.compile(r"SKIP_TILL_NEXT_MATCH"),
     "docs/explain 过时旧名（代码里已没有的枚举，单列）"),
    ("docs/explain/path2_pattern_framework_plain.md", re.compile(r"fuzzy (匹配|matching)"), "「一致 / 等于」的通用说法（fuzzy matching）"),
    ("docs/feature_candidates.md", re.compile(r"e5b_matching\.py|11-control-matching\.md"), PATHS),
    ("docs/feature_candidates.md", re.compile(r"层匹配|非匹配|匹配后|必须匹配|不匹配时间|匹配方式|时间匹配|同期匹配|要匹配|匹配粒度"), PAIRING),
]


def main() -> int:
    out = subprocess.run(
        [sys.executable, str(HERE / "residual_check.py"), "area", "CLAUDE.md", "docs/path2", "docs/explain", "docs/feature_candidates.md"],
        capture_output=True, text=True,
    ).stdout
    rows = []
    bad = 0
    for raw in out.splitlines():
        m = re.match(r"  ((?:CLAUDE\.md|docs/[^:]+)):(\d+): (.*)$", raw)
        if not m:
            continue
        rel, _, text = m.groups()
        for prefix, rx, cat in RULES:
            if rel.startswith(prefix) and rx.search(text):
                rows.append(f"{rel}\t{text}\t{cat}")
                break
        else:
            print("分不进去：", rel, _, text[:80])
            bad += 1
    head = "# 票 05 人工判定清单：读过上下文判为可留的行。格式：相对路径<TAB>该行去掉首尾空白后的原文<TAB>类别\n"
    (HERE / "allow_05.tsv").write_text(head + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"写了 {len(rows)} 行，分不进去 {bad} 行")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
