"""display 三态在「现状(耦合)」与「方案①纯 peak 域」下的归属差异,并把差异拆到通道。

对每个 pk(以纯 peak 域的登记集为基准,close/high 象限除外它与现状一致)统计:
  现状口径(=①a,已证逐字等价):broken(被 bo 突破过) / eaten(被后来的峰 supersede,
                                 锚 elevated 价) / alive
  纯域口径:eaten_pure(锚未抬升价,且不知道谁被突破过)

拆分:
  D1 = 纯域判 eaten 但现状判 broken(根因:纯域看不见突破移除)
  D2 = 纯域判 eaten 但现状判 alive 且从未被突破(根因:elevation 锚差 = §2.4 通道)
  D3 = 现状判 eaten 但纯域判 alive(反向,理论上应为 0:纯域杀得更多)
另外单独隔离 §2.4:把 bo 域的 supersede 锚从 elevated 换成 original,看 eaten 集变化。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

from plan1_prototype import PeakRegistrar, BOConsumer, CensusBO   # noqa: E402
from path2.atoms.breakout import Peak                             # noqa: E402
from path2.calc.measure import measure_at                         # noqa: E402
from path2_web.data import slice_window                           # noqa: E402

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
BASE = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
            exceed_threshold=0.003, peak_supersede_threshold=0.01,
            vol_baseline_period=63)


class TracingConsumer(BOConsumer):
    """在 ①a 基础上记录 per-pk 状态;supersede_anchor='elevated'|'original' 切锚。"""

    def __init__(self, *a, supersede_anchor="elevated", **kw):
        super().__init__(*a, **kw)
        self.anchor = supersede_anchor

    def detect(self, peaks, df):
        by_reg = {}
        for pe in peaks:
            by_reg.setdefault(pe.reg_idx, []).append(pe)
        active = []
        self.broken_ids, self.eaten_ids = set(), set()
        self.bo_bars = []
        for i in range(len(df)):
            for pe in by_reg.get(i, []):
                newp = Peak(index=pe.index, price=pe.price, pk_id=pe.pk_id,
                            volume_peak=pe.volume_peak, relative_height=pe.relative_height)
                keep = []
                for op in active:
                    base = op.price if self.anchor == "elevated" else (
                        op.original_price if op.original_price is not None else op.price)
                    if (pe.price - base) / base < self.pst:
                        keep.append(op)
                    else:
                        self.eaten_ids.add(op.pk_id)
                active = keep
                active.append(newp)
            bp = measure_at(df, i, self.bm)
            ep = measure_at(df, i, self.pm)
            broken, remaining = [], []
            for peak in active:
                base = peak.original_price if peak.original_price is not None else peak.price
                if bp > peak.price * (1 + self.et):
                    broken.append(peak)
                    self.broken_ids.add(peak.pk_id)
                    if bp > base * (1 + self.pst):
                        pass
                    else:
                        if ep > peak.price:
                            if peak.original_price is None:
                                peak.original_price = peak.price
                            peak.price = ep
                        remaining.append(peak)
                else:
                    remaining.append(peak)
            active = remaining
            if broken:
                self.bo_bars.append(i)
        self.alive_ids = {p.pk_id for p in active}
        return self.bo_bars


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    pm, bm = sys.argv[2] if len(sys.argv) > 2 else "high", sys.argv[3] if len(sys.argv) > 3 else "close"
    files = sorted(PKL.glob("*.pkl"))
    random.Random(20260831).shuffle(files)
    tot = dict(pk=0, broken=0, eaten=0, alive=0, eaten_pure=0,
               D1=0, D2=0, D3=0, anchor_only=0, bo_break_eatenpure=0)
    done = 0
    for f in files:
        if done >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            win = slice_window(raw, START, END)
        except Exception:
            continue
        if len(win) < 400:
            continue
        done += 1
        kw = dict(BASE, peak_measure=pm, breakout_measure=bm)
        reg = PeakRegistrar(**kw)
        peaks = reg.detect(win)
        cur = TracingConsumer(replicate_supersede=True, supersede_anchor="elevated", **kw)
        cur.detect(peaks, win)
        alt = TracingConsumer(replicate_supersede=True, supersede_anchor="original", **kw)
        alt.detect(peaks, win)

        pure_eaten = set(reg.eaten_by)
        ids = {p.pk_id for p in peaks}
        tot["pk"] += len(ids)
        tot["broken"] += len(cur.broken_ids)
        tot["eaten"] += len(cur.eaten_ids)
        tot["alive"] += len(ids - cur.broken_ids - cur.eaten_ids)
        tot["eaten_pure"] += len(pure_eaten)
        tot["D1"] += len(pure_eaten & cur.broken_ids)
        tot["D2"] += len(pure_eaten - cur.broken_ids - cur.eaten_ids)
        tot["D3"] += len(cur.eaten_ids - pure_eaten)
        tot["anchor_only"] += len(cur.eaten_ids ^ alt.eaten_ids)
        # 用户时序反驳的直接计数:纯域判 eaten 的峰里,有多少在现状里真的先被 bo 突破过
        tot["bo_break_eatenpure"] += len(pure_eaten & cur.broken_ids)

    print(f"股票数={done}  peak_measure={pm} breakout_measure={bm}  窗口 {START}~{END}")
    print(f"pk 总数 = {tot['pk']}")
    print(f"现状三态: broken={tot['broken']} ({100*tot['broken']/tot['pk']:.1f}%)  "
          f"eaten={tot['eaten']} ({100*tot['eaten']/tot['pk']:.1f}%)  "
          f"alive={tot['alive']} ({100*tot['alive']/tot['pk']:.1f}%)")
    print(f"纯 peak 域判 eaten = {tot['eaten_pure']} ({100*tot['eaten_pure']/tot['pk']:.1f}%)")
    print(f"  D1 纯域eaten∩现状broken = {tot['D1']} ({100*tot['D1']/tot['pk']:.1f}% of pk) "
          f"← 纯域看不见突破移除")
    print(f"  D2 纯域eaten∩现状alive且没被突破 = {tot['D2']} ({100*tot['D2']/tot['pk']:.1f}%) "
          f"← elevation 锚差(§2.4 通道)")
    print(f"  D3 现状eaten∩纯域非eaten = {tot['D3']} (应为 0)")
    print(f"隔离 §2.4:同为 bo 域、仅把 supersede 锚 elevated→original,eaten 集对称差 = "
          f"{tot['anchor_only']} ({100*tot['anchor_only']/tot['pk']:.2f}% of pk)")
    print(f"用户时序反驳直查:纯域判 eaten 的峰中,现状里确实先被 bo 突破过的 = "
          f"{tot['bo_break_eatenpure']} —— 方案① 全部保留(①a 与现状 bo 集逐字等价)")


if __name__ == "__main__":
    main()
