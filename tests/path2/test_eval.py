"""path2/eval.py:match 买点 N 日前瞻收益(match_forward_returns)/
前瞻跌幅(match_forward_drawdowns,mfr 的下行镜像)。"""
from dataclasses import dataclass

import pandas as pd
import pytest

from path2.core import Event
from path2.dag.result import PatternMatch, PredicateTrace
from path2.eval import (
    _resolve_end_events,
    match_first_passage,
    match_forward_returns,
    match_forward_drawdowns,
)


class Ev(Event):
    pass


def _ev(s, e):
    return Ev(start_idx=s, end_idx=e, confirm_idx=s)


def _match(binding, node="tb"):
    """手造单 node 的 PatternMatch(children 与 node_index 展平一致,过不变式)。"""
    members = binding if isinstance(binding, tuple) else (binding,)
    return PatternMatch(
        start_idx=members[0].start_idx, end_idx=members[-1].end_idx, confirm_idx=members[0].start_idx,
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


def test_sample_bar_indices_default():
    from path2.core import Event

    class _E(Event):
        pass

    e = _E(start_idx=10, end_idx=12, confirm_idx=10)
    assert list(e.sample_bar_indices()) == [10, 11, 12]


# ---------------------------------------------------------------------------
# end_node 路径解析(_resolve_end_events)+ 三函数路径口径(统一标准协议)。
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Seg(Event):
    pass


@dataclass(frozen=True)
class Container(Event):
    segs: tuple = ()

    def child_slots(self):
        return {"segments": self.segs}


def _path_match():
    """手造 tb 容器 match:容器内嵌 2 个 seg child(0-0 与 2-3,段间有间隙 1)。"""
    segs = (Seg(start_idx=0, end_idx=0, confirm_idx=0),
            Seg(start_idx=2, end_idx=3, confirm_idx=2))
    cont = Container(start_idx=0, end_idx=3, confirm_idx=0, segs=segs)
    return PatternMatch(start_idx=0, end_idx=3, confirm_idx=0,
                        node_index={"tb": cont}, children=(cont,))


def test_resolve_plain_node_id():
    m = _path_match()
    assert _resolve_end_events(m, "tb") == (m.node_index["tb"],)


def test_resolve_path_child_slot():
    # 路径第二段 = 父内 slot 名(家庭身份),非 class_id(全局身份)
    m = _path_match()
    events = _resolve_end_events(m, "tb.segments")
    assert [e.start_idx for e in events] == [0, 2]


def test_resolve_path_missing_slot_raises():
    m = _path_match()
    with pytest.raises(KeyError, match="slot"):
        _resolve_end_events(m, "tb.nope")


def test_resolve_multi_level_path_raises():
    m = _path_match()
    with pytest.raises(ValueError, match="最多一级"):
        _resolve_end_events(m, "a.b.c")


def test_resolve_missing_parent_raises():
    m = _path_match()
    with pytest.raises(KeyError):
        _resolve_end_events(m, "nope")


def test_match_forward_returns_path_samples_all_child_bars():
    m = _path_match()
    win = pd.DataFrame({  # 3 根样本 bar(0 和 2/3,间隙 1 不计), high/close 足够
        "high": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0],
        "close": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    })
    rets = match_forward_returns(m, "tb.segments", win, [1])
    # 样本 bar 0/2/3 的 max(high[t+1])/close[t]-1 = 0/0/1 → mean 1/3。
    # 三态区分:gap 包含采样(0/0/0/1)得 0.25、空解析得 None,均不等于 1/3。
    assert rets[1] == pytest.approx(1.0 / 3.0)


# ---------------------------------------------------------------------------
# sample_window 双边样本消费窗截取(t4 配套,spec §10):逐买点日 t 仅当
# lo <= t <= hi 参与;None = 全量(向后兼容)。核心断言语义 = 「带窗的两段容器」
# 与「手工物理截成仅窗内段的容器(全量)」结果逐值相等。
# ---------------------------------------------------------------------------

def _two_seg_match(s1, e1, s2, e2):
    """手造 tb 容器 match:容器内嵌 2 个 seg child(span [s1,e1] 与 [s2,e2])。"""
    segs = (Seg(start_idx=s1, end_idx=e1, confirm_idx=s1),
            Seg(start_idx=s2, end_idx=e2, confirm_idx=s2))
    cont = Container(start_idx=s1, end_idx=e2, confirm_idx=s1, segs=segs)
    return PatternMatch(start_idx=s1, end_idx=e2, confirm_idx=s1,
                        node_index={"tb": cont}, children=(cont,))


def _one_seg_match(s, e):
    """手造 tb 容器 match:仅 1 个 seg child(span [s,e])——物理截段对照组。"""
    segs = (Seg(start_idx=s, end_idx=e, confirm_idx=s),)
    cont = Container(start_idx=s, end_idx=e, confirm_idx=s, segs=segs)
    return PatternMatch(start_idx=s, end_idx=e, confirm_idx=s,
                        node_index={"tb": cont}, children=(cont,))


