"""arch:可分离性在参数网格上的抗打性(preempt skeptic)。
对拍独立 Registrar vs BODetector 内部登记序列,扫 total_window / min_side_bars /
min_relative_height / peak_supersede_threshold / peak_measure / breakout_measure。
"""
import sys, random, warnings, itertools
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


class Census(BODetector):
    def detect(self, df):
        self.registered = []
        return super().detect(df)

    def _detect_peak_in_window(self, df, current_idx):
        prev = {id(p) for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        for p in self._active_peaks:
            if id(p) not in prev:
                self.registered.append((p.index, round(float(p.price), 8), current_idx))


def registrar(df, tw, msb, mrh, pst, pm):
    active, out = [], []
    ms = measure_series(df, pm)
    lows = df['low'].values
    for i in range(len(df)):
        ws = i - tw
        if ws < 0:
            continue
        measures = list(ms.iloc[ws:i])
        mx = max(measures); li = measures.index(mx)
        if li < msb or li >= len(measures) - msb:
            continue
        gi = ws + li
        if any(p.index == gi for p in active):
            continue
        wl = min(lows[ws:i])
        if wl <= 0:
            continue
        rh = (mx - wl) / wl
        if rh < mrh:
            continue
        out.append((gi, round(float(mx), 8), i))
        active = [op for op in active if (mx - op.price) / op.price < pst]
        active.append(Peak(index=gi, price=mx, pk_id=0, volume_peak=0.0, relative_height=rh))
    return out


GRID = [dict(total_window=tw, min_side_bars=msb, min_relative_height=mrh,
             peak_supersede_threshold=pst, peak_measure=pm, breakout_measure=bm)
        for tw, msb in [(10, 2), (20, 6), (40, 6), (60, 20)]
        for mrh in (0.02, 0.2)
        for pst in (0.002, 0.01, 0.05, 0.30)
        for pm in ("high", "close")
        for bm in ("high", "close")]


def main():
    random.seed(11)
    files = sorted(PKL.glob("*.pkl"))
    sample = random.sample(files, 40)
    wins = []
    for f in sample:
        try:
            df = pd.read_pickle(f)
            w = slice_window(df, START, END)
            if w is None or len(w) < 250:
                continue
            wins.append((f.stem, w.reset_index(drop=True)))
        except Exception:
            pass
    n_ok = n_diff = 0
    bad = []
    for kw in GRID:
        for sym, w in wins:
            det = Census(vol_baseline_period=63, exceed_threshold=0.003, **kw)
            list(run(det, w))
            ref = det.registered
            got = registrar(w, kw["total_window"], kw["min_side_bars"],
                            kw["min_relative_height"], kw["peak_supersede_threshold"],
                            kw["peak_measure"])
            if ref == got:
                n_ok += 1
            else:
                n_diff += 1
                if len(bad) < 6:
                    d = [(a, b) for a, b in itertools.zip_longest(ref, got) if a != b][:3]
                    bad.append((sym, kw, len(ref), len(got), d))
    print(f"网格 {len(GRID)} 组参数 × {len(wins)} 股 = {n_ok + n_diff} 次对拍")
    print(f"  逐字相同 {n_ok} | 不同 {n_diff}")
    for b in bad:
        print("DIFF", b[0], b[1], f"len ref={b[2]} got={b[3]}")
        for a, g in b[4]:
            print("    ref:", a, " got:", g)


if __name__ == "__main__":
    main()
