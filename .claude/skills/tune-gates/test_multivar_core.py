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

from multivar_core import (Classification, Dim, apply_overrides, check_predicate_axes, classify,  # noqa: E402
                           col_of, detection_combos, influence_dims, loosest_level, node_col,
                           probe_dim, probe_levels, upstream_closure)
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
    assert probe_dim(mod, BASE, ("bo", "exceed_threshold"), 0.01).detector_nodes == ("bo", "pk")
    # bo 与 pk 共享同一个 BODetector 实例(一趟同时产两条流),故该维同时改变两个 node
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


# ---------------------------------------------------------------- 研究设计展开
def _screen_grid(n_dims=6, n_levels=3):
    grid = {("s", f"p{i}"): list(range(n_levels)) for i in range(n_dims)}
    grid[("s", "f")] = [1, 2, 3]                       # F 维不进检测组合
    kinds = {d: "D" for d in grid}; kinds[("s", "f")] = "F"
    return grid, Classification(kinds, {}, {}, {}), {f"s.p{i}": 1 for i in range(n_dims)}


def test_detection_combos_screen_design_73():
    """6 个检测参数各 3 档:工作点 + 12 个单翻转 + 60 个两两翻转 = 73,顺序确定、工作点在首位。"""
    grid, cls, ref = _screen_grid()
    combos = detection_combos(grid, cls, "screen", ref)
    assert len(combos) == 73 == 1 + 2 * 6 + 4 * 15
    work = {d: 1 for d in grid if d != ("s", "f")}
    assert combos[0] == work
    assert combos == detection_combos(grid, cls, "screen", dict(reversed(list(ref.items()))))
    assert [sum(c[d] != work[d] for d in work) for c in combos] == [0] + [1] * 12 + [2] * 60
    assert len({tuple(sorted(c.items())) for c in combos}) == 73
    assert all(("s", "f") not in c for c in combos)
    # 单翻转按维序、档按档位表序;两两翻转按维对序
    assert combos[1] == {**work, ("s", "p0"): 0} and combos[2] == {**work, ("s", "p0"): 2}
    assert combos[13] == {**work, ("s", "p0"): 0, ("s", "p1"): 0}


def test_detection_combos_screen_needs_working_point_on_grid():
    grid, cls, ref = _screen_grid(n_dims=2)
    with pytest.raises(ValueError, match="工作点"):
        detection_combos(grid, cls, "screen", None)
    with pytest.raises(ValueError, match=r"s\.p1"):
        detection_combos(grid, cls, "screen", {**ref, "s.p1": 7})


def test_detection_combos_grid_ignores_ref_point():
    grid, cls, ref = _screen_grid(n_dims=2)
    assert len(detection_combos(grid, cls, "grid", ref)) == 9 == len(detection_combos(grid, cls))


# ---------------------------------------------------------------- 逐档合法性(合成 app)
class _SynDet:
    def __init__(self, width):
        self.width = width


class _SynParams:
    def __init__(self, d):
        self.d = d

    @classmethod
    def from_dict(cls, d, strict=True):
        if d["det"]["width"] == 99:
            raise ValueError("width 不能取 99")
        return cls(d)


def _syn_build_pattern(p):
    import types
    w = p.d["det"]["width"]
    if w == 7:
        raise AssertionError("width=7 违反构造不变式")
    node = types.SimpleNamespace(node_id="n", detector=_SynDet(min(w, 5)), where=(), consumes_stream=None)
    return types.SimpleNamespace(nodes=[node], edges=())


def _syn_eval_meta(params=None):
    return {"end_node": "n", "head_buffer_trading_days": 3}


def _syn_app():
    import types
    return types.SimpleNamespace(Params=_SynParams, build_pattern=_syn_build_pattern, eval_meta=_syn_eval_meta)


def test_probe_levels_marks_illegal_levels_with_error_text():
    """Params.from_dict 抛异常的档、build_pattern 抛异常的档各自标非法并带原文;底座档与其他档照常;
    构造出同一个 pattern 的档(宽度 5 以上被截到 5)等价键相同。"""
    base = {"det": {"width": 1}}
    rows = probe_levels(_syn_app(), base, ("det", "width"), [1, 99, 7, 5, 6])
    assert [r["value"] for r in rows] == [1, 99, 7, 5, 6]
    assert [r["legal"] for r in rows] == [True, False, False, True, True]
    assert rows[1]["error"] == "ValueError: width 不能取 99"
    assert rows[2]["error"] == "AssertionError: width=7 违反构造不变式"
    assert all(r["state_key"] is None and r["end_node"] is None and r["head_buffer"] is None for r in rows[1:3])
    assert rows[3]["state_key"] == rows[4]["state_key"] != rows[0]["state_key"]
    assert all((r["end_node"], r["head_buffer"], r["error"]) == ("n", 3, None) for r in (rows[0], rows[3], rows[4]))
    assert base == {"det": {"width": 1}}


