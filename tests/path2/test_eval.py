"""path2/eval.py:match 买点 N 日前瞻收益(match_forward_returns)。"""
import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, PredicateTrace
from path2.eval import match_forward_returns


class Ev(Event):
    class_id = "test_eval_ev"


def _ev(s, e):
    return Ev(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def _match(binding, node="tb"):
    """手造单 node 的 PatternMatch(children 与 node_index 展平一致,过不变式)。"""
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        event_id="m", start_idx=members[0].start_idx, end_idx=members[-1].end_idx,
        pattern_id="p", node_index={node: binding}, children=members,
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )


def _df(closes, highs):
    return pd.DataFrame({
        "close": [float(c) for c in closes],
        "high":  [float(h) for h in highs],
    })


# idx     0    1    2    3    4
# close: 100  200  300  400  500
# high:  110  400  350  500  550     ← 故意让 high 在中段冲高又回落,坐实"最大涨幅≠端点"
DF5 = _df([100, 200, 300, 400, 500],
          [110, 400, 350, 500, 550])


def test_multi_day_window_average():
    """多日窗口:各买点日 max(high[t+1..t+N])/close[t]-1 的算术平均。tb=[0,1], N=2:
    t=0: max(high[1..2])/close[0]-1 = 400/100-1 = 3.0;
    t=1: max(high[2..3])/close[1]-1 = 500/200-1 = 1.5;
    → mean = 2.25。"""
    m = _match(_ev(0, 1))
    assert match_forward_returns(m, "tb", DF5, [2]) == {2: pytest.approx(2.25)}


def test_peak_not_at_endpoint():
    """涨幅取窗口内最高价、非端点:tb=[0,0], N=2:
    close[t+N]=close[2]=300 端点收益仅 2.0;
    但 max(high[1..2])=400 → 最大涨幅 = 3.0,严格 > 端点。"""
    m = _match(_ev(0, 0))
    assert match_forward_returns(m, "tb", DF5, [2]) == {2: pytest.approx(3.0)}


def test_single_day_window():
    """N=1 窗口只有 t+1 一根。tb=[2,2], N=1: high[3]/close[2]-1 = 500/300-1 = 2/3。"""
    m = _match(_ev(2, 2))
    assert match_forward_returns(m, "tb", DF5, [1]) == {1: pytest.approx(2 / 3)}


def test_partial_out_of_range_skipped():
    """部分越界:只平均未越界买点日。tb=[2,3], N=2:
    t=2: max(high[3..4])/close[2]-1 = 550/300-1 = 5/6;t=3: idx5 越界 → skip → 5/6。"""
    m = _match(_ev(2, 3))
    assert match_forward_returns(m, "tb", DF5, [2]) == {2: pytest.approx(5 / 6)}


def test_all_out_of_range_none():
    """全部越界 → 该 horizon None;其他 horizon 不受影响。tb=[3,4]:
    N=3 全越界 → None;N=1: t=3: high[4]/close[3]-1 = 550/400-1 = 0.375,t=4 skip → 0.375。"""
    m = _match(_ev(3, 4))
    out = match_forward_returns(m, "tb", DF5, [3, 1])
    assert out[3] is None
    assert out[1] == pytest.approx(0.375)


def test_multi_horizon_keys():
    """多 horizon 一次调用返回全部键。"""
    m = _match(_ev(0, 0))
    out = match_forward_returns(m, "tb", DF5, (1, 2, 3))
    assert set(out) == {1, 2, 3}


def test_missing_node_raises():
    """node 缺失 → KeyError。"""
    m = _match(_ev(0, 1))
    with pytest.raises(KeyError):
        match_forward_returns(m, "nope", DF5, [1])
