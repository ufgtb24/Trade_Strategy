"""throwback v4:post-burst 三态价格行为状态机(UP/DOWN/STABLE)。

设计 spec:docs/superpowers/specs/2026-08-16-tb-v4-state-machine-design.md(定稿)。
本模块 = 状态机核(纯函数)+ 事件类/detector 装配 + on_gate 接线/debug_break
埋点(Task 4)。

enter 相位(spec 内部矛盾裁定,2026-08-16 实施):spec §2 伪代码把
``count >= K → STABLE`` 写在 ``else: count += 1`` 之前(字面 = 第 K+1 根不刷新
才入段),与 §3「企稳在 enter 根已成立(confirm == enter)」、§8「K = 不刷新
根数」、§11「连续 K 根不刷新转 STABLE 开段」三处明文冲突——按后三者,enter =
第 K 根不刷新根本身(当根计数达标当根入段)。本实现取三处一致口径
(先计数后判定)。
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


class TbV4Seg(NamedTuple):
    """单个企稳段:enter=入段根(第 K 根不刷新),exit=收口根,outcome=关闭方式。"""
    enter: int
    exit: int
    outcome: str


class TbV4MachineResult(NamedTuple):
    """一台状态机(一个 burst)的完整产出。machine_outcome ∈ ('break','budget')。"""
    segments: tuple[TbV4Seg, ...]
    machine_outcome: str


def _emit_tb_gate_v4(bo_idx: int, gate_idx: int, gate_name: str,
                     measured: MeasuredKindAware, threshold,
                     vol_window: int,
                     on_gate: Optional[Callable[[GateFailure], None]],
                     *, op: Optional[str] = None,
                     threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit(避免 3 处埋点重复 boilerplate)。

    从 throwback_v1._emit_tb_gate 逐字复制(仅函数名、vol_window 参数名与
    docstring 不同)。与 t1 模板的口径差异:evaluation_lookback 随 gate_idx 移动
    ((gate_idx - vol_window, gate_idx - 1);t1 固定 (bo_idx - atr_window, bo_idx))。

    t4 gate 名表(整机短路点,spec §7;段级收口一律不 emit):
    - break_no_stable:  全局退出时 0 段
    - break_truncate:   全局退出截断末段(事件仍产)
    - budget_no_stable: 预算扫满 0 段

    TB 是 span 事件,attempt 定义采解读 X 松对齐(spec §2.4.2):
    一台状态机 = 一次 attempt,attempt 起点 = bo_idx + 1,三类整机短路共用
    同一 failure_event_window 公式。
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
        evaluation_lookback=(gate_idx - vol_window, gate_idx - 1),
        symbol=current_symbol.get() or '',
    ))


def enumerate_segments_v4(
    closes: np.ndarray, opens: np.ndarray, bo_idx: int, global_bottom: float,
    vol: np.ndarray, *,
    max_rise_k: float = 1.5, stop_confirm_bars: int = 1, max_span: int = 60,
    on_gate: Optional[Callable] = None, vol_window: int = 14,
    real_closes: Optional[np.ndarray] = None,
) -> TbV4MachineResult:
    """三态状态机(spec §2,检查顺序固定)。

    UP:peak 更新(含触发根)→ 首根阴线或收跌转 DOWN;DOWN:严格新低刷新 trough
    (计数清零)、rise 臂优先(close > trough + max_rise_k·vol(i),vol NaN 降级不
    触发)、本根不刷新即计数且计数达 K 当根入 STABLE(enter=第 K 根不刷新根);
    STABLE:rise 或 close>peak 收段并 ratchet global_bottom=trough,破段底收 weak
    转 DOWN 重滚(re-entry 原生)。任何状态 close < global_bottom 机器终止(段内
    则末段 'break' 截断)。预算 max_span 扫满仍段内 → 'timeout' 收口。全判据无
    前瞻。on_gate 只收三类整机短路点(名表见 _emit_tb_gate_v4 docstring):
    全局退出 0 段 / 全局退出截断末段 / 预算尽 0 段;段级收口(rise/weak/timeout)
    与"机器已完成产出"的退出(段外破线且 ≥1 段、预算尽且已有段)不 emit。
    debug_break 就地埋点(判据执行现场):tb_seg 确认型 start 档=段诞生当根
    (DOWN→STABLE enter)、end 档=段收口根(rise/weak/break 收段 exit=i-1、
    timeout=end);pause 时可见状态机内部变量(state/peak/trough/cnt/gbot),监控
    机器如何运行。容器 tb 端点由子段承担,不独立埋(同 bar 双埋=噪声)。
    vol_window 双重身份:detector 层计算 vol 数组的窗口 + gate 的
    evaluation_lookback 宽度。

    real_closes:阴线臂专用的 K 线真 close 列(spec §5:阴线判定 = close < open,
    K 线形态判据、不随 measure 变)。None = 现行为(用 closes 列判阴线,纯函数层
    向后兼容);非 None 时**仅阴线臂**改用 real_closes[i] < opens[i],其余全部
    比较(收跌臂 closes[i] < closes[i-1] 在内)仍用 measure 列(spec §5「全部
    比较同一 measure」的唯一跨列例外)。detect 恒传 df['close']。
    """
    n = len(closes)
    end = min(bo_idx + max_span, n - 1)
    state = 'UP'
    peak = float(closes[bo_idx])
    trough = float('inf')
    cnt = 0
    gbot = float(global_bottom)
    enter = -1
    segs: list[TbV4Seg] = []

    def vol_at(i: int) -> Optional[float]:
        v = float(vol[i])
        return v if v == v else None          # NaN → None(rise 臂降级)

    for i in range(bo_idx + 1, end + 1):
        c = float(closes[i])
        # ══ 0 全局退出(最高优先)══
        if c < gbot:
            if state == 'STABLE':
                _emit_tb_gate_v4(bo_idx, i, 'break_truncate',
                                 MeasuredKindAware(kind='anchor_delta',
                                                   value=c - gbot,
                                                   label='破位差'),
                                 0.0, vol_window, on_gate,
                                 op='>=', threshold_param=None)
                segs.append(TbV4Seg(enter, i - 1, 'break'))
                debug_break(i - 1, anchor_kind='end')   # break 截断·段收口根
            elif not segs:
                # 段外破线且 0 段 = 整机短路(一台机器零产出)
                _emit_tb_gate_v4(bo_idx, i, 'break_no_stable',
                                 MeasuredKindAware(kind='anchor_delta',
                                                   value=c - gbot,
                                                   label='破位差'),
                                 0.0, vol_window, on_gate,
                                 op='>=', threshold_param=None)
            # 段外破线且已有 ≥1 段:机器已完成产出,非截断 → 不 emit
            return TbV4MachineResult(tuple(segs), 'break')
        # ══ 1 UP ══
        if state == 'UP':
            if c > peak:
                peak = c                       # 更新先于转换判定(peak 含触发根)
            red = (float(real_closes[i]) < float(opens[i])
                   if real_closes is not None
                   else c < float(opens[i]))   # 阴线臂:真 close < open(spec §5)
            if red or c < float(closes[i - 1]):
                state, trough, cnt = 'DOWN', c, 0
        # ══ 2 DOWN ══
        elif state == 'DOWN':
            v = vol_at(i)
            if c < trough:                     # 严格小于才叫刷新(等值=不刷新)
                trough, cnt = c, 0
            elif v is not None and c > trough + max_rise_k * v:
                state = 'UP'                   # rise 臂优先于 stable 臂(V 反转不产段)
            else:
                cnt += 1                       # 本根计一根不刷新;含本根达 K 即入段
                if cnt >= stop_confirm_bars:
                    state, enter = 'STABLE', i  # trough 即段底,无需冻结变量
                    debug_break(i, anchor_kind='start')   # tb_seg 确认型·start 档=段诞生当根(原 confirm)
        # ══ 3 STABLE ══
        else:
            v = vol_at(i)
            if (v is not None and c > trough + max_rise_k * v) and (c > peak):
                gbot = trough                  # ratchet(INV-1:gbot ≤ trough 恒成立)
                segs.append(TbV4Seg(enter, i - 1, 'rise'))
                debug_break(i - 1, anchor_kind='end')   # rise 收段·段收口根
                state = 'UP'
                if c > peak:
                    peak = c
            elif c < trough:
                segs.append(TbV4Seg(enter, i - 1, 'weak'))
                debug_break(i - 1, anchor_kind='end')   # weak 收段·段收口根
                state, trough, cnt = 'DOWN', c, 0
    if state == 'STABLE':
        segs.append(TbV4Seg(enter, end, 'timeout'))   # 预算类含末根
        debug_break(end, anchor_kind='end')   # timeout 收口·段收口根
    if not segs:
        # 预算尽 0 段 = 整机短路(state==STABLE 时上面必已 append timeout 段)
        _emit_tb_gate_v4(bo_idx, end, 'budget_no_stable',
                         MeasuredKindAware(kind='count', value=max_span,
                                           label='max_span 扫满(无段)'),
                         max_span, vol_window, on_gate)
    return TbV4MachineResult(tuple(segs), 'budget')


# ── 事件类 + detector 装配(Task 3;spec §3/§4)──


@dataclass(frozen=True)
class ThrowbackSegmentV4(Event):
    """企稳段。span=[enter, exit];confirm=enter(确认型);段内每 bar 是 eval 买点样本。
    outcome ∈ ('rise','weak','break','timeout');break 仅末段。"""
    anchor_bo_id: str = ""
    outcome: str = "weak"


@dataclass(frozen=True)
class ThrowbackEventV4(Event):
    """一 burst 的企稳段容器(确认型:confirm=start=首段 enter)。outcome=末段关闭方式;
    machine_outcome ∈ ('break','budget') = 整机死法(与末段 outcome 独立,B1)。"""
    segments: tuple[ThrowbackSegmentV4, ...] = ()
    anchor_bo_id: str = ""
    outcome: str = "weak"
    machine_outcome: str = "break"

    def child_slots(self):
        return {"segments": self.segments}


class ThrowbackDetectorV4:
    """派生 detector:消费 burst 流,每 burst 一台三态状态机,产容器事件。

    一句话定位(spec §11③):post-burst 回踩跟踪状态机——DOWN 找底、STABLE 产
    企稳买点段、UP 等下一轮回踩;修复 rise-before-confirm 召回杀手(rise 不再
    终止机器)且 re-entry 为原生属性。

    核心判据见 enumerate_segments_v4 docstring(spec §2)。vol 全程一次预计算
    (calculate_tr_median,即时取 i-1);数值比较用 measure(默认 close),阴线臂
    恒用 close/open(K 线形态判据);anchor 三模式:span_min(burst span 全 bar
    measure 最小,默认)/ min_bo(各 bo 当根取 min)/ last_bo(末 bo 上一根)。
    多源 L2+(detect(burst_stream, df));输出按 (end_idx, start_idx) 升序;
    前缀族同 cluster 多 burst → 多容器各带单来源 anchor_bo_id,不去重。
    """
    has_debug_hooks: ClassVar[bool] = True
    event_cls = ThrowbackEventV4
    on_gate = None

    def __init__(self, *, max_rise_k: float = 1.5, stop_confirm_bars: int = 1,
                 vol_window: int = 14, anchor_mode: str = 'span_min',
                 max_span: int = 60, measure: str = 'close'):
        if measure not in VALID_MEASURES:
            raise ValueError(f"measure 必须在 {VALID_MEASURES},实际 {measure!r}")
        if anchor_mode not in ('last_bo', 'min_bo', 'span_min'):
            raise ValueError(f"anchor_mode 必须是 'last_bo'|'min_bo'|'span_min',实际 {anchor_mode!r}")
        self._kw = dict(max_rise_k=max_rise_k, stop_confirm_bars=stop_confirm_bars,
                        vol_window=vol_window, anchor_mode=anchor_mode,
                        max_span=max_span, measure=measure)

    def detect(self, burst_stream: Iterable[BurstEvent],
               df: pd.DataFrame) -> Iterator[ThrowbackEventV4]:
        events: List[ThrowbackEventV4] = []
        # vol 全程一次预计算;measure 列与 anchor 定价同口径(measure_series,
        # 阴线臂在状态机内恒用 close/open,不随 measure 变)
        vol = calculate_tr_median(df['high'], df['low'], df['close'],
                                  self._kw['vol_window']).values
        measure = self._kw['measure']
        measure_col = measure_series(df, measure)
        for burst in burst_stream:
            last_bo = burst.members[-1]
            bo = last_bo.end_idx
            debug_break(bo, anchor_kind='entry')   # tb 容器 entry 档(attempt 入口;端点由子段承担)
            if bo < 1 or bo >= len(df):
                continue
            mode = self._kw['anchor_mode']
            if mode == 'last_bo':
                gbot = measure_at(df, bo - 1, measure)
            elif mode == 'min_bo':
                gbot = min(measure_at(df, b.end_idx, measure) for b in burst.members)
            else:  # span_min
                gbot = min(measure_at(df, i, measure)
                           for i in range(burst.start_idx, burst.end_idx + 1))
            res = enumerate_segments_v4(
                measure_col.values, df['open'].values, bo, float(gbot), vol,
                max_rise_k=self._kw['max_rise_k'],
                stop_confirm_bars=self._kw['stop_confirm_bars'],
                max_span=self._kw['max_span'],
                on_gate=self.on_gate, vol_window=self._kw['vol_window'],
                real_closes=df['close'].values)
            if not res.segments:
                continue
            src_id = last_bo.instance_id
            segs = tuple(
                ThrowbackSegmentV4(start_idx=s.enter, end_idx=s.exit,
                                   confirm_idx=s.enter, anchor_bo_id=src_id,
                                   outcome=s.outcome)
                for s in res.segments)
            events.append(ThrowbackEventV4(
                start_idx=segs[0].start_idx, end_idx=segs[-1].end_idx,
                confirm_idx=segs[0].start_idx, segments=segs,
                anchor_bo_id=src_id, outcome=segs[-1].outcome,
                machine_outcome=res.machine_outcome))
        events.sort(key=lambda e: (e.end_idx, e.start_idx))   # run() 要 end 升序
        yield from events