def test_classify_probes_with_first_legal_alternative():
    """探针跳过构造不出来的替代档,取第一个合法的;替代档全都非法 → 人话拒绝。"""
    base = {"det": {"width": 1}}
    cls = classify(_syn_app(), base, {("det", "width"): [1, 99, 7, 3]}, {})
    assert cls.kinds[("det", "width")] == "D" and cls.detector_nodes[("det", "width")] == ("n",)
    with pytest.raises(ValueError, match="全都构造不出来"):
        classify(_syn_app(), base, {("det", "width"): [1, 99, 7]}, {})


# ---------------------------------------------------------------- 买点事件键 / 入场 bar / 长表列
import hashlib as _hashlib  # noqa: E402
from dataclasses import dataclass as _dataclass  # noqa: E402
import numpy as _np  # noqa: E402
import pandas as _pd  # noqa: E402
import multivar_core as MC  # noqa: E402
from path2.core import Event  # noqa: E402
from path2.dag.edges import TemporalEdge  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from path2.eval import spans_first_passage  # noqa: E402


def test_seg_id_of_is_deterministic_and_one_to_one():
    key = ((3, 7), (12, 12))
    expected = int.from_bytes(_hashlib.blake2b(json.dumps([[3, 7], [12, 12]], separators=(",", ":")).encode(),
                                               digest_size=8).digest(), "little", signed=True)
    assert MC.seg_id_of(key) == expected == MC.seg_id_of([(3, 7), (12, 12)]) == MC.seg_id_of(((_np.int64(3), 7), (12, 12)))
    keys = [((s, e),) for s in range(80) for e in range(s, 80)]
    keys += [((s, s + 2), (s + 5, s + 9)) for s in range(80)] + [((s + 5, s + 9), (s, s + 2)) for s in range(80)]
    ids = [MC.seg_id_of(k) for k in keys]
    assert len(set(ids)) == len(keys)                       # 区间组不同 → seg_id 不同(含顺序不同)
    assert all(-2 ** 63 <= i < 2 ** 63 for i in ids)
    assert json.loads(MC.span_key_json(key)) == [[3, 7], [12, 12]]


@_dataclass(frozen=True)
class _Pt(Event):
    pass


@_dataclass(frozen=True)
class _Seg(Event):
    pass


@_dataclass(frozen=True)
class _SegEndOnly(Event):
    """覆写样本 bar 取法:只取末根。"""
    def sample_bar_indices(self):
        return range(self.end_idx, self.end_idx + 1)


def test_entry_idx_of_takes_earliest_sample_bar_inside_window():
    evs = (_Seg(10, 15, confirm_idx=15), _Seg(2, 5, confirm_idx=5))
    assert MC.entry_idx_of(evs, 4, 30) == 4                 # 窗外的 2、3 不算
    assert MC.entry_idx_of(evs, 0, 30) == 2
    assert MC.entry_idx_of((_SegEndOnly(10, 15, confirm_idx=15),), 0, 30) == 15   # 走 sample_bar_indices
    with pytest.raises(ValueError):
        MC.entry_idx_of(evs, 20, 30)


def test_row_columns_label_modes():
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    spec = mod.build_pattern(mod.Params.from_dict(BASE, strict=True))
    kw = dict(module_path="path2_apps.bb_v1.dag_spec", base_dict=BASE, wide_overrides={}, scan_grid=SCAN_GRID,
              where_levels=WHERE_LEVELS, end_node="tb", label_horizon=40, fp_k=5.0)
    full = MC.row_columns(MC.ScanConfig(**kw), cls, spec)
    deferred = MC.row_columns(MC.ScanConfig(**kw, label_mode="deferred"), cls, spec)
    tail = ["buy_date", "seg_id", "M", "c0_atr_pct"]
    assert full[-10:] == tail + ["fr", "dd", "fp_up", "fp_down", "fp_both", "fp_none"]
    assert deferred[-4:] == tail and deferred == full[:-6]
    with pytest.raises(ValueError, match="标签模式"):
        MC.ScanConfig(**kw, label_mode="lazy")


