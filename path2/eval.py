"""path2 评估层:match 买点的 N 日内最大涨幅(pattern 质量度量)。

走势-无关:只依赖 Event 区间 + df["close"]/df["high"]。不放 calc/(calc 约定
纯数值、无 Event 依赖,本模块要碰 Event/PatternMatch)。
"""
from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from path2.core import Event
from path2.dag.result import PatternMatch


def match_forward_returns(
    match: PatternMatch,
    end_node: str,
    df: pd.DataFrame,
    horizons: Sequence[int],
) -> dict[int, Optional[float]]:
    """end_node event(买点窗)内逐买点日 max(high[t+1..t+N])/close[t]-1 的均值,
    每 horizon 一项——"未来 N 日内最大涨幅",非端点收益。

    df 必须就是产生该 match 的那个窗口 df(event 的 start_idx/end_idx 是它的
    0-based 行位置索引,索引对齐由调用方保证)。
    t+N 越界的买点日跳过(要求整个 N 日窗口完整可见);某 horizon 全部越界 → 该项 None。
    end_node 缺失 → KeyError;绑定不为 Event 类型 → TypeError。
    """
    ev = match.node_index[end_node]            # 缺失 → KeyError(语义自然)
    if not isinstance(ev, Event):
        raise TypeError(f"end_node {end_node!r} 绑定为序列,仅支持单 Event 绑定")
    close = df["close"]
    high = df["high"]
    n_bars = len(df)
    out: dict[int, Optional[float]] = {}
    for n in horizons:
        rets = [
            float(high.iloc[t + 1 : t + n + 1].max()) / float(close.iat[t]) - 1.0
            for t in range(ev.start_idx, ev.end_idx + 1)
            if t + n < n_bars
        ]
        out[n] = sum(rets) / len(rets) if rets else None
    return out
