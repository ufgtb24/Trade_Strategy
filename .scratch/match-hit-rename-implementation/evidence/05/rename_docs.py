"""票 05：CLAUDE.md、docs/path2、docs/explain、docs/feature_candidates.md 里旧义 match 与「匹配」的逐处替换。

只跑一次（在仓库根目录、git mv 之后）；独立审查后改过的词已同步进表，从基线重跑能复现最终结果。每条替换带预期次数，次数不符整批不写；行数变了也不写，
所以只换词、不增删行。不进表的（泛指的「匹配」、统计配对、过时旧名 MatchContext 等）一律不碰。

译法：
- 指产出（一次命中）：match → hit，「匹配」→「命中」；
- 指求解过程（「匹配引擎」「匹配逻辑」「匹配期」）：→「求解」，和票 01 的 _solve.py、票 04 的
  authoring-path2-app 同一译法，「不参与命中」读不通；
- 代码名照 spec：PatternMatch → PatternHit，.matches / matches: → hits，matches() → has_hit()；
- 代码里已经没有的旧名（MatchContext、dropped_matches、SKIP_TILL_NEXT_MATCH 等）不改，进过时清单。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 每个 docs/path2、docs/explain 文件都先过这几条代码名规则（次数不校验，靠之后的残留检查收口）
CODE_RULES = [
    (re.compile(r"\bPatternMatch\b"), "PatternHit"),
    (re.compile(r"\.matches\b"), ".hits"),
    (re.compile(r"\bmatch\.(role_index|event_id|start_idx|end_idx|pattern_id|children|predicate_trace)\b"), r"hit.\1"),
    (re.compile(r"\bmatch = result"), "hit = result"),
    (re.compile(r"\bfor match in\b"), "for hit in"),
]

PATH2 = "docs/path2/"
EXPLAIN = "docs/explain/"

TABLE: dict[str, list[tuple[str, str, int]]] = {
    "CLAUDE.md": [
        ("`detected、qualified、matched`", "`detected、qualified、in_hit`", 1),
        ("物化 match）", "物化 hit）", 1),
        ("漏匹配", "漏命中", 2),
    ],
    PATH2 + "README.md": [
        ("匹配从哪里铺开", "求解从哪里铺开", 1),
        ("判定这次匹配不成立", "判定这次命中不成立", 1),
        ("真正的形态匹配", "真正的形态命中", 2),
        ("- `matches`——真正的", "- `hits`——真正的", 1),
        ("guide/matching-and-results.md", "guide/hits-and-results.md", 4),
        ("匹配与结果：", "命中与结果：", 1),
    ],
    PATH2 + "api-reference.md": [
        ("不含任何匹配算法", "不含任何求解算法", 1),
        ("analyze()（匹配引擎入口）", "analyze()（求解引擎入口）", 1),
        ("真正去匹配](#6-path2dagengine--真正去匹配)", "真正去求解](#6-path2dagengine--真正去求解)", 1),
        ("匹配结果长什么样](#7-path2dagresult--匹配结果长什么样)", "命中结果长什么样](#7-path2dagresult--命中结果长什么样)", 1),
        ("参与外层故事的匹配", "参与外层故事的求解", 1),
        ('把"成串"留到匹配期再算', '把"成串"留到求解期再算', 1),
        ("为防止漏匹配", "为防止漏命中", 1),
        ("不含任何匹配逻辑", "不含任何求解逻辑", 1),
        ("顺序不影响匹配", "顺序不影响求解", 1),
        ("等到匹配出诡异结果", "等到求解出诡异结果", 1),
        ("## 6. path2.dag.engine — 真正去匹配", "## 6. path2.dag.engine — 真正去求解", 1),
        ("`matches()` 是它的", "`has_hit()` 是它的", 1),
        ("from path2.dag import analyze, matches", "from path2.dag import analyze, has_hit", 1),
        ("唯一公开的匹配入口", "唯一公开的求解入口", 1),
        ("边、匹配策略", "边、求解策略", 1),
        ("并不参与形态匹配", "并不参与求解", 1),
        ("### `matches`", "### `has_hit`", 1),
        ("def matches(spec: PatternSpec", "def has_hit(spec: PatternSpec", 1),
        ("## 7. path2.dag.result — 匹配结果长什么样", "## 7. path2.dag.result — 命中结果长什么样", 1),
        ("matches: Tuple[PatternHit, ...]", "hits: Tuple[PatternHit, ...]", 1),
        ("| `matches` | 所有完整命中结果", "| `hits` | 所有完整命中结果", 1),
        ("**`events` vs `matches` 的区别**", "**`events` vs `hits` 的区别**", 1),
        ('`matches` 是"真正拼成', '`hits` 是"真正拼成', 1),
        ("本身不进 `match`", "本身不进 `hit`", 1),
        ("你只能在匹配期把", "你只能在求解期把", 1),
        ("和匹配口径保持一致", "和求解口径保持一致", 1),
        ("不参与形态匹配，只当", "不参与求解，只当", 1),
        ("却不在任何 `match` 里", "却不在任何 `hit` 里", 1),
        ("形态匹配真正关心的是", "求解真正关心的是", 1),
    ],
    PATH2 + "concepts.md": [
        ("引擎负责匹配", "引擎负责求解", 1),
        ("[匹配语义：引擎到底怎么找出一次命中](#匹配语义)", "[求解语义：引擎到底怎么找出一次命中](#求解语义)", 1),
        ("[匹配语义](#匹配语义)", "[求解语义](#求解语义)", 1),
        ("不是某次具体匹配的结果", "不是某次具体求解的结果", 1),
        ("不写任何匹配逻辑", "不写任何求解逻辑", 1),
        ("引擎匹配并不读它", "引擎求解并不读它", 1),
        ("参与外层 DAG 匹配", "参与外层 DAG 求解", 1),
        ("不污染形态匹配", "不污染形态命中", 1),
        ("不进任何完整形态匹配", "不进任何完整形态命中", 1),
        ("## 匹配语义", "## 求解语义", 1),
        ("matches: Tuple[PatternHit, ...]", "hits: Tuple[PatternHit, ...]", 1),
        ("- `matches`：全部完整命中", "- `hits`：全部完整命中", 1),
    ],
    PATH2 + "example-bottom-burst.md": [
        ("怎么在数据里把它匹配出来", "怎么在数据里把它找出来", 1),
        ("不是匹配算法", "不是求解算法", 1),
        ("怎么快速匹配", "怎么快速求解", 1),
        ("既不让它污染走势匹配", "既不让它污染走势命中", 1),
        ("残缺匹配", "残缺命中", 3),
        ('当成一次"匹配"', '当成一次"命中"', 1),
        ("真正的走势匹配", "真正的走势命中", 1),
        ("残缺 match", "残缺 hit", 2),
        ("和 `matches`（只要是/否）", "和 `has_hit`（只要是/否）", 1),
        ("import analyze, matches", "import analyze, has_hit", 1),
        ("if matches(df):", "if has_hit(df):", 1),
        ("| `matches` | `Tuple[PatternHit, ...]`", "| `hits` | `Tuple[PatternHit, ...]`", 1),
        ("具体匹配到了哪段下跌", "具体命中了哪段下跌", 1),
        ("`matches(df, params)`", "`has_hit(df, params)`", 1),
        ("（events / matches / spec）", "（events / hits / spec）", 1),
    ],
    PATH2 + "getting-started.md": [
        ("你的第一个走势匹配", "你的第一次命中", 1),
        ("引擎自动匹配", "引擎自动求解", 1),
        ("能匹配到东西", "能命中东西", 1),
        ("不影响匹配结果", "不影响求解结果", 1),
        ("`from path2.dag import matches`，`matches(spec, df)`", "`from path2.dag import has_hit`，`has_hit(spec, df)`", 2),
        ("path2 匹配流程", "path2 求解流程", 1),
    ],
    PATH2 + "guide/authoring-patterns.md": [
        ("「DAG 匹配」", "「DAG 求解」", 1),
        ("对匹配逻辑没有任何影响", "对求解逻辑没有任何影响", 1),
        ("像普通节点一样参与匹配", "像普通节点一样参与求解", 1),
        ("参与后续匹配", "参与后续求解", 1),
        ("真正的形态匹配", "真正的形态命中", 1),
        ("跑匹配并读结果", "跑求解并读结果", 1),
        ("引擎在匹配时构造", "引擎在求解时构造", 1),
        ("不用等跑匹配才发现", "不用等跑求解才发现", 1),
        ("读取匹配结果", "读取命中结果", 1),
        ("matches: Tuple[PatternHit, ...]", "hits: Tuple[PatternHit, ...]", 1),
        ("你最关心的是 `matches`", "你最关心的是 `hits`", 1),
        ("从 `matches` 读结果", "从 `hits` 读结果", 1),
    ],
    PATH2 + "guide/building-blocks.md": [
        ("不影响匹配结果", "不影响求解结果", 1),
        ("只匹配到这一个孤立角色", "只绑定这一个孤立角色", 1),
    ],
    PATH2 + "guide/edges.md": [
        ("任何匹配/搜索逻辑", "任何求解/搜索逻辑", 1),
        ("不会漏匹配", "不会漏命中", 1),
        ("就会漏匹配", "就会漏命中", 1),
        ("不参与任何形态匹配", "不参与任何求解", 1),
        ("不用写一行匹配逻辑", "不用写一行求解逻辑", 1),
        ("**漏匹配**", "**漏命中**", 1),
        ("同样触发漏匹配", "同样触发漏命中", 1),
    ],
    PATH2 + "guide/hits-and-results.md": [
        ("# 匹配与结果指南", "# 命中与结果指南", 1),
        ("import analyze, matches", "import analyze, has_hit", 1),
        # 这个局部变量是 bool，不是 hit，留着 hit 这个名字会读混
        ("hit    = matches(spec, df, params=None)", "found  = has_hit(spec, df, params=None)", 1),
        ("`matches` 是个偷懒的快捷方式", "`has_hit` 是个偷懒的快捷方式", 1),
        ("这个角色匹配一串", "这个角色绑定一串", 1),
        ("不漏掉同段匹配", "不漏掉同段命中", 1),
        ("真正的形态匹配", "真正的形态命中", 1),
        ("你拿到的 `matches` 里", "你拿到的 `hits` 里", 1),
        ("| `matches` | `Tuple[PatternHit, ...]`", "| `hits` | `Tuple[PatternHit, ...]`", 1),
        ('`matches` 是"把这些点', '`hits` 是"把这些点', 1),
    ],
    PATH2 + "miss-detection-guide.md": [
        ('"设计正确、不该匹配"', '"设计正确、不该命中"', 1),
        ("直接进了 match", "直接进了 hit", 1),
        ("· matches 为空 ·", "· hits 为空 ·", 1),
        ("还没进 match 的 event", "还没进 hit 的 event", 1),
        ("| **match** |", "| **hit** |", 1),
    ],
    EXPLAIN + "dag_solve_logic_analysis.md": [
        ("完整 match 对象", "完整 hit 对象", 2),
        ("reify → match", "reify → hit", 1),
        ("一个完整匹配", "一个完整命中", 1),
        ("漏匹配", "漏命中", 2),
    ],
    EXPLAIN + "path2_pattern_framework_plain.md": [
        ("`matches(df) -> True/False`", "`has_hit(df) -> True/False`", 1),
        ("def matches(df, params) -> bool:", "def has_hit(df, params) -> bool:", 1),
    ],
    EXPLAIN + "next_mode_ptr_advance_通俗解释.md": [
        ("依次生产 match", "依次生产 hit", 2),
        ("反复找同一个 match", "反复找同一个 hit", 1),
        ("藏着多个 match", "藏着多个 hit", 1),
        ("第二次找到的 match", "第二次找到的 hit", 1),
        ("第一次 match 里", "第一次 hit 里", 1),
        ("找新的 match", "找新的 hit", 1),
        ("**match 之间的事件互不重叠**", "**hit 之间的事件互不重叠**", 1),
        ("最多只能进一个 match", "最多只能进一个 hit", 1),
        ("参与不同的 match", "参与不同的 hit", 1),
        ("几十个 match", "几十个 hit", 1),
        ("一票数据上的 match 之间", "一票数据上的 hit 之间", 1),
    ],
    EXPLAIN + "path2_漏检分析_v1_v2_脉络.md": [
        ("以独立 match 形式", "以独立 hit 形式", 1),
        ("有 marker 但无 match", "有 marker 但无 hit", 1),
        ("有 marker 无 match", "有 marker 无 hit", 1),
    ],
    EXPLAIN + "tune-gates_调参工作流使用指南.md": [
        ("好几条 match 共享", "好几条 hit 共享", 2),
    ],
    "docs/feature_candidates.md": [
        ("宽进 match", "宽进 hit", 4),
        ("去重后的 match", "去重后的 hit", 1),
        ("`match_forward_returns`", "`hit_forward_returns`", 1),
        ("前缀族的多条 match", "前缀族的多条 hit", 1),
        ("只有 match 的股票", "只有 hit 的股票", 1),
        ("逐 match 计", "逐 hit 计", 2),
        ("版本 match 到、而", "版本命中、而", 1),
        ("版本也 match 到的", "版本也命中的", 1),
        (" 条 match / ", " 条 hit / ", 1),
    ],
}


def main() -> int:
    out: dict[Path, str] = {}
    failed = False
    for rel, rules in TABLE.items():
        path = Path(rel)
        before = path.read_text(encoding="utf-8")
        text = before
        if rel.startswith((PATH2, EXPLAIN)):
            for rx, new in CODE_RULES:
                text = rx.sub(new, text)
        for old, new, want in rules:
            got = text.count(old)
            if got != want:
                print(f"次数不符 {rel}: {old!r} 预期 {want} 实际 {got}")
                failed = True
            text = text.replace(old, new)
        if text.count("\n") != before.count("\n"):
            print(f"行数变了 {rel}")
            failed = True
        out[path] = text
    if failed:
        print("有不符，一个文件都没写")
        return 1
    for path, text in out.items():
        path.write_text(text, encoding="utf-8")
    print(f"写了 {len(out)} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
