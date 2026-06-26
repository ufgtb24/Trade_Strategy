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


def _match(binding, role="tb"):
    """手造单 role 的 PatternMatch(children 与 role_index 展平一致,过不变式)。"""
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        event_id="m", start_idx=members[0].start_idx, end_idx=members[-1].end_idx,
        pattern_id="p", role_index={role: binding}, children=members,
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )


def _df(closes):
    return pd.DataFrame({"close": [float(c) for c in closes]})


# close = [100, 200, 300, 400, 500],索引 0..4
DF5 = _df([100, 200, 300, 400, 500])


def test_multi_day_window_average():
    """多日窗口:各买点日收益的算术平均。tb=[0,1], N=2:
    t=0: 300/100-1=2.0;t=1: 400/200-1=1.0 → mean=1.5。"""
    m = _match(_ev(0, 1))
    assert match_forward_returns(m, "tb", DF5, [2]) == {2: pytest.approx(1.5)}


def test_single_day_window():
    """单日窗口(start==end)。tb=[2,2], N=1: 400/300-1=1/3。"""
    m = _match(_ev(2, 2))
    assert match_forward_returns(m, "tb", DF5, [1]) == {1: pytest.approx(1 / 3)}


def test_partial_out_of_range_skipped():
    """部分越界:只平均未越界买点日。tb=[2,3], N=2:
    t=2: 500/300-1=2/3;t=3 → idx5 越界跳过 → 2/3。"""
    m = _match(_ev(2, 3))
    assert match_forward_returns(m, "tb", DF5, [2]) == {2: pytest.approx(2 / 3)}


def test_all_out_of_range_none():
    """全部越界 → 该 horizon None;其他 horizon 不受影响。tb=[3,4]:
    N=3 全越界 → None;N=1: t=3: 500/400-1=0.25,t=4 越界跳过 → 0.25。"""
    m = _match(_ev(3, 4))
    out = match_forward_returns(m, "tb", DF5, [3, 1])
    assert out[3] is None
    assert out[1] == pytest.approx(0.25)


def test_multi_horizon_keys():
    """多 horizon 一次调用返回全部键。"""
    m = _match(_ev(0, 0))
    out = match_forward_returns(m, "tb", DF5, (1, 2, 3))
    assert set(out) == {1, 2, 3}


def test_missing_role_raises():
    """role 缺失 → KeyError。"""
    m = _match(_ev(0, 1))
    with pytest.raises(KeyError):
        match_forward_returns(m, "nope", DF5, [1])
