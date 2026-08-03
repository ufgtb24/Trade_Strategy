"""path2/eval.py:match 买点 N 日前瞻收益(match_forward_returns)/
前瞻跌幅(match_forward_drawdowns,mfr 的下行镜像)。"""
import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, PredicateTrace
from path2.eval import match_forward_returns, match_forward_drawdowns


class Ev(Event):
    class_id = "test_eval_ev"


def _ev(s, e):
    return Ev(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e, confirm_idx=s)


def _match(binding, node="tb"):
    """手造单 node 的 PatternMatch(children 与 node_index 展平一致,过不变式)。"""
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        event_id="m", start_idx=members[0].start_idx, end_idx=members[-1].end_idx, confirm_idx=members[0].start_idx,
        pattern_id="p", node_index={node: binding}, children=members,
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )


def _df(closes, highs, lows=None):
    """造 OHLC 子集(close/high/low)。lows 缺省取 close*0.99(仅占位,
    不影响 mfr 测试——mfr 不读 low;drawdown 测试需显式传 lows)。"""
    if lows is None:
        lows = [c * 0.99 for c in closes]
    return pd.DataFrame({
        "close": [float(c) for c in closes],
        "high":  [float(h) for h in highs],
        "low":   [float(l) for l in lows],
    })


# idx     0    1    2    3    4
# close: 100  200  300  400  500
# high:  110  400  350  500  550     ← 故意让 high 在中段冲高又回落,坐实"最大涨幅≠端点"
DF5 = _df([100, 200, 300, 400, 500],
          [110, 400, 350, 500, 550])

# drawdown 专用 DF:close/high 与 DF5 同(便于与 mfr 同买点对照),
# low 在中段砸坑(50/150)又回升,坐实"最大跌幅≠端点"且为 mfr 的下行镜像。
# idx     0    1    2    3    4
# close: 100  200  300  400  500
# high:  110  400  350  500  550     (同 DF5)
# low:    95   50  250  150  480     ← 中段砸坑
DD5 = _df([100, 200, 300, 400, 500],
          [110, 400, 350, 500, 550],
          [95, 50, 250, 150, 480])


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


# ---------------------------------------------------------------------------
# match_forward_drawdowns —— mfr 的下行镜像(min(low)/close-1),
# 签名/越界守卫/返回类型/错误语义与 match_forward_returns 逐字一致。
# ---------------------------------------------------------------------------

def test_drawdown_multi_day_window_average():
    """多日窗口:各买点日 min(low[t+1..t+N])/close[t]-1 的算术平均(与 mfr 镜像)。
    tb=[0,1], N=2:
    t=0: min(low[1..2])/close[0]-1 = min(50,250)/100-1 = -0.5;
    t=1: min(low[2..3])/close[1]-1 = min(250,150)/200-1 = -0.25;
    → mean = -0.375。"""
    m = _match(_ev(0, 1))
    assert match_forward_drawdowns(m, "tb", DD5, [2]) == {2: pytest.approx(-0.375)}


def test_drawdown_trough_not_at_endpoint():
    """跌幅取窗口内最低价、非端点(与 test_peak_not_at_endpoint 镜像)。tb=[0,0], N=2:
    close[t+N]=close[2]=300 端点仍是涨(300/100-1=2.0);
    但 min(low[1..2])=50 → 最大跌幅 = 50/100-1 = -0.5,严格 < 端点。"""
    m = _match(_ev(0, 0))
    assert match_forward_drawdowns(m, "tb", DD5, [2]) == {2: pytest.approx(-0.5)}


def test_drawdown_rise_then_pullback_mirror():
    """先涨后跌回(XAGE 缩影):同一 DF/同一买点下 mfr 正且大、drawdown 大负,
    证明 drawdown 补的是 mfr"只看涨"看不到的下行。tb=[0,0], N=2:
    mfr  = max(high[1..2])/close[0]-1 = 400/100-1 = 3.0(正);
    draw = min(low[1..2])/close[0]-1  = 50/100-1  = -0.5(大负)。"""
    m = _match(_ev(0, 0))
    assert match_forward_returns(m, "tb", DD5, [2]) == {2: pytest.approx(3.0)}
    assert match_forward_drawdowns(m, "tb", DD5, [2]) == {2: pytest.approx(-0.5)}


def test_drawdown_single_sided_down():
    """单边下跌:forward_drawdown ≈ min(low[t+1..t+N])/close[t]-1(单买点日均=自身)。
    tb=[0,0], N=2:min(low[1..2])=min(380,280)=280,close[0]=500 → 280/500-1=-0.44。"""
    df_down = _df([500, 400, 300, 200, 100],
                  [510, 410, 310, 210, 110],
                  [480, 380, 280, 180, 80])
    m = _match(_ev(0, 0))
    out = match_forward_drawdowns(m, "tb", df_down, [2])
    expected = min(380, 280) / 500 - 1   # min(low[1..2])/close[0]-1
    assert out[2] == pytest.approx(expected)


def test_drawdown_partial_out_of_range_skipped():
    """部分越界:只平均未越界买点日(与 mfr 同口径)。tb=[2,3], N=2:
    t=2: min(low[3..4])/close[2]-1 = min(150,480)/300-1 = -0.5;
    t=3: idx5 越界 → skip → -0.5。"""
    m = _match(_ev(2, 3))
    assert match_forward_drawdowns(m, "tb", DD5, [2]) == {2: pytest.approx(-0.5)}


def test_drawdown_all_out_of_range_none():
    """全部越界 → 该 horizon None;其他 horizon 不受影响(与 mfr 同)。tb=[3,4]:
    N=3 全越界 → None;N=1: t=3: low[4]/close[3]-1 = 480/400-1 = 0.2。"""
    m = _match(_ev(3, 4))
    out = match_forward_drawdowns(m, "tb", DD5, [3, 1])
    assert out[3] is None
    assert out[1] == pytest.approx(0.2)


def test_drawdown_multi_horizon_keys():
    """多 horizon 一次调用返回全部键。"""
    m = _match(_ev(0, 0))
    out = match_forward_drawdowns(m, "tb", DD5, (1, 2, 3))
    assert set(out) == {1, 2, 3}


def test_drawdown_missing_node_raises():
    """node 缺失 → KeyError(与 mfr 同)。"""
    m = _match(_ev(0, 1))
    with pytest.raises(KeyError):
        match_forward_drawdowns(m, "nope", DD5, [1])