class TestSampleWindow:
    def test_forward_returns_clipped(self):
        """两段 span [10,12] 与 [20,22];sample_window=(0,15) → 只有第一段 3 天参与,
        与手工构造的仅 [10,12] 段容器(全量)结果逐值相等。high 台阶:11..15=106..114
        (段1)、21..25=116..124(段2),其余基线 101 → 两段值域不同,窗外日混入必改变均值。
        仅段1: N=1 mean=0.08、N=5 mean=0.14;两段全量 N=1 mean=0.13(≠ 截窗值)。
        end_node 用 'tb.segments'(child span 并集)——'tb' 会解析到容器整 span
        (含段间间隙逐日),非 tb_seg 段级样本口径。"""
        n = 30
        high = [101.0] * n
        for i, h in zip(range(11, 16), (106, 108, 110, 112, 114)):
            high[i] = float(h)
        for i, h in zip(range(21, 26), (116, 118, 120, 122, 124)):
            high[i] = float(h)
        df = pd.DataFrame({"close": [100.0] * n, "high": high, "low": [99.0] * n})
        two, one = _two_seg_match(10, 12, 20, 22), _one_seg_match(10, 12)
        clipped = match_forward_returns(two, "tb.segments", df, [1, 5], sample_window=(0, 15))
        assert clipped == match_forward_returns(one, "tb.segments", df, [1, 5])
        assert clipped[1] == pytest.approx(0.08)
        assert clipped[5] == pytest.approx(0.14)
        # 无窗 ≠ 截窗:窗外段2 的 3 天确实在全量里参与过
        assert match_forward_returns(two, "tb.segments", df, [1, 5]) != clipped

    def test_first_passage_clipped(self):
        """两段 span [25,27] 与 [35,37](均 ≥20,M 样本足;[10,12] 会让 M 全 NaN、
        四态全零而平凡化);sample_window=(0,30) → 四态只数窗内日。M≈0.01(k=5 →
        up 线 105 / dn 线≈95.24):段1 翌日 high=110 → up×3;段2 翌日 low=90 →
        down×3——两段状态不同,窗外日混入必改变计数。end_node 用 'tb.segments'
        (child span 并集,与 forward_returns 用例同口径)。"""
        n = 45
        high, low = [100.5] * n, [99.5] * n
        for i in (26, 27, 28):
            high[i] = 110.0
        for i in (36, 37, 38):
            low[i] = 90.0
        df = pd.DataFrame({"close": [100.0] * n, "high": high, "low": low})
        two, one = _two_seg_match(25, 27, 35, 37), _one_seg_match(25, 27)
        clipped = match_first_passage(two, "tb.segments", df, 1, sample_window=(0, 30))
        assert clipped == match_first_passage(one, "tb.segments", df, 1)
        assert clipped == {"up": 3, "down": 0, "both": 0, "none": 0}
        # 无窗版本含窗外段2 的 3 个 down
        assert match_first_passage(two, "tb.segments", df, 1) == \
            {"up": 3, "down": 3, "both": 0, "none": 0}

    def test_forward_drawdowns_clipped(self):
        """两段 span [10,12] 与 [20,22];sample_window=(0,15) → 只有第一段 3 天参与,
        与手工构造的仅 [10,12] 段容器(全量)结果逐值相等。low 台阶:11..15=94..86
        (段1)、21..25=84..76(段2,更深),其余基线 99 → 两段值域不同,窗外日混入必
        改变均值。仅段1: N=1 mean=-0.08、N=5 mean=-0.14;两段全量 N=1 mean=-0.13
        (≠ 截窗值)。end_node 用 'tb.segments'(child span 并集,与 returns 用例同口径)。
        (Task 7 裁定 a 补参:ret 截 / dd 全量的口径分裂会打破「ret ≥ dd」不变量。)"""
        n = 30
        low = [99.0] * n
        for i, l in zip(range(11, 16), (94, 92, 90, 88, 86)):
            low[i] = float(l)
        for i, l in zip(range(21, 26), (84, 82, 80, 78, 76)):
            low[i] = float(l)
        df = pd.DataFrame({"close": [100.0] * n, "high": [101.0] * n, "low": low})
        two, one = _two_seg_match(10, 12, 20, 22), _one_seg_match(10, 12)
        clipped = match_forward_drawdowns(two, "tb.segments", df, [1, 5],
                                          sample_window=(0, 15))
        assert clipped == match_forward_drawdowns(one, "tb.segments", df, [1, 5])
        assert clipped[1] == pytest.approx(-0.08)
        assert clipped[5] == pytest.approx(-0.14)
        # 无窗 ≠ 截窗:窗外段2 的 3 天确实在全量里参与过
        assert match_forward_drawdowns(two, "tb.segments", df, [1, 5]) != clipped

    def test_none_keeps_behavior(self):
        """sample_window=None 结果与不加参数完全一致(三函数各验一遍,回归护栏)。"""
        n = 30
        df = pd.DataFrame({
            "close": [100.0] * n,
            "high": [101.0 + i * 0.1 for i in range(n)],
            "low": [99.0] * n,
        })
        m = _two_seg_match(10, 12, 20, 22)
        assert match_forward_returns(m, "tb.segments", df, [1, 5], sample_window=None) == \
            match_forward_returns(m, "tb.segments", df, [1, 5])
        assert match_forward_drawdowns(m, "tb.segments", df, [1, 5], sample_window=None) == \
            match_forward_drawdowns(m, "tb.segments", df, [1, 5])
        assert match_first_passage(m, "tb.segments", df, 1, sample_window=None) == \
            match_first_passage(m, "tb.segments", df, 1)
