"""throwback 可执行整理买窗事件(2026-07 重写)。

tb event [start_idx, end_idx] = 突破后可执行的整理买窗:
  - start_idx = 止跌企稳确认点(不再回溯到 trough,即时性);
  - end_idx   = 大涨前一根 / 破位前一根 / timeout(视 outcome 定);
  - outcome ∈ ('rise', 'break', 'timeout')= 窗口关闭方式(见 ThrowbackEvent);
  - 事件存在 ⟺ Phase 1 confirm 成功(confirm 前 anchor break / rise-before-confirm 不产)。
可执行窗语义:窗内每一 bar 都是"当时已知买点仍开"的即时买入日,label pipeline
逐日消费(path2/eval.py::match_forward_returns)。

anchor = measure_at(bo-1, anchor_measure);Phase 1 全程 measure_at(i, support_measure)
≥ anchor;ATR 取 bo-1(避开 bo 当根异常 TR)。
预算:确认点 ∈ [bo+1, bo+max_start_gap],买点窗宽 confirm→end ≤ max_window。
Phase 2 rise 判据:high[i] - base_min ≥ big_rise_k*atr,base_min = running min low
over [trough, i-1](锚 trough,反映从整理底部起的反弹力度)。
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

# tb 事件结局值域:phase2 三条出路
_TB_OUTCOMES = ("rise", "break", "timeout")


class ThrowbackResult(NamedTuple):
    """evaluate_throwback 成功返回值;失败返回 None(不产事件)。

    outcome ∈ _TB_OUTCOMES:phase 2 的三种收窗方式。
    """
    start_idx: int
    end_idx: int
    outcome: str


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


def _find_confirm_idx(df: pd.DataFrame, bo_idx: int, anchor: float,
                    max_start_gap: int, atr: float,
                    stop_confirm_bars: int, big_rise_k: float,
                    support_measure: str = "low",
                    on_gate: Optional[Callable[[GateFailure], None]] = None,
                    atr_window: int = 14) -> Optional[tuple[int, int]]:
    """Phase 1:定位止跌企稳确认点。返回 (confirm_idx, trough_idx) 或 None。

    扫 [bo+1, bo+max_start_gap];三条不产事件的短路:
      - 任一根 measure_at(i, support_measure) < anchor → phase1_break → None;
      - 任一根 high[i] - base_min ≥ big_rise_k*atr(base_min = running min low
        over [bo+1, i-1])→ phase1_rise_before_confirm → None;
      - 扫满未 confirm → phase1_no_confirm_timeout → None。
    confirm 条件(K = stop_confirm_bars):i - trough_idx ≥ K,且 [trough_idx, i] 内
      至少一根 K 线含 stop signal(_STOP_SIGNALS = 下影/阳线/收涨之一)。
      trough_idx = argmin(low) over [bo+1, i](动态更新);当 i 刷新 trough 时
      i-trough=0,天然不满足 K,当前根不 confirm。

    注意:base_min 是 running min low over [bo+1, i-1](不含当前 i)——同根内
    high-low 相消会失效 rise 检测;与 phase 2 内部同口径。
    """
    end = min(bo_idx + max_start_gap, len(df) - 1)
    trough_idx = bo_idx + 1
    # inf 起手:首轮(i=bo+1)由循环末的 running-min 更新自动 seed 成 low[bo+1],与
    # 直接初始化等价;但不在循环外读 low[bo+1]——bo 落在数据末根时该下标越界。
    base_min = float('inf')
    for i in range(bo_idx + 1, end + 1):
        # 1. anchor break
        measured_support = measure_at(df, i, support_measure)
        if measured_support < anchor:
            _emit_tb_gate(bo_idx, i, 'phase1_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measured_support - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate,
                          op='>=', threshold_param=None)
            return None
        # 2. maintain trough_idx (argmin over [bo+1, i])
        lo_i = float(df['low'].iat[i])
        if lo_i < float(df['low'].iat[trough_idx]):
            trough_idx = i
        # 3. rise-before-confirm(仅当 i ≥ bo+2 时 base_min 已覆盖 [bo+1, i-1])
        if i >= bo_idx + 2:
            rise = float(df['high'].iat[i]) - base_min
            if rise >= big_rise_k * atr:
                _emit_tb_gate(bo_idx, i, 'phase1_rise_before_confirm',
                              MeasuredKindAware(kind='rise_atr',
                                                value=rise / atr if atr > 0 else 0.0,
                                                label='大涨幅/ATR'),
                              big_rise_k, atr_window, on_gate,
                              op='>=', threshold_param='big_rise_k')
                return None
        # 4. confirm: K-bar trough-age + stop evidence in [trough, i]
        if i - trough_idx >= stop_confirm_bars:
            if any(_has_stop_signal(df, t) for t in range(trough_idx, i + 1)):
                debug_break(i, anchor_kind='confirm', class_id='tb')   # v3 · confirm point
                return i, trough_idx
        # 5. running-min update for next iteration
        if lo_i < base_min:
            base_min = lo_i
    _emit_tb_gate(bo_idx, end, 'phase1_no_confirm_timeout',
                  MeasuredKindAware(kind='count', value=max_start_gap,
                                    label='max_start_gap 扫满(无确认)'),
                  max_start_gap, atr_window, on_gate)
    return None


def _find_end_idx(df: pd.DataFrame, confirm_idx: int, trough_idx: int,
                  anchor: float, max_window: int, atr: float, big_rise_k: float,
                  support_measure: str = "low",
                  on_gate: Optional[Callable[[GateFailure], None]] = None,
                  bo_idx: Optional[int] = None,
                  atr_window: int = 14) -> tuple[int, str]:
    """Phase 2:确认后找结局。返回 (end_idx, outcome ∈ _TB_OUTCOMES)——never None。

    扫 [confirm+1, confirm+max_window],三条出路:
      - measure_at(i, support_measure) < anchor → (i-1, 'break'),emit phase2_break;
      - high[i] - base_min ≥ big_rise_k*atr → (i-1, 'rise')(成功路径,不 emit gate);
      - 扫满无 rise 无 break → (min(confirm+max_window, len-1), 'timeout')。
    base_min = running min low over [trough_idx, i-1];初始 seed = min low over
      [trough_idx, confirm_idx](因为 i=confirm+1 时 base 应含 confirm 那一根)。
    rise 幅度以 trough 为参照(整理底部)而非 confirm——反映真实反弹力度。
    """
    end_scan = min(confirm_idx + max_window, len(df) - 1)
    # seed base_min:覆盖 [trough_idx, confirm_idx](i=confirm+1 时需已含 confirm)
    base_min = float(df['low'].iloc[trough_idx: confirm_idx + 1].min())
    for i in range(confirm_idx + 1, end_scan + 1):
        # 1. anchor break → 产事件 outcome='break',end=i-1
        measured_support = measure_at(df, i, support_measure)
        if measured_support < anchor:
            _emit_tb_gate(bo_idx, i, 'phase2_break',
                          MeasuredKindAware(kind='anchor_delta',
                                            value=measured_support - anchor,
                                            label='破位差'),
                          0.0, atr_window, on_gate,
                          op='>=', threshold_param=None)
            debug_break(i - 1, anchor_kind='end', class_id='tb')
            return i - 1, "break"
        # 2. rise → 产事件 outcome='rise',end=i-1
        if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
            debug_break(i - 1, anchor_kind='end', class_id='tb')
            return i - 1, "rise"
        # 3. update base_min for next iteration
        lo_i = float(df['low'].iat[i])
        if lo_i < base_min:
            base_min = lo_i
    debug_break(end_scan, anchor_kind='end', class_id='tb')
    return end_scan, "timeout"


def evaluate_throwback(
    bo: BOEvent, df: pd.DataFrame, *,
    max_start_gap: int = 5,
    max_window: int = 5,
    atr_window: int = 14,
    big_rise_k: float = 1.5,
    stop_confirm_bars: int = 2,
    anchor_measure: str = "high",
    support_measure: str = "close",
    on_gate: Optional[Callable[[GateFailure], None]] = None,
) -> Optional[ThrowbackResult]:
    """对单个 BO 判可执行整理买窗。成功返回 ThrowbackResult(start,end,outcome),失败返回 None。

    anchor = measure_at(bo-1, anchor_measure);ATR 取 bo-1(bo 当根异常 TR 污染)。
    Phase 1:确认点 = 首个 i∈[bo+1, bo+max_start_gap] 满足 i-trough≥stop_confirm_bars
      且 [trough, i] 内含 stop signal;confirm 前 anchor break / rise ≥ big_rise_k×atr → None。
    Phase 2:base_min 锚 trough,扫 [confirm+1, confirm+max_window],三 outcome:
      'break' = anchor 破位收窗(end=i-1);'rise' = 大涨收窗(end=i-1);
      'timeout' = 扫满收窗(end=min(confirm+max_window, len-1))。三种均产事件。

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
    r = _find_confirm_idx(df, bo_idx, anchor, max_start_gap, atr,
                        stop_confirm_bars, big_rise_k, support_measure,
                        on_gate=on_gate, atr_window=atr_window)
    if r is None:
        return None
    confirm_idx, trough_idx = r
    end_idx, outcome = _find_end_idx(df, confirm_idx, trough_idx, anchor,
                                     max_window, atr, big_rise_k, support_measure,
                                     on_gate=on_gate, bo_idx=bo_idx,
                                     atr_window=atr_window)
    return ThrowbackResult(confirm_idx, end_idx, outcome)