# 合成 app:A 点事件 → B 区间事件(TemporalEdge,gap ≤5)。A 在 25、35,B 在 [27,30]、[37,41] → 两个 match。
class _PtDet:
    event_cls = _Pt

    def __init__(self, width):
        self.width = width

    def detect(self, df):
        return iter([_Pt(25, 25, confirm_idx=25), _Pt(35, 35, confirm_idx=35)])


class _SegDet:
    def __init__(self, cls):
        self.event_cls = cls

    def detect(self, df):
        return iter([self.event_cls(27, 30, confirm_idx=30), self.event_cls(37, 41, confirm_idx=41)])


class _Params:
    def __init__(self, d):
        self.d = d

    @classmethod
    def from_dict(cls, d, strict=True):
        return cls(d)


def _two_node_app(seg_cls):
    import types

    def build_pattern(p):
        return PatternSpec(pattern_id="syn", nodes=(NodeSpec("A", detector=_PtDet(p.d["a"]["width"])),
                                                    NodeSpec("B", detector=_SegDet(seg_cls))),
                           edges=(TemporalEdge("A", "B", min_gap=0, max_gap=5),))
    return types.SimpleNamespace(Params=_Params, build_pattern=build_pattern,
                                 eval_meta=lambda params=None: {"end_node": "B", "head_buffer_trading_days": 0})


def _syn_win(n=60, seed=0):
    rng = _np.random.default_rng(seed)
    close = 10 * _np.exp(_np.cumsum(rng.normal(0, 0.02, n)))
    return _pd.DataFrame({"date": _pd.bdate_range("2024-01-01", periods=n), "open": close,
                          "high": close * (1 + rng.uniform(0, 0.03, n)), "low": close * (1 - rng.uniform(0, 0.03, n)),
                          "close": close, "volume": 1e6})


def _syn_scan(seg_cls, label_mode):
    grid = {("a", "width"): [1, 2]}
    cfg = MC.ScanConfig(module_path="unused", base_dict={"a": {"width": 1}}, wide_overrides={}, scan_grid=grid,
                        where_levels={}, end_node="B", label_horizon=5, fp_k=1.0, label_mode=label_mode)
    win = _syn_win()
    app = _two_node_app(seg_cls)
    rows, segs = MC.scan_one_stock("SYN", win, win["date"][20], win["date"][45], cfg, mod=app)
    cls = classify(app, cfg.base_dict, grid, {})
    return rows, segs, cfg, win, MC.row_columns(cfg, cls, app.build_pattern(_Params(cfg.base_dict)))


def test_scan_one_stock_full_mode_new_columns():
    rows, segs, _cfg, win, cols = _syn_scan(_Seg, "full")
    spans = [((27, 30),), ((37, 41),)]
    assert segs == {MC.seg_id_of(k): k for k in spans}
    assert len(rows) == 4 and all(set(r) == set(cols) for r in rows)      # 2 个检测组合 × 2 个 match
    M, c0 = MC.stock_scales(win)
    for r in rows:
        key = ((r["B.start"], r["B.end"]),)
        assert r["seg_id"] == MC.seg_id_of(key)
        assert r["M"] == M[r["B.start"]] and r["c0_atr_pct"] == c0[r["B.start"]]
        fp = spans_first_passage(win, key, 5, 1.0, sample_window=(20, 45))
        assert [r[f"fp_{s}"] for s in MC.STATES] == [fp[s] for s in MC.STATES]
    assert _np.isfinite([r["M"] for r in rows]).all() and _np.isfinite([r["c0_atr_pct"] for r in rows]).all()


def test_scan_one_stock_deferred_mode_computes_no_labels(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("延迟标签模式不得调用标签函数")
    for name in ("match_first_passage", "match_forward_returns", "match_forward_drawdowns"):
        monkeypatch.setattr(MC, name, boom)
    rows, segs, _cfg, _win, cols = _syn_scan(_Seg, "deferred")
    assert len(rows) == 4 and all(set(r) == set(cols) for r in rows)
    assert not any(c in cols for c in MC.LABEL_COLS)
    assert segs == {MC.seg_id_of(k): k for k in [((27, 30),), ((37, 41),)]}


def test_scan_one_stock_deferred_rejects_custom_sample_bars():
    with pytest.raises(ValueError, match="样本 bar"):
        _syn_scan(_SegEndOnly, "deferred")
    rows, _segs, *_ = _syn_scan(_SegEndOnly, "full")              # 完整标签模式照常
    assert len(rows) == 4 and all(r["M"] == MC.stock_scales(_syn_win())[0][r["B.end"]] for r in rows)
