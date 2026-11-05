"""票 05：记忆目录里指 app 产出的 match、旧三档 matched 与「匹配」的逐处替换。

只跑一次，动手前记忆目录已整份备份（路径见完成记录）。每条替换带预期次数，次数不符或行数变了，一个文件都不写。
文件名和 frontmatter 的 name: 不动。代码名照合回后的代码：`hit_forward_returns`、`_hit_to_dict`、`tests/.../test_has_hit.py`。
记忆里有含 2026 年窗口的结果，所以这张表的前后文里不放数字。
"""
from __future__ import annotations

import sys
from pathlib import Path

MEM = Path.home() / ".claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory"

TABLE: dict[str, list[tuple[str, str, int]]] = {
    "MEMORY.md": [
        ("(match-preserving)", "(hit-preserving)", 1),
        ("没生成/没 match/confirm 位置", "没生成/没命中/confirm 位置", 1),
    ],
    "feedback_argument_discipline.md": [("traced∪matched", "traced∪in_hit", 1)],
    "feedback_label_alignment_check.md": [
        ("path2/eval.py::match_forward_returns", "path2/eval.py::hit_forward_returns", 1),
        ("逐 match 精确一致", "逐 hit 精确一致", 1),
    ],
    "feedback_visual_companion_ui_only.md": [("未匹配归因", "未命中归因", 1)],
    "project_bo_burst_redesign.md": [
        ("match-preserving", "hit-preserving", 4),
        ("逐 match 相等", "逐 hit 相等", 1),
        ("match-改进错断", "hit-改进错断", 1),
    ],
    "project_bottom_burst_recall_collapse.md": [("match-preserving", "hit-preserving", 1)],
    "project_burst_allends_chain.md": [
        ("同簇前缀 match 层塌缩", "同簇前缀 hit 层塌缩", 1),
        ("res.matches", "res.hits", 1),
        ("四格 matches DIFF", "四格 hits DIFF", 1),
    ],
    "project_first_drought_window_truncation.md": [
        ("零 match 增量", "零 hit 增量", 1),
        ("完整 pattern 的 match 数", "完整 pattern 的 hit 数", 1),
        ("真正进 match", "真正进 hit", 1),
        ("只有 match 的股票", "只有 hit 的股票", 1),
        ("条 match，", "条 hit，", 1),
        ("重放的 match 更多", "重放的 hit 更多", 1),
        ("重放 match 集", "重放 hit 集", 1),
    ],
    "project_first_passage_mfr_orthogonal.md": [(" matches,小样本", " hits,小样本", 1)],
    "project_multivar_region_budget.md": [("逐 match 精确等价", "逐 hit 精确等价", 1)],
    "project_path2_app_optimization_workflow.md": [("后只读 matches", "后只读 hits", 1)],
    "project_path2_edge_causality_lesson.md": [("match.node_index", "hit.node_index", 1)],
    "project_path2_event_diagnosis_playbook.md": [
        ("没生成/没match/", "没生成/没命中/", 2),
        ("analysis.events/matches", "analysis.events/hits", 1),
    ],
    "project_path2_nesting_mechanism.md": [
        ("其平凡 match 是", "其平凡 hit 是", 1),
        ("残缺 match", "残缺 hit", 6),
        ("match.children", "hit.children", 1),
        ("inner_analyze().matches", "inner_analyze().hits", 1),
        ("res.matches", "res.hits", 2),
        ("漏匹配", "漏命中", 2),
        ("role/match 行", "role/hit 行", 1),
        ("垃圾 match", "垃圾 hit", 1),
        ("match-preserving", "hit-preserving", 4),
        ("in-tree test_matches", "in-tree test_has_hit", 1),
    ],
    "project_path2_pk_not_event.md": [
        ("events/matches/band", "events/hits/band", 1),
        ("② match 只序列化", "② hit 只序列化", 1),
        ("_match_to_dict", "_hit_to_dict", 1),
        ("任何 match 的 node_index", "任何 hit 的 node_index", 1),
        ("残缺 match", "残缺 hit", 1),
    ],
    "project_path2_web_multi_pattern_ux.md": [("没被 pattern2 matched", "没被 pattern2 命中", 1)],
    "project_tb_buypoint_modeling.md": [
        ("无match爆炸", "无hit爆炸", 1),
        ("根 match 放大", "根 hit 放大", 1),
        ("随多 match 语义改", "随多 hit 语义改", 1),
        ("test_matches.py", "test_has_hit.py", 1),
    ],
    "project_tb_v1_revert_toxic_gate.md": [("match/", "hit/", 2)],
    "reference_path2_role_term_deprecated.md": [
        ("在一个 match 里", "在一个 hit 里", 1),
        ("(match 内 node_id", "(hit 内 node_id", 1),
    ],
}


def main() -> int:
    out = {}
    failed = False
    for name, rules in TABLE.items():
        path = MEM / name
        before = path.read_text(encoding="utf-8")
        text = before
        for old, new, want in rules:
            got = text.count(old)
            if got != want:
                print(f"次数不符 {name}: {old!r} 预期 {want} 实际 {got}")
                failed = True
            text = text.replace(old, new)
        if text.count("\n") != before.count("\n"):
            print(f"行数变了 {name}")
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
