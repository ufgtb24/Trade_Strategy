"""arch:bo 能否在峰的【登记当根】就突破它 —— 决定 K7「按距离去重」是否需要 tie-break。

背景:K7 = satelliteData 按 barIdx 去重、保留 |owner.start_idx - barIdx| 最小者。
skeptic 论证「pk 的距离恒 < bo 的距离」;本脚本检验取等是否可达。
机制:BODetector.emit() 步骤1 先 _detect_peak_in_window(df,i),步骤2 才遍历
_active_peaks 判突破 —— 刚在第 i 根登记的峰当根就在 active 集里,当根即可被突破。
"""
import sys, random, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
          exceed_threshold=0.003, peak_supersede_threshold=0.01,
          vol_baseline_period=63, peak_measure="high")


class Census(BODetector):
    """记录每个 pk_id 的登记 bar。"""
    def detect(self, df):
        self.reg = {}
        return super().detect(df)

    def _detect_peak_in_window(self, df, i):
        prev = {id(p) for p in self._active_peaks}
        super()._detect_peak_in_window(df, i)
        for p in self._active_peaks:
            if id(p) not in prev:
                self.reg[p.pk_id] = i


def main():
    random.seed(5)
    tot = same = 0
    lag = []
    for bm in ("close", "high"):
        for f in random.sample(sorted(PKL.glob("*.pkl")), 150):
            try:
                df = pd.read_pickle(f)
                w = slice_window(df, "2024-09-19", "2026-03-08")
                if w is None or len(w) < 250:
                    continue
                w = w.reset_index(drop=True)
            except Exception:
                continue
            d = Census(breakout_measure=bm, **KW)
            for e in run(d, w):
                for pid in e.broken_peak_ids:
                    r = d.reg.get(pid)
                    if r is None:
                        continue
                    tot += 1
                    lag.append(e.start_idx - r)
                    if e.start_idx == r:
                        same += 1
    print(f"(bo, 被突破 peak) 配对数: {tot}")
    print(f"  bo 落在该峰【登记当根】: {same}  ({same / max(1, tot):.2%})  ← 平局率")
    s = pd.Series(lag)
    print("  bo_bar - 登记bar 分布:",
          dict(s.describe(percentiles=[.01, .5, .99]).round(2)))
    print(f"  最小值 = {int(s.min())} (0 即取等; <0 应不可能)")


if __name__ == "__main__":
    main()
