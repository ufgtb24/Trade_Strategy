"""skeptic 独立探针:high-peak vs close-peak 的 peak 集合/bo 集合重叠度。

不改代码库,只用公开 API + 记录 detector 内部登记事件。
输出:每票的 peak 登记数、bar 重合率、bo 集合差集大小。
"""
import sys, glob, os
import pandas as pd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from path2.atoms.breakout import BODetector
from path2_web.data import slice_window

PKL_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"

BO_KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
             exceed_threshold=0.003, peak_supersede_threshold=0.01,
             vol_baseline_period=63)


class Probe(BODetector):
    """记录 peak 登记(bar_idx, price, 登记 bar)与死亡原因。"""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.registered = []      # (peak_bar, price, register_bar)
        self.elevated = []        # (peak_bar, old_price, new_price, bar)
        self.superseded = []      # (peak_bar, cause, bar)

    def _detect_peak_in_window(self, df, current_idx):
        before = {id(p): p for p in self._active_peaks}
        n0 = self._peak_id_counter
        super()._detect_peak_in_window(df, current_idx)
        if self._peak_id_counter > n0:
            p = self._active_peaks[-1]
            self.registered.append((p.index, p.price, current_idx, p.pk_id))
        for oid, p in before.items():
            if oid not in {id(q) for q in self._active_peaks}:
                self.superseded.append((p.index, 'peak_supersede', current_idx))

    def emit(self, df, i):
        snap = {id(p): (p.index, p.price) for p in self._active_peaks}
        ev = super().emit(df, i)
        alive = {id(p) for p in self._active_peaks}
        for oid, (idx, price) in snap.items():
            if oid not in alive:
                self.superseded.append((idx, 'bo_supersede', i))
        for p in self._active_peaks:
            if id(p) in snap and snap[id(p)][1] != p.price:
                self.elevated.append((p.index, snap[id(p)][1], p.price, i))
        return ev


def run(df, peak_measure, breakout_measure):
    d = Probe(peak_measure=peak_measure, breakout_measure=breakout_measure, **BO_KW)
    bos = list(d.detect(df))
    return d, bos


def main():
    syms = sys.argv[1:] if len(sys.argv) > 1 else ["TRON"]
    if syms == ["SAMPLE"]:
        files = sorted(glob.glob(os.path.join(PKL_DIR, "*.pkl")))[:120]
        syms = [os.path.basename(f)[:-4] for f in files]
    rows = []
    for s in syms:
        p = os.path.join(PKL_DIR, f"{s}.pkl")
        if not os.path.exists(p):
            print(f"skip {s}: no pkl"); continue
        df = pd.read_pickle(p)
        try:
            win = slice_window(df, "2024-09-19", "2026-03-08").reset_index(drop=True)
        except Exception as e:
            print(f"skip {s}: {e}"); continue
        if len(win) < 100:
            continue
        dh, boh = run(win, "high", "close")
        dc, boc = run(win, "close", "close")
        ph = {r[0] for r in dh.registered}
        pc = {r[0] for r in dc.registered}
        bh = {e.start_idx for e in boh}
        bc = {e.start_idx for e in boc}
        rows.append(dict(sym=s, n=len(win),
                         pk_high=len(ph), pk_close=len(pc),
                         pk_both=len(ph & pc), pk_union=len(ph | pc),
                         bo_high=len(bh), bo_close=len(bc),
                         bo_both=len(bh & bc), bo_union=len(bh | bc),
                         elev_h=len(dh.elevated), sup_h=len(dh.superseded)))
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    if len(t) <= 12:
        print(t.to_string(index=False))
    print("\n--- 汇总 (n=%d) ---" % len(t))
    print(t[["pk_high","pk_close","pk_both","pk_union","bo_high","bo_close","bo_both","bo_union","elev_h","sup_h"]].sum())
    if t["pk_union"].sum():
        print("peak bar 重合率 = %.3f" % (t["pk_both"].sum()/t["pk_union"].sum()))
    if t["bo_union"].sum():
        print("bo bar 重合率   = %.3f" % (t["bo_both"].sum()/t["bo_union"].sum()))

main()
