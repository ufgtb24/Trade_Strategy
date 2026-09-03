"""throwback_v1 跨层 DAG 集成测试(终审 I4 补):验证「引擎 max_gap(TemporalEdge)
行为」与「tb node where(day_drop)对 res.matches 的过滤」这两条跨层契约。

背景:93ab1cf(首段即停重写)删掉了 test_throwback_event.py,其中
test_dag_engine_bo_to_tb_match / test_detect_multi_bo_same_span_yields_multi_instances
monkeypatch evaluate_throwback 走 DAG 引擎断言 node_index span,重写后旧函数已消灭、
monkeypatch 目标不复存在,只能靠等价重建覆盖回来——旧口径只剩结构断言
(e.max_gap == tb.max_span / predicate 的 field/op/threshold),没人验过它们真的
挡得住不合格事件、真的算得出正确的 span。

放置位置:选本文件(tests/path2/atoms/)而非 tests/path2_apps/bb_v1/test_bb_v1.py——
本测试验证的是 throwback_v1 模块本身与通用 DAG 引擎的接口契约(任意 app 复用同一
detector 都成立),不依赖 bb_v1 的具体默认参数;结构上延续被删文件的选址与分区
(DAG 集成 + 多实例不变式相邻)。

fake bo/burst 生产者(_FakeBO/_FakeBurst)绕开真实 BODetector/BurstDetector 的
价格行为判定,直接注入预构造的 BOEvent/BurstEvent——只有 tb node 用真实
ThrowbackDetectorV1(未 mock),这样断言的是"引擎跑真实 detector 输出"而非"引擎
正确调用了一个 mock"。
"""
import pandas as pd

import path2.atoms.throwback_v1 as tb
from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.throwback_v1 import FirstSegment, ThrowbackDetectorV1
from path2.dag import where as W
from path2.dag.edges import Child, TemporalEdge
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")


def _burst(*bos):
    first, last = bos[0], bos[-1]
    return BurstEvent(start_idx=first.start_idx, end_idx=last.end_idx,
                      confirm_idx=last.end_idx, members=tuple(bos))


def _base_series(n, base=100.0):
    return [(base, base + 1.0, base - 1.0, base, 1000) for _ in range(n)]


def _make_df(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])


class _FakeBO:
    """孤立 bo 生产者:直接吐预构造 BOEvent 列表,不跑真实价格行为判定。"""
    event_cls = BOEvent

    def __init__(self, bos):
        self._bos = bos

    def detect(self, df):
        return iter(self._bos)


class _FakeBurst:
    """burst 生产者:直接吐预构造 BurstEvent 列表(消费流 node:引擎传 (stream, df))。"""
    event_cls = BurstEvent

    def __init__(self, bursts):
        self._bursts = bursts

    def detect(self, bos, df):
        return iter(self._bursts)


