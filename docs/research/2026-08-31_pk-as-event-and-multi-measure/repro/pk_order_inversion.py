"""arch:登记 bar 升序时,峰 bar 是否也升序?(lead 对"第五种写法"的杀手检验;
即便第五写法已被 Event 协议拒绝,该统计仍决定 satellite 点的时序形态)"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
          exceed_threshold=0.003, peak_supersede_threshold=0.01,
          vol_baseline_period=63, peak_measure="high", breakout_measure="close")

class Census(BODetector):
    def detect(self, df):
        self.reg = []
        return super().detect(df)
    def _detect_peak_in_window(self, df, i):
        prev = {id(p) for p in self._active_peaks}
        super()._detect_peak_in_window(df, i)
        for p in self._active_peaks:
            if id(p) not in prev:
                self.reg.append((p.index, i))

random.seed(3)
files = random.sample(sorted(PKL.glob("*.pkl")), 200)
n_sym = n_pk = n_inv = 0; inv_syms = 0; lags = []
for f in files:
    try:
        df = pd.read_pickle(f)
        w = slice_window(df, "2024-09-19", "2026-03-08")
        if w is None or len(w) < 250: continue
        w = w.reset_index(drop=True)
    except Exception: continue
    det = Census(**KW); list(run(det, w))
    reg = det.reg
    n_sym += 1; n_pk += len(reg)
    lags += [ci - pi for pi, ci in reg]
    inv = sum(1 for a, b in zip(reg, reg[1:]) if b[0] <= a[0])
    n_inv += inv
    if inv: inv_syms += 1
print(f"{n_sym} 股 / {n_pk} 个 peak")
print(f"相邻登记对中「峰 bar 未严格递增」的次数: {n_inv}  ({n_inv/max(1,n_pk-n_sym):.1%})，涉及 {inv_syms} 只股")
s = pd.Series(lags)
print("登记滞后 (登记bar - 峰bar) 分布:", dict(s.describe(percentiles=[.5,.9,.99]).round(2)))
