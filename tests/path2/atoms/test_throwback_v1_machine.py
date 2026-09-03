"""tb v1 首段状态机纯函数测试:判据逐条(spec §3 检查顺序)+ 三 gate + debug 锚。

约定:vol 注入式常数 1.0(k=1.5 → 反弹阈 trough+1.5);opens 缺省 = close*0.99(无阴线,
UP→DOWN 只靠收跌);bo=3(closes[0..3] 平台),gbot=50(不触发破线,除非显式给)。
"""
import numpy as np
import pytest

import path2.atoms.throwback_v1 as tb
from path2.atoms.throwback_v1 import FirstSegment, run_first_segment


def mk(closes, opens=None, vol=1.0):
    closes = np.asarray(closes, dtype=float)
    opens = (np.asarray(opens, dtype=float) if opens is not None else closes * 0.99)
    vol = (np.asarray(vol, dtype=float) if np.ndim(vol) else np.full(len(closes), float(vol)))
    return closes, opens, vol


def run(closes, opens=None, vol=1.0, bo=3, gbot=50.0, k=1.5, K=1, ms=60, on_gate=None,
        real_closes=None):
    c, o, v = mk(closes, opens, vol)
    return run_first_segment(c, o, bo, gbot, v, max_rise_k=k, stop_confirm_bars=K,
                             max_span=ms, on_gate=on_gate, vol_window=14,
                             real_closes=(None if real_closes is None
                                          else np.asarray(real_closes, dtype=float)))


class TestUpToDown:
    def test_decline_bar_then_stable_K1_then_rise(self):
        # i=4 收跌 99<100 → DOWN trough=99;i=5 99.5 不刷新且 <100.5 → cnt=1≥1 → STABLE enter=5;
        # i=6 120 > 99+1.5 → rise,exit=5
        assert run([100, 100, 100, 100, 99, 99.5, 120]) == FirstSegment(5, 5, 'rise')

    def test_red_bar_triggers_down_even_if_close_up(self):
        opens = [99, 99, 99, 99, 102, 100, 100]        # i=4 阴线:close 101 < open 102
        assert run([100, 100, 100, 100, 101, 101.2, 130], opens) == FirstSegment(5, 5, 'rise')

    def test_no_pullback_stays_up_and_returns_none(self):
        gates = []
        assert run([100, 100, 100, 100, 101, 101.2, 130], ms=3, on_gate=gates.append) is None
        assert [g.gate_name for g in gates] == ['budget_no_stable']


class TestDown:
    def test_new_low_refreshes_trough_and_resets_count(self):
        # K=2:i=4 DOWN trough=99;i=5 98.5 刷新 cnt=0;i=6 98.6 cnt=1;i=7 98.7 cnt=2 → enter=7
        assert run([100, 100, 100, 100, 99, 98.5, 98.6, 98.7, 130], K=2) == FirstSegment(7, 7, 'rise')

    def test_equal_value_is_not_refresh(self):
        # i=5 close == trough(99)→ 不刷新 → cnt=1 → enter=5
        assert run([100, 100, 100, 100, 99, 99, 130]) == FirstSegment(5, 5, 'rise')

    def test_rebound_returns_to_up_not_death(self):
        # i=4 DOWN trough=99;i=5 101 > 100.5 → UP(不判死);i=6 100<101 收跌 → DOWN trough=100;
        # i=7 100.2 → enter=7;i=8 130 → rise
        assert run([100, 100, 100, 100, 99, 101, 100, 100.2, 130]) == FirstSegment(7, 7, 'rise')

    def test_vol_nan_degrades_rebound_arm(self):
        # i=5 105 本应反弹回 UP,但 vol NaN → 反弹臂降级 → 计数 → enter=5;
        # i=6 vol=1.0 有效,130 同时满足 vol 臂(130>99+1.5)与 peak 臂(130>100)→ rise,exit=5
        vol = [1.0] * 7
        vol[5] = float('nan')
        assert run([100, 100, 100, 100, 99, 105, 130], vol=vol) == FirstSegment(5, 5, 'rise')


