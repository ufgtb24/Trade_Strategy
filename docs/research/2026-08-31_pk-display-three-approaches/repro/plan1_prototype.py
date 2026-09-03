"""方案①(consumes_stream)原型:把 BODetector 拆成 纯 peak 域 + 消费 pk 流的 bo 域。

三个被对拍的实现:
  REF   —— 现状 BODetector(耦合)。用 CensusBO 记录登记序列与 bo 序列。
  P1A   —— 方案①-a:PeakRegistrar(纯几何,不含任何突破逻辑)出 pk 流;
           BOConsumer 拿 pk 流,在自己域内**重算** peak-peak supersede(锚 elevated 价)
           + elevation + 突破移除。即"尽最大努力复刻现状"的版本。
  P1C   —— 方案①-c:同上,但 bo 域**不重算** peak-peak supersede(峰一旦登记就一直是
           阻力位,直到被突破移除)。即"朴素解耦"的版本。

本文件只做纯分析用途,不进正式代码路径。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector, Peak          # noqa: E402
from path2.calc.measure import measure_at, measure_series  # noqa: E402
from path2.calc.volume import calculate_vol_ratio          # noqa: E402


# ─────────────────────────── REF:现状(耦合) ───────────────────────────
class CensusBO(BODetector):
    """记录现状实现的登记序列 / bo 序列 / 每 bar 活跃峰快照。"""

    def detect(self, df):
        self.registered = []     # (reg_bar, peak_idx, price@登记, pk_id)
        self.bos = []            # (bo_bar, pk_count, broken_pk_idxs, broken_pk_ids)
        self.active_trace = []   # (bar, tuple(peak_idx))
        for ev in super().detect(df):
            self.bos.append((ev.start_idx, ev.pk_count,
                             tuple(p for p, _, _ in ev.referenced_points),
                             ev.broken_peak_ids))
            yield ev

    def emit(self, df, i):
        ev = super().emit(df, i)
        self.active_trace.append((i, tuple(p.index for p in self._active_peaks)))
        return ev

    def _detect_peak_in_window(self, df, current_idx):
        before = self._peak_id_counter
        super()._detect_peak_in_window(df, current_idx)
        if self._peak_id_counter > before:
            p = self._active_peaks[-1]        # 新峰恒在末尾
            self.registered.append((current_idx, p.index, round(float(p.price), 8), p.pk_id))


# ───────────────────── 方案①:纯 peak 域(不含突破逻辑) ─────────────────────
@dataclass(frozen=True)
class PkEvent:
    """PeakEvent 的原型:点几何(peak bar)+ 登记 bar(bo 域复放时序所必需)。"""
    index: int          # 峰所在 bar(= start_idx = end_idx)
    reg_idx: int        # 登记 bar = 真正可知的那根(因果口径)
    price: float
    relative_height: float
    volume_peak: float
    pk_id: int
    supersede_floor: float   # price/(1+pst):登记时即可算,供 bo 域施 peak-peak supersede


class PeakRegistrar:
    """纯几何 peak 登记器:窗口 argmax + 侧翼 + 相对高度 + 同位去重。

    不含任何突破逻辑。peak-peak supersede 在本域**不影响登记集**(证明见报告),
    故本域是否施 supersede 对 pk 流内容零影响;这里施(锚未抬升价)只为顺带
    产出 display 用的 eaten 判定。
    """

    def __init__(self, total_window, min_side_bars, min_relative_height,
                 peak_supersede_threshold, peak_measure, vol_baseline_period=63, **_ignore):
        self.tw = total_window
        self.msb = min_side_bars
        self.mrh = min_relative_height
        self.pst = peak_supersede_threshold
        self.pm = peak_measure
        self.vbp = vol_baseline_period

    def detect(self, df) -> List[PkEvent]:
        ms = measure_series(df, self.pm)
        lows = df['low']
        vol = calculate_vol_ratio(df['volume'], self.vbp)
        active: List[PkEvent] = []
        out: List[PkEvent] = []
        self.eaten_by: dict = {}          # pk_id → 吃掉它的 pk_id(纯域口径)
        pid = 0
        for i in range(len(df)):
            ws = i - self.tw
            if ws < 0:
                continue
            measures = list(ms.iloc[ws:i])
            mx = max(measures)
            li = measures.index(mx)              # 并列取最左,同现状
            if li < self.msb or li >= len(measures) - self.msb:
                continue
            gi = ws + li
            if any(p.index == gi for p in active):
                continue
            wl = min(lows.iloc[ws:i])
            if wl <= 0:
                continue
            rh = (mx - wl) / wl
            if rh < self.mrh:
                continue
            vp = vol.iloc[gi]
            pe = PkEvent(index=gi, reg_idx=i, price=float(mx), relative_height=float(rh),
                         volume_peak=0.0 if pd.isna(vp) else float(vp), pk_id=pid,
                         supersede_floor=float(mx) / (1 + self.pst))
            pid += 1
            keep = []
            for op in active:
                if (mx - op.price) / op.price < self.pst:
                    keep.append(op)
                else:
                    self.eaten_by[op.pk_id] = pe.pk_id
            active = keep
            active.append(pe)
            out.append(pe)
        self.alive_at_end = {p.pk_id for p in active}
        return out


# ───────────────────── 方案①:bo 域(消费 pk 流) ─────────────────────
class BOConsumer:
    """detect(peaks, df):逐 bar 复放。replicate_supersede=True → 方案①-a;False → ①-c。"""

    def __init__(self, exceed_threshold, peak_supersede_threshold, breakout_measure,
                 peak_measure, replicate_supersede=True, **_ignore):
        self.et = exceed_threshold
        self.pst = peak_supersede_threshold
        self.bm = breakout_measure
        self.pm = peak_measure          # ★ elevation 口径:bo 域仍需 peak_measure
        self.replicate = replicate_supersede

    def detect(self, peaks: List[PkEvent], df):
        by_reg: dict = {}
        for pe in peaks:
            by_reg.setdefault(pe.reg_idx, []).append(pe)
        active: List[Peak] = []
        self.bos = []
        self.active_trace = []
        self.superseded_in_bo = set()
        for i in range(len(df)):
            # 1. 本 bar 登记的新峰(现状:峰检测先跑)
            for pe in by_reg.get(i, []):
                newp = Peak(index=pe.index, price=pe.price, pk_id=pe.pk_id,
                            volume_peak=pe.volume_peak, relative_height=pe.relative_height)
                if self.replicate:
                    keep = []
                    for op in active:
                        # 与现状逐字同式:锚 op.price(可能已被 elevation 抬升)
                        if (pe.price - op.price) / op.price < self.pst:
                            keep.append(op)
                        else:
                            self.superseded_in_bo.add(op.pk_id)
                    active = keep
                active.append(newp)
            # 2. 突破检测(与现状 emit 第 2 段逐字同构)
            bp = measure_at(df, i, self.bm)
            ep = measure_at(df, i, self.pm)
            broken, remaining = [], []
            for peak in active:
                exceed_price = peak.price * (1 + self.et)
                base = peak.original_price if peak.original_price is not None else peak.price
                supersede_price = base * (1 + self.pst)
                if bp > exceed_price:
                    broken.append(peak)
                    if bp > supersede_price:
                        pass                       # 大幅突破:移除
                    else:
                        if ep > peak.price:
                            if peak.original_price is None:
                                peak.original_price = peak.price
                            peak.price = ep
                        remaining.append(peak)
                else:
                    remaining.append(peak)
            active = remaining
            self.active_trace.append((i, tuple(p.index for p in active)))
            if broken:
                self.bos.append((i, len(broken), tuple(p.index for p in broken),
                                 tuple(p.pk_id for p in broken)))
        return self.bos


def run_all(df, replicate=True, **kw):
    """返回 (ref, p1) 两侧的可对拍摘要。"""
    ref = CensusBO(**kw)
    list(ref.detect(df))
    reg = PeakRegistrar(**kw)
    peaks = reg.detect(df)
    con = BOConsumer(replicate_supersede=replicate, **kw)
    con.detect(peaks, df)
    return ref, reg, peaks, con
