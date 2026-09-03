"""throwback v1(2026-08-25 重写):post-burst **首段即停**的价格行为状态机。

一句话定位:每 burst 一台 UP/DOWN/STABLE 机器,DOWN 找底(K 根不刷新入段)、STABLE 为唯一
买点窗,rise / weak / break / timeout 任一收口即终止;一 burst 至多一个扁平事件。与 v4
(throwback_v4.py,多段容器 + ratchet + re-entry)的唯一差异 = 首段收口即停(2026-08-25
用户裁定:多段无意义,先做对单次买入)。

核心判据:见 run_first_segment docstring(spec §3 伪代码逐条对应,含检查顺序与严格不等式约定)。
口径:单一 measure(默认 close)统一全部数值比较;阴线臂恒用真 close/open;波动单位 =
median TR 即时取 i-1(calc.atr.calculate_tr_median,vol NaN 热身 → 反弹臂降级);
global_bottom = burst span [start_idx, end_idx] 内 measure 最小(旧 span_min,固定)。
可执行窗语义不变:窗内每 bar 都是即时买入日,label pipeline 逐日消费(end_node='tb')。
输出字段:见 ThrowbackEventV1。资格型门槛(回踩段单日跌幅)只出字段 max_day_drop,阈值由
app where 表达(bb_v1:W.attr("max_day_drop", "<", max_day_drop_pct)),detector 不设门。

设计文档:docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, ClassVar, Iterable, Iterator, List, NamedTuple, Optional

import numpy as np
import pandas as pd

from path2.atoms.breakout import BurstEvent
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import VALID_MEASURES, measure_at, measure_series
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol
from path2.debug_ctx import debug_break


# tb 事件结局值域:首段四种收口方式
_TB_OUTCOMES = ("rise", "weak", "break", "timeout")


def _revert_max_day_drop(df: pd.DataFrame, bo_idx: int, confirm_idx: int) -> float:
    """回踩段 [revert_idx, confirm_idx] 内最大单日跌幅(pct 口径;资格型原始量,落字段 max_day_drop)。

    revert_idx = bo 后第一根「阴线(c<o)或收跌(c<c_prev)」bar(找不到则 bo+1);
    段内遍历收跌日,返回 max (c[i-1]-c[i])/c[i-1](无收跌日 → 0.0)。
    只用 ≤confirm_idx 的数据(无前瞻)。口径拍板(2026-08-18 研究,
    docs/research/2026-08-18_tb-v1-revert-quality/):绝对跌幅优于 TR 中位数归一。
    """
    c = df['close']
    o = df['open']
    revert_idx = bo_idx + 1
    for i in range(bo_idx + 1, confirm_idx + 1):
        if float(c.iat[i]) < float(o.iat[i]) or float(c.iat[i]) < float(c.iat[i - 1]):
            revert_idx = i
            break
    max_drop = 0.0
    for i in range(revert_idx, confirm_idx + 1):
        ci, cprev = float(c.iat[i]), float(c.iat[i - 1])
        if ci < cprev and cprev > 0:
            max_drop = max(max_drop, (cprev - ci) / cprev)
    return max_drop


def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  vol_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit。

    一 burst 一次 run_first_segment = 一次 attempt,attempt 起点 = bo+1;
    failure_event_window=(bo+1, gate_idx);evaluation_lookback=(gate_idx-vol_window, gate_idx-1)
    (median TR 即时窗,随 gate_idx 移动)。on_gate is None → 早退(生产路径零开销,
    非 scan/diagnose 分野:真实 scan 也挂 collector)。
    """
    if on_gate is None:
        return
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
        evaluation_lookback=(gate_idx - vol_window, gate_idx - 1),
        symbol=current_symbol.get() or '',
    ))


class FirstSegment(NamedTuple):
    """首段结果:enter=入段根(第 K 根不刷新根),exit=收口根,outcome ∈ _TB_OUTCOMES。"""
    enter: int
    exit: int
    outcome: str


