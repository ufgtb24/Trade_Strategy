"""票 06 生成全仓终检的两份判定清单（读过上下文定的规则都写在这里）。在仓库根目录运行。

allow_06.tsv：票 01～05 的逐行判定取并集，再加本票新判的逐行判定。行原文变了就不再命中，会落回「未归类」。
allow_path_06.tsv：整文件判定。用于已关闭的票、本批自身的记录这类不逐行看的文件，和行里有结果数字的落盘账本。
"""
import re
from pathlib import Path

EV = ".scratch/match-hit-rename-implementation/evidence"
OLD = [f"{EV}/0{n}/allow_0{n}.tsv" for n in range(1, 6)]
NEW_SENSE = "新义本身"
RECORD = "本批改名的指针（改名 spec 的路径、改名这件事本身）"
AVOID = "词表 _Avoid_ 里写明的旧说法（票面要求）"
ARCHIVE = "归档或已关闭票的文件名（统计配对 11-control-matching、决定票 08 blind-match-list）"
GENERIC = "中文「匹配」泛指（只匹配真目录、版本不匹配、用途匹配、匹配词）"
SAME = "「一致 / 等于」：测试名"

# 文件 → 该文件的默认类别，以及按片段判的例外（读过全部这些行）
LINE_RULES = {
    ".scratch/annotation-path2/manual.md": (NEW_SENSE, {}),
    ".scratch/annotation-path2/spec.md": (NEW_SENSE, {
        "全仓 match → hit": RECORD, "随 match-hit-rename": RECORD, "11-control-matching": ARCHIVE}),
    ".scratch/annotation-path2/map.md": (NEW_SENSE, {"08-blind-match-list": ARCHIVE}),
    "path2/GLOSSARY.md": (NEW_SENSE, {"_Avoid_: match ——": AVOID, "matched baseline ——": AVOID}),
    "GLOSSARY-MAP.md": (NEW_SENSE, {}),
    "AGENTS.md": (GENERIC, {}),      # CLAUDE.md 的软链，git 里算两个文件；这两行就是票 05 判过的用途匹配、匹配词
    ".gitignore": (GENERIC, {}),
    "docs/setup/ubuntu_tkinter_font_fix.md": (GENERIC, {}),
    "tests/scripts/test_make_train_snapshot.py": (SAME, {}),
}
CLOSED = "已关闭的票（共用执行边界第 8 条）"
WHOLE_FILE = [
    (".scratch/match-hit-rename/", "本批改名自身的记录（spec、票面、拆分总览里的新旧对照）"),
    (".scratch/match-hit-rename-implementation/", "本批改名自身的记录（spec、票面、拆分总览里的新旧对照）"),
    (".scratch/annotation-path2/research/", "研究目录（共用执行边界第 8 条）"),
    (".scratch/annotation-path2/prototypes/", "已 resolved 决定票的原型（历史资产，依赖旧数据格式）"),
    (".scratch/annotation-path2/issues/01-structured-annotation.md", CLOSED),
    (".scratch/annotation-path2/issues/05-measure-in-context.md", CLOSED),
    (".scratch/annotation-path2/issues/08-blind-match-list.md", CLOSED),
    (".scratch/annotation-path2/issues/14-naming.md", CLOSED),
    (".scratch/annotation-path2/issues/15-display-consistency.md", CLOSED),
    (".scratch/annotation-path2-implementation/issues/01-snapshot-fingerprint-and-annotation-dir.md", CLOSED),
    (".scratch/annotation-path2-implementation/issues/11-app-and-compare-overlay.md", CLOSED),
    (".scratch/annotation-path2/issues/04-final-check-count.md", ARCHIVE),
    ("path2_web_ui/package-lock.json", "第三方包名（minimatch、picomatch、balanced-match）"),
    ("experiments/news_sentiment_benchmark/", "别的系统（新闻情感评测，正则变量与英文说明）"),
    ("docs/sample_usage/bb_v1.jsonl", "落盘账本的值（共用执行边界第 7 条：一行旧义说明文字，三行统计配对）"),
]

rows = set()
for f in OLD:
    for raw in Path(f).read_text(encoding="utf-8").splitlines():
        if raw.strip() and not raw.startswith("#"):
            rows.add(raw)
for rel, (default, exceptions) in LINE_RULES.items():
    for line in Path(rel).read_text(encoding="utf-8").splitlines():
        if re.search(r"match|匹配", line, re.IGNORECASE):
            cat = next((c for key, c in exceptions.items() if key in line), default)
            rows.add(f"{rel}\t{line.strip()}\t{cat}")
Path(f"{EV}/06/allow_06.tsv").write_text(
    "# 票 06 全仓终检的逐行判定：票 01～05 取并集 + gen_allow.py 里的规则\n" + "\n".join(sorted(rows)) + "\n", encoding="utf-8")
Path(f"{EV}/06/allow_path_06.tsv").write_text(
    "# 票 06 全仓终检的整文件判定\n" + "\n".join(f"{p}\t{c}" for p, c in WHOLE_FILE) + "\n", encoding="utf-8")
print(len(rows), len(WHOLE_FILE))
