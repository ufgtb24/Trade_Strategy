"""ThrowbackEventV1 + ThrowbackDetectorV1(首段即停)测试:字段 / e2e 四 outcome / gate 契约 /
debug 锚 fire 序列 / 排序不变式 / max_day_drop 字段。

fixture 约定:_base_series 造 n 根平台 (o=h=l=c=base),vol_window=3 让 median TR 在第 4 根即有效
(TR=2:high-low),便于用小数据流。bo 由 _bo/_burst 造,burst span 可单根可多根;gbot = span 内
**全部 bar** 的 measure 最小——注意 _base_series 造出的 base 根若落在 span 内会参与取最小。
"""
from unittest.mock import patch

import pandas as pd
import pytest

import path2.atoms.throwback_v1 as tb
from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v1 import ThrowbackDetectorV1, ThrowbackEventV1, _revert_max_day_drop
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


def _make_df(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")


def _burst(*bos):
    first, last = bos[0], bos[-1]
    return BurstEvent(start_idx=first.start_idx, end_idx=last.end_idx,
                      confirm_idx=last.end_idx, members=tuple(bos))


def _base_series(n, base=100.0):
    # high-low=2 → TR=2 → median TR=2;k=1.5 → 反弹阈 trough+3
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def _det(**kw):
    d = dict(max_rise_k=1.5, stop_confirm_bars=1, vol_window=3, max_span=20, measure='close')
    d.update(kw)
    return ThrowbackDetectorV1(**d)


@pytest.fixture(autouse=True)
def _reset_symbol():
    yield
    set_current_symbol(None)


class TestInit:
    def test_defaults_and_measure_validation(self):
        d = ThrowbackDetectorV1()
        assert d._kw == dict(max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20,
                             measure='close')
        with pytest.raises(ValueError):
            ThrowbackDetectorV1(measure='nope')
        assert ThrowbackDetectorV1.event_cls is ThrowbackEventV1
        assert ThrowbackDetectorV1.on_gate is None and ThrowbackDetectorV1.has_debug_hooks

    def test_stop_confirm_bars_below_one_rejected(self):
        # cnt 在第一根不刷新根即变 1,K<=0 与 K=1 行为完全等价(退化区间无独立语义)——
        # 拒绝而非静默退化,防旧 K=0(独立语义:trough 当根确认)被误搬来变成 K=1。
        ThrowbackDetectorV1(stop_confirm_bars=1)   # 边界合法值不抛
        with pytest.raises(ValueError):
            ThrowbackDetectorV1(stop_confirm_bars=0)
        with pytest.raises(ValueError):
            ThrowbackDetectorV1(stop_confirm_bars=-1)


class TestEventFields:
    def test_rise_event_fields(self):
        # Ruling 1: burst 改双 bo(_bo(8), _bo(9)),用 rows[8]的 base-100 根把 gbot 压到 100
        # (单 bo 版 gbot=close[9]=103 会让回踩根 102.5 <103 提前 break_no_stable,产不出事件)。
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)         # bo_9,rows[8] 仍是 base-100 根 → gbot=100
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),         # 10 收跌 → DOWN trough=102.5
                 (102.5, 103.0, 102.0, 102.8, 1000),         # 11 不刷新 → STABLE enter=11
                 (102.8, 108.0, 102.8, 107.0, 1000)]         # 12 107 > 102.5+1.5*medTR → rise
        df = _make_df(rows)
        evs = list(_det().detect([_burst(_bo(8), _bo(9))], df))
        assert len(evs) == 1
        e = evs[0]
        assert (e.start_idx, e.end_idx, e.confirm_idx) == (11, 11, 11)
        assert e.outcome == 'rise' and e.anchor_bo_id == 'bo_9#0'
        assert e.max_day_drop == pytest.approx(_revert_max_day_drop(df, 9, 11))
        assert e.max_day_drop == pytest.approx((103.0 - 102.5) / 103.0)

    def test_break_by_span_min_uses_burst_span(self):
        # span [7,9] 三根都改写:close[7]=101,close[8]=102,close[9]=103 → gbot=min=101。
        # 回踩根 10 close=102,夹在 101(span gbot)与 103(last_bo gbot)之间 → 两种口径分叉:
        rows = _base_series(10)
        rows[7] = (101.5, 102.5, 100.5, 101.0, 3000)
        rows[8] = (101.5, 102.5, 101.0, 102.0, 1000)
        rows[9] = (103.0, 104.0, 102.0, 103.0, 5000)
        rows += [(102.0, 103.0, 101.0, 102.0, 1000),   # 10 收跌(102<103)→ DOWN trough=102;102>=101 不破线
                 (102.0, 102.5, 101.5, 102.0, 1000),    # 11 不刷新 → STABLE enter=11
                 (102.0, 111.0, 102.0, 110.0, 1000)]    # 12 110>peak → rise,exit=11
        df = _make_df(rows)
        # span 口径:gbot=101,回踩 102 不破线 → 正常入段收口,产一条 rise 事件
        evs = list(_det().detect([_burst(_bo(7), _bo(9))], df))
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(11, 11, 'rise')]
        # 对照:last_bo 口径(burst span 收窄成单根 9)→ gbot=close[9]=103,回踩 102<103 → 入段前破线,不产
        gates = []
        det = _det(); det.on_gate = gates.append
        assert list(det.detect([_burst(_bo(9))], df)) == []
        assert [g.gate_name for g in gates] == ['break_no_stable']

    def test_boundary_bo_skipped(self):
        df = _make_df(_base_series(6))
        assert list(_det().detect([_burst(_bo(0))], df)) == []       # bo<1
        assert list(_det().detect([_burst(_bo(6))], df)) == []       # bo>=len


