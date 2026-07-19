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

import sys
from dataclasses import dataclass
from typing import Callable, ClassVar, Iterable, Iterator, List, NamedTuple, Optional

import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.calc.atr import calculate_atr
from path2.calc.measure import VALID_MEASURES, measure_at
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol
from path2.debug_ctx import debug_break
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


def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  atr_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit(避免 4 处埋点重复 boilerplate)。

    TB 是 span 事件,attempt 定义采解读 X 松对齐(spec §2.4.2):
    一次 evaluate_throwback = 一次 attempt,attempt 起点 = bo.end_idx + 1,
    阶段一/二失败共用同一 failure_event_window 公式。
    """
    if on_gate is None:
        return
    # debug hook · dead-code when DEBUG_MODE=0 (see debug_ctx.py::_DEBUG_MODE).
    # NOT the scan bypass: real scan attaches on_gate=collector.add (non-None),
    # so this line executes during scan too. `on_gate is None` above is a local
    # invariant (no gate-failure consumer attached), not the scan/diagnose split.
    debug_break(gate_idx, anchor_kind='gate', class_id='tb', stop_at_frame=sys._getframe(1))
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        start_idx=bo_idx + 1,
        gate_idx=gate_idx,
        anchor_bar=bo_idx,
        class_id='tb',
        gate_name=gate_name,
        measured=measured,
        threshold=threshold,
        op=op,
        threshold_param=threshold_param,
        evaluation_lookback=(bo_idx - atr_window, bo_idx),
        symbol=current_symbol.get() or '',
    ))


def _find_start_idx(df: pd.DataFrame, bo_idx: int, anchor: float,
                    max_start_gap: int, atr: float, pullback_min_atr: float,
                    support_measure: str = "low",
                    on_gate: Optional[Callable[[GateFailure], None]] = None,
                    atr_window: int = 14) -> Optional[int]:
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
        measured_support = measure_at(df, i, support_measure)
        if measured_support < anchor:
            # gate: phase1_break · 寻底扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor (anchor = 突破那根 bar 的前一根收盘价)
            # measured=anchor_delta(当前支撑价 - anchor, 负值即破位;支撑价由 support_measure 决定, 通常是 low)
            # 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
            _emit_tb_gate(bo_idx, i, 'phase1_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measured_support - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate,
                          op='>=', threshold_param=None)
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
                depth = peak - float(df['low'].iat[trough_idx])
                if depth >= pullback_min_atr * atr:
                    debug_break(trough_idx, anchor_kind='trough', class_id='tb')  # v2 · phase1 success(与 event.start_idx 对齐)
                    return trough_idx
                # gate: phase1_pullback_shortage · 已探得止跌形态, 但从 bo 高点到止跌位的下跌幅度是否够 ATR 倍数
                # measured=pullback_atr(下跌深度 depth 除以 ATR; depth = bo 高点价 - 止跌价; ATR = atr_window 根真实波幅的平均)
                # 判据: pullback_atr>=pullback_min_atr 通过; 否则失败, 回撤不足, 不构成有效 throwback
                _emit_tb_gate(bo_idx, i, 'phase1_pullback_shortage',
                              MeasuredKindAware(kind='pullback_atr',
                                                value=depth / atr if atr > 0 else 0.0,
                                                label='回落深度/ATR'),
                              pullback_min_atr, atr_window, on_gate,
                              op='>=', threshold_param='pullback_min_atr')
                return None
    # gate: phase1_no_trough_timeout · 寻底扫描窗内(共 max_start_gap 根)始终未确认止跌
    # measured=count(扫描已扫满的窗宽 = max_start_gap 根)
    # 判据: 窗内某根需同时满足连续两根不再创新低、止跌信号触发、下跌深度达 ATR 倍数三条; 扫满未满足则失败
    _emit_tb_gate(bo_idx, end, 'phase1_no_trough_timeout',
                  MeasuredKindAware(kind='count', value=max_start_gap,
                                    label='max_start_gap 扫满'),
                  max_start_gap, atr_window, on_gate)
    return None


def _find_end_idx(df: pd.DataFrame, start_idx: int, anchor: float,
                  max_window: int, atr: float, big_rise_k: float,
                  support_measure: str = "low",
                  on_gate: Optional[Callable[[GateFailure], None]] = None,
                  bo_idx: Optional[int] = None,
                  atr_window: int = 14) -> Optional[int]:
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
        measured_support = measure_at(df, i, support_measure)
        if measured_support < anchor:
            # gate: phase2_break · 反弹推进扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor
            # measured=anchor_delta(当前支撑价 - anchor, 负值即破位;含义同 phase1_break)
            # 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
            _emit_tb_gate(bo_idx, i, 'phase2_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measured_support - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate,
                          op='>=', threshold_param=None)
            return None
        if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
            debug_break(i - 1, anchor_kind='end', class_id='tb')  # v2 · phase2 rise end(⚠ i-1 与 event.end_idx 对齐, 非 i)
            return i - 1
        lo_i = float(df['low'].iat[i])
        if lo_i < base_min:
            base_min = lo_i
    debug_break(end_scan, anchor_kind='end', class_id='tb')  # v2 · phase2 timeout end(与 event.end_idx 对齐)
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
    on_gate: Optional[Callable[[GateFailure], None]] = None,
) -> Optional[ThrowbackResult]:
    """对单个 BO 判可买入区间。成功返回 ThrowbackResult(start,end),失败返回 None。

    anchor = measure_at(bo-1, anchor_measure);必要条件 = [bo+1, end] 全程
    measure_at(i, support_measure) ≥ anchor。ATR 取 bo-1(bo 当根异常波动会污染当根 ATR)。
    start = 止跌点 ∈ [bo+1, bo+max_start_gap];end = 大涨前一根 / timeout(start+max_window)。纯走势。

    on_gate:Stage 3 调试埋点(非 None 时,阶段一/二内部短路失败会吐 GateFailure);
    一次调用本函数 = 一次 attempt(X 松对齐,详见 `_emit_tb_gate`)。bo_idx<1/atr<=0 两处
    边界前置检查不 emit(非阶段一/二判据,brief 未列 gate_name)。
    """
    bo_idx = bo.end_idx
    debug_break(bo_idx, anchor_kind='entry', class_id='tb')  # v2 · attempt entry(dead code when _DEBUG_MODE=False)
    if bo_idx < 1 or bo_idx >= len(df):
        return None
    atr = _atr_at(df, bo_idx - 1, atr_window)     # ★ bo-1:避开 bo 当根异常 TR
    if atr <= 0.0:
        return None
    anchor = measure_at(df, bo_idx - 1, anchor_measure)
    start = _find_start_idx(df, bo_idx, anchor, max_start_gap, atr,
                            pullback_min_atr, support_measure,
                            on_gate=on_gate, atr_window=atr_window)
    if start is None:
        return None
    end = _find_end_idx(df, start, anchor, max_window, atr,
                        big_rise_k, support_measure,
                        on_gate=on_gate, bo_idx=bo_idx, atr_window=atr_window)
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
    has_debug_hooks: ClassVar[bool] = True

    event_cls = ThrowbackEvent
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

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
            r = evaluate_throwback(bo, df, on_gate=self.on_gate, **self._kw)
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
