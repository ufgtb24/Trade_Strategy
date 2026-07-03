"""ThrowbackEvent + ThrowbackDetector 单测(2026-06 重构)。"""
import pandas as pd
import pytest

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackEvent, ThrowbackDetector, ThrowbackResult
import path2.atoms.throwback as tb_mod


def _bo(end_idx, vol_ratio=3.0):
    return BOEvent(event_id=f"bo_{end_idx}", start_idx=end_idx, end_idx=end_idx, vol_ratio=vol_ratio)


# ---- ThrowbackEvent 瘦身后字段 ----

def test_event_fields_minimal():
    ev = ThrowbackEvent(event_id="tb_21_24", start_idx=21, end_idx=24, anchor_bo_id="bo_20")
    assert ev.start_idx == 21 and ev.end_idx == 24
    assert ev.anchor_bo_id == "bo_20"
    assert ev.class_id == "tb"


def test_event_no_trigger_or_strength_attrs():
    ev = ThrowbackEvent(event_id="tb_5_5", start_idx=5, end_idx=5, anchor_bo_id="bo_4")
    assert not hasattr(ev, "trigger_idx")
    assert not hasattr(ev, "strength")
    assert not hasattr(ev, "confirmed")


def test_event_start_eq_end_ok():
    ev = ThrowbackEvent(event_id="tb_5_5", start_idx=5, end_idx=5, anchor_bo_id="bo_4")
    assert ev.start_idx == ev.end_idx == 5


def test_event_frozen():
    ev = ThrowbackEvent(event_id="tb_5_6", start_idx=5, end_idx=6, anchor_bo_id="bo_4")
    with pytest.raises(Exception):  # FrozenInstanceError
        ev.anchor_bo_id = "x"  # type: ignore


# ---- ThrowbackDetector(monkeypatch evaluate_throwback 返回 Optional[ThrowbackResult])----

def test_detector_only_emits_success(monkeypatch):
    table = {10: ThrowbackResult(11, 13),   # 成功
             20: None,                       # 失败(破位/无回踩)→ 不产
             30: None}
    monkeypatch.setattr(tb_mod, "evaluate_throwback", lambda bo, df, **kw: table[bo.end_idx])
    evs = list(ThrowbackDetector().detect([_bo(10), _bo(20), _bo(30)], df=None))
    assert len(evs) == 1
    assert evs[0].anchor_bo_id == "bo_10"
    assert evs[0].start_idx == 11 and evs[0].end_idx == 13


def test_detector_sorts_by_end_idx(monkeypatch):
    table = {10: ThrowbackResult(20, 25),    # 远
             12: ThrowbackResult(13, 14)}     # 近
    monkeypatch.setattr(tb_mod, "evaluate_throwback", lambda bo, df, **kw: table[bo.end_idx])
    evs = list(ThrowbackDetector().detect([_bo(10), _bo(12)], df=None))
    assert [e.end_idx for e in evs] == [14, 25]
    assert [e.anchor_bo_id for e in evs] == ["bo_12", "bo_10"]


def test_detector_event_id_is_span_id(monkeypatch):
    monkeypatch.setattr(tb_mod, "evaluate_throwback",
                        lambda bo, df, **kw: ThrowbackResult(21, 24))
    ev = list(ThrowbackDetector().detect([_bo(20)], df=None))[0]
    assert ev.event_id == "tb_21_24"  # span_id("tb",21,24)


def test_detector_passes_new_kwargs(monkeypatch):
    seen = {}
    def fake(bo, df, **kw):
        seen.update(kw)
        return None
    monkeypatch.setattr(tb_mod, "evaluate_throwback", fake)
    list(ThrowbackDetector(max_start_gap=3, max_window=4, atr_window=10,
                           big_rise_k=2.0, pullback_min_atr=0.5,
                           anchor_measure="close", support_measure="close"
                           ).detect([_bo(5)], df=None))
    assert seen == dict(max_start_gap=3, max_window=4, atr_window=10,
                        big_rise_k=2.0, pullback_min_atr=0.5,
                        anchor_measure="close", support_measure="close")


def test_detector_empty_and_all_filtered(monkeypatch):
    assert list(ThrowbackDetector().detect([], df=None)) == []
    monkeypatch.setattr(tb_mod, "evaluate_throwback", lambda bo, df, **kw: None)
    assert list(ThrowbackDetector().detect([_bo(10), _bo(20)], df=None)) == []


def test_detector_invalid_measure_raises():
    with pytest.raises(ValueError, match="anchor_measure"):
        ThrowbackDetector(anchor_measure="foo")
    with pytest.raises(ValueError, match="support_measure"):
        ThrowbackDetector(support_measure="bar")


# ---- dag 集成:bo → tb 经 TemporalEdge ----

from path2.runner import run
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze


class _FakeBO:
    def __init__(self, bos): self._bos = bos
    def detect(self, df): return iter(self._bos)


def test_run_enforces_end_order(monkeypatch):
    table = {10: ThrowbackResult(20, 25), 12: ThrowbackResult(13, 14)}
    monkeypatch.setattr(tb_mod, "evaluate_throwback", lambda bo, df, **kw: table[bo.end_idx])
    evs = list(run(ThrowbackDetector(), [_bo(10), _bo(12)], None))
    assert [e.end_idx for e in evs] == [14, 25]


def test_dag_engine_bo_to_tb_match(monkeypatch):
    # tb.start = bo.end+1;gap = tb.start − bo.end = 1 ∈ [1,10]
    monkeypatch.setattr(tb_mod, "evaluate_throwback",
                        lambda bo, df, **kw: ThrowbackResult(bo.end_idx + 1, bo.end_idx + 3))
    bo_node = NodeSpec("bo", detector=_FakeBO([_bo(20)]))
    tb_node = NodeSpec("tb", detector=ThrowbackDetector(), consumes_stream="bo")
    spec = PatternSpec(pattern_id="p3", nodes=(bo_node, tb_node),
                       edges=(TemporalEdge("bo", "tb", min_gap=1, max_gap=10),))
    res = analyze(spec, df=object())
    assert len(res.matches) == 1
    m = res.matches[0]
    assert m.role_index["bo"].end_idx == 20
    assert m.role_index["tb"].start_idx == 21
    assert m.role_index["tb"].end_idx == 23


# ---- 去重:两个 bo 收敛到同一 span → 一个 tb 事件 ----

def test_detector_dedupes_same_span(monkeypatch):
    # 两个不同 bo 收敛到同一 (start,end) 窗 → 同 event_id → 必须去重为 1 个事件
    monkeypatch.setattr(tb_mod, "evaluate_throwback",
                        lambda bo, df, **kw: ThrowbackResult(133, 133))
    evs = list(ThrowbackDetector().detect([_bo(131), _bo(132)], df=None))
    assert len(evs) == 1
    assert evs[0].event_id == "tb_133"


def test_detector_dedup_passes_run_invariant(monkeypatch):
    # 去重后过 run() 不再触发 event_id 单 run 内重复
    monkeypatch.setattr(tb_mod, "evaluate_throwback",
                        lambda bo, df, **kw: ThrowbackResult(133, 133))
    evs = list(run(ThrowbackDetector(), [_bo(131), _bo(132)], None))  # 不应抛 ValueError
    assert len(evs) == 1
