"""throwback v3:V1 语义多段化(re-entry)状态机。

tb v3 把 V1(judged/reference 双口径 + anchor_mode 三模式定锚)扩展为多段:
一 bo 可产出多个企稳段(买点窗)——weak/rise/timeout 段级退出后,段外从退出根
重新滚动 trough 并企稳确认(re-entry);仅 judged 收盘破全局 anchor 才整 bo 终止
(当前段以 'break' 截断)。不带 V2 的 pre_ok/distribute/k_exit/当根不创新低。

事件结构(V2 容器模式):ThrowbackEventV3 容器内嵌
ThrowbackSegmentV3 子段;容器 span=[首段 enter, 末段 exit],
confirm=start(首段 enter);容器无独立退出判据,end=末段 exit、outcome=末段结局
(2026-08-11 spec 用户选 A:先看实证再定是否引入容器级上限)。

判据(全部 V1 语义):
- anchor:anchor_mode 定锚(reference 口径);judged 收盘破 anchor → 全局终止
- 段外:滚动 trough = argmin(reference_measure)(从段外起点起);
  rise-before-confirm(high - base_min ≥ big_rise_k*atr,base_min 锚段外起点)
  → 整 bo 终止;企稳确认 = SCB(no_new_low: i-trough ≥ K / rising: 连续不降
  计数 ≥ K,比较用 judged)+ [trough, i] 含 stop signal
- 段内(按序):1. 破 anchor → 全局终止(break 截断);2. judged < trough 的
  reference 价 → weak 退段;3. high - base_min ≥ big_rise_k*atr(base_min 锚
  trough,seed = min low over [trough, confirm])→ rise 退段;4. 段长超限 →
  timeout 退段;5. 否则继续段(刷新 base_min)
- 收尾:预算扫满仍段内 → 强制 timeout 闭合;0 段 → 不产事件
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, ClassVar, Iterable, Iterator, List, Optional

import pandas as pd

from path2.atoms.breakout import BOEvent, BurstEvent
from path2.calc.atr import calculate_atr
from path2.calc.measure import VALID_MEASURES, measure_at
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol
from path2.debug_ctx import debug_break


# ── 从 throwback_v1(2026-08-25 重写前)逐字搬入的私有 helper(v3 为冻结遗留,不再依赖 v1)──
_STOP_SIGNALS = ('lower_shadow', 'bullish', 'close_up')


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


def _atr_at(atr: pd.Series, idx: int) -> float:
    """预算 ATR 序列在 idx 处的值;越界/NaN → 0.0。

    取预算序列(detect 每股算一次)而非每次调用重算全序列——与 throwback_v0 /
    throwback.py 的同名 helper 同签名同语义。
    """
    if idx < 0 or idx >= len(atr):
        return 0.0
    v = float(atr.iat[idx])
    return v if v == v else 0.0   # NaN != NaN → fallback 0.0


# tb v3 段结局值域:段级三条出路 + 全局终止截断
_TB_SEG_OUTCOMES = ("weak", "rise", "timeout", "break")


def _emit_tb_gate_v3(bo_idx: int, gate_idx: int, gate_name: str,
                     measured: MeasuredKindAware, threshold,
                     atr_window: int,
                     on_gate: Optional[Callable[[GateFailure], None]],
                     *, op: Optional[str] = None,
                     threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit(避免 5 处埋点重复 boilerplate)。

    从 throwback_v1._emit_tb_gate 逐字复制(仅函数名与 docstring 不同),埋点同为
    debug_break(bar, anchor_kind='gate'),无 class 维度;GateFailure 自身不带身份,
    node_id 由 gate_collector per-node wrapper 注入。

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
    debug_break(gate_idx, anchor_kind='gate', stop_at_frame=sys._getframe(1))
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        start_idx=bo_idx + 1,
        gate_idx=gate_idx,
        anchor_bar=bo_idx,
        gate_name=gate_name,
        measured=measured,
        threshold=threshold,
        op=op,
        threshold_param=threshold_param,
        evaluation_lookback=(bo_idx - atr_window, bo_idx),
        symbol=current_symbol.get() or '',
    ))


def enumerate_segments_v3(
    df: pd.DataFrame, bo_idx: int, anchor: float,
    max_start_gap: int, max_window: int, atr: float,
    stop_confirm_bars: int, big_rise_k: float,
    judged_measure: str = "close",
    reference_measure: str = "close",
    scb_mode: str = "no_new_low",
    on_gate: Optional[Callable[[GateFailure], None]] = None,
    atr_window: int = 14,
) -> List[tuple]:
    """V3 多段状态机:扫 [bo+1, bo+max_start_gap],枚举企稳段。返回 [(enter, exit, outcome)]。

    outcome ∈ _TB_SEG_OUTCOMES;'break' 只可能出现在末段(全局终止截断);
    weak/rise/timeout 段退出后段外继续(可 re-entry)。全判据无前瞻。

    状态:
    - 段外(找企稳):滚动 trough = argmin(reference_measure) over [段外起点, i]
      (段外起点 = bo+1 或段退出根);judged < anchor → 全局终止(phase1_break);
      high - base_min ≥ big_rise_k*atr(base_min = running min low over
      [段外起点, i-1])→ 整 bo 终止(phase1_rise_before_confirm);
      企稳确认 = SCB + [trough, i] 含 stop signal。
    - 段内(守段,按序):1. judged < anchor → 全局终止(phase2_break,段 'break'
      截断);2. judged < trough_price(trough 的 reference 价,开段时冻结)→
      phase2_weak 退段;3. high - base_min ≥ big_rise_k*atr → 退段('rise');
      4. i - enter ≥ max_window → 退段('timeout');5. 继续段(刷新 base_min)。
      段内 base_min = running min low over [trough, i-1],seed = min low over
      [trough, confirm](同 V1 phase2)。
    收尾:预算扫满仍段内 → 强制 timeout 闭合(段不悬空);扫满 0 段 → emit
    phase1_no_confirm_timeout(仅首段外扫满时)。
    """
    end = min(bo_idx + max_start_gap, len(df) - 1)
    segments: List[tuple] = []
    local_trough = bo_idx + 1          # 当前段外候选底部(argmin 起点=段外起点)
    in_segment = False
    enter = -1
    trough_price = 0.0                 # 段 trough 的 reference 价(开段冻结)
    rising_count = 0                   # scb_mode="rising":连续不降计数
    base_min = float('inf')            # running min low:段外锚段外起点、段内锚 trough
    for i in range(bo_idx + 1, end + 1):
        measured = measure_at(df, i, judged_measure)
        # ══ 全局检查(段内/段外共用):judged 收盘破 anchor → 整 bo 终止 ══
        if measured < anchor:
            if in_segment:
                _emit_tb_gate_v3(bo_idx, i, 'phase2_break',
                              MeasuredKindAware(kind='anchor_delta',
                                                value=measured - anchor,
                                                label='破位差'),
                              0.0, atr_window, on_gate,
                              op='>=', threshold_param=None)
                debug_break(i - 1, anchor_kind='end')
                segments.append((enter, i - 1, 'break'))
            else:
                _emit_tb_gate_v3(bo_idx, i, 'phase1_break',
                              MeasuredKindAware(kind='anchor_delta',
                                                value=measured - anchor,
                                                label='破位差'),
                              0.0, atr_window, on_gate,
                              op='>=', threshold_param=None)
            return segments
        if in_segment:
            # ══ 段内(按序 2-5)══
            # 2. weak:judged 收盘破段 trough 的 reference 价 → 退段(可 re-entry)
            if measured < trough_price:
                _emit_tb_gate_v3(bo_idx, i, 'phase2_weak',
                              MeasuredKindAware(kind='anchor_delta',
                                                value=measured - trough_price,
                                                label='跌破企稳底'),
                              0.0, atr_window, on_gate,
                              op='>=', threshold_param=None)
                debug_break(i - 1, anchor_kind='end')
                segments.append((enter, i - 1, 'weak'))
                in_segment = False
                local_trough = i      # 段退出根 = 新段外起点
                base_min = float(df['low'].iat[i])   # base 锚退出根(重滚起点)
                continue
            # 3. rise:大涨脱离(涨幅以 trough 为参照)→ 退段
            if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
                debug_break(i - 1, anchor_kind='end')
                segments.append((enter, i - 1, 'rise'))
                in_segment = False
                local_trough = i
                base_min = float(df['low'].iat[i])
                continue
            # 4. timeout:段长超限 → 退段
            if i - enter >= max_window:
                debug_break(i, anchor_kind='end')
                segments.append((enter, i, 'timeout'))
                in_segment = False
                local_trough = i
                base_min = float(df['low'].iat[i])
                continue
            # 5. 继续段:刷新 base_min(段内创新低不退出——收盘口径)
            lo_i = float(df['low'].iat[i])
            if lo_i < base_min:
                base_min = lo_i
        else:
            # ══ 段外(找企稳)══
            m_i = measure_at(df, i, reference_measure)
            if m_i < measure_at(df, local_trough, reference_measure):
                local_trough = i
                rising_count = 0      # 刷新 trough:新起点
            elif scb_mode == "rising":
                if measure_at(df, i, judged_measure) >= measure_at(df, i - 1, judged_measure):
                    rising_count += 1
                else:
                    rising_count = 0
            # rise-before-confirm(局部 base_min 锚段外起点;inf 起手自然保护首根)
            if float(df['high'].iat[i]) - base_min >= big_rise_k * atr:
                _emit_tb_gate_v3(bo_idx, i, 'phase1_rise_before_confirm',
                              MeasuredKindAware(kind='rise_atr',
                                                value=(float(df['high'].iat[i]) - base_min) / atr if atr > 0 else 0.0,
                                                label='大涨幅/ATR'),
                              big_rise_k, atr_window, on_gate,
                              op='>=', threshold_param='big_rise_k')
                return segments      # 整 bo 终止:没等到企稳就大涨,不进多段
            # 企稳确认(SCB + stop signal)
            bars_ok = (rising_count >= stop_confirm_bars if scb_mode == "rising"
                       else i - local_trough >= stop_confirm_bars)
            if bars_ok and any(_has_stop_signal(df, t) for t in range(local_trough, i + 1)):
                debug_break(i, anchor_kind='confirm')
                in_segment = True
                enter = i
                trough_price = measure_at(df, local_trough, reference_measure)
                base_min = float(df['low'].iloc[local_trough: i + 1].min())
                continue
            lo_i = float(df['low'].iat[i])
            if lo_i < base_min:
                base_min = lo_i
    # 收尾:预算扫满仍段内 → 强制 timeout 闭合(段不悬空)
    if in_segment:
        debug_break(end, anchor_kind='end')
        segments.append((enter, end, 'timeout'))
    # 0 段:首段外扫满无确认 → emit(与 V1 phase1_no_confirm_timeout 同语义)
    if not segments:
        _emit_tb_gate_v3(bo_idx, end, 'phase1_no_confirm_timeout',
                      MeasuredKindAware(kind='count', value=max_start_gap,
                                        label='max_start_gap 扫满(无确认)'),
                      max_start_gap, atr_window, on_gate)
    return segments


@dataclass(frozen=True)
class ThrowbackSegmentV3(Event):
    """回踩期内单个企稳段。span=[enter, exit];enter=企稳确认根;exit=退出根。
    段 span 内每 bar 是买点(eval 样本,经容器 child_slots 展开)。confirm=enter。
    outcome ∈ ('weak', 'rise', 'timeout', 'break');break 只出现在末段。"""
    anchor_bo_id: str = ""
    outcome: str = "weak"


@dataclass(frozen=True)
class ThrowbackEventV3(Event):
    """突破后回踩期企稳段容器(一 bo 多段)。确认型:confirm=start=首段 enter;
    end=末段 exit;outcome=末段结局(诊断用,不进 where/eval)。"""
    segments: tuple[ThrowbackSegmentV3, ...] = ()
    anchor_bo_id: str = ""   # 本实例来源 bo 的标识:交错标注后取源 bo 的 instance_id(detect 期 bo 已标注);同窗口多 bo 各带单来源
    outcome: str = "weak"

    def child_slots(self):
        return {"segments": self.segments}


class ThrowbackDetectorV3:
    """派生 detector:消费 burst 流,逐 burst 枚举多段(re-entry),产容器事件。

    anchor 口径由 anchor_mode 控制(默认 span_min,与 V1 detect 同款三模式):
      last_bo = last_bo 上一根 reference 价 / min_bo = 串内各 bo 当根取 min /
      span_min = burst span [start_idx, end_idx] 全部 bar 取 min。
    核心判据(详见 enumerate_segments_v3):ATR 取 bo-1;段外找企稳(V1 phase1
    语义,rise-before-confirm 终止整 bo);段内按序 weak/rise/timeout/破 anchor
    (V1 phase2 语义);weak/rise/timeout 段退出后可 re-entry;破 anchor 全局终止。

    多源 L2+ detector(detect(self, burst_stream, df) 双参,走 run() 变参透传)。
    end_idx 升序排序(过 run() 升序不变式);实例流语义:同窗口多 bo 直出多实例
    (同 span 多实例,由物化标注按流序编号,各带单来源 anchor_bo_id),不再合并。
    """
    has_debug_hooks: ClassVar[bool] = True

    event_cls = ThrowbackEventV3
    on_gate = None

    def __init__(self, *, max_start_gap: int = 7, max_window: int = 5,
                 atr_window: int = 14, big_rise_k: float = 1.5,
                 stop_confirm_bars: int = 2,
                 judged_measure: str = "close", reference_measure: str = "close",
                 scb_mode: str = "no_new_low", anchor_mode: str = "span_min"):
        if judged_measure not in VALID_MEASURES:
            raise ValueError(f"judged_measure 必须在 {VALID_MEASURES},实际 {judged_measure!r}")
        if reference_measure not in VALID_MEASURES:
            raise ValueError(f"reference_measure 必须在 {VALID_MEASURES},实际 {reference_measure!r}")
        if scb_mode not in ("no_new_low", "rising"):
            raise ValueError(f"scb_mode 必须是 'no_new_low'|'rising',实际 {scb_mode!r}")
        if anchor_mode not in ("last_bo", "min_bo", "span_min"):
            raise ValueError(f"anchor_mode 必须是 'last_bo'|'min_bo'|'span_min',实际 {anchor_mode!r}")
        self._kw = dict(max_start_gap=max_start_gap, max_window=max_window,
                        atr_window=atr_window, big_rise_k=big_rise_k,
                        stop_confirm_bars=stop_confirm_bars,
                        judged_measure=judged_measure,
                        reference_measure=reference_measure,
                        scb_mode=scb_mode, anchor_mode=anchor_mode)

    def detect(self, burst_stream: Iterable[BurstEvent], df: pd.DataFrame) -> Iterator[ThrowbackEventV3]:
        events = []
        atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])
        for burst in burst_stream:
            last_bo = burst.members[-1]
            # anchor 口径由 anchor_mode 控制(与 V1 detect 同款三模式)
            mode = self._kw['anchor_mode']
            if mode == 'last_bo':
                anchor = measure_at(df, last_bo.end_idx - 1, self._kw['reference_measure'])
            elif mode == 'min_bo':
                anchor = min(measure_at(df, b.end_idx, self._kw['reference_measure'])
                             for b in burst.members)
            else:  # 'span_min'(默认)
                anchor = min(measure_at(df, i, self._kw['reference_measure'])
                             for i in range(burst.start_idx, burst.end_idx + 1))
            bo_idx = last_bo.end_idx
            debug_break(bo_idx, anchor_kind='entry')
            if bo_idx < 1 or bo_idx >= len(df):
                continue
            atr = _atr_at(atr_series, bo_idx - 1)
            if atr <= 0.0:
                continue
            segs = enumerate_segments_v3(
                df, bo_idx, anchor,
                self._kw['max_start_gap'], self._kw['max_window'], atr,
                self._kw['stop_confirm_bars'], self._kw['big_rise_k'],
                judged_measure=self._kw['judged_measure'],
                reference_measure=self._kw['reference_measure'],
                scb_mode=self._kw['scb_mode'],
                on_gate=self.on_gate, atr_window=self._kw['atr_window'])
            if not segs:
                continue
            # 容器装配:一个 bo → 一个 ThrowbackEventV3(容器),内嵌 N 个企稳段。
            # 容器 span = [首段 enter, 末段 exit],confirm = 首段 enter(确认型);
            # 段才是样本(eval 的 end_node='tb_v3.segments' 逐段展开)。
            src_id = last_bo.instance_id
            segments = tuple(
                ThrowbackSegmentV3(start_idx=s, end_idx=e, confirm_idx=s,
                                   anchor_bo_id=src_id, outcome=r)
                for s, e, r in segs)
            events.append(ThrowbackEventV3(
                start_idx=segments[0].start_idx,
                end_idx=segments[-1].end_idx,
                confirm_idx=segments[0].start_idx,
                segments=segments,
                anchor_bo_id=src_id,
                outcome=segments[-1].outcome))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # ★ run() 要 end 升序
        yield from events
