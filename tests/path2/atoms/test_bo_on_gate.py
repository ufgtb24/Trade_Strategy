import pandas as pd
import pytest
from path2.atoms.breakout import BODetector
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


@pytest.fixture(autouse=True)
def _reset_current_symbol():
    """避免 set_current_symbol("TEST") 跨测试污染 ContextVar(其余 test_debug.py 假设默认 None)。
    承 Task 10 教训:BurstDetector on_gate 测试同样需要这个 fixture 防止顺序依赖假失败。"""
    yield
    set_current_symbol(None)


def _make_df_no_peak() -> pd.DataFrame:
    # 单调下跌 · 无 peak · 触发 peak_no_local_max / peak_side_bars_insufficient
    n = 50
    return pd.DataFrame({
        'open': [100 - i for i in range(n)],
        'close': [100 - i - 0.5 for i in range(n)],
        'high': [100 - i + 0.5 for i in range(n)],
        'low': [100 - i - 1 for i in range(n)],
        'volume': [1000.0] * n,
    })


def _make_df_hidden_peak(n: int) -> pd.DataFrame:
    """flat 基线 + bar index5 有一个小幅凸起(high=10.05 vs 基线 10.0)。
    low 全程 9.9,不受凸起影响,便于精确控制 relative_height。"""
    highs = [10.0] * n
    highs[5] = 10.05
    return pd.DataFrame({
        'open': [9.95] * n,
        'close': [9.95] * n,
        'high': highs,
        'low': [9.9] * n,
        'volume': [1000.0] * n,
    })


def test_no_active_peak_broken_gate_emitted():
    """无 active peak 时,每 bar 都会吐 no_active_peak_broken"""
    set_current_symbol("TEST")
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    # 应该多个 no_active_peak_broken(每 bar 一个)· 或 peak_no_local_max
    gates = [g.gate_name for g in captured]
    assert 'no_active_peak_broken' in gates or 'peak_relative_height_insufficient' in gates
    napb = next(g for g in captured if g.gate_name == 'no_active_peak_broken')
    assert napb.op is None
    assert napb.threshold_param is None


def test_bo_gate_failure_event_window_is_point():
    """BO 点事件 · failure_event_window = (i, i)"""
    set_current_symbol("TEST")
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    for g in captured:
        assert g.failure_event_window[0] == g.failure_event_window[1], \
            f"BO 应为点事件 · 但 window = {g.failure_event_window}"
        assert g.class_id == 'bo'
        # evaluation_lookback 应指向 [i - total_window, i - 1]
        assert g.evaluation_lookback is not None


def test_peak_side_bars_insufficient_gate_emitted():
    """单调下跌下,窗内最高点总在窗首(local idx 0) · 恒 < min_side_bars → peak_side_bars_insufficient"""
    set_current_symbol("TEST")
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    side_bars_gates = [g for g in captured if g.gate_name == 'peak_side_bars_insufficient']
    assert len(side_bars_gates) > 0
    gf = side_bars_gates[0]
    assert gf.class_id == 'bo'
    assert gf.failure_event_window[0] == gf.failure_event_window[1]
    assert gf.measured.kind == 'side_bars_offset'
    assert gf.threshold == 3
    assert gf.op == '>='
    assert gf.threshold_param == 'min_side_bars'


def test_peak_relative_height_insufficient_gate_emitted():
    """窗内存在合规位置的 local max,但相对高度不足 min_relative_height → peak_relative_height_insufficient"""
    set_current_symbol("TEST")
    df = _make_df_hidden_peak(n=11)  # idx0..10 · 凸起在 idx5
    detector = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.5)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    height_gates = [g for g in captured if g.gate_name == 'peak_relative_height_insufficient']
    assert len(height_gates) == 1
    gf = height_gates[0]
    assert gf.class_id == 'bo'
    assert gf.failure_event_window == (10, 10)
    assert gf.measured.kind == 'relative_height'
    assert gf.measured.value == pytest.approx((10.05 - 9.9) / 9.9)
    assert gf.threshold == 0.5
    assert gf.op == '>='
    assert gf.threshold_param == 'min_relative_height'


def test_peak_already_active_gate_emitted():
    """peak 一旦被建立,只要仍在窗口内、仍是 local max,后续 bar 重复命中同一 index → peak_already_active"""
    set_current_symbol("TEST")
    df = _make_df_hidden_peak(n=13)  # idx0..12 · 凸起在 idx5,min_relative_height 足够低使 peak 成立
    detector = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.01)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    list(detector.detect(df))
    already_active_gates = [g for g in captured if g.gate_name == 'peak_already_active']
    assert len(already_active_gates) > 0
    gf = already_active_gates[0]
    assert gf.class_id == 'bo'
    assert gf.failure_event_window[0] == gf.failure_event_window[1]
    assert gf.measured.kind == 'peak_idx'
    assert gf.measured.value == 5  # peak 建立于 idx5


def test_no_gate_when_on_gate_none():
    """on_gate 未挂时不 emit(生产路径无开销)"""
    df = _make_df_no_peak()
    detector = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    # detector.on_gate 默认 None(未设)
    list(detector.detect(df))  # 不应抛错


def test_peak_no_local_max_window_start_op_is_ge():
    """spec 2026-07-12: sentinel-numeric #4 · op='>=' + threshold_param=None."""
    set_current_symbol("TEST")
    df = pd.DataFrame({
        'open':  [10.0] * 5, 'close': [10.0] * 5,
        'high':  [10.1] * 5, 'low':   [9.9]  * 5,
        'volume': [1000.0] * 5,
    })
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.1)
    captured: list = []
    det.on_gate = captured.append
    list(det.detect(df))
    ws_gates = [g for g in captured
                if g.gate_name == 'peak_no_local_max' and g.measured.kind == 'window_start']
    assert ws_gates, f'期望至少 1 个 window_start 分支的 peak_no_local_max,captured={[g.gate_name for g in captured]}'
    gf = ws_gates[0]
    assert gf.op == '>=', f'op={gf.op!r},期望 ">="'
    assert gf.threshold_param is None
    assert gf.threshold == 0


def test_peak_no_local_max_window_min_low_op_is_gt():
    """spec 2026-07-12: sentinel-numeric #8 · op='>' + threshold_param=None."""
    set_current_symbol("TEST")
    n = 11
    highs = [10.0] * n
    highs[5] = 10.5   # 局部峰 · global idx5 · 满足 side_bars 两侧检查
    df = pd.DataFrame({
        'open': [10.0] * n, 'close': [10.0] * n,
        'high': highs, 'low': [-1.0] * n,   # low<=0 触发 window_min_low 除零守卫
        'volume': [1000.0] * n,
    })
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.1)
    captured: list = []
    det.on_gate = captured.append
    list(det.detect(df))
    wml_gates = [g for g in captured
                 if g.gate_name == 'peak_no_local_max' and g.measured.kind == 'window_min_low']
    assert wml_gates, f'期望至少 1 个 window_min_low 分支的 peak_no_local_max,captured={[g.gate_name for g in captured]}'
    gf = wml_gates[0]
    assert gf.op == '>', f'op={gf.op!r},期望 ">"'
    assert gf.threshold_param is None
    assert gf.threshold == 0
