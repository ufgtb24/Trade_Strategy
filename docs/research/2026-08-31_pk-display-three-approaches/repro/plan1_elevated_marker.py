"""现状 referenced_points 画的是 elevation 后的 price(不是峰那根的真实价)吗?量之。

referenced_points = (p.index, p.price, f"pk{id}");p.price 在小幅突破后被抬升。
于是卫星 marker 的 y 坐标可能高于 peak bar 上的任何真实价格。
方案①(pk 流)画的是登记价(未抬升) ⇒ 这里的差 = 换方案后卫星位置的位移。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))

from path2.atoms.breakout import BODetector          # noqa: E402
from path2.calc.measure import measure_series        # noqa: E402
from path2_web.data import slice_window              # noqa: E402

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")


def main(n=60, pm="high", bm="close"):
    files = sorted(PKL.glob("*.pkl"))
    random.Random(99).shuffle(files)
    tot = raised = 0
    ratios = []
    done = 0
    for f in files:
        if done >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            w = slice_window(raw, "2021-01-01", "2026-03-08")
        except Exception:
            continue
        if len(w) < 400:
            continue
        done += 1
        det = BODetector(total_window=20, min_side_bars=6, min_relative_height=0.2,
                         exceed_threshold=0.003, peak_supersede_threshold=0.01,
                         vol_baseline_period=63, peak_measure=pm, breakout_measure=bm)
        ms = measure_series(w, pm)
        for ev in det.detect(w):
            for idx, price, _lab in ev.referenced_points:
                tot += 1
                true_p = float(ms.iloc[idx])
                if price > true_p * (1 + 1e-9):
                    raised += 1
                    ratios.append(price / true_p - 1)
    r = np.array(ratios) if ratios else np.array([0.0])
    print(f"股票数={done} peak={pm} breakout={bm}")
    print(f"referenced_points 总点数 = {tot};y 坐标高于该 bar 真实 {pm} 价的 = {raised} "
          f"({100*raised/max(1,tot):.1f}%)")
    print(f"抬升幅度(相对真实价): p50={np.percentile(r,50)*100:.2f}% "
          f"p95={np.percentile(r,95)*100:.2f}% max={r.max()*100:.2f}%")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