class TestStable:
    def test_peak_arm_alone_does_not_rise(self):
        # k=100 → vol 臂不可达;i=6 100.5 > peak=100 但 and 语义下单臂不够 → 扫满预算 → timeout
        assert run([100, 100, 100, 100, 99, 99.5, 100.5], k=100, ms=60) == FirstSegment(5, 6, 'timeout')

    def test_vol_arm_below_peak_does_not_rise(self):
        # i=6 92.5 > 90+1.5 满足 vol 臂,但仍低于 peak=100 → and 语义下不 rise → 段继续 → timeout
        assert run([100, 100, 100, 100, 90, 90.5, 92.5], ms=60) == FirstSegment(5, 6, 'timeout')

    def test_nan_vol_in_stable_cannot_rise(self):
        # STABLE 阶段 vol NaN → rise 臂整体不成立(and 语义),即使 close 130 同时 > peak 也不触发
        vol = [1.0] * 7
        vol[6] = float('nan')
        assert run([100, 100, 100, 100, 99, 99.5, 130], vol=vol) == FirstSegment(5, 6, 'timeout')

    def test_equal_to_peak_is_not_rise_then_timeout_includes_last_bar(self):
        # ms=3 → end=6;i=6 close==peak 不触发;扫满 STABLE → timeout,end=6(含末根)
        assert run([100, 100, 100, 100, 99, 99.5, 100], k=100, ms=3) == FirstSegment(5, 6, 'timeout')

    def test_weak_exit(self):
        assert run([100, 100, 100, 100, 95, 95.5, 94.9]) == FirstSegment(5, 5, 'weak')

    def test_end_clamped_to_last_bar(self):
        # n=7,ms=60 → end=6;STABLE 到末根 → timeout(5,6)
        assert run([100, 100, 100, 100, 99, 99.5, 99.6], k=100) == FirstSegment(5, 6, 'timeout')


class TestGlobalBottom:
    def test_break_before_stable_returns_none_with_gate(self):
        gates = []
        assert run([100, 100, 100, 100, 97], gbot=98, on_gate=gates.append) is None
        assert len(gates) == 1
        g = gates[0]
        assert g.gate_name == 'break_no_stable'
        assert g.failure_event_window == (4, 4) and g.start_idx == 4 and g.gate_idx == 4
        assert g.anchor_bar == 3
        assert g.measured.kind == 'anchor_delta' and g.measured.value == pytest.approx(97 - 98)

    def test_break_truncate_in_stable_still_yields_event(self):
        gates = []
        assert run([100, 100, 100, 100, 95, 95.5, 93], gbot=94,
                   on_gate=gates.append) == FirstSegment(5, 5, 'break')
        assert [g.gate_name for g in gates] == ['break_truncate']
        assert gates[0].gate_idx == 6

    def test_equal_to_gbot_is_not_break(self):
        assert run([100, 100, 100, 100, 95, 95.5, 130], gbot=95) == FirstSegment(5, 5, 'rise')

    def test_budget_no_stable_gate_fields(self):
        gates = []
        assert run([100, 101, 102, 103, 104, 105, 106], ms=3, on_gate=gates.append) is None
        g = gates[0]
        assert g.gate_name == 'budget_no_stable'
        assert g.gate_idx == 6 and g.failure_event_window == (4, 6)
        assert g.measured.kind == 'count' and g.measured.value == 3

    def test_no_gate_when_on_gate_none(self):
        assert run([100, 100, 100, 100, 97], gbot=98) is None   # 不抛、不 emit


class TestRealCloses:
    def test_red_arm_uses_real_close_not_measure(self):
        # measure 列全程不阴线(opens 99),但真 close[4]=98 < open 99 → 阴线 → DOWN trough=101(measure)
        opens = [99] * 7
        real = [100, 100, 100, 100, 98, 100, 100]
        assert run([100, 100, 100, 100, 101, 101.5, 130], opens,
                   real_closes=real) == FirstSegment(5, 5, 'rise')
        assert run([100, 100, 100, 100, 101, 101.5, 130], opens, ms=3) is None


class TestDebugAnchors:
    def test_fire_sequence_confirm_then_end(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break',
                            lambda i, *, anchor_kind, **_kw: calls.append((anchor_kind, i)))
        assert run([100, 100, 100, 100, 99, 99.5, 120]) == FirstSegment(5, 5, 'rise')
        assert calls == [('confirm', 5), ('end', 5)]

    def test_timeout_end_anchor_is_last_bar(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tb, 'debug_break',
                            lambda i, *, anchor_kind, **_kw: calls.append((anchor_kind, i)))
        run([100, 100, 100, 100, 99, 99.5, 100], k=100, ms=3)
        assert calls == [('confirm', 5), ('end', 6)]

    def test_bo_at_last_bar_empty_scan(self):
        # end = min(bo+max_span, n-1) = bo(4) → 循环区间为空,一根都没扫;
        # 不该 emit 任何 gate(旧行为误 emit budget_no_stable,首尾颠倒且
        # measured.value 与实际扫描数不符,已修——空扫描与「未入段」是两回事)
        gates = []
        assert run([100, 100, 100, 100, 100], bo=4, on_gate=gates.append) is None
        assert gates == []
