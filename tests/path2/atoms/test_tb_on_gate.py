"""ThrowbackDetector on_gate 埋点单测(4 gate:phase1_break / phase1_pullback_shortage /
phase1_no_trough_timeout / phase2_break)。

TB 是 span 事件,attempt 定义采解读 X 松对齐(spec §2.4.2):一次 evaluate_throwback 调用
= 一次 attempt,阶段一/二失败共用同 failure_event_window 公式(start_idx=bo_idx+1)。
"""
import pandas as pd
import pytest

from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackDetector, _find_start_idx, _find_end_idx
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
    否则 atr==0.0 短路提前 return None、_find_start_idx 根本不会被调用(0 gate 捕获)。
    """
    n = 30
    bo_idx = 15
    df = pd.DataFrame({
        'open': [100.0] * n, 'close': [100.0] * n,
        'high': [101.0] * n, 'low': [99.5] * n,
        'volume': [1000.0] * n,
    })
    # bo_{bo_idx} 触发 · anchor = high[bo_idx-1] = 101
    # bo 后 close[bo_idx+1] = 90 < 101 破位(support_measure 默认 'low'=99.5 本身已破位)
    df.loc[bo_idx + 1, 'close'] = 90.0
    bo = BOEvent(event_id=f"bo_{bo_idx}", start_idx=bo_idx, end_idx=bo_idx,
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


def test_phase1_pullback_shortage():
    """止跌确认但回落深度 < pullback_min_atr*atr → phase1_pullback_shortage。

    复用 test_throwback.py::test_find_start_idx_pullback_gate_fail 同款 fixture:
    双根不创新低 + 阳线止跌确认@i=2,但回落深度 peak(100)-low(99.7)=0.3 < 1.0×atr(1.0)。
    """
    rows = [
        (99.8, 100.0, 99.7, 99.9, 1000),
        (99.8, 100.0, 99.75, 99.9, 1000),
        (99.8, 100.0, 99.80, 99.95, 1000),
        (99.9, 100.1, 99.85, 100.0, 1000),
    ]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=10,
                        atr=1.0, pullback_min_atr=1.0,
                        on_gate=captured.append, atr_window=14)
    assert r is None
    shortages = [g for g in captured if g.gate_name == 'phase1_pullback_shortage']
    assert len(shortages) == 1
    gf = shortages[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1  # bo_idx + 1
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.anchor_bar == 0
    assert gf.measured.kind == 'pullback_atr'
    assert gf.measured.value == pytest.approx(0.25)  # depth(0.25)/atr(1.0)
    assert gf.threshold == 1.0
    assert gf.op == '>='
    assert gf.threshold_param == 'pullback_min_atr'


def test_phase1_no_trough_timeout():
    """扫满 max_start_gap 全程创新低、无止跌确认 → phase1_no_trough_timeout。

    复用 test_throwback.py::test_find_start_idx_no_stop_in_window 同款 fixture。
    """
    rows = [(100.0 - i, 100.5 - i, 99.5 - i, 100.0 - i, 1000) for i in range(6)]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_start_idx(df, bo_idx=0, anchor=90.0, max_start_gap=5,
                        atr=1.0, pullback_min_atr=0.0,
                        on_gate=captured.append, atr_window=14)
    assert r is None
    timeouts = [g for g in captured if g.gate_name == 'phase1_no_trough_timeout']
    assert len(timeouts) == 1
    gf = timeouts[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.gate_idx == 5   # end = min(bo_idx+max_start_gap, len-1) = 5
    assert gf.measured.kind == 'count'
    assert gf.measured.value == 5
    assert gf.threshold == 5
    tm = timeouts[0]
    assert tm.op is None
    assert tm.threshold_param is None


def test_phase2_break():
    """start 后阶段二破位(support_measure < anchor)→ phase2_break。

    复用 test_throwback.py::test_find_end_idx_break_returns_none 同款 fixture。
    """
    rows = [
        (95.0, 95.5, 95.0, 95.2, 1000),
        (95.0, 95.5, 89.0, 90.0, 1000),   # 1 low=89<anchor=90 破位
    ]
    df = _make_df(rows)
    captured: list[GateFailure] = []
    r = _find_end_idx(df, start_idx=0, anchor=90.0, max_window=10,
                      atr=1.0, big_rise_k=1.5,
                      on_gate=captured.append, bo_idx=0, atr_window=14)
    assert r is None
    breaks = [g for g in captured if g.gate_name == 'phase2_break']
    assert len(breaks) == 1
    gf = breaks[0]
    assert gf.class_id == 'tb'
    assert gf.start_idx == 1  # bo_idx + 1 (X 松对齐,与 start_idx 参数无关)
    assert gf.failure_event_window == (1, gf.gate_idx)
    assert gf.gate_idx == 1
    assert gf.anchor_bar == 0
    assert gf.measured.kind == 'anchor_delta'
    assert gf.measured.value == pytest.approx(-1.0)  # low(89)-anchor(90)
    assert gf.threshold == 0.0
    # spec 2026-07-12: sentinel-numeric #10/#13 · op='>=' + threshold_param=None
    assert gf.op == '>='
    assert gf.threshold_param is None


def test_no_gate_when_on_gate_none():
    """on_gate 未挂时不 emit、不抛异常(生产路径无开销)。"""
    bos, df = _fixture_phase1_break()
    detector = ThrowbackDetector()
    # detector.on_gate 保持默认 None
    list(detector.detect(iter(bos), df))  # 不应抛错
