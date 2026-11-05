"""票 03 的改名脚本：把 path2_web_ui 的 src、tests、e2e 里旧义 match 换成 hit、第三档换成 in_hit。

只跑一次，留在证据里说明这批替换怎么来的；之后的手工修改不在这里。用法（在 worktree 根目录）：
    python rename_frontend.py

分四层，顺序不能换：
1. 跳过：与本概念无关的文件和行（参数快照比较的 match 字段、前缀匹配、对照 tag 词表）。
2. 逐文件特例：同一个词在那个文件里另有所指（UnionCell.matched、旧义的 unmatched、中文「匹配」的改写）。
3. 标识符、CSS 类名：照拆分总览的改名对照，派生名按同一条规则推出。
4. 兜底的单词：'matched' 字面量和 matched、matches、match。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("path2_web_ui")
DIRS = ("src", "tests", "e2e")
SUFFIXES = {".ts", ".vue", ".py"}

# ── 1. 跳过 ──────────────────────────────────────────────────────────────────
SKIP_FILES = {
    "tests/params-chip.spec.ts",            # 参数快照比较的 match 字段（允许列表「一致 / 等于」）
    "tests/view.symbol-search.spec.ts",     # 前缀匹配
    "src/components/ParamsChip.vue",        # 同参数快照比较
    "src/components/workingCopyLayers.ts",  # str.match
}
SKIP_LINE = re.compile(
    r"export interface ParamsDiffResp"                # types.ts：参数快照比较的 match 字段
    r"|const TAG_WORDS\b"                             # e2e：compare 下不出现对照 tag 的词表（新义）
    r"|for \(const t of \['missing', 'matched'"       # 同上（vitest）
    r"|pattern_id match'"                             # view.multi：symbol、pattern_id 一致
    r"|SUB_GRID_LEFT / RIGHT match chart\.ts"         # subGeometry：与硬编码值一致
)

# ── 2. 逐文件特例（子串替换，按顺序）──────────────────────────────────────────
HAS_HIT_COMMON = [
    ("at least one matched", "at least one has-hit"),
    ("only matched cell", "only has-hit cell"),
]
FILE_SPECIAL: dict[str, list[tuple[str, str]]] = {
    # UnionCell.matched 的意思是「这个 pattern 在这只股票上有 hit」，不是事件第三档
    "src/stores/view.ts": [
        ("num: number | null; fr: number | null; fd: number | null; matched: boolean",
         "num: number | null; fr: number | null; fd: number | null; hasHit: boolean"),
        ("matched: (pp?.summary?.hits ?? 0) > 0", "hasHit: (pp?.summary?.hits ?? 0) > 0"),
        ("if (cell.matched)", "if (cell.hasHit)"),
        ("&& c.matched)", "&& c.hasHit)"),
        ("focusMatch(bracket / 命中匹配 click)", "focusHit(bracket / hit 列表 click)"),
        ("// 匹配 trace 展开的唯一判据", "// hit trace 展开的唯一判据"),
        ("sidebar「命中匹配」列表", "sidebar hit 列表"),
        ("_previewHits", "_previewApplies"),   # 布尔：preview 对得上当前股票与 pattern，不是 hit
    ],
    "src/components/SidebarResultList.vue": [
        ("{ matched: cell.matched }", "{ 'has-hit': cell.hasHit }"),
        ("td.col.matched", "td.col.has-hit"),
        ("区别于绿 matched", "区别于绿 has-hit"),
        ("(#dcfce7,matched)", "(#dcfce7,has-hit)"),
    ],
    "src/components/DetailSidebar.vue": [
        ("<!-- 命中匹配列表:", "<!-- hit 列表:"),
        ("// ─── 匹配 trace 双向高亮", "// ─── hit trace 双向高亮"),
        ("点击命中匹配列表行", "点击 hit 列表行"),
    ],
    "src/render/visible.ts": [
        ("所有匹配内实例", "所有 hit 内实例"),
        ("matched: Set<string>, qualified", "inHit: Set<string>, qualified"),
        ("if (matched.has(", "if (inHit.has("),
        ("export function matchedIds(", "export function inHitIds("),
    ],
    "src/components/CandidateStatusBar.vue": [
        ("Sort matches by start_idx to match packBrackets", "Sort hits by start_idx to stay aligned with packBrackets"),
    ],
    "tests/view.multi.spec.ts": HAS_HIT_COMMON + [
        ("bo_only matched", "bo_only has hit"),
        ("bbb matched", "bbb has hit"),
        ("bbb unmatched", "bbb no hit"),
        ("both unmatched", "both no hit"),
        ("both have at least one matched", "both have at least one has-hit"),
        ("被 matched 闸挡掉", "被 hit 闸挡掉"),
    ],
    "tests/components/SidebarResultList.multi.spec.ts": HAS_HIT_COMMON + [
        ("matched 类只在 num > 0 时加(num=0 无 matched", "has-hit 类只在 num > 0 时加(num=0 无 has-hit"),
        ("toContain('matched')", "toContain('has-hit')"),
        ("at least one matched visible pattern", "at least one has-hit visible pattern"),
        ("bbb matched", "bbb has hit"),
        ("bo_only matched", "bo_only has hit"),
    ],
    "tests/unionRows.spec.ts": [
        ("and matched bool", "and hasHit bool"),
        (".matched)", ".hasHit)"),
        ("CCC bbb matched=1, BBB bo_only matched=1", "CCC bbb hits=1, BBB bo_only hits=1"),
    ],
    "tests/components.kline-click.spec.ts": [
        ("unmatched marker(qualified/detected)", "没进 hit 的 marker(qualified/detected)"),
        ("view.focus{Match,Event}", "view.focus{Hit,Event}"),
    ],
    "tests/stores.spec.ts": [
        ("bo_20#0 未匹配 → detected", "bo_20#0 没进 hit → detected"),
        ("bo_9#0 匹配 → matched", "bo_9#0 进了 hit → in_hit"),
        ("未匹配 event", "没进 hit 的 event"),
        ("未匹配的 boX", "没进 hit 的 boX"),
    ],
    "tests/fixtures.ts": [
        ("// 未匹配", "// 没进 hit"),
        ("凑成完整匹配", "凑成完整 hit"),
    ],
    "tests/components/DetailSidebar.spec.ts": [
        ("(down1#0 匹配,", "(down1#0 进 hit,"),
        ("(side1#0 匹配,", "(side1#0 进 hit,"),
        ("burst band: 1 匹配", "burst band: 1 进 hit"),
        ("tb band: 1 匹配", "tb band: 1 进 hit"),
    ],
    "tests/chart-helpers.spec.ts": [("`MATCH:${id}`", "`HIT:${id}`"), ("MATCH:m1", "HIT:m1")],
    "tests/render.visible.spec.ts": [("SHORT_MATCH", "SHORT_HIT")],
    "e2e/miss-detection-walkthrough.spec.ts": [
        ("Matched/Qualified 档", "in_hit/qualified 档"),
        ("切到 Detected 档", "切到 detected 档"),
        ("clickByText('.level-btn', 'Detected')", "clickByText('.level-btn', 'detected')"),
    ],
    "e2e/flow.spec.ts": [
        ("level 切档(Matched / Qualified / Detected)", "level 切档(in_hit / qualified / detected)"),
        ("level control: Detected → Qualified → Matched", "level control: detected → qualified → in_hit"),
        ("{ name: 'Matched' }", "{ name: 'in_hit' }"),
        ("{ name: 'Qualified' }", "{ name: 'qualified' }"),
        ("{ name: 'Detected' }", "{ name: 'detected' }"),
        ("Matched 应为 active", "in_hit 应为 active"),
        ("切到 Detected", "切到 detected"),
        ("切到 Qualified", "切到 qualified"),
        ("切回 Matched", "切回 in_hit"),
    ],
    "e2e/sidebar-chart-focus.spec.ts": [
        ("hasText: 'Matched'", "hasText: 'in_hit'"),
        (".toHaveText('Matched')", ".toHaveText('in_hit')"),
        ("非-matched", "非 in_hit"),
    ],
    "tests/components/ChartArea.spec.ts": [
        ("toContain('Matched')", "toContain('in_hit')"),
        ("toContain('Qualified')", "toContain('qualified')"),
        ("toContain('Detected')", "toContain('detected')"),
        ("toBe('Matched')", "toBe('in_hit')"),
        ("b.text() === 'Matched'", "b.text() === 'in_hit'"),
        ("b.text() === 'Detected'", "b.text() === 'detected'"),
        ('clicking "Detected"', 'clicking "detected"'),
        ("原来的 Matched 不再 active", "原来的 in_hit 不再 active"),
    ],
}
# 所有文件通用的子串：tooltip 顶行、「命中匹配」这个旧标题
SUBSTR_ALL: list[tuple[str, str]] = [
    ("命中匹配列表", "hit 列表"),
    ("命中匹配单行", "hit 列表单行"),
    ("命中匹配多行", "hit 列表多行"),
    ("命中匹配某行", "hit 列表某行"),
    ("点命中匹配行", "点 hit 行"),
    ("命中匹配行", "hit 行"),
]

# ── 3. 标识符与 CSS 类名（整词替换，长的在前）──────────────────────────────────
WORDS: dict[str, str] = {
    "setRealCandidateMatches": "setRealCandidateHits",
    "setCandidateMatches": "setCandidateHits",
    "candidateMatchIds": "candidateHitIds",
    "focusedMatchId": "focusedHitId",
    "selectedMatchId": "selectedHitId",
    "selectedMatch": "selectedHit",
    "focusMatch": "focusHit",
    "targetMatchId": "targetHitId",
    "markedMatchIds": "markedHitIds",
    "seedMatches": "seedHits",
    "selectMatchRow": "selectHitRow",
    "selectMatch": "selectHit",
    "matchRows": "hitRows",
    "matchLabelIdx": "hitLabelIdx",
    "matchLabel": "hitLabel",
    "matchesLabelVisible": "hitsLabelVisible",
    "matchesLabel": "hitsLabel",
    "matchIds": "hitIds",
    "matchId": "hitId",
    "droppedMatches": "droppedHits",
    "waitForMatches": "waitForHits",
    "matchesReferencing": "hitsReferencing",
    "refMatches": "refHits",
    "matchedIdsOf": "inHitIdsOf",
    "matchedIdsJs": "inHitIdsJs",
    "matchedIds": "inHitIds",
    "matchedEventIds": "inHitEventIds",
    "matchedCountForNode": "inHitCountForNode",
    "matchedBtn": "inHitBtn",
    "eMatched": "eInHit",
    "bo_match": "bo_hit",
    "match_A": "hit_A",
    "match_B": "hit_B",
    "match_1": "hit_1",
    "preview_match_1": "preview_hit_1",
}
CSS_AND_PHRASES: list[tuple[str, str]] = [
    ("dropped-matches-notice", "dropped-hits-notice"),
    ("match-row--selected", "hit-row--selected"),
    ("match-row", "hit-row"),
    ("match-span", "hit-span"),
    ("match-ret", "hit-ret"),
    ("match-dd", "hit-dd"),
    ("match-trace", "hit-trace"),
    ("per-match", "per-hit"),
    ("multi-match", "multi-hit"),
]
WORD_RE = re.compile(r"\b(" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")\b")

# ── 4. 兜底的单词 ────────────────────────────────────────────────────────────
FALLBACK: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<=['\"])matched(?=['\"])"), "in_hit"),            # 第三档的字面量
    (re.compile(r"\bconst matched\b"), "const inHit"),                # 局部集合
    (re.compile(r"(?<=, )matched(?=, qualified\))"), "inHit"),        # eventTierOf 的实参
    (re.compile(r"\bmatched\b"), "in_hit"),                           # 其余都在注释和用例名里
    (re.compile(r"\bMatches\b"), "Hits"),
    (re.compile(r"\bMatch\b"), "hit"),
    (re.compile(r":matches="), ":hits="),
    (re.compile(r"\bmatches\b(?!\s*\()"), "hits"),                    # 留 el.matches(...) 这种 DOM 调用
    (re.compile(r"(?<![.\w])match\b(?!\()"), "hit"),                  # 留 str.match(...)
]
SHORTHAND: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bconst \{ hits: hits \}"), "const { hits }"),
    (re.compile(r"\bhits: hits\b(?!\.)"), "hits"),
]


def convert(rel: str, text: str) -> str:
    special = FILE_SPECIAL.get(rel, [])
    out = []
    for line in text.split("\n"):
        if SKIP_LINE.search(line):
            out.append(line)
            continue
        for a, b in special:
            line = line.replace(a, b)
        line = re.sub(r"(?<![A-Za-z])Match:", "hit:", line)   # tooltip 顶行；focusMatch: 这种不算
        for a, b in SUBSTR_ALL:
            line = line.replace(a, b)
        for a, b in CSS_AND_PHRASES:
            line = line.replace(a, b)
        line = WORD_RE.sub(lambda m: WORDS[m.group(1)], line)
        for rx, b in FALLBACK:
            line = rx.sub(b, line)
        for rx, b in SHORTHAND:
            line = rx.sub(b, line)
        out.append(line)
    return "\n".join(out)


def main() -> None:
    changed = 0
    for d in DIRS:
        for f in sorted((ROOT / d).rglob("*")):
            if not f.is_file() or f.suffix not in SUFFIXES:
                continue
            rel = f.relative_to(ROOT).as_posix()
            if rel in SKIP_FILES:
                continue
            old = f.read_text(encoding="utf-8")
            new = convert(rel, old)
            if new != old:
                f.write_text(new, encoding="utf-8")
                changed += 1
    print("改动文件数", changed)


if __name__ == "__main__":
    main()