class TestDagIntegration:
    """两条独立 burst→tb 观测,验证 day_drop where 只放行合格的一条、node_index span 正确。"""

    def test_day_drop_where_filters_match_and_node_index_span(self):
        # burst1:span[8,9],last_bo close=103,回踩单日跌 (103-102.5)/103≈0.00485(<0.20 阈值)
        rows = _base_series(10)
        rows[9] = (100.0, 104.0, 100.0, 103.0, 5000)         # 9: last_bo
        rows += [(103.0, 103.5, 102.0, 102.5, 1000),          # 10: 收跌 → DOWN trough=102.5
                 (102.5, 103.0, 102.0, 102.8, 1000),           # 11: 不刷新 → STABLE enter=11
                 (102.8, 108.0, 102.8, 107.0, 1000)]           # 12: rise,exit=11
        burst1 = _burst(_bo(8), _bo(9))

        # burst2:span[13,16]留宽余量(gbot=50)防破位截断,last_bo close=200,
        # 回踩单日跌 (200-150)/200=0.25(>=0.20 阈值,应被 where 拦下,不进 matches)
        rows += [
            (50.0, 51.0, 49.0, 50.0, 3000),        # 13: 低锚,压低 span 内 gbot
            (100.0, 101.0, 99.0, 100.0, 1000),     # 14
            (100.0, 101.0, 99.0, 100.0, 1000),     # 15
            (196.0, 202.0, 195.0, 200.0, 5000),    # 16: last_bo,close=200
            (200.0, 200.0, 149.0, 150.0, 2000),    # 17: 回踩单日跌 25%,trough=150
            (150.0, 151.0, 149.0, 151.0, 500),     # 18: 不刷新 → STABLE enter=18
            (151.0, 210.0, 151.0, 205.0, 1000),    # 19: 预算末根(vol 未热身,timeout 收口)
        ]
        burst2 = _burst(_bo(13), _bo(16))
        df = _make_df(rows)

        bo_node = NodeSpec("bo", detector=_FakeBO([_bo(9), _bo(16)]))
        burst_node = NodeSpec("burst", detector=_FakeBurst([burst1, burst2]), consumes_stream="bo")
        tb_node = NodeSpec(
            "tb", detector=ThrowbackDetectorV1(vol_window=3),
            where=(("day_drop", W.attr("max_day_drop", "<", 0.20)),),
            consumes_stream="burst")
        spec = PatternSpec(
            pattern_id="p_tb_dag_it",
            nodes=(bo_node, burst_node, tb_node),
            edges=(TemporalEdge(Child("burst", "last_bo"), "tb",
                                min_gap=1, max_gap=20, anchor_field="anchor_bo_id"),))

        res = analyze(spec, df=df)

        # 两条 tb 事件都产了(where 不影响 detect() 产出,只影响 match 集)
        tb_events = [e for e in res.events if isinstance(e, tb.ThrowbackEventV1)]
        assert len(tb_events) == 2
        drops = sorted(e.max_day_drop for e in tb_events)
        assert drops[0] < 0.20 <= drops[1]

        # 只有 max_day_drop<0.20 的那条(burst1 锚)进 res.matches;node_index["tb"] span 正确
        assert len(res.matches) == 1
        m = res.matches[0]
        assert "bo" not in m.node_index                        # bo 孤立 node 不进 node_index
        assert m.node_index["burst"].end_idx == 9               # burst 承载合格的 last_bo(=9)
        assert (m.node_index["tb"].start_idx, m.node_index["tb"].end_idx) == (11, 11)
        # anchor_bo_id 与 burst.last_bo 的(交错标注后)instance_id 相对一致(不锚具体字符串)
        assert m.node_index["tb"].anchor_bo_id == m.node_index["burst"].child("last_bo").instance_id


class TestDetectMultiInstanceInvariant:
    """不变式(ThrowbackDetectorV1 docstring:"同窗口多 bo 各产一条(实例流语义,
    各带单来源 anchor_bo_id)"):同 (enter,exit) 不去重,两个 burst(不同 last_bo)
    各产一条独立事件对象。monkeypatch run_first_segment 只固定段结果,隔离状态机
    本身的正确性(那部分由 test_throwback_v1_machine.py 覆盖),纯测 detect() 的
    per-burst 迭代/不去重逻辑。"""

    def test_same_span_different_last_bo_yields_two_instances(self, monkeypatch):
        monkeypatch.setattr(tb, 'run_first_segment', lambda *a, **kw: FirstSegment(5, 5, 'rise'))
        df = _make_df(_base_series(10))
        evs = list(ThrowbackDetectorV1().detect([_burst(_bo(1)), _burst(_bo(2))], df))
        assert [(e.start_idx, e.end_idx) for e in evs] == [(5, 5), (5, 5)]
        assert {e.anchor_bo_id for e in evs} == {"bo_1#0", "bo_2#0"}
        assert evs[0] is not evs[1]
