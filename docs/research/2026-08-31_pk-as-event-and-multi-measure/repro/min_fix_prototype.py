"""skeptic 最小修复原型:验证 no_active_peak_broken 补 threshold + 活跃 peak 列表后,
诊断侧栏能否直接回答用户的原始困惑(「129 是不是 peak / 差多少」)。

不改生产代码:用子类在外部复刻补全后的 gate 载荷,打印 FailedAttemptsCard 会渲染成什么。
"""
import sys, os
import pandas as pd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from path2.atoms.breakout import BODetector
from path2.calc.measure import measure_at
from path2_web.data import slice_window

KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
          exceed_threshold=0.003, peak_supersede_threshold=0.01,
          vol_baseline_period=63, peak_measure="high", breakout_measure="close")


class Enriched(BODetector):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.records = {}

    def emit(self, df, i):
        ev = super().emit(df, i)
        if ev is None and self._active_peaks:
            bp = measure_at(df, i, self.breakout_measure)
            peaks = [(p.index, p.price, p.price * (1 + self.exceed_threshold), p.pk_id)
                     for p in self._active_peaks]
            binding = min(t for _, _, t, _ in peaks)   # 通过条件是 ∃ → 卡住的是最易过的门槛
            self.records[i] = (bp, binding, peaks)
        return ev


def main():
    df = pd.read_pickle("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/TRON.pkl")
    win = slice_window(df, "2024-09-19", "2026-03-08").reset_index(drop=True)
    d = Enriched(**KW)
    list(d.detect(win))
    print("诊断侧栏(FailedAttemptsCard)在补全后会渲染成 —— bar 136~154(pk6 存活区间):\n")
    for i in range(136, 155):
        if i not in d.records:
            print(f"  bar {i:3d}: (当根有突破,无 gate)")
            continue
        bp, binding, peaks = d.records[i]
        t0 = f"突破价 {bp:.5f} > {binding:.5f} (exceed_threshold) ✗"
        lst = "; ".join(f"pk{pid}@{idx}门槛{thr:.5f}" for idx, _, thr, pid in peaks)
        print(f"  bar {i:3d}: [Tier0] {t0}")
        print(f"            [Tier1] 活跃peak: {lst}")
    bp, binding, peaks = d.records[147]
    pk6 = [p for p in peaks if p[3] == 6][0]
    print(f"\n用户原始困惑的直答(bar 147):129 是 peak(pk6),门槛 {pk6[2]:.5f},"
          f"当日 close {bp:.5f},差 {(pk6[2]-bp)/bp*100:.1f}%")


main()
