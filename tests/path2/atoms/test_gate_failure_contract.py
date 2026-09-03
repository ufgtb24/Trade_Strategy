"""契约不变式:所有 detector emit 出的 GateFailure 满足
   threshold_param is not None ==> op is not None——防未来新增 gate 只填一半。"""
import pandas as pd
import pytest
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.breakout import BurstEvent
from path2.atoms.throwback_v1 import ThrowbackDetectorV1
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


@pytest.fixture(autouse=True)
def _reset_current_symbol():
    yield
    set_current_symbol(None)


def _collect_bo_gates() -> list[GateFailure]:
    """跑各 fixture 数据吸集尽量多的 BO gate。"""
    set_current_symbol("TEST")
    captured: list[GateFailure] = []

    # 单调下跌 → no_active_peak_broken / peak_side_bars_insufficient / peak_no_local_max
    n = 50
    df = pd.DataFrame({
        'open': [100 - i for i in range(n)],
        'close': [100 - i - 0.5 for i in range(n)],
        'high': [100 - i + 0.5 for i in range(n)],
        'low': [100 - i - 1 for i in range(n)],
        'volume': [1000.0] * n,
    })
    det = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    det.on_gate = captured.append
    list(det.detect(df))

    # 隐藏 peak → peak_relative_height_insufficient
    highs = [10.0] * 11
    highs[5] = 10.05
    df2 = pd.DataFrame({
        'open': [9.95] * 11, 'close': [9.95] * 11,
        'high': highs, 'low': [9.9] * 11, 'volume': [1000.0] * 11,
    })
    det2 = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.5)
    det2.on_gate = captured.append
    list(det2.detect(df2))
    return captured


def test_bo_gate_invariant_op_and_param_same_nullability():
    for g in _collect_bo_gates():
        # spec 2026-07-12: 放松为单向蕴含 threshold_param is not None ==> op is not None
        # (sentinel-numeric 场景:op 非 None + threshold_param None 合法)
        if g.threshold_param is not None:
            assert g.op is not None, \
                f'契约违约:{g.gate_name} · threshold_param={g.threshold_param!r} 但 op is None'


def test_burst_gate_invariant_op_and_param_same_nullability():
    """跑 BurstDetector 用异常小 gap_max/异常大 min_bos 触发 chain_break + min_bos_insufficient。"""
    set_current_symbol("TEST")
    from path2.atoms.breakout import BOEvent as _BOEvent, BurstEvent  # 用真类型
    # 构 3 个 bo,gap=10>gap_max=5 → chain_break + 末簇 size=1<min_bos=2 → min_bos_insufficient
    bos = [
        _BOEvent(start_idx=0, end_idx=0, confirm_idx=0, drought=None,
                 vol_ratio=None, peak_vol_max=0.0),
        _BOEvent(start_idx=15, end_idx=15, confirm_idx=15, drought=15,
                 vol_ratio=None, peak_vol_max=0.0),
    ]
    df = pd.DataFrame({'volume': [1000.0] * 30})
    det = BurstDetector(gap_max=5, min_bos=2, vol_baseline_period=5)
    captured: list[GateFailure] = []
    det.on_gate = captured.append
    list(det.detect(bos, df))
    assert len(captured) > 0
    for g in captured:
        # spec 2026-07-12: 放松为单向蕴含 threshold_param is not None ==> op is not None
        # (sentinel-numeric 场景:op 非 None + threshold_param None 合法)
        if g.threshold_param is not None:
            assert g.op is not None, \
                f'契约违约:{g.gate_name} · threshold_param={g.threshold_param!r} 但 op is None'


def test_tb_gate_invariant_op_and_param_same_nullability():
    """跑 ThrowbackDetectorV1 触发一个真实 tb gate(break_no_stable:入段前 close < span_min)。"""
    set_current_symbol("TEST")
    rows = [(100.0, 101.0, 99.0, 100.0, 1000.0)] * 10
    rows[9] = (100.0, 104.0, 100.0, 103.0, 5000.0)      # bo_9,gbot=103
    rows += [(103.0, 103.5, 100.0, 100.5, 1000.0)]      # 10 < gbot → break_no_stable
    df = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    from path2.atoms.breakout import BOEvent as _BOEvent
    bo = _BOEvent(start_idx=9, end_idx=9, confirm_idx=9, instance_id="bo_9#0")
    burst = BurstEvent(start_idx=9, end_idx=9, confirm_idx=9, members=(bo,))
    det = ThrowbackDetectorV1(vol_window=3)
    captured: list[GateFailure] = []
    det.on_gate = captured.append
    list(det.detect([burst], df))
    assert len(captured) > 0, "tb fixture 未触发任何 gate → 契约测试 vacuous"
    for g in captured:
        if g.threshold_param is not None:
            assert g.op is not None, \
                f'契约违约:{g.gate_name} · threshold_param={g.threshold_param!r} 但 op is None'
