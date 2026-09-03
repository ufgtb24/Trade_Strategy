"""S1: peak_measure=high vs close 的 peak 登记集合 / bo 集合结构对照。

只构造 BODetector 实例传不同参数,不改任何库代码。
RecordingBO 通过 _peak_id_counter 变化捕获"本 bar 新登记的 peak"(新 peak 恒为
_active_peaks 末元素),从而拿到完整登记历史(而非仅存活集合)。

输出: 每股一行统计 + 全样本汇总。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector          # noqa: E402
from path2_web.data import slice_window              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"

# bb_v1 的 bo section(params.yaml 实值)
BO_BASE = dict(
    total_window=20, min_side_bars=6, min_relative_height=0.2,
    exceed_threshold=0.003, peak_supersede_threshold=0.01,
    vol_baseline_period=63, breakout_measure="close",
)


class RecordingBO(BODetector):
    """记录全部被登记过的 peak(index, price, relative_height, pk_id)。"""

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
            self.registered.append(
                dict(reg_bar=current_idx, index=p.index, price=p.price,
                     rel_h=p.relative_height, pk_id=p.pk_id))


DIST_C = []
DIST_H = []


def run_one(df, peak_measure):
    det = RecordingBO(peak_measure=peak_measure, **BO_BASE)
    bos = list(det.detect(df))
    return det.registered, bos


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    rows = []
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
        if len(win) < 120:
            continue
        sym = f.stem
        try:
            reg_h, bos_h = run_one(win, "high")
            reg_c, bos_c = run_one(win, "close")
        except Exception as e:
            print(f"skip {sym}: {e}", file=sys.stderr)
            continue
        done += 1

        bars_h = {r["index"] for r in reg_h}
        bars_c = {r["index"] for r in reg_c}
        bo_h = {e.start_idx for e in bos_h}
        bo_c = {e.start_idx for e in bos_c}

        # 共享 bar 上的价位比
        ph = {r["index"]: r["price"] for r in reg_h}
        pc = {r["index"]: r["price"] for r in reg_c}
        shared = bars_h & bars_c
        ratios = [ph[b] / pc[b] for b in shared if pc[b] > 0]

        # close 独有 peak 距最近 high peak 的 bar 距离
        d_close_only = []
        for b in sorted(bars_c - bars_h):
            if bars_h:
                d_close_only.append(min(abs(b - x) for x in bars_h))

        for b in sorted(bars_c - bars_h):
            if bars_h:
                DIST_C.append(min(abs(b - x) for x in bars_h))
        for b in sorted(bars_h - bars_c):
            if bars_c:
                DIST_H.append(min(abs(b - x) for x in bars_c))
        rows.append(dict(
            symbol=sym, bars=len(win),
            n_pk_high=len(bars_h), n_pk_close=len(bars_c),
            n_pk_shared=len(shared),
            n_pk_high_only=len(bars_h - bars_c),
            n_pk_close_only=len(bars_c - bars_h),
            mean_price_ratio=(sum(ratios) / len(ratios)) if ratios else float("nan"),
            n_bo_high=len(bo_h), n_bo_close=len(bo_c),
            n_bo_shared=len(bo_h & bo_c),
            n_bo_high_only=len(bo_h - bo_c),
            n_bo_close_only=len(bo_c - bo_h),
            mean_dist_close_only=(sum(d_close_only) / len(d_close_only)) if d_close_only else float("nan"),
        ))

    out = pd.DataFrame(rows)
    out.to_csv(Path(__file__).parent / "s1_peak_overlap.csv", index=False)
    tot = out[[c for c in out.columns if c.startswith("n_")]].sum()
    print(f"样本股票数 = {len(out)}  (窗口 {START}~{END})")
    print("--- 全样本合计 ---")
    print(tot.to_string())
    print()
    print(f"peak bar 重叠(Jaccard, 合计口径) = "
          f"{tot['n_pk_shared'] / max(1, tot['n_pk_high'] + tot['n_pk_close'] - tot['n_pk_shared']):.4f}")
    print(f"close peak 中位于 high peak 集合内的比例 = {tot['n_pk_shared'] / max(1, tot['n_pk_close']):.4f}")
    print(f"high  peak 中位于 close peak 集合内的比例 = {tot['n_pk_shared'] / max(1, tot['n_pk_high']):.4f}")
    print(f"bo bar 重叠(Jaccard) = "
          f"{tot['n_bo_shared'] / max(1, tot['n_bo_high'] + tot['n_bo_close'] - tot['n_bo_shared']):.4f}")
    print()
    print("共享 bar 上 high_price/close_price 均值(逐股均值的均值) = "
          f"{out['mean_price_ratio'].mean():.5f}")
    print("close 独有 peak 距最近 high peak 的 bar 距离(逐股均值的均值) = "
          f"{out['mean_dist_close_only'].mean():.2f}")
    import numpy as np
    for nm, arr in (("close独有→最近high", DIST_C), ("high独有→最近close", DIST_H)):
        a = np.array(arr, dtype=float)
        if len(a) == 0:
            continue
        print(f"{nm}: n={len(a)} median={np.median(a):.1f} "
              f"P(<=3)={np.mean(a<=3):.3f} P(<=6)={np.mean(a<=6):.3f} P(<=10)={np.mean(a<=10):.3f}")


if __name__ == "__main__":
    main()
