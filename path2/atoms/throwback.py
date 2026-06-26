"""throwback 可买入区间事件(2026-06 重构)。

tb event [start_idx, end_idx] = 回踩成功后的「可买入窗」:
  - start_idx = 止跌点(回落段最低点),最早可买入位置;
  - end_idx   = 大涨前一根(窗口在大动作前收) 或 timeout(start+max_window);
  - 事件存在 ⟺ 回踩成功(破位则不产事件,下游零歧义)。
区间语义 = 允许入场窗、偏好 start 端(非等价入场);纯走势,不含成交量判断。

anchor = measure_at(bo-1, anchor_measure);必要条件 = [bo+1, end] 全程
measure_at(i, support_measure) ≥ anchor(破位即不产)。ATR 取 bo-1(避开 bo 当根异常 TR)。
预算:止跌点 ∈ [bo+1, bo+max_start_gap],买点窗宽 ≤ max_window。
大涨价基 = high;base_min = [start, i-1] 的 running min low(不含当前根)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, NamedTuple, Optional

import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.calc.atr import calculate_atr
from path2.calc.measure import VALID_MEASURES, measure_at
from path2.core import Event
from path2.stdlib import span_id


# 止跌 K 线证据集(_positive_signals 子集):下影 / 阳线 / 收涨
_STOP_SIGNALS = ('lower_shadow', 'bullish', 'close_up')


class ThrowbackResult(NamedTuple):
    """evaluate_throwback 成功返回值;失败返回 None(不产事件)。"""
    start_idx: int
    end_idx: int


def _positive_signals(df: pd.DataFrame, i: int) -> List[str]:
    """5 类积极信号 OR;返回所有触发的信号名称列表(可空)。

    阈值(Nison/Bulkowski 教科书):
      doji:         body/rng ≤ 0.10
      lower_shadow: (min(o,c)-l)/rng ≥ 0.50
      bullish:      c > o
      close_up:     c > prev_c
      gap_up:       open[i] > close[i-1]
    """
    o = float(df['open'].iat[i])
    c = float(df['close'].iat[i])
    h = float(df['high'].iat[i])
    l = float(df['low'].iat[i])
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    prev_c = float(df['close'].iat[i - 1]) if i > 0 else c

    sigs: List[str] = []
    if body / rng <= 0.10:
        sigs.append('doji')
    if (min(o, c) - l) / rng >= 0.50:
        sigs.append('lower_shadow')
    if c > o:
        sigs.append('bullish')
    if c > prev_c:
        sigs.append('close_up')
    if i > 0 and o > df['close'].iat[i - 1]:
        sigs.append('gap_up')
    return sigs


def _has_stop_signal(df: pd.DataFrame, i: int) -> bool:
    """该根是否含止跌 K 线证据(下影/阳线/收涨之一)。"""
    sigs = _positive_signals(df, i)
    return any(s in sigs for s in _STOP_SIGNALS)


def _atr_at(df: pd.DataFrame, idx: int, period: int) -> float:
    """idx 处的 Wilder ATR;越界/NaN → 0.0。"""
    atr = calculate_atr(df['high'], df['low'], df['close'], period)
    v = float(atr.iat[idx])
    return v if v == v else 0.0   # NaN != NaN → fallback 0.0


def _find_start_idx(df: pd.DataFrame, bo_idx: int, anchor: float,
                    max_start_gap: int, atr: float, pullback_min_atr: float,
                    support_measure: str = "low") -> Optional[int]:
    """阶段一:定位止跌点(回落段最低点)。返回 trough_idx 或 None。

    从 bo_idx+1 扫到 bo_idx+max_start_gap(买点不离 bo 过远):
      - 任一根 measure_at(i, support_measure) < anchor → 破位 → None;
      - 首个「连续两根不创新低」(low[i]≥low[i-1] ∧ low[i-1]≥low[i-2])
        且 {i-1,i} 含止跌 K 线证据 → 止跌确认;
      - 回落门:peak(max high over [bo_idx, trough]) − low[trough]
        ≥ pullback_min_atr×atr,否则 None(没回踩、直接横住);
      - 返回 trough = argmin(low) over [bo_idx+1, i]。
    止跌/trough/回落门固定用 low/high(走势内禀);support_measure 只参数化破位比较。
    """
    end = min(bo_idx + max_start_gap, len(df) - 1)
    trough_idx = bo_idx + 1
    for i in range(bo_idx + 1, end + 1):
        if measure_at(df, i, support_measure) < anchor:
            return None
        lo_i = float(df['low'].iat[i])
        if lo_i < float(df['low'].iat[trough_idx]):
            trough_idx = i
        if i >= bo_idx + 2:
            lo_p = float(df['low'].iat[i - 1])
            lo_pp = float(df['low'].iat[i - 2])
            if (lo_i >= lo_p and lo_p >= lo_pp
                    and (_has_stop_signal(df, i - 1) or _has_stop_signal(df, i))):
                peak = float(df['high'].iloc[bo_idx: trough_idx + 1].max())
                if peak - float(df['low'].iat[trough_idx]) >= pullback_min_atr * atr:
                    return trough_idx
                return None
    return None


def _find_end_idx(df: pd.DataFrame, start_idx: int, anchor: float,
                  max_window: int, atr: float, big_rise_k: float,
                  support_measure: str = "low") -> Optional[int]:
    """阶段二:定位 end(大涨前一根 / timeout)。返回 end_idx 或 None(破位)。

    base_min = running min(low) over [start_idx, i-1](不含当前根 i)。
    从 start_idx+1 扫到 start_idx+max_window(买点窗不持续过长):
      - measure_at(i, support_measure) < anchor → 破位 → None;
      - high[i] − base_min ≥ big_rise_k×atr → 大涨 → end = i−1;
      - 扫满无大涨无破位 → timeout → end = min(start_idx+max_window, len-1)。
    大涨价基固定 high(更早关窗=保守买点窗)。
    """
    end_scan = min(start_idx + max_window, len(df) - 1)
    base_min = float(df['low'].iat[start_idx])
    for i in range(start_idx + 1, end_scan + 1):
        if measure_at(df, i, support_measure) < anchor:
            return None
        if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
            return i - 1
        lo_i = float(df['low'].iat[i])
        if lo_i < base_min:
            base_min = lo_i
    return end_scan


def evaluate_throwback(
    bo: BOEvent, df: pd.DataFrame, *,
    max_start_gap: int = 5,
    max_window: int = 5,
    atr_window: int = 14,
    big_rise_k: float = 1.5,
    pullback_min_atr: float = 1.0,
    anchor_measure: str = "high",
    support_measure: str = "close",
) -> Optional[ThrowbackResult]:
    """对单个 BO 判可买入区间。成功返回 ThrowbackResult(start,end),失败返回 None。

    anchor = measure_at(bo-1, anchor_measure);必要条件 = [bo+1, end] 全程
    measure_at(i, support_measure) ≥ anchor。ATR 取 bo-1(bo 当根异常波动会污染当根 ATR)。
    start = 止跌点 ∈ [bo+1, bo+max_start_gap];end = 大涨前一根 / timeout(start+max_window)。纯走势。
    """
    bo_idx = bo.end_idx
    if bo_idx < 1 or bo_idx >= len(df):
        return None
    atr = _atr_at(df, bo_idx - 1, atr_window)     # ★ bo-1:避开 bo 当根异常 TR
    if atr <= 0.0:
        return None
    anchor = measure_at(df, bo_idx - 1, anchor_measure)
    start = _find_start_idx(df, bo_idx, anchor, max_start_gap, atr,
                            pullback_min_atr, support_measure)
    if start is None:
        return None
    end = _find_end_idx(df, start, anchor, max_window, atr,
                        big_rise_k, support_measure)
    if end is None:
        return None
    return ThrowbackResult(start, end)


@dataclass(frozen=True)
class ThrowbackEvent(Event):
    """可买入区间派生事件。start_idx=止跌点;end_idx=大涨前一根/timeout。
    只在回踩成功时被 detector 产出(破位则不产)。

    输出字段(where 可引用):
    - anchor_bo_id: 触发本事件的那根 BO 的 event_id(追溯用);
                    多 BO 映射到同 span 时按 event_id 去重保留首个
    """
    class_id = "tb"
    anchor_bo_id: str = ""


class ThrowbackDetector:
    """派生 detector:消费 bo 流,逐 BO 调 evaluate_throwback,仅成功时产事件。

    核心判据(详见 evaluate_throwback / _find_start_idx / _find_end_idx):
      anchor = measure_at(bo-1, anchor_measure);ATR 取 bo-1 处(避开 BO 当根异常 TR)。
      阶段一(_find_start_idx,找止跌点):
        扫 [bo+1, bo+max_start_gap];任一根 support_measure < anchor → 破位返回 None;
        首个「连续两根不创新低」且 {i-1, i} 含止跌 K 线证据(下影/阳线/收涨之一)→ 止跌确认;
        再验回落深度:peak_high(over [bo, trough]) - low[trough] ≥ pullback_min_atr × atr,
        不满足 → None;成功返回 trough_idx。
      阶段二(_find_end_idx,找大涨前一根 / timeout):
        从 start+1 扫到 start+max_window;任一根 support_measure < anchor → 破位返回 None;
        high[i] - running_min_low(over [start, i-1]) ≥ big_rise_k × atr → 大涨,end = i-1;
        扫满无破位无大涨 → timeout,end = start + max_window。
      anchor_measure 定锚价、support_measure 定破位比较,语义不同需同时检查。

    多源 L2+ detector(detect(self, bo_stream, df) 双参,走 run() 变参透传)。
    end_idx 升序排序(过 run() 升序不变式):trigger 随 bo 顺序可能乱序,收集后排序再 yield。
    多个 bo 映射到同 span 时按 event_id 去重(buyable-window 身份 = span)。

    输出字段详见 ThrowbackEvent。
    """

    event_cls = ThrowbackEvent

    def __init__(self, *, max_start_gap: int = 5, max_window: int = 5,
                 atr_window: int = 14, big_rise_k: float = 1.5,
                 pullback_min_atr: float = 1.0,
                 anchor_measure: str = "high", support_measure: str = "low"):
        if anchor_measure not in VALID_MEASURES:
            raise ValueError(f"anchor_measure 必须在 {VALID_MEASURES},实际 {anchor_measure!r}")
        if support_measure not in VALID_MEASURES:
            raise ValueError(f"support_measure 必须在 {VALID_MEASURES},实际 {support_measure!r}")
        self._kw = dict(max_start_gap=max_start_gap, max_window=max_window,
                        atr_window=atr_window, big_rise_k=big_rise_k,
                        pullback_min_atr=pullback_min_atr,
                        anchor_measure=anchor_measure,
                        support_measure=support_measure)

    def detect(self, bo_stream: Iterable[BOEvent], df: pd.DataFrame) -> Iterator[ThrowbackEvent]:
        events = []
        for bo in bo_stream:
            r = evaluate_throwback(bo, df, **self._kw)
            if r is not None:
                start = r.start_idx
                events.append(ThrowbackEvent(
                    event_id=span_id(self.event_cls.class_id, start, r.end_idx),
                    start_idx=start, end_idx=r.end_idx,
                    anchor_bo_id=bo.event_id))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # ★ run() 要 end 升序
        seen: set[str] = set()
        for e in events:
            if e.event_id in seen:   # 同窗多 bo → 同 span 同 id,去重(buyable-window 身份=span)
                continue
            seen.add(e.event_id)
            yield e
