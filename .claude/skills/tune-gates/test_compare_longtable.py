# -*- coding: utf-8 -*-
"""compare_longtable 的 (a) 组固定维判定:必须按「同一趟 detect 产出的 node 组」算。

多流 detector 一趟产多条流时,同一个真扫维会同时影响这一组里的每个 node,
写死等于首个 node 会让 fixed 落空、(a) 组退化成全网格(bb_v1 实测 3 → 9 格)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import itertools  # noqa: E402
import random  # noqa: E402
import types  # noqa: E402

import pandas as pd  # noqa: E402

from compare_longtable import (MIN_SYMBOLS, _engine_keys, _first_detect_group, _fixed_dims,  # noqa: E402
                               _plan_cells, _table_fp_counts, _table_keys, compare_symbols, coverage_ok)
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from tests.path2.dogfood_multistream import RangeEvent, RangeNoteDetector  # noqa: E402


def _multistream_spec():
    det = RangeNoteDetector(span=3, min_bars=5)
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])


def _multistream_spec_with_leading_substructure_node():
    """同 `_multistream_spec`,但额外挂一个 detector=None 的子结构 node "aaa_seg",
    字典序排在 "note"/"range" 之前——复现 tb_seg 这类子结构 node 排在根 detector
    node 前面时,拓扑序 [0] 落在它头上的场景。"""
    det = RangeNoteDetector(span=3, min_bars=5)
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range", children={"seg": "aaa_seg"}),
        NodeSpec("note", det, produces_stream="note", solve=False),
        NodeSpec("aaa_seg", event_cls=RangeEvent),
    ])


def test_first_detect_group_covers_all_siblings_of_one_call():
    """一趟 detect 产两条流 ⟹ 组里两个 node 都在。"""
    assert _first_detect_group(_multistream_spec()) == {"range", "note"}


def test_first_detect_group_skips_leading_substructure_node():
    """拓扑序 [0] 是 detector=None 的子结构 node 时,仍要返回真正首趟 detect 那组
    node,而不是退化成空集(旧实现直接拿 [0] 的 detector 建 key,会撞上 None)。"""
    assert _first_detect_group(_multistream_spec_with_leading_substructure_node()) == {"range", "note"}


def test_fixed_dims_keeps_multistream_dim_fixed():
    """同时影响 range 与 note 的 D 维必须被钉住(⊆ 组),而非因 != [first] 落空。"""
    dims = [("range", "span"), ("other", "thing")]
    cl = {"kinds": {"range.span": "D", "other.thing": "D"},
          "detector_nodes": {"range.span": ["range", "note"], "other.thing": ["other"]}}
    ref_point = {"range.span": 3, "other.thing": 7}
    got = _fixed_dims(dims, cl, ref_point, {"range", "note"},
                      lambda d: f"{d[0]}.{d[1]}")
    assert got == {("range", "span"): 3}


def test_fixed_dims_ignores_dim_with_empty_detector_nodes():
    """空集 ⊆ 任何集合——不能因此把 where 维也钉住。"""
    cl = {"kinds": {"x.y": "D"}, "detector_nodes": {"x.y": []}}
    got = _fixed_dims([("x", "y")], cl, {"x.y": 1}, {"range"}, lambda d: f"{d[0]}.{d[1]}")
    assert got == {}


# ---- 抽样格只从研究设计展开出的检测组合里取 ----

def _cl(design):
    return {"kinds": {"a.x": "D", "a.f": "F", "b.z": "D", "b.w": "D"},
            "scan_grid": {"a.x": [1, 2, 3], "a.f": [1, 2], "b.z": [4, 5, 6], "b.w": [7, 8, 9]},
            "design": design, "ref_point": {"a.x": 2, "b.z": 5, "b.w": 8}}


def test_plan_cells_grid_matches_full_cartesian_order():
    """grid 设计:候选 = 全网格笛卡尔积且同序,(a) 组钉住固定维后按其余维取遍。"""
    cl = _cl("grid")
    dims = [("a", "x"), ("a", "f"), ("b", "z"), ("b", "w")]
    full = [dict(zip(dims, v)) for v in itertools.product(*cl["scan_grid"].values())]
    cells_a, cells_b, cells_c = _plan_cells(cl, {}, random.Random(0), 5, 3)
    assert cells_a == full
    fixed = {("a", "x"): 2}
    cells_a, _, _ = _plan_cells(cl, fixed, random.Random(0), 5, 3)
    assert cells_a == [c for c in full if c[("a", "x")] == 2]


def test_plan_cells_screen_only_samples_design_combos():
    """screen 设计:每个抽样格的检测参数部分都在设计组合里,F 维照样取遍全部档;候选不够时不报错。"""
    import study_io as S
    cl = _cl("screen")
    design = {tuple(sorted(c.items())) for c in S.design_combos(cl)}
    assert len(design) == 1 + 6 + 12
    cells_a, cells_b, cells_c = _plan_cells(cl, {("a", "x"): 2}, random.Random(0), 1000, 1000)
    assert len(cells_b) >= 2 * len(design)                    # 抽样上限大于候选数:全取
    for c in cells_a + cells_b + cells_c:
        assert tuple(sorted((S.dotted(d), v) for d, v in c.items() if d != ("a", "f"))) in design
    assert {c[("a", "f")] for c in cells_b} == {1, 2}
    assert all(c[("a", "x")] == 2 for c in cells_a)


# ---- 首次穿越四态按买点事件回填与去重 ----

def _match(mid, tb, burst):
    ev = lambda s, e: types.SimpleNamespace(start_idx=s, end_idx=e)  # noqa: E731
    return types.SimpleNamespace(match_id=mid, node_index={"tb": ev(*tb), "burst": ev(*burst)})


def test_engine_keys_backfill_first_passage_per_buy_span():
    """同一买点事件的两条 match:serialize 只给第一条填四态;回填后与长表的逐行满额四态逐行一致,
    而 match_fp_counts 与长表按买点事件键去重后的四态和一致。"""
    fp1, fp3 = {"up": 2, "down": 1, "both": 0, "none": 3}, {"up": 0, "down": 4, "both": 1, "none": 0}
    matches = [_match("m1", (10, 12), (1, 5)), _match("m2", (10, 12), (2, 5)), _match("m3", (20, 21), (15, 18))]
    out_matches = [
        {"match_id": "m1", "buy_span": [[10, 12]], "forward_return": 0.1, "first_passage": fp1},
        {"match_id": "m2", "buy_span": [[10, 12]], "forward_return": 0.1, "first_passage": None},
        {"match_id": "m3", "buy_span": [[20, 21]], "forward_return": None, "first_passage": fp3},
    ]
    match_fp_counts = {s: fp1[s] + fp3[s] for s in fp1}
    g = pd.DataFrame([
        {"burst.start": 1, "burst.end": 5, "tb.start": 10, "tb.end": 12, "fr": 0.1, **{f"fp_{s}": v for s, v in fp1.items()}},
        {"burst.start": 2, "burst.end": 5, "tb.start": 10, "tb.end": 12, "fr": 0.1, **{f"fp_{s}": v for s, v in fp1.items()}},
        {"burst.start": 15, "burst.end": 18, "tb.start": 20, "tb.end": 21, "fr": float("nan"), **{f"fp_{s}": v for s, v in fp3.items()}},
    ])
    key_nodes = ("burst", "tb")
    assert _engine_keys(matches, out_matches, key_nodes) == _table_keys(g, key_nodes)
    assert _table_fp_counts(g, ["tb.start", "tb.end"]) == match_fp_counts
    # 不去重就会把同一段买点算两次——这正是要拦住的口径
    assert {s: int(g[f"fp_{s}"].sum()) for s in fp1} != match_fp_counts


# ---- 股票覆盖红线 ----

def test_compare_symbols_stay_inside_scan_range(tmp_path):
    """参与比较的只取扫描范围内、没被扫描过滤掉的股票——扫描范围外的股票长表里本来没有行。"""
    for stem in ("AAX", "ABX", "BAX", "BDX", "CAX"):
        (tmp_path / f"{stem}.pkl").write_bytes(b"")
    syms, n_universe = compare_symbols(str(tmp_path), r"^[A-Z][A-C]", r"^A", {"ABX"})
    assert [p.stem for p in syms] == ["AAX"] and n_universe == 1
    syms, n_universe = compare_symbols(str(tmp_path), r"^[A-Z][A-C]", None, set())
    assert [p.stem for p in syms] == ["AAX", "ABX", "BAX", "CAX"] and n_universe == 5


def test_coverage_needs_min_symbols_unless_whole_scan_range_compared():
    assert coverage_ok(MIN_SYMBOLS, MIN_SYMBOLS, 8000)
    assert not coverage_ok(MIN_SYMBOLS - 1, MIN_SYMBOLS - 1, 8000)
    assert not coverage_ok(MIN_SYMBOLS - 1, MIN_SYMBOLS, 8000)   # 抽到够数,但有股票窗口为空、没真比
    assert coverage_ok(59, 59, 59)                               # 小范围试扫:扫描范围内的股票全部比过