@dataclass(frozen=True)
class ThrowbackEvent(Event):
    """突破后可执行整理买窗事件。start_idx=止跌企稳确认点;end_idx=大涨前一根 / 破位前一根 / timeout。
    confirm_idx = start_idx:确认类,成立条件(止跌企稳)在 start_idx 满足,end_idx 只是大涨验证窗口。

    outcome 是"窗口关闭的原因",三值 ∈ _TB_OUTCOMES:
    - "rise":  确认后出现 big_rise → 涨前一根收窗(常见成功场景);
    - "break": 确认后 anchor 被跌破 → 破位前一根收窗(真实失败样本);
    - "timeout": 扫满 max_window 无 rise 无 break → 上界收窗(纠结型 / 弱信号)。
    事件存在 ⟺ Phase 1 confirm 成功;confirm 前的 anchor break / rise-before-confirm 不产事件。

    输出字段(where 可引用):
    - anchor_bo_id: 触发本事件的那根 BO 的 event_id(追溯用);
                    多 BO 映射到同 span 时按 event_id 去重保留首个
    - outcome:     "rise" / "break" / "timeout"(窗口关闭原因)
    """
    class_id = "tb"
    anchor_bo_id: str = ""
    outcome: str = "rise"


class ThrowbackDetector:
    """派生 detector:消费 bo 流,逐 BO 调 evaluate_throwback,产事件(含失败结局)。

    核心判据(详见 evaluate_throwback / _find_confirm_idx / _find_end_idx):
      anchor = measure_at(bo-1, anchor_measure);ATR 取 bo-1 处(避开 BO 当根异常 TR)。
      Phase 1(_find_confirm_idx,找 confirm):扫 [bo+1, bo+max_start_gap];三条不产事件:
        - support_measure < anchor → phase1_break;
        - high[i] - base_min ≥ big_rise_k*atr(base_min 锚 bo+1) → phase1_rise_before_confirm;
        - 扫满无 confirm → phase1_no_confirm_timeout。
        confirm 条件:i-trough ≥ stop_confirm_bars 且 [trough,i] 内含 stop signal
        (_STOP_SIGNALS = 下影/阳线/收涨之一)。
      Phase 2(_find_end_idx,找 outcome):扫 [confirm+1, confirm+max_window],base_min
        锚 trough,三 outcome:
        - support_measure < anchor → outcome='break', end=i-1(事件仍产, phase2_break gate);
        - high[i] - base_min ≥ big_rise_k*atr → outcome='rise', end=i-1;
        - 扫满 → outcome='timeout', end=min(confirm+max_window, len-1)。
      anchor_measure 定锚价、support_measure 定破位比较,语义不同需同时检查。

    多源 L2+ detector(detect(self, bo_stream, df) 双参,走 run() 变参透传)。
    end_idx 升序排序(过 run() 升序不变式):trigger 随 bo 顺序可能乱序,收集后排序再 yield。
    多个 bo 映射到同 span 时按 event_id 去重(buyable-window 身份 = span);同 span 不同
    outcome 属逻辑不可能(evaluate 对同 bo 决定性),不额外处理。

    输出字段详见 ThrowbackEvent。
    """
    has_debug_hooks: ClassVar[bool] = True

    event_cls = ThrowbackEvent
    on_gate = None   # Detector.on_gate protocol 静态声明,运行时不自动继承;默认 None = 生产路径无开销

    def __init__(self, *, max_start_gap: int = 7, max_window: int = 5,
                 atr_window: int = 14, big_rise_k: float = 1.5,
                 stop_confirm_bars: int = 2,
                 anchor_measure: str = "high", support_measure: str = "low"):
        if anchor_measure not in VALID_MEASURES:
            raise ValueError(f"anchor_measure 必须在 {VALID_MEASURES},实际 {anchor_measure!r}")
        if support_measure not in VALID_MEASURES:
            raise ValueError(f"support_measure 必须在 {VALID_MEASURES},实际 {support_measure!r}")
        self._kw = dict(max_start_gap=max_start_gap, max_window=max_window,
                        atr_window=atr_window, big_rise_k=big_rise_k,
                        stop_confirm_bars=stop_confirm_bars,
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
                    confirm_idx=start,   # 确认类:止跌企稳那根确认(start_idx 即确认点)
                    anchor_bo_id=bo.event_id,
                    outcome=r.outcome))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # ★ run() 要 end 升序
        seen: set[str] = set()
        for e in events:
            if e.event_id in seen:   # 同窗多 bo → 同 span 同 id,去重(buyable-window 身份=span)
                continue
            seen.add(e.event_id)
            yield e
