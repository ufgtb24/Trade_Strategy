import pandas as pd
import pytest
from path2.atoms.breakout import BurstDetector, BOEvent, BurstEvent
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


@pytest.fixture(autouse=True)
def _reset_current_symbol():
    """避免 set_current_symbol("TEST") 跨测试污染 ContextVar(其余 test_debug.py 假设默认 None)。"""
    yield
    set_current_symbol(None)


def make_bo(idx: int) -> BOEvent:
    # pk_count/broken_peak_ids 已改 @property(派生自 broken_refs,契约 C5);
    # 本 fixture 不需要突破峰,broken_refs 留空即可(原 pk_count=1/broken_peak_ids=()
    # 本就互不一致,从未被断言)。
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx,
                   drought=None, vol_ratio=None, peak_vol_max=0.0)


def test_chain_break_emits_gate_failure():
    """相邻 bo gap > gap_max 触发 chain_break gate"""
    set_current_symbol("TEST")
    bos = [make_bo(90), make_bo(105)]  # gap = 15 > gap_max = 10
    detector = BurstDetector(gap_max=10, min_bos=2)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    df = pd.DataFrame({'volume': [0.0] * 200})
    list(detector.detect(bos, df))
    # 应该有一条 chain_break · 前簇(bo_90 单独)因 min_bos=2 也可能吐 min_bos_insufficient
    chain_breaks = [g for g in captured if g.gate_name == 'chain_break']
    assert len(chain_breaks) == 1
    gf = chain_breaks[0]
    assert gf.gate_idx == 105  # trigger bar = seq[k].start_idx
    assert gf.failure_event_window == (90, 105) or gf.failure_event_window == (90, 90)
    assert gf.symbol == 'TEST'
    assert gf.measured.kind == 'gap'
    assert gf.measured.value == 15
    assert gf.threshold == 10
    # chain_break case
    assert gf.op == '<='
    assert gf.threshold_param == 'gap_max'


def test_min_bos_insufficient_at_stream_end():
    """簇末 k - head + 1 < min_bos 触发 min_bos_insufficient"""
    set_current_symbol("TEST")
    bos = [make_bo(90), make_bo(92)]  # gap=2 一簇 · 但 min_bos=5 不够
    detector = BurstDetector(gap_max=10, min_bos=5)
    captured: list[GateFailure] = []
    detector.on_gate = captured.append
    df = pd.DataFrame({'volume': [0.0] * 200})
    list(detector.detect(bos, df))
    min_bos_gates = [g for g in captured if g.gate_name == 'min_bos_insufficient']
    assert len(min_bos_gates) == 1
    gf = min_bos_gates[0]
    assert gf.failure_event_window == (90, 92)
    assert gf.threshold == 5
    # min_bos_insufficient case
    assert gf.op == '>='
    assert gf.threshold_param == 'min_bos'


def test_no_gate_when_on_gate_none():
    """on_gate 未挂时不 emit(生产路径无开销)"""
    bos = [make_bo(90), make_bo(105)]
    detector = BurstDetector(gap_max=10, min_bos=2)
    # detector.on_gate 默认无(未设 · 应保持 None 或不存在)
    df = pd.DataFrame({'volume': [0.0] * 200})
    list(detector.detect(bos, df))  # 不应抛错