def run_first_segment(
    closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float,
    vol: np.ndarray, *,
    max_rise_k: float = 1.5, stop_confirm_bars: int = 1, max_span: int = 20,
    on_gate: Optional[Callable[[GateFailure], None]] = None, vol_window: int = 14,
    real_closes: Optional[np.ndarray] = None,
) -> Optional[FirstSegment]:
    """UP/DOWN/STABLE 价格行为状态机,**首段收口即停**(spec §3,检查顺序固定不可换)。

    扫描 [bo+1, min(bo+max_span, n-1)],每根按序:
      0. close < global_bottom → 终止:STABLE 中 → (enter, i-1, 'break') 并 emit break_truncate;
         入段前 → emit break_no_stable,返回 None。
      1. UP:peak = max(peak, close)(更新先于转换判定);阴线(真 close < open)或收跌
         (close < close[i-1])→ DOWN,trough = close,count = 0。
      2. DOWN:close < trough(严格)→ 刷新 trough、count 清零;否则 close > trough + k·vol(i)
         → 回 UP(反弹不判死,等下一轮回踩;vol NaN 时该臂降级不触发);否则 count += 1,
         count ≥ K → STABLE,enter = i(第 K 根不刷新根本身)。
      3. STABLE:close > trough + k·vol(i) **且** close > peak → (enter, i-1, 'rise');
         close < trough → (enter, i-1, 'weak')。两者都终止。
    预算扫满仍 STABLE → (enter, end, 'timeout')(含末根);未入段 → emit budget_no_stable,None。
    全部数值比较用 closes/opens 所代表的 measure 列;阴线臂用 real_closes(None 时退回 closes)。
    全部严格不等式(等值不触发)。debug_break:confirm@enter、end@收口根(埋在判据现场)。
    rise / weak / timeout 收口不 emit gate。
    vol NaN 时 rise 臂整体不成立(`and` 语义,`v is not None` 为假即短路),该段只能走
    weak / break / timeout。
    """
    n = len(closes)
    end = min(bo_idx + max_span, n - 1)
    if end <= bo_idx:
        return None   # 空扫描(bo 已在数据末尾,一根都没扫);不 emit gate(与边界不启动同精神)
    state = 'UP'
    peak = float(closes[bo_idx])
    trough = float('inf')
    cnt = 0
    gbot = float(global_bottom)
    enter = -1

    def vol_at(i: int) -> Optional[float]:
        v = float(vol[i])
        return v if v == v else None          # NaN → None(反弹臂降级)

    for i in range(bo_idx + 1, end + 1):
        c = float(closes[i])
        # ══ 0 全局退出(最高优先)══
        if c < gbot:
            if state == 'STABLE':
                _emit_tb_gate(bo_idx, i, 'break_truncate',
                              MeasuredKindAware(kind='anchor_delta', value=c - gbot, label='破位差'),
                              0.0, vol_window, on_gate, op='>=', threshold_param=None)
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'break')
            _emit_tb_gate(bo_idx, i, 'break_no_stable',
                          MeasuredKindAware(kind='anchor_delta', value=c - gbot, label='破位差'),
                          0.0, vol_window, on_gate, op='>=', threshold_param=None)
            return None
        # ══ 1 UP ══
        if state == 'UP':
            if c > peak:
                peak = c
            red = (float(real_closes[i]) if real_closes is not None else c) < float(opens[i])
            if red or c < float(closes[i - 1]):
                state, trough, cnt = 'DOWN', c, 0
        # ══ 2 DOWN ══
        elif state == 'DOWN':
            v = vol_at(i)
            if c < trough:
                trough, cnt = c, 0
            elif v is not None and c > trough + max_rise_k * v:
                state = 'UP'
            else:
                cnt += 1
                if cnt >= stop_confirm_bars:
                    state, enter = 'STABLE', i
                    debug_break(i, anchor_kind='confirm')
        # ══ 3 STABLE ══
        else:
            v = vol_at(i)
            if (v is not None and c > trough + max_rise_k * v) and c > peak:
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'rise')
            if c < trough:
                debug_break(i - 1, anchor_kind='end')
                return FirstSegment(enter, i - 1, 'weak')
    if state == 'STABLE':
        debug_break(end, anchor_kind='end')
        return FirstSegment(enter, end, 'timeout')
    _emit_tb_gate(bo_idx, end, 'budget_no_stable',
                  MeasuredKindAware(kind='count', value=max_span, label='max_span 扫满(未入段)'),
                  max_span, vol_window, on_gate)
    return None