class TestOutcomesE2E:
    def test_weak_outcome(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 95.0, 96.0, 5000)                    # bo_9,gbot=96
        rows += [(96.0, 97.0, 95.5, 98.0, 1000),                      # 10 阳线收涨 → 仍 UP
                 (98.0, 98.5, 97.0, 97.5, 1000),                      # 11 收跌 → DOWN trough=97.5
                 (97.5, 98.0, 97.0, 97.6, 1000),                      # 12 不刷新 → STABLE enter=12
                 (97.6, 97.8, 96.5, 97.0, 1000)]                      # 13 97 < 97.5 → weak,end=12
        evs = list(_det().detect([_burst(_bo(9))], _make_df(rows)))
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(12, 12, 'weak')]

    def test_break_outcome_in_stable(self):
        # Ruling 2:brief 原有一次先赋值后被整个覆盖的死代码,已删;保留其解释作普通注释——
        # 99.8 < gbot 入段前 → 不产;换成先企稳再破线。
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 99.0, 100.0, 5000)                   # gbot=100
        rows += [(101.0, 101.5, 100.2, 100.4, 1000),                  # 10 阴线(100.4<101)→ DOWN trough=100.4
                 (100.4, 100.9, 100.3, 100.5, 1000),                  # 11 不刷新 → STABLE enter=11
                 (100.5, 100.6, 99.0, 99.5, 1000)]                    # 12 99.5<gbot → break,end=11
        gates = []
        det = _det(); det.on_gate = gates.append
        set_current_symbol("T")
        evs = list(det.detect([_burst(_bo(9))], _make_df(rows)))
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(11, 11, 'break')]
        assert [g.gate_name for g in gates] == ['break_truncate']

    def test_timeout_outcome_includes_last_bar(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),                  # 10 DOWN trough=102.5
                 (102.5, 103.0, 102.0, 102.6, 1000),                  # 11 STABLE enter=11
                 (102.6, 103.0, 102.2, 102.7, 1000),                  # 12 横盘
                 (102.7, 103.0, 102.2, 102.65, 1000)]                 # 13 末根,横盘
        evs = list(_det(max_span=4).detect([_burst(_bo(8), _bo(9))], _make_df(rows)))   # end=min(13, 13)
        assert [(e.start_idx, e.end_idx, e.outcome) for e in evs] == [(11, 13, 'timeout')]

    def test_multiple_bursts_sorted_by_end_then_start(self):
        # Ruling 1: 两处 burst 都改双 bo,把 gbot 压到未被改写的 base 根(8→100,17→107)
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]                   # bo_9 → (11,11,'rise')
        rows += _base_series(6, base=107.0)
        rows[18] = (107.0, 112.0, 107.0, 110.0, 5000)                  # bo_18
        rows += [(110.0, 110.5, 109.0, 109.5, 1000), (109.5, 110.0, 109.0, 109.8, 1000),
                 (109.8, 116.0, 109.8, 115.0, 1000)]                   # → (20,20,'rise')
        df = _make_df(rows)
        evs = list(_det().detect([_burst(_bo(17), _bo(18)), _burst(_bo(8), _bo(9))], df))   # 乱序喂入
        assert [(e.start_idx, e.end_idx) for e in evs] == [(11, 11), (20, 20)]
        assert [e.anchor_bo_id for e in evs] == ['bo_9#0', 'bo_18#0']


