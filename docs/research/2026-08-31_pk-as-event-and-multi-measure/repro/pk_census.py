"""arch 临时实证:统计一个扫描窗内 peak 的登记数 / 被突破数 / 永不被突破数。
用途:回答「pk 成 event 后灰层 marker 密度」与「当前有多少 peak 结构性不可见」。
不修改任何库代码,只做子类 instrument。
"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"

BO_KW = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
             exceed_threshold=0.003, peak_supersede_threshold=0.01,
             vol_baseline_period=63, peak_measure="high")


class Census(BODetector):
    def detect(self, df):
        self.registered = []      # (pk_id, index, confirm_i)
        return super().detect(df)

    def _detect_peak_in_window(self, df, current_idx):
        before = len(self._active_peaks)
        prev_ids = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        for p in self._active_peaks:
            if p.pk_id not in prev_ids:
                self.registered.append((p.pk_id, p.index, current_idx))


def census(df, breakout_measure):
    det = Census(breakout_measure=breakout_measure, **BO_KW)
    evs = list(run(det, df))
    broken = set()
    for e in evs:
        broken.update(e.broken_peak_ids)
    reg = det.registered
    return dict(n_bars=len(df), n_bo=len(evs), n_pk=len(reg),
                n_pk_broken=len(broken), n_pk_never=len(reg) - len(broken))


def main():
    random.seed(7)
    files = sorted(PKL.glob("*.pkl"))
    sample = random.sample(files, 300)
    rows = []
    for f in sample:
        try:
            df = pd.read_pickle(f)
            win = slice_window(df, START, END)
            if win is None or len(win) < 250:
                continue
            win = win.reset_index(drop=True)
            r_close = census(win, "close")
            r_high = census(win, "high")
            rows.append(dict(sym=f.stem, bars=r_close["n_bars"],
                             pk=r_close["n_pk"],
                             bo_close=r_close["n_bo"], never_close=r_close["n_pk_never"],
                             bo_high=r_high["n_bo"], never_high=r_high["n_pk_never"]))
        except Exception as ex:
            continue
    d = pd.DataFrame(rows)
    print("N symbols:", len(d))
    print(d[["bars", "pk", "bo_close", "never_close", "bo_high", "never_high"]].describe(
        percentiles=[.1, .25, .5, .75, .9, .99]).round(2).to_string())
    print()
    print("pk 总数:", int(d.pk.sum()),
          " | close 口径永不被突破:", int(d.never_close.sum()),
          f"({d.never_close.sum()/d.pk.sum():.1%})",
          " | high 口径永不被突破:", int(d.never_high.sum()),
          f"({d.never_high.sum()/d.pk.sum():.1%})")
    print("每股每窗中位数: pk=%.0f  bo_close=%.0f  bo_high=%.0f" %
          (d.pk.median(), d.bo_close.median(), d.bo_high.median()))


if __name__ == "__main__":
    main()