@dataclass(frozen=True)
class ThrowbackEventV1(Event):
    """突破后可执行整理买窗事件(首段即停)。span=[enter, exit];confirm_idx = start_idx
    (确认型:企稳在 enter 根已成立,砍掉 end 仍可判)。

    outcome = 窗口关闭原因,四值 ∈ _TB_OUTCOMES:
    - "rise":   close > trough + k·vol 且 close > peak → 涨前一根收窗(成功脱离);
    - "weak":   close < trough → 企稳被跌破前一根收窗;
    - "break":  close < global_bottom(burst span 内最低)→ 破位前一根收窗(事件仍产);
    - "timeout": 预算 max_span 扫满仍在段内 → 末根收窗(含末根)。
    事件存在 ⟺ 首次 DOWN→STABLE 发生;入段前破线 / 预算尽未入段不产。

    输出字段(where 可引用):
    - anchor_bo_id:  本实例来源 bo(burst 末 bo)的 instance_id;
    - outcome:       上述四值;
    - max_day_drop:  资格型原始量——回踩段 [bo 后首根阴线或收跌, enter] 内单日最大跌幅
                     (pct;无收跌日 0.0;无前瞻)。阈值由 app where 表达(bb_v1 day_drop 闸)。
    """
    anchor_bo_id: str = ""
    outcome: str = "rise"
    max_day_drop: float = 0.0


class ThrowbackDetectorV1:
    """派生 detector:消费 burst 流,每 burst 一台首段即停状态机,产扁平事件。

    参数(5 个,全部几何/口径参数;资格型门槛不在此):
      max_rise_k=1.5      反弹/脱离阈值,vol(i) 倍数;DOWN→UP 反弹臂与 STABLE rise 出口共用
      stop_confirm_bars=1 K = 不刷新根数,enter = 第 K 根不刷新根本身
      vol_window=14       median TR 滚动窗(即时取 i-1;非 Wilder ATR)
      max_span=20         全局预算,扫描 [bo+1, bo+max_span];与 app edge max_gap 共用 SSoT
      measure='close'     全部数值比较口径(阴线臂恒 close/open)
    global_bottom = burst span [start_idx, end_idx] 内 measure 最小值(固定,不再可选)。
    核心判据见 run_first_segment。多源 L2+ detector(detect(self, burst_stream, df) 双参,
    走 run() 变参透传);输出按 (end_idx, start_idx) 升序(run() 升序不变式);同窗口多 bo
    各产一条(实例流语义,各带单来源 anchor_bo_id)。vol 与 measure 列全程一次预计算。
    """
    has_debug_hooks: ClassVar[bool] = True

    event_cls = ThrowbackEventV1
    on_gate = None   # Detector.on_gate protocol 静态声明;默认 None = 生产路径无开销

    def __init__(self, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                 vol_window: int = 14, max_span: int = 20, measure: str = 'close'):
        if measure not in VALID_MEASURES:
            raise ValueError(f"measure 必须在 {VALID_MEASURES},实际 {measure!r}")
        if stop_confirm_bars < 1:
            raise ValueError(
                f"stop_confirm_bars 必须 >= 1,实际 {stop_confirm_bars!r};"
                "cnt 在第一根不刷新根即变 1,K=0 与 K=1 行为完全等价(退化区间无独立语义)")
        self._kw = dict(max_rise_k=max_rise_k, stop_confirm_bars=stop_confirm_bars,
                        vol_window=vol_window, max_span=max_span, measure=measure)

    def detect(self, burst_stream: Iterable[BurstEvent], df: pd.DataFrame) -> Iterator[ThrowbackEventV1]:
        events: List[ThrowbackEventV1] = []
        vol = calculate_tr_median(df['high'], df['low'], df['close'],
                                  self._kw['vol_window']).values
        measure = self._kw['measure']
        closes = measure_series(df, measure).values
        opens = df['open'].values
        real_closes = df['close'].values
        for burst in burst_stream:
            last_bo = burst.members[-1]
            bo = last_bo.end_idx
            if bo < 1 or bo >= len(df):
                continue                            # 边界不启动:不打 entry 锚(锚 bar 越界/attempt 不成立)
            gbot = min(measure_at(df, i, measure)
                       for i in range(burst.start_idx, burst.end_idx + 1))
            debug_break(bo, anchor_kind='entry')   # attempt 入口(每 burst 一次;成功=entry→confirm→end,失败=entry→gate 守恒)
            seg = run_first_segment(
                closes, opens, bo, float(gbot), vol,
                max_rise_k=self._kw['max_rise_k'],
                stop_confirm_bars=self._kw['stop_confirm_bars'],
                max_span=self._kw['max_span'],
                on_gate=self.on_gate, vol_window=self._kw['vol_window'],
                real_closes=real_closes)
            if seg is None:
                continue
            events.append(ThrowbackEventV1(
                start_idx=seg.enter, end_idx=seg.exit,
                confirm_idx=seg.enter,
                anchor_bo_id=last_bo.instance_id,
                outcome=seg.outcome,
                max_day_drop=_revert_max_day_drop(df, bo, seg.enter)))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # run() 要 end 升序
        yield from events
