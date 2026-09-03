"""S9: 回应 skeptic 的两个补充检查。

(1) `body_top` 作为「算子对照」的强度：用与 close-vs-high 完全同一把尺子，量
    body_top-vs-high 的 peak bar 重合（Jaccard）与位移分布。
    判读:若 Jaccard 显著高于 close-vs-high 的 0.308 ⟹ body_top 只是弱算子扰动,
    「三者边际不可区分」的说服力打折;若接近 ⟹ 同强度对照,该句硬起来。

(2) 邻近去重的单链聚类会传递(1-6-12 连成一簇),簇跨度可能远超 min_side_bars。
    报簇跨度分布(max / p95),若出现跨度 20+ 的长链,「同一个顶」的口径被拉过头。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector          # noqa: E402
from path2_web.data import slice_window              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"      # 与 S1 同窗,数字直接可比
NBHD_GAP = 6                                  # = bb_v1 min_side_bars

BO_BASE = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
               exceed_threshold=0.003, peak_supersede_threshold=0.01,
               vol_baseline_period=63, breakout_measure="close")


class RecordingBO(BODetector):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.registered = []

    def detect(self, df):
        self.registered = []
        yield from super().detect(df)

    def _detect_peak_in_window(self, df, current_idx):
        before = self._peak_id_counter
        super()._detect_peak_in_window(df, current_idx)
        if self._peak_id_counter > before:
            self.registered.append(self._active_peaks[-1].index)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    pair_tot = {p: [0, 0, 0] for p in [("high", "close"), ("high", "body_top"),
                                       ("close", "body_top")]}   # [A, B, 交集]
    disp = {p: [] for p in pair_tot}          # B 独有 → 最近 A 的 bar 距离
    spans_hc, spans_hb = [], []               # 单链簇跨度(被突破 peak bar)
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
        if len(win) < 120:
            continue
        try:
            S, BRK = {}, {}
            for m in ("high", "close", "body_top"):
                det = RecordingBO(peak_measure=m, **BO_BASE)
                evs = list(det.detect(win))
                S[m] = set(det.registered)
                BRK[m] = {rp[0] for e in evs for rp in e.referenced_points}
        except Exception:
            continue
        done += 1

        for (a, b) in pair_tot:
            pair_tot[(a, b)][0] += len(S[a])
            pair_tot[(a, b)][1] += len(S[b])
            pair_tot[(a, b)][2] += len(S[a] & S[b])
            for x in S[b] - S[a]:
                if S[a]:
                    disp[(a, b)].append(min(abs(x - y) for y in S[a]))

        for tag, bars in (("hc", BRK["high"] | BRK["close"]),
                          ("hb", BRK["high"] | BRK["body_top"])):
            bs = sorted(bars)
            if not bs:
                continue
            start = prev = bs[0]
            for x in bs[1:]:
                if x - prev > NBHD_GAP:
                    (spans_hc if tag == "hc" else spans_hb).append(prev - start)
                    start = x
                prev = x
            (spans_hc if tag == "hc" else spans_hb).append(prev - start)

    print(f"样本股票数 = {done}  窗口 {START}~{END}（与 S1 同窗，数字直接可比）\n")
    print("(1) peak 登记 bar 集合的重合与位移")
    print(f"  {'对照':22s}{'|A|':>7s}{'|B|':>7s}{'交集':>7s}{'Jaccard':>9s}"
          f"{'位移中位':>9s}{'P(<=3)':>8s}")
    for (a, b), (na, nb, inter) in pair_tot.items():
        dd = np.array(disp[(a, b)], dtype=float)
        j = inter / max(1, na + nb - inter)
        print(f"  {a:>8s} vs {b:<10s}{na:7d}{nb:7d}{inter:7d}{j:9.4f}"
              f"{(np.median(dd) if len(dd) else float('nan')):9.1f}"
              f"{(np.mean(dd <= 3) if len(dd) else float('nan')):8.3f}")

    print(f"\n(2) 邻近去重单链簇跨度分布(gap<={NBHD_GAP} 归一簇，跨度 = 簇内 max bar − min bar)")
    for tag, arr in (("high∪close(实际用的)", spans_hc), ("high∪body_top", spans_hb)):
        a = np.array(arr, dtype=float)
        if not len(a):
            continue
        print(f"  {tag:22s} n={len(a):6d} 中位={np.median(a):.1f} "
              f"p95={np.percentile(a,95):.1f} max={a.max():.0f} "
              f"P(跨度>{NBHD_GAP})={np.mean(a>NBHD_GAP):.3f} "
              f"P(跨度>=20)={np.mean(a>=20):.4f} 单元素簇占比={np.mean(a==0):.3f}")


if __name__ == "__main__":
    main()
