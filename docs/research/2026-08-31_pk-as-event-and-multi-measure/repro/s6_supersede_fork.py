"""S6: 「supersede 跨集合」这条设计岔路的实证 —— 跨集合会不会把 close_pk 吃光?

peak-peak supersede 规则(breakout.py:534-539):新 peak 的价高出旧 peak >1%
(peak_supersede_threshold)时,旧 peak 被淘汰。恒等式 max(high) >= max(close) ⟹
同一窗口的 high_pk 价位恒 >= close_pk 价位。所以若两套 peak 共用一个 active 集合,
high_pk 会系统性地淘汰 close_pk —— 多 measure 功能会大面积 no-op。

量两件事:
  (a) 同一 bar 上都被登记时,P(price_high > price_close * 1.01)
  (b) 把两套登记流按登记时刻合并进一个 active 集合、只施 peak-peak supersede 规则,
      统计各 measure 的存活比例(忽略突破移除,是保守上界)
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector          # noqa: E402
from path2_web.data import slice_window              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
SUP = 0.01      # peak_supersede_threshold (bb_v1 params.yaml)

BO_BASE = dict(
    total_window=20, min_side_bars=6, min_relative_height=0.2,
    exceed_threshold=0.003, peak_supersede_threshold=SUP,
    vol_baseline_period=63, breakout_measure="close",
)


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
            p = self._active_peaks[-1]
            self.registered.append((current_idx, p.index, p.price))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    ratios = []
    surv = {"high": [0, 0], "close": [0, 0]}     # [存活, 总数]
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
        if len(win) < 300:
            continue
        try:
            dh = RecordingBO(peak_measure="high", **BO_BASE)
            list(dh.detect(win))
            dc = RecordingBO(peak_measure="close", **BO_BASE)
            list(dc.detect(win))
        except Exception:
            continue
        done += 1

        ph = {idx: pr for _, idx, pr in dh.registered}
        pc = {idx: pr for _, idx, pr in dc.registered}
        for b in set(ph) & set(pc):
            if pc[b] > 0:
                ratios.append(ph[b] / pc[b])

        # (b) 合并进单一 active 集合,只施 peak-peak supersede
        stream = ([(rb, "high", idx, pr) for rb, idx, pr in dh.registered] +
                  [(rb, "close", idx, pr) for rb, idx, pr in dc.registered])
        stream.sort(key=lambda x: (x[0], 0 if x[1] == "close" else 1))  # 同步登记时 high 后到
        active = []
        killed = {"high": 0, "close": 0}
        total = {"high": 0, "close": 0}
        for rb, m, idx, pr in stream:
            total[m] += 1
            keep = []
            for om, oidx, opr in active:
                if (pr - opr) / opr < SUP:
                    keep.append((om, oidx, opr))
                else:
                    killed[om] += 1
            active = keep + [(m, idx, pr)]
        for m in ("high", "close"):
            surv[m][0] += total[m] - killed[m]
            surv[m][1] += total[m]

    r = np.array(ratios)
    print(f"样本股票数 = {done}  窗口 {START}~{END}  supersede 阈值 = {SUP}")
    print(f"(a) 同 bar 双登记 n={len(r)}  "
          f"price_high/price_close: median={np.median(r):.4f} mean={r.mean():.4f}  "
          f"P(ratio>1+{SUP})={np.mean(r > 1 + SUP):.4f}")
    print("(b) 单一 active 集合 + 跨集合 peak-peak supersede(忽略突破移除,存活率上界):")
    for m in ("high", "close"):
        k, t = surv[m]
        print(f"    {m:6s} 登记 {t:6d} 存活 {k:6d}  存活率={k / max(1, t):.4f}")


if __name__ == "__main__":
    main()
