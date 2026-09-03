"""throwback 嵌套容器版:突破后回踩期企稳段容器(2026-08 重构)。

tb event [start_idx, end_idx] = 突破后回踩期企稳容器(可执行整理买窗):
  - 一个 bo 收成一个容器事件,内嵌 N 个企稳段 child(ThrowbackSegment);
  - start_idx = 首段 enter(企稳确认根);end_idx = 末段 exit(企稳退出根);
  - confirm_idx = start_idx(确认型:企稳成立那根即容器开始);
  - 容器 outcome = 末段退出原因(事后标签,仅诊断/统计用,不进 where/eval)。
可执行窗语义:段 span 内每一 bar 都是"当时已知买点仍开"的即时买入日,label
pipeline 经 eval_meta 的 end_node 路径(tb.segments)由 path2/eval.py::_resolve_end_events
逐段展开消费(段间间隙不计入样本;容器本身不再 override 样本)。

状态机总览(理解主循环的关键,先读这段再读函数):
  对每个 bo,扫 [bo+1, bo+max_start_gap] 一个区间,每根 bar 处于两种状态之一:
    - 段外(找买点):更新候选底部 local_trough → 企稳确认(四条件)则进入段内;
      期间若 low 跌破当前锚点 → oversold 全局终止(整个 bo 不再产段);
    - 段内(守买点):按序检查 派发(distribute)→ 跌破(oversold)→ 回升脱离(rise)
      → 下跌脱离(break)→ 满窗(timeout)→ 否则继续段。
      前三者之外,rise/break/timeout 是"段退出"(段收尾后还可再开新段,
      一 bo 多段);distribute/oversold 是"全局退出"(整个 bo 终止)。
  段 = 一次企稳确认(enter)到一次退出(exit);容器(ThrowbackEvent)= 一个 bo 的
  全部段。enter 即买点确认根,段内每 bar 都是"当时已知买点仍开"的即时买入日。

枚举核心 = enumerate_stabilization_segments(无前瞻状态机,V2,自 tb-buypoint-c
原样复制,逻辑零修改):
  - 企稳进入 = 局部 trough 后满 stop_confirm_bars + [trough, i] 含 stop signal
    + 前置下跌(close[trough] < close[trough-trend_lookback],过滤滞涨)
    + 当根不创新低(lo >= low[trough])——后两条是 V2 相对 V1 新增的过滤;
  - 段退出 = 回升脱离(rise,以段起始收盘为参照涨 k_exit*atr)/
    下跌脱离未破上一个 trough(break,以段起始收盘为参照跌 k_exit*atr)/
    持续满窗(timeout);
  - 全局退出 = 派发(distribute,高位长上影/极端暴涨)/ 跌破锚点(oversold),终止枚举;
  - 跌破锚点动态:首段前用 burst 锚点(anchor=bo-1 measure);首段后用上一个 trough。

anchor = measure_at(bo-1, anchor_measure);ATR 取 bo-1(避开 bo 当根异常 TR)。
预算:企稳进入 ∈ [bo+1, bo+max_start_gap],买点窗宽 enter→exit ≤ max_window。
V1(旧 ThrowbackEvent/evaluate_throwback)整体已搬入 throwback_v1.py。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Iterable, Iterator, List, Optional

import pandas as pd

from path2.atoms.breakout import BOEvent
from path2.calc.atr import calculate_atr
from path2.calc.measure import VALID_MEASURES, measure_at
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol
from path2.debug_ctx import debug_break


# 止跌 K 线证据集(_positive_signals 子集):下影 / 阳线 / 收涨
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


def _emit_tb_gate(on_gate, bo_idx, i, gate_name, kind, value, threshold, op,
                  threshold_param, atr_window, end=None):
    """V2 gate emit helper(on_gate 非 None 时组装 GateFailure)。end 用于 no_stabilization 的 window。"""
    if on_gate is None:
        return
    gate_idx = i if end is None else end
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx), start_idx=bo_idx + 1,
        gate_idx=gate_idx, anchor_bar=bo_idx, gate_name=gate_name,
        measured=MeasuredKindAware(kind=kind, value=value, label=gate_name),
        threshold=threshold, op=op, threshold_param=threshold_param,
        evaluation_lookback=(bo_idx - atr_window, bo_idx),
        symbol=current_symbol.get() or ''))


def enumerate_stabilization_segments(
    df: pd.DataFrame, bo_idx: int, anchor: float,
    max_start_gap: int, max_window: int, atr: float,
    stop_confirm_bars: int, big_rise_k: float,
    support_measure: str = "low",
    on_gate: Optional[Callable[[GateFailure], None]] = None,
    atr_window: int = 14,
    trend_lookback: int = 3, k_exit: float = 1.5,
    k1: float = 1.5, k2: float = 3.0, M: int = 5,
) -> List[tuple]:
    """V2:扫 [bo+1, bo+max_start_gap],枚举止跌企稳段(买点窗)。返回 [(enter, exit, reason)]。
    reason ∈ {'rise','break','timeout','distribute','oversold'}。全判据无前瞻。详见
    docs/superpowers/specs/2026-08-04-tb-v2-design.md §4。

    段外(找买点):更新 local_trough → 跌破锚点(全局 oversold 退出)→ 企稳确认
      (前置下跌 close[trough]<close[trough-trend_lookback] + trough 后满 SCB +
      含止跌信号 + 当根不创新低)。
    段内(按序):派发(全局 distribute)→ 跌破(全局 oversold)→ 回升脱离(rise 段退出)
      → 下跌脱离(break 段退出)→ timeout → 继续段(创新低刷新 local_trough)。
    跌破锚点动态:troughs 空→anchor;非空→low[troughs[-1]]。段退出时 troughs.append
    并重置 local_trough=退出根(新段从该根重新搜索候选底部,trough low 天然递增,spec §5)。
    诊断 gate:oversold / distribute / no_stabilization(扫满 0 段)。

    V2 vestigial 参数(签名兼容,当前实现未使用):
      - support_measure: V2 一律用 df['low'] 做 trough/跌破判据(spec §4 用 low);
      - big_rise_k:      V2 回升/下跌脱离用 k_exit*atr,派发用 k1/k2(spec §4)。
    """
    end = min(bo_idx + max_start_gap, len(df) - 1)   # 扫描预算:bo 后 max_start_gap 根
    segments: List[tuple] = []
    troughs: List[int] = []          # 已确认 trough idx(递增)——段退出时 append,供动态锚
    local_trough = bo_idx + 1        # 当前段候选底部:从 bo 后第一根起滚动 argmin(low)
    in_segment = False               # 状态:False=段外(找买点),True=段内(守买点)
    enter = -1                       # 当前段 enter(企稳确认根)= 买点确认根
    enter_seg_close = 0.0            # 段起始收盘:rise/break 段退出的参照价
    terminated = False               # 全局终止(distribute/oversold 后 True,不再产段)

    # 动态破位锚:首段前 = 突破前的价格锚(anchor,bo-1 的 anchor_measure),守住"突破
    # 即回踩"的底线——回踩连它都跌破说明突破失败;首段后 = 上一个已确认 trough 的
    # low(随 trough 递增而下移)——防止把新段内的正常回撤误判为破位。用 low 判破位
    # 意味着"盘中插破即弃",不要求收盘确认(V1 用 support_measure=close 收盘口径,
    # 这是 V1/V2 行为差异的关键点之一)。
    def fall_anchor() -> float:
        return anchor if not troughs else float(df['low'].iat[troughs[-1]])

    # 状态机主循环:每根 bar 按 in_segment 走两条路径之一——
    #   段外:更新 trough → 破位则全局终止 → 四条件齐备则开新段(enter=i);
    #   段内:按序检查六步(派发/跌破/回升/下跌/超时/继续)。
    # 无前瞻保证:所有判据只用 <= i 的数据。
    for i in range(bo_idx + 1, end + 1):
        lo = float(df['low'].iat[i]); hi = float(df['high'].iat[i])
        o = float(df['open'].iat[i]); c = float(df['close'].iat[i])

        if in_segment:
            body = abs(c - o)
            upper_shadow = hi - max(o, c)
            recent_high = max(float(df['high'].iat[j]) for j in range(max(i - M + 1, bo_idx + 1), i + 1))
            # step1 派发(全局退出):高位长上影(冲高回落,M 根内新高后长上影)
            # 或单根暴涨(实体 ≥ k2*atr 且收阳)——这类 bar 说明买点窗口已失效
            # (要么见顶要么已追高),之后不再有可执行买点,整个 bo 终止。
            if ((upper_shadow >= 2 * body and upper_shadow >= k1 * atr and hi >= recent_high)
                    or (body >= k2 * atr and c > o)):
                segments.append((enter, i, 'distribute'))
                debug_break(i, anchor_kind='end')  # distribute 出口·段 end
                _emit_tb_gate(on_gate, bo_idx, i, 'distribute', 'anchor_delta',
                              upper_shadow / atr if upper_shadow >= 2 * body else body / atr,
                              k1 if upper_shadow >= 2 * body else k2, '>=', None, atr_window)
                terminated = True; break
            # step2 跌破退出(全局):low 插破当前锚点,企稳逻辑被证伪,
            # 之后即使反弹也不可信——整个 bo 终止(与段外 oversold 同一判据)。
            if lo < fall_anchor():
                segments.append((enter, i, 'oversold'))
                debug_break(i, anchor_kind='end')  # oversold 出口·段 end
                _emit_tb_gate(on_gate, bo_idx, i, 'oversold', 'anchor_delta',
                              lo - fall_anchor(), 0.0, '>=', None, atr_window)
                terminated = True; break
            # step3 回升脱离(段退出):以段起始收盘 enter_seg_close 为参照涨
            # k_exit*atr,说明企稳后反弹已有力度——"涨够了",本段买点窗收尾;
            # 但只退出本段,后续若再企稳还可开新段(一 bo 多段)。
            if c - enter_seg_close >= k_exit * atr:
                segments.append((enter, i, 'rise')); troughs.append(local_trough)
                debug_break(i, anchor_kind='end')  # rise 出口·段 end
                local_trough = i  # 段退出重置:新段从退出根 i 起重新搜索候选底部(spec §4.1/§5 递增)
                in_segment = False; continue
            # step4 下跌脱离(段退出,未破锚点):以段起始收盘为参照跌 k_exit*atr
            # (但未破锚点)——企稳确认失败,本段收尾;同样只退段,可再开新段。
            # 与 step2 的区别:step2 是破"结构底线"(锚),本步只是"段内幅度超限"。
            if enter_seg_close - c >= k_exit * atr:
                segments.append((enter, i, 'break')); troughs.append(local_trough)
                debug_break(i, anchor_kind='end')  # break 出口·段 end
                local_trough = i  # 段退出重置(同 rise):新段从 i 起重新搜索候选底部
                in_segment = False; continue
            # step5 timeout(段退出)
            if i - enter >= max_window:
                segments.append((enter, i, 'timeout')); troughs.append(local_trough)
                debug_break(i, anchor_kind='end')  # timeout 出口·段 end
                local_trough = i  # 段退出重置(同 rise):新段从 i 起重新搜索候选底部
                in_segment = False; continue
            # step6 继续段:段内创新低但未破锚点——正常回踩,段继续持有,
            # 只刷新候选底部 local_trough(它也是本段后续跌破判据的参照)。
            if lo < float(df['low'].iat[local_trough]):
                local_trough = i
        else:
            # 段外(找买点):先更新候选底部,再查破位,最后试企稳确认。
            if lo < float(df['low'].iat[local_trough]):
                local_trough = i
            # 跌破退出(全局):同段内 step2,low 插破锚点即整个 bo 终止(见 fall_anchor)。
            if lo < fall_anchor():
                _emit_tb_gate(on_gate, bo_idx, i, 'oversold', 'anchor_delta',
                              lo - fall_anchor(), 0.0, '>=', None, atr_window)
                terminated = True; break
            # 企稳确认(买点,四条件全满足才开段):
            #   ① 前置下跌 close[trough] < close[trough-trend_lookback]——trough 确实
            #      处在一段下跌里,滤"横盘滞涨"型(该过滤是 V2 新增,代价=滤掉浅回调强势股);
            #   ② trough 后满 stop_confirm_bars 根——止跌需要时间验证,不追第一根反包;
            #   ③ [trough, i] 内至少一根含止跌信号(下影/阳线/收涨)——有 K 线证据;
            #   ④ 当根不创新低 lo >= low[trough]——企稳本身成立(V2 新增,防 trough 刚
            #      刷新就确认的假企稳)。
            # V1 只要求 ②③;①④ 是 V2 加的过滤闸,收紧的同时也误杀了一批
            # "bo 后浅回调、一两根就企稳"的强势样本(见 bb_v1 vs bottom_burst 对比)。
            pre_ok = (local_trough - trend_lookback >= 0 and
                      float(df['close'].iat[local_trough]) < float(df['close'].iat[local_trough - trend_lookback]))
            if (pre_ok and i - local_trough >= stop_confirm_bars
                    and any(_has_stop_signal(df, t) for t in range(local_trough, i + 1))
                    and lo >= float(df['low'].iat[local_trough])):
                in_segment = True
                enter = i
                enter_seg_close = c
                debug_break(i, anchor_kind='confirm')  # 段诞生点·段调试入口(bar=enter=start_idx)
    # 收尾:扫满预算(bo+max_start_gap)仍 in_segment → 强制 timeout 闭合——
    # 段不能悬空(否则这段的买点 bar 全部丢失),以预算末根为 exit 收段。
    if not terminated and in_segment:
        segments.append((enter, end, 'timeout')); troughs.append(local_trough)
        debug_break(end, anchor_kind='end')  # 收尾 timeout·段 end(bar=预算末根)
    # 0 段 gate
    if not terminated and not segments:
        _emit_tb_gate(on_gate, bo_idx, end, 'no_stabilization', 'count',
                      max_start_gap, max_start_gap, None, None, atr_window, end=end)
    return segments


def _atr_at(atr: pd.Series, idx: int) -> float:
    """预算 ATR 序列在 idx 处的值;越界/NaN → 0.0。"""
    if idx < 0 or idx >= len(atr):
        return 0.0
    v = float(atr.iat[idx])
    return v if v == v else 0.0   # NaN != NaN → fallback 0.0


@dataclass(frozen=True)
class ThrowbackSegment(Event):
    """回踩期内单个企稳段。span=[enter, exit];enter=企稳确认根;exit=退出根。
    段 span 内每 bar 是买点(eval 样本)。confirm=enter(确认型,与 V1 同构)。"""
    anchor_bo_id: str = ""
    outcome: str = "rise"  # rise/break/timeout/distribute/oversold(诊断用,不进 where/eval)


@dataclass(frozen=True)
class ThrowbackEvent(Event):
    """突破后回踩期企稳段容器。确认型:confirm=start=首段 enter;end=末段 exit。
    内嵌企稳段 child。容器 outcome=末段结局(诊断用,不进 where/eval)。"""
    segments: tuple[ThrowbackSegment, ...] = ()
    anchor_bo_id: str = ""   # 本实例来源 bo 的标识:交错标注后取源 bo 的 instance_id(detect 期 bo 已标注);同窗口多 bo 各带单来源
    outcome: str = "rise"

    def child_slots(self):
        return {"segments": self.segments}


class ThrowbackDetector:
    """V2 容器版:枚举企稳段,一个 bo 收成一个容器(内嵌 N 段)。确认型 confirm=start=首段 enter。"""
    has_debug_hooks: ClassVar[bool] = True
    event_cls = ThrowbackEvent
    on_gate = None

    def __init__(self, *, max_start_gap: int = 30, max_window: int = 5,
                 atr_window: int = 14, big_rise_k: float = 1.5,
                 stop_confirm_bars: int = 2, anchor_measure: str = "high",
                 support_measure: str = "low", trend_lookback: int = 3,
                 k_exit: float = 1.5, k1: float = 1.5, k2: float = 3.0, M: int = 5):
        self._kw = dict(max_start_gap=max_start_gap, max_window=max_window,
                        atr_window=atr_window, big_rise_k=big_rise_k,
                        stop_confirm_bars=stop_confirm_bars,
                        anchor_measure=anchor_measure, support_measure=support_measure,
                        trend_lookback=trend_lookback, k_exit=k_exit,
                        k1=k1, k2=k2, M=M)

    def detect(self, bo_stream: Iterable[BOEvent], df: pd.DataFrame) -> Iterator[ThrowbackEvent]:
        # on_gate 包装:补 gate debug 钩子。状态机 inline emit GateFailure 不走 debug_break,
        # detect 层包一层补回(保持 diagnose 钩子行为)。
        # debug_break 在 _DEBUG_MODE=False 时第一行 return,生产零成本。
        if self.on_gate is not None:
            _real = self.on_gate

            def _on_gate(gf):
                debug_break(gf.gate_idx, anchor_kind='gate')
                _real(gf)
            gate_cb = _on_gate
        else:
            gate_cb = None
        events = []
        atr_series = calculate_atr(df['high'], df['low'], df['close'], self._kw['atr_window'])
        for bo in bo_stream:
            bo_idx = bo.end_idx
            debug_break(bo_idx, anchor_kind='entry')
            if bo_idx < 1 or bo_idx >= len(df):
                continue
            # anchor/ATR 都取 bo-1:bo 当根的异常 TR 会污染量纲,锚价也一样
            # (突破当根之后才是回踩,参照物应是突破前的价格)。
            atr = _atr_at(atr_series, bo_idx - 1)
            if atr <= 0.0:
                continue
            anchor = measure_at(df, bo_idx - 1, self._kw['anchor_measure'])
            segs = enumerate_stabilization_segments(
                df, bo_idx, anchor,
                self._kw['max_start_gap'], self._kw['max_window'], atr,
                self._kw['stop_confirm_bars'], self._kw['big_rise_k'],
                self._kw['support_measure'],
                on_gate=gate_cb, atr_window=self._kw['atr_window'],
                trend_lookback=self._kw['trend_lookback'],
                k_exit=self._kw['k_exit'], k1=self._kw['k1'],
                k2=self._kw['k2'], M=self._kw['M'])
            if not segs:
                continue
            # 容器装配:一个 bo → 一个 ThrowbackEvent(容器),内嵌 N 个企稳段。
            # 容器 span = [首段 enter, 末段 exit],confirm = 首段 enter(确认型);
            # 段才是样本(eval 的 end_node='tb.segments' 逐段展开),容器本身
            # 只做"一个 bo 的全部买点窗"的组织单元。
            src_id = bo.instance_id
            segments = tuple(
                ThrowbackSegment(start_idx=s, end_idx=e, confirm_idx=s,
                                 anchor_bo_id=src_id, outcome=r)
                for s, e, r in segs)
            events.append(ThrowbackEvent(
                start_idx=segments[0].start_idx,
                end_idx=segments[-1].end_idx,
                confirm_idx=segments[0].start_idx,          # 确认型:首段 enter
                segments=segments,
                anchor_bo_id=src_id,
                outcome=segments[-1].outcome))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))
        yield from events
