# -*- coding: utf-8 -*-
"""multivar_core 纯函数单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_multivar_core.py -q
"""
import json, subprocess, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from multivar_core import (Dim, apply_overrides, check_predicate_axes, classify, col_of,  # noqa: E402
                           detection_combos, influence_dims, loosest_level, node_col,
                           probe_dim, upstream_closure)
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402

BASE = json.loads((Path(__file__).parent / "fixtures/bb_v1_p2_wide.json").read_text())
SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
             ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"): [4, 8, 12, 20],
             ("burst", "min_bos"): [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"): [1, 2, 3, 4],
             ("tb", "max_rise_k"): [1.0, 1.5, 2.5, 4.0]}
WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                ("burst", "distinct_pk_min"): [1, 3, 4],
                ("burst", "vol_spike_min"): [0, 10, 15],
                ("burst", "peak_age_min"): [0, 125]}


def test_probe_where_dim():
    pr = probe_dim(mod, BASE, ("burst", "first_drought_min"), 20)
    assert pr.detector_nodes == () and not pr.edges_changed
    assert pr.where_clauses == (("burst", "first_drought", ">="),)


def test_probe_detector_dims():
    assert probe_dim(mod, BASE, ("burst", "gap_max"), 12).detector_nodes == ("burst",)
    assert probe_dim(mod, BASE, ("bo", "exceed_threshold"), 0.01).detector_nodes == ("bo",)
    # max_start_gap(旧字段,已删)→ max_span:两者承载同一性质——tb 方案 C 里 max_span
    # 既是 ThrowbackDetectorV1 的构造参数,又是 burst→tb edge 的 max_gap(SSoT,dag_spec.py
    # 边声明处注释"共用同一 SSoT (tb.max_span)"),故同时驱动 detector_nodes 与 edges_changed。
    pr = probe_dim(mod, BASE, ("tb", "max_span"), 9)
    assert pr.detector_nodes == ("tb",) and pr.edges_changed      # 同时是 edge max_gap 的 SSoT


def test_classify_bb_v1():
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    assert cls.kinds[("burst", "min_bos")] == "F"
    assert cls.filter_fields[("burst", "min_bos")] == ("burst", "count", ">=")
    for d in [("bo", "min_relative_height"), ("bo", "exceed_threshold"), ("burst", "gap_max"),
              ("tb", "stop_confirm_bars"), ("tb", "max_rise_k")]:
        assert cls.kinds[d] == "D"
    for d in WHERE_LEVELS:
        assert cls.kinds[d] == "W"
    assert cls.where_fields[("burst", "vol_spike_min")] == ("burst", "max_bar_vol_ratio", ">=")


def test_classify_rejects_where_in_scan_grid():
    bad = dict(SCAN_GRID); bad[("burst", "first_drought_min")] = [0, 20]
    with pytest.raises(ValueError, match=r"burst\.first_drought_min 是 where 阈值"):
        classify(mod, BASE, bad, {})


def test_classify_rejects_detector_dim_in_where_levels():
    with pytest.raises(ValueError, match=r"burst\.gap_max 不是纯 where 阈值"):
        classify(mod, BASE, SCAN_GRID, {("burst", "gap_max"): [4, 8]})


def test_classify_rejects_non_loosest_f_base():
    # F 维不变量:detection_combos 把 F 维踢出组合后,该维在整个扫描期间恒等于底座值,
    # 只有底座本身就是按运算符算出的最松档,"最松档构造+事后按字段谓词切"才与"直接以
    # 底座值构造"等价——否则是静默数值错误(偏小、不抛异常)。底座 min_bos=2 而档位
    # [1,2,3,4] 按 >= 的最松档是 1,应报错。
    bad = apply_overrides(BASE, {}, {("burst", "min_bos"): 2})
    with pytest.raises(ValueError, match=r"burst\.min_bos 是过滤型"):
        classify(mod, bad, SCAN_GRID, WHERE_LEVELS)


def test_loosest_level_op_aware():
    assert loosest_level([1, 2, 3, 4], ">=") == 1
    assert loosest_level([1, 2, 3, 4], ">") == 1
    assert loosest_level([0.0, 0.1, 0.2], "<=") == 0.2
    assert loosest_level([0.0, 0.1, 0.2], "<") == 0.2
    # <=/< 语义下 None(不设闸)比任何数值都松,若档位表含 None 须优先取 None
    assert loosest_level([None, 0.2], "<") is None


def test_upstream_closure_and_influence():
    spec = mod.build_pattern(mod.Params.from_dict(BASE))
    assert upstream_closure(spec, "tb") == ("tb", "burst", "bo")
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    inf = influence_dims(spec, cls, SCAN_GRID)
    assert inf["bo"] == (("bo", "min_relative_height"), ("bo", "exceed_threshold"))
    assert inf["burst"] == inf["bo"] + (("burst", "gap_max"),)
    assert inf["tb"] == inf["burst"] + (("tb", "stop_confirm_bars"), ("tb", "max_rise_k"))


def test_detection_combos_excludes_filter_dims():
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    combos = detection_combos(SCAN_GRID, cls)
    assert len(combos) == 4 ** 5
    assert ("burst", "min_bos") not in combos[0]
    assert list(combos[0]) == [d for d in SCAN_GRID if d != ("burst", "min_bos")]


def test_apply_overrides_deep_copies():
    out = apply_overrides(BASE, {"tb": {"max_day_drop_pct": None}}, {("burst", "gap_max"): 12})
    assert out["burst"]["gap_max"] == 12 and out["tb"]["max_day_drop_pct"] is None
    assert BASE["burst"]["gap_max"] == 8


def test_check_predicate_axes_rejects_negation_target():
    # PatternSpec 校验(_validate_dag)拒绝"neg_dst 同时被正向边引用",实测构造即抛
    # ValueError(与本测试意图无关的失败点)——按 brief 预留的 contingency 改用最小 stub:
    # check_predicate_axes 只读 spec.edges,不需要真正合法的 PatternSpec。
    # stub 里额外混入一条【非】NegationEdge(dst="b")——覆盖 isinstance(e, NegationEdge)
    # 这条过滤本身:删掉它现有断言不会失败(过度拒绝无测),须正面断言"b" 上的 where 不被误拒。
    # check_predicate_axes 不区分调用方传入的字段来自 W 维还是 F 维(复审 I-4:两者在
    # region 侧走同一条谓词轴,字典 shape 完全相同)——本测试直接覆盖两类调用。
    import types
    from path2.dag.edges import NegationEdge, TemporalEdge
    spec = types.SimpleNamespace(
        edges=(NegationEdge("bo2", "burst"), TemporalEdge("a", "b", min_gap=1, max_gap=5)),
        nodes=())
    with pytest.raises(ValueError, match="NegationEdge"):
        check_predicate_axes(spec, {("burst", "first_drought_min"): ("burst", "first_drought", ">=")})
    check_predicate_axes(spec, {})    # 空字典不报错
    # 非 negation 边(TemporalEdge)的 dst="b" 上的谓词维不该被误拒
    check_predicate_axes(spec, {("b", "some_min"): ("b", "some_field", ">=")})
    # F 维命中 negation dst 同样要拒(调用方按 {**where_fields, **filter_fields} 传入并集)
    with pytest.raises(ValueError, match="NegationEdge"):
        check_predicate_axes(spec, {("tb", "max_day_drop_pct"): ("burst", "day_drop", "<")})


def test_col_of():
    assert col_of(("burst", "gap_max")) == "burst.gap_max"


def test_node_col():
    assert node_col("burst", "gap_max") == "burst.gap_max"