class TestGateContract:
    def test_break_no_stable_gate_fields(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000)]                   # 10 <gbot=103 → break_no_stable
        gates = []
        det = _det(); det.on_gate = gates.append
        set_current_symbol("SYM")
        assert list(det.detect([_burst(_bo(9))], _make_df(rows))) == []
        assert len(gates) == 1
        g = gates[0]
        assert isinstance(g, GateFailure) and g.gate_name == 'break_no_stable'
        assert g.failure_event_window == (10, 10) and g.start_idx == 10 and g.gate_idx == 10
        assert g.anchor_bar == 9 and g.symbol == 'SYM'
        assert g.evaluation_lookback == (10 - 3, 9)
        assert g.threshold_param is None or g.op is not None

    def test_budget_no_stable_gate(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 105.0, 103.0, 104.0, 1000), (104.0, 106.0, 104.0, 105.0, 1000)]  # 一路涨
        gates = []
        det = _det(max_span=2); det.on_gate = gates.append
        assert list(det.detect([_burst(_bo(9))], _make_df(rows))) == []
        assert [g.gate_name for g in gates] == ['budget_no_stable']
        assert gates[0].gate_idx == 11 and gates[0].measured.value == 2

    def test_no_gate_on_success_paths(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]
        gates = []
        det = _det(); det.on_gate = gates.append
        assert len(list(det.detect([_burst(_bo(8), _bo(9))], _make_df(rows)))) == 1
        assert gates == []

    def test_emit_helper_skips_debug_break_when_on_gate_none(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break', lambda i, *, anchor_kind, **_kw: calls.append(i))
        from path2.dag.gate_failure import MeasuredKindAware
        tb._emit_tb_gate(9, 12, 'break_no_stable', MeasuredKindAware(kind='count', value=0.0, label='x'),
                         0.0, 14, None)
        assert calls == []
        collected = []
        tb._emit_tb_gate(9, 12, 'break_no_stable', MeasuredKindAware(kind='count', value=0.0, label='x'),
                         0.0, 14, collected.append)
        assert calls == [12] and len(collected) == 1


class TestDebugAnchors:
    def test_success_fire_sequence_entry_confirm_end(self):
        # Ruling 1: 双 bo burst,gbot 压到 rows[8]=100(base 根)
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 102.0, 102.5, 1000), (102.5, 103.0, 102.0, 102.8, 1000),
                 (102.8, 108.0, 102.8, 107.0, 1000)]
        with patch('path2.atoms.throwback_v1.debug_break') as mock_break:
            evs = list(_det().detect([_burst(_bo(8), _bo(9))], _make_df(rows)))
        calls = [(c.kwargs['anchor_kind'], c.args[0]) for c in mock_break.call_args_list]
        assert calls == [('entry', 9), ('confirm', 11), ('end', 11)]
        assert (evs[0].start_idx, evs[0].end_idx) == (11, 11)      # 锚 bar 与事件字段对齐

    def test_failure_fire_sequence_entry_gate(self):
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)
        rows += [(103.0, 103.5, 100.0, 100.5, 1000)]
        det = _det(); det.on_gate = lambda gf: None
        with patch('path2.atoms.throwback_v1.debug_break') as mock_break:
            list(det.detect([_burst(_bo(9))], _make_df(rows)))
        calls = [(c.kwargs['anchor_kind'], c.args[0]) for c in mock_break.call_args_list]
        assert calls == [('entry', 9), ('gate', 10)]


class TestRevertMaxDayDrop:
    def test_algorithm_unchanged(self):
        rows = _base_series(10)
        rows += [(100.0, 101.0, 90.0, 92.0, 1000),     # 10 阴线 revert_idx=10:drop (100-92)/100=0.08
                 (92.0, 93.0, 80.0, 82.0, 1000),       # 11 drop (92-82)/92≈0.1087
                 (82.0, 84.0, 81.0, 83.0, 1000)]       # 12 收涨
        df = _make_df(rows)
        assert _revert_max_day_drop(df, 9, 12) == pytest.approx((92.0 - 82.0) / 92.0)
        assert _revert_max_day_drop(df, 9, 9) == 0.0
