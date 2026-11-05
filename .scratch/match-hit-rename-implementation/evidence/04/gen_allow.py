"""把残留检查的「未归类」行按读过上下文定下的规则写成 allow_04.tsv（格式见 evidence/01/residual_check.py）。分不进去的行报错。"""
import re, subprocess, sys
from pathlib import Path
E = Path(".scratch/match-hit-rename-implementation/evidence")
res = subprocess.run([sys.executable, str(E/"01/residual_check.py"), "area", ".claude/skills", "--detail"], capture_output=True, text=True).stdout
rows = []
sec = None
for ln in res.splitlines():
    if ln.startswith("## "):
        sec = ln[3:]
    elif sec == "未归类" and ln.startswith("  "):
        rel, no, text = ln.strip().split(":", 2)
        rows.append((rel, text.strip()))
STAT = "统计里的配对（层匹配差等，同日或同层普通买入对照）"
SAME = "「一致 / 等于」的通用说法"
CN = "中文「匹配」泛指（pid、锚点、档位、指纹、代码、分类、区间等对得上）"
RE_ = "正则与模式匹配"
FW = "测试框架"
WL = "web-loop 工作流脚本"
T03 = "归票 03（web-loop 示例第 62 行，本票不动）"
RULES = [
    (T03, lambda r, t: r.endswith("web-loop/examples/path2.md")),
    (WL, lambda r, t: "/web-loop/" in r),
    (STAT, lambda r, t: "层匹配" in t and "test_tune.py" not in r or r.endswith("scripts/scoring.py") or "matched-difference-window" in t
        or "_pool_matching_" in t or "_date_matching_" in t),
    (STAT, lambda r, t: "test_tune.py" in r and "层匹配" in t),
    (RE_, lambda r, t: re.search(r"_FC_HEAD\.match|_FC_CLOSED\.match|_PLAIN_WORD\.match", t)),
    (FW, lambda r, t: "test_validate.py" in r and "match" in t and ("_refused" in t or "raises" in t)),
    (FW, lambda r, t: 'raises(UsageError, match="精确匹配")' in t),
    (SAME, lambda r, t: re.search(r"def test_\w*match\w*|test_\w+_matches?_\w+|check_\w*matches\w*|\*\*match\b|set\(match\)|in match\.items|;match 按顶层|does-not-match", t)),
    (CN, lambda r, t: "匹配" in t),
]
out = ["# 票 04 人工判定清单（照票 01 的格式，只收 .claude/skills）：读过上下文判为可留的行。格式：相对路径<TAB>该行去掉首尾空白后的原文<TAB>类别"]
miss = []
for rel, text in rows:
    assert "\t" not in text, rel
    for cat, fn in RULES:
        if fn(rel, text):
            out.append(f"{rel}\t{text}\t{cat}")
            break
    else:
        miss.append((rel, text))
for m in miss:
    print("分不进去", m)
Path(E/"04/allow_04.tsv").write_text("\n".join(out) + "\n", encoding="utf-8")
print(len(rows), "行未归类；写入", len(out) - 1, "；分不进去", len(miss))
