"""方案① vs 现状 的真实数据对拍(四个 measure 象限 × N 只股票)。

数据源:主仓 /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls(只读)。
本 worktree 的 datasets/pkls 不存在,但主仓有 8325 个 pkl —— 故本轮用真实数据,
不是合成数据。

输出三组对拍:
  (1) 登记集:REF.registered vs PeakRegistrar 输出 (peak_idx, reg_bar) 逐字
  (2) bo 集(①-a 复刻 supersede):REF.bos vs BOConsumer(replicate=True)
  (3) bo 集(①-c 朴素解耦):REF.bos vs BOConsumer(replicate=False)
另报 display 口径差:纯 peak 域 eaten 判定 vs bo 域(elevated 锚)eaten 判定。
"""
from __future__ import annotations

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
START, END = "2021-01-01", "2026-03-08"
BASE = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
            exceed_threshold=0.003, peak_supersede_threshold=0.01,
            vol_baseline_period=63)
QUADRANTS = [("high", "close"), ("high", "high"), ("close", "close"), ("close", "high")]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    files = sorted(PKL.glob("*.pkl"))
    random.Random(20260831).shuffle(files)
    stats = {q: dict(sym=0, reg_diff=0, boa_diff=0, boc_diff=0,
                     reg_ref=0, reg_p1=0, bo_ref=0, bo_a=0, bo_c=0,
                     pk_total=0, eaten_pure=0, eaten_bo=0, eaten_mismatch=0,
                     dup_reg=0) for q in QUADRANTS}
    examples = []
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
        if len(win) < 400:
            continue
        done += 1
        for pm, bm in QUADRANTS:
            kw = dict(BASE, peak_measure=pm, breakout_measure=bm)
            st = stats[(pm, bm)]
            st["sym"] += 1
            ref = CensusBO(**kw)
            list(ref.detect(win))
            reg = PeakRegistrar(**kw)
            peaks = reg.detect(win)
            a = BOConsumer(replicate_supersede=True, **kw)
            a.detect(peaks, win)
            c = BOConsumer(replicate_supersede=False, **kw)
            c.detect(peaks, win)

            ref_reg = [(r[1], r[0]) for r in ref.registered]      # (peak_idx, reg_bar)
            p1_reg = [(p.index, p.reg_idx) for p in peaks]
            st["reg_ref"] += len(ref_reg)
            st["reg_p1"] += len(p1_reg)
            if len({i for i, _ in ref_reg}) != len(ref_reg):
                st["dup_reg"] += 1
            if ref_reg != p1_reg:
                st["reg_diff"] += 1
                if len(examples) < 3 and (pm, bm) == ("close", "high"):
                    extra = [x for x in ref_reg if x not in p1_reg][:5]
                    examples.append((f.stem, pm, bm, extra))

            ref_bo = [(b[0], b[2]) for b in ref.bos]              # (bar, broken peak idxs)
            a_bo = [(b[0], b[2]) for b in a.bos]
            c_bo = [(b[0], b[2]) for b in c.bos]
            st["bo_ref"] += len(ref_bo)
            st["bo_a"] += len(a_bo)
            st["bo_c"] += len(c_bo)
            if ref_bo != a_bo:
                st["boa_diff"] += 1
            if ref_bo != c_bo:
                st["boc_diff"] += 1

            st["pk_total"] += len(peaks)
            st["eaten_pure"] += len(reg.eaten_by)
            st["eaten_bo"] += len(a.superseded_in_bo)
            st["eaten_mismatch"] += len(set(reg.eaten_by) ^ a.superseded_in_bo)

    print(f"股票数 = {done}  窗口 {START}~{END}  参数 = bb_v1 基线")
    hdr = f"{'peak/bo':14s} {'股数':>5s} {'登记不同':>8s} {'①a-bo不同':>10s} {'①c-bo不同':>10s}"
    print(hdr)
    for q in QUADRANTS:
        s = stats[q]
        print(f"{q[0]+'/'+q[1]:14s} {s['sym']:5d} {s['reg_diff']:8d} {s['boa_diff']:10d} {s['boc_diff']:10d}")
    print()
    print(f"{'peak/bo':14s} {'登记REF':>9s} {'登记①':>9s} {'boREF':>8s} {'bo①a':>8s} {'bo①c':>8s} {'Δ①c%':>8s}")
    for q in QUADRANTS:
        s = stats[q]
        d = 100.0 * (s['bo_c'] - s['bo_ref']) / max(1, s['bo_ref'])
        print(f"{q[0]+'/'+q[1]:14s} {s['reg_ref']:9d} {s['reg_p1']:9d} {s['bo_ref']:8d} "
              f"{s['bo_a']:8d} {s['bo_c']:8d} {d:+7.2f}%")
    print()
    print("display 口径(eaten 判定)差异 —— 纯 peak 域(锚未抬升价) vs bo 域(锚 elevated 价):")
    for q in QUADRANTS:
        s = stats[q]
        print(f"  {q[0]+'/'+q[1]:14s} pk总数={s['pk_total']:7d} "
              f"eaten纯域={s['eaten_pure']:6d} eaten-bo域={s['eaten_bo']:6d} "
              f"对称差={s['eaten_mismatch']:5d} ({100.0*s['eaten_mismatch']/max(1,s['pk_total']):.2f}% of pk)")
    print()
    print("REF 内出现同一 peak bar 被重复登记(C1 触发)的股数:")
    for q in QUADRANTS:
        print(f"  {q[0]+'/'+q[1]:14s} {stats[q]['dup_reg']}/{stats[q]['sym']}")
    for e in examples:
        print("C1 例:", e)


if __name__ == "__main__":
    main()
