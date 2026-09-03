"""参数扫:验证「①a ≡ 现状 ⟺ breakout_measure ⪯ peak_measure」不是参数运气。

四象限 × exceed_threshold{0.003,0.005} × peak_supersede_threshold{0.01,0.03}
× min_relative_height{0.1,0.2} × min_side_bars{5,6},每格 N 只股票。
"""
from __future__ import annotations

import itertools
import pickle
import random
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

from plan1_prototype import CensusBO, PeakRegistrar, BOConsumer   # noqa: E402
from path2_web.data import slice_window                            # noqa: E402

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2022-01-01", "2026-03-08"
ORDER = {"low": 0, "close": 1, "body_top": 2, "high": 3}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    files = sorted(PKL.glob("*.pkl"))
    random.Random(1234).shuffle(files)
    wins = []
    for f in files:
        if len(wins) >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            w = slice_window(raw, START, END)
        except Exception:
            continue
        if len(w) >= 350:
            wins.append((f.stem, w))

    grid = list(itertools.product(
        [("high", "close"), ("high", "high"), ("close", "close"), ("close", "high"),
         ("body_top", "high"), ("high", "body_top"), ("close", "body_top")],
        [0.003, 0.005], [0.01, 0.03], [0.1, 0.2], [5, 6]))
    print(f"格子数={len(grid)} × 股票 {len(wins)}  窗口 {START}~{END}")
    viol_le = viol_gt = ok_le = ok_gt = 0
    bad = []
    for (pm, bm), et, pst, mrh, msb in grid:
        kw = dict(total_window=20, min_side_bars=msb, min_relative_height=mrh,
                  exceed_threshold=et, peak_supersede_threshold=pst,
                  vol_baseline_period=63, peak_measure=pm, breakout_measure=bm)
        le = ORDER[bm] <= ORDER[pm]
        for sym, w in wins:
            ref = CensusBO(**kw)
            list(ref.detect(w))
            peaks = PeakRegistrar(**kw).detect(w)
            a = BOConsumer(replicate_supersede=True, **kw)
            a.detect(peaks, w)
            same = ([(r[1], r[0]) for r in ref.registered] == [(p.index, p.reg_idx) for p in peaks]
                    and [(b[0], b[2]) for b in ref.bos] == [(b[0], b[2]) for b in a.bos])
            if le:
                ok_le += same
                viol_le += (not same)
                if not same and len(bad) < 5:
                    bad.append((sym, pm, bm, et, pst, mrh, msb))
            else:
                ok_gt += same
                viol_gt += (not same)
    print(f"bm ⪯ pm 的格子:逐字相同 {ok_le}, 不同 {viol_le}   ← 预言:不同=0")
    print(f"bm ≻ pm 的格子:逐字相同 {ok_gt}, 不同 {viol_gt}   ← 预言:不同>0")
    for b in bad:
        print("反例:", b)


if __name__ == "__main__":
    main()
