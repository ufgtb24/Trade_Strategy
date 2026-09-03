"""arch 临时实证:peak「登记集」是否可从 BODetector 里分离成独立上游流。

假设 H:登记决策 = 纯几何(4 闸) + peak_already_active 去重;而 elevation / supersede
只影响 active 集的存续,不阻止新 peak 登记 ⇒ 一个不含任何突破逻辑的独立 PeakRegistrar
应当产出与 BODetector 逐字相同的登记集(pk_id, index, price@登记, rel_height, confirm bar)。
唯一可能的偏离:BODetector 因突破移除了某 peak 后同一 bar 被重新登记(独立版不会,
因为它的 active 集里那个 peak 还在)。本脚本直接对拍两者。
"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
import pandas as pd
from path2.atoms.breakout import BODetector, Peak
from path2.calc.measure import measure_series
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"
BO_KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
             exceed_threshold=0.003, peak_supersede_threshold=0.01,
             vol_baseline_period=63, peak_measure="high")


class Census(BODetector):
    """记录 BODetector 真实登记序列。"""
    def detect(self, df):
        self.registered = []
        return super().detect(df)

    def _detect_peak_in_window(self, df, current_idx):
        prev = {id(p) for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        for p in self._active_peaks:
            if id(p) not in prev:
                self.registered.append((p.index, round(float(p.price), 8),
                                        round(float(p.relative_height), 8), current_idx))


class Registrar:
    """不含任何突破逻辑的独立 peak 登记器(只吃 df)。"""
    def __init__(self, total_window, min_side_bars, min_relative_height,
                 peak_supersede_threshold, peak_measure, **_ignored):
        self.tw, self.msb, self.mrh = total_window, min_side_bars, min_relative_height
        self.pst, self.pm = peak_supersede_threshold, peak_measure

    def detect(self, df):
        active = []
        out = []
        ms = measure_series(df, self.pm)
        for i in range(len(df)):
            ws = i - self.tw
            if ws < 0:
                continue
            measures = list(ms.iloc[ws:i])
            mx = max(measures)
            li = measures.index(mx)
            if li < self.msb or li >= len(measures) - self.msb:
                continue
            gi = ws + li
            if any(p.index == gi for p in active):
                continue
            wl = min(df['low'].iloc[ws:i])
            if wl <= 0:
                continue
            rh = (mx - wl) / wl
            if rh < self.mrh:
                continue
            p = Peak(index=gi, price=mx, pk_id=len(out), volume_peak=0.0, relative_height=rh)
            out.append((gi, round(float(mx), 8), round(float(rh), 8), i))
            active = [op for op in active if (mx - op.price) / op.price < self.pst]
            active.append(p)
        return out


def main():
    random.seed(7)
    files = sorted(PKL.glob("*.pkl"))
    sample = random.sample(files, 300)
    n_ok = n_diff = n_sym = 0
    diffs = []
    dup_index_syms = 0
    for f in sample:
        try:
            df = pd.read_pickle(f)
            win = slice_window(df, START, END)
            if win is None or len(win) < 250:
                continue
            win = win.reset_index(drop=True)
        except Exception:
            continue
        for bm in ("close", "high"):
            det = Census(breakout_measure=bm, **BO_KW)
            list(run(det, win))
            ref = det.registered
            got = Registrar(**BO_KW).detect(win)
            n_sym += 1
            idxs = [r[0] for r in ref]
            if len(set(idxs)) != len(idxs):
                dup_index_syms += 1
            if ref == got:
                n_ok += 1
            else:
                n_diff += 1
                if len(diffs) < 5:
                    diffs.append((f.stem, bm, ref, got))
    print(f"对拍 {n_sym} 组(股×breakout_measure): 逐字相同 {n_ok}, 不同 {n_diff}")
    print(f"BODetector 内出现同一 bar 被重复登记的组数: {dup_index_syms}")
    for d in diffs:
        print("DIFF", d[0], d[1])
        print("  ref:", d[2][:8])
        print("  got:", d[3][:8])


if __name__ == "__main__":
    main()
