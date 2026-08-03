"""ThrowbackDetector on_gate 埋点单测(4 gate:phase1_break / phase1_rise_before_confirm /
phase1_no_confirm_timeout / phase2_break)。

TB 是 span 事件,attempt 定义采解读 X 松对齐(spec §2.4.2):一次 evaluate_throwback 调用
= 一次 attempt,阶段一/二失败共用同 failure_event_window 公式(start_idx=bo_idx+1)。
"""
import pandas as pd
import pytest

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackDetector, _find_confirm_idx, _find_end_idx
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


@pytest.fixture(autouse=True)
def _reset_current_symbol():
    """避免 set_current_symbol("TEST") 跨测试污染 ContextVar(承 Task 10/11 教训)。"""
    yield
    set_current_symbol(None)


def _make_df(rows):
    """构造 OHLCV DataFrame。rows: list of (o, h, l, c, v)。"""
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


def _fixture_phase1_break() -> tuple[list, pd.DataFrame]:
    """构造 anchor 破位 · 阶段一破位 fixture。

    bo_idx=15(而非 10):evaluate_throwback 用 _atr_at(df, bo_idx-1, atr_window=14),
    Wilder ATR 首个有效值在 idx=atr_window-1=13,故需 bo_idx-1>=13 ⟺ bo_idx>=14,
    否则 atr==0.0 短路提前 return None、_find_confirm_idx 根本不会被调用(0 gate 捕获)。
    """
    n = 30
    bo_idx = 15
    df = pd.DataFrame({
        'open': [100.0] * n, 'close': [100.0] * n,
        'high': [101.0] * n, 'low': [99.5] * n,
        'volume': [1000.0] * n,
    })
    # bo_{bo_idx} 触发 · anchor = high[bo_idx-1] = 101
    # bo 后 low[bo_idx+1] = 90 < 101 破位(新 detector default support_measure='low')
    df.loc[bo_idx + 1, 'low'] = 90.0
    bo = BOEvent(event_id=f"bo_{bo_idx}", start_idx=bo_idx, end_idx=bo_idx, confirm_idx=bo_idx,
                 drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                 peak_vol_max=0.0, referenced_points=())
    return [bo], df


def test_phase1_break_gate():
    set_current_symbol("TEST")
    bos, df = _fixture_phase1_break()
    detector = ThrowbackDetector()
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(iter(bos), df))
    breaks = [g for g in captured if g.gate_name == 'phase1_break']
    assert len(breaks) >= 1
    gf = breaks[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 16  # bo.end_idx + 1 (bo_idx=15)
    assert gf.failure_event_window[0] == 16
    assert gf.failure_event_window[1] == gf.gate_idx
    # spec 2026-07-12: sentinel-numeric #10/#13 · op='>=' + threshold_param=None
    assert gf.op == '>='
    assert gf.threshold_param is None
    # 破位差 = low(90) - anchor(101) = -11
    assert gf.measured.kind == 'anchor_delta'
    assert gf.measured.value == pytest.approx(-11.0)


def test_phase1_no_confirm_timeout():
    """扫满 max_start_gap 无 confirm(全根刷 trough 或无 stop signal)→ phase1_no_confirm_timeout。"""
    # 全根刷新 trough(每根新低)→ i-trough 恒 0,永不满足 K → no confirm
    rows = [(100.0 - i, 100.5 - i, 99.5 - i, 100.0 - i, 1000) for i in range(6)]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=5,
                        atr=1.0, stop_confirm_bars=2, big_rise_k=99.0,
                        on_gate=captured.append, atr_window=14)
    assert r is None
    timeouts = [g for g in captured if g.gate_name == 'phase1_no_confirm_timeout']
    assert len(timeouts) == 1
    gf = timeouts[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.gate_idx == 5   # end = min(bo_idx+max_start_gap, len-1) = 5
    assert gf.measured.kind == 'count'
    assert gf.measured.value == 5
    assert gf.threshold == 5
    assert gf.op is None
    assert gf.threshold_param is None


def test_phase1_rise_before_confirm():
    """confirm 前 high[i]-base_min ≥ big_rise_k*atr → phase1_rise_before_confirm gate → None。"""
    rows = [
        (100.0, 100.5, 99.0, 100.0, 1000),   # 0 bo
        (99.0, 99.5, 95.0, 96.0, 1000),      # 1 trough low=95, base_min=95
        (96.0, 99.0, 95.5, 98.8, 1000),      # 2 high=99, high-base=4 ≥ 1.5×2=3 → rise before confirm
    ]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_confirm_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                        atr=2.0, stop_confirm_bars=2, big_rise_k=1.5,
                        on_gate=captured.append, atr_window=14)
    assert r is None
    rises = [g for g in captured if g.gate_name == 'phase1_rise_before_confirm']
    assert len(rises) == 1
    gf = rises[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.gate_idx == 2
    assert gf.measured.kind == 'rise_atr'
    assert gf.measured.value == pytest.approx(2.0)   # rise(4)/atr(2)
    assert gf.threshold == 1.5
    assert gf.op == '>='
    assert gf.threshold_param == 'big_rise_k'


def test_phase2_break():
    """confirm 后 support_measure < anchor → 事件仍产 outcome='break',但 gate 仍 emit。"""
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),   # 0 trough
        (95.0, 95.5, 95.0, 95.1, 1000),   # 1 confirm
        (95.0, 95.5, 89.0, 90.0, 1000),   # 2 low=89<anchor=90 破位
    ]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_end_idx(df, confirm_idx=1, trough_idx=0, anchor=90.0,
                      max_window=10, atr=1.0, big_rise_k=99.0,
                      on_gate=captured.append, bo_idx=0, atr_window=14)
    # 事件仍产(不 None)
    assert r == (1, "break")
    # gate 仍 emit(诊断层看得见)
    breaks = [g for g in captured if g.gate_name == 'phase2_break']
    assert len(breaks) == 1
    gf = breaks[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1  # bo_idx + 1
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.gate_idx == 2
    assert gf.anchor_bar == 0
    assert gf.measured.kind == 'anchor_delta'
    assert gf.measured.value == pytest.approx(-1.0)
    assert gf.threshold == 0.0
    assert gf.op == '>='
    assert gf.threshold_param is None


def test_no_gate_when_on_gate_none():
    """on_gate 未挂时不 emit、不抛异常(生产路径无开销)。"""
    bos, df = _fixture_phase1_break()
    detector = ThrowbackDetector()
    # detector.on_gate 保持默认 None
    evs = list(detector.detect(iter(bos), df))
    assert evs == []   # phase1_break 场景 → 不产事件
