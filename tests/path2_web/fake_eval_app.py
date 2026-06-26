"""测试假 app(dag_spec 形态):可控买点位置 + eval_meta 协议。

analyze 在窗口 df 里按固定日期 BUY_DATES 落 tb 点事件(日期不在窗内则不产生);
三个日期由测试的窗口安排成:首部缓冲内 / 严格窗内 / 尾部缓冲内。
"""
from dataclasses import dataclass

from path2.core import Event
from path2.dag.result import AnalysisResult, PatternMatch, PredicateTrace


@dataclass(frozen=True)
class FakeTb(Event):
    class_id = "fake_eval_tb"


BUY_DATES = ("2024-12-20", "2025-01-10", "2025-03-05")


def _match(ev):
    return PatternMatch(
        event_id=f"m_{ev.event_id}", start_idx=ev.start_idx, end_idx=ev.end_idx,
        pattern_id="fake_eval", role_index={"tb": ev}, children=(ev,),
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )


def analyze(df, params=None):
    dates = [str(d)[:10] for d in df["date"]]
    evs = tuple(
        FakeTb(event_id=f"tb_{d}", start_idx=dates.index(d), end_idx=dates.index(d))
        for d in BUY_DATES if d in dates
    )
    return AnalysisResult(events=evs, matches=tuple(_match(e) for e in evs), spec=None)


def eval_meta(params=None):
    return {"end_role": "tb", "head_buffer_trading_days": 10}
