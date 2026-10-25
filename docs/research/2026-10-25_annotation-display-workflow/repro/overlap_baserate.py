"""两件事实,给「标完怎么判 app 认没认出」和「重叠即推荐」用:

1. 随便画一个框,会不会「碰巧」跟某种事件重叠?——按种类量覆盖率(多少比例的 K 线被至少一个该种事件盖住)
   和随机框的重叠概率(框长 1/5/20/60 根),以及随机框与最贴近那个事件的重叠度(交集/并集)中位数。
   这是「重叠就算认出 / 重叠就推荐」的运气基线。
2. 「现成 detector 用默认参数」和「app 里用的参数」产出的同种事件差多少?——bo、burst、tb 三种,
   比较 bb_v1 声明里的事件与默认参数版的事件(按起止根对齐)。

只读截到 2025-12-31 的副本;窗口 2024-10-01..2025-12-31,只在 2025 年那一段(看图范围)里统计。
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from bench_detectors import SNAP, all_atoms_spec  # noqa: E402
from chart_workflow.loader import load_bars  # noqa: E402
from path2.dag.engine import run_streams  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb_v1  # noqa: E402
from path2_web.data import slice_window  # noqa: E402

N_STOCKS = 200
BOX_LENS = (1, 5, 20, 60)
N_BOX = 200          # 每只股票每种框长随机抽多少个框
KINDS = ("bo", "pk", "burst", "tb_v2", "tb_v1", "tb_v4", "trend", "platform", "dist")


def spans(evs):
    return [(e.start_idx, e.end_idx) for e in evs]


def main():
    random.seed(7)
    rng = np.random.default_rng(7)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    random.shuffle(syms)
    spec_all = all_atoms_spec()
    p = bb_v1.load_params()
    spec_bb = bb_v1.build_pattern(p)
    cov = defaultdict(list)
    hit = defaultdict(list)          # (kind, L) -> 每只股票随机框重叠比例
    iou = defaultdict(list)          # (kind, L) -> 重叠到的框与最贴近事件的交并比
    mism = defaultdict(lambda: [0, 0, 0])   # kind -> [两边都有, 只在默认参数版, 只在 bb_v1]
    n = 0
    for sym in syms:
        if n >= N_STOCKS:
            break
        try:
            df = load_bars(SNAP, sym, "2025-12-31")
        except Exception:
            continue
        if len(df) < 1000:
            continue
        win = slice_window(df, "2024-10-01", "2025-12-31")
        lo = int(win["date"].searchsorted(pd.Timestamp("2025-01-01")))
        hi = len(win) - 1
        sa = run_streams(spec_all, win)
        sb = run_streams(spec_bb, win)
        n += 1
        for k in KINDS:
            sp = [(max(s, lo), e) for s, e in spans(sa[k]) if e >= lo]
            covered = np.zeros(hi + 1, bool)
            for s, e in sp:
                covered[s:e + 1] = True
            cov[k].append(covered[lo:].mean())
            for L in BOX_LENS:
                starts = rng.integers(lo, hi - L + 2, N_BOX)
                h = 0
                for b0 in starts:
                    b1 = b0 + L - 1
                    best = 0.0
                    for s, e in sp:
                        inter = min(b1, e) - max(b0, s) + 1
                        if inter > 0:
                            best = max(best, inter / (max(b1, e) - min(b0, s) + 1))
                    if best > 0:
                        h += 1
                        iou[(k, L)].append(best)
                hit[(k, L)].append(h / N_BOX)
        # 默认参数版 vs bb_v1 里的同种事件(只看起点落在 2025 的)
        for k_all, k_bb in (("bo", "bo"), ("burst", "burst"), ("tb_v1", "tb")):
            a = {(e.start_idx, e.end_idx) for e in sa[k_all] if e.start_idx >= lo}
            b = {(e.start_idx, e.end_idx) for e in sb[k_bb] if e.start_idx >= lo}
            mism[k_bb][0] += len(a & b)
            mism[k_bb][1] += len(a - b)
            mism[k_bb][2] += len(b - a)
    print(f"样本 {n} 只,2025 年看图范围")
    print("种类      覆盖率中位  | 随机框碰上至少一个该种事件的概率(中位/均值) 框长=" + "/".join(map(str, BOX_LENS)))
    out = {"n": n, "coverage": {}, "hit": {}, "iou": {}, "mismatch": {}}
    for k in KINDS:
        hs = "  ".join(f"{statistics.median(hit[(k, L)]):.2f}/{statistics.mean(hit[(k, L)]):.2f}" for L in BOX_LENS)
        ios = "  ".join(f"{statistics.median(iou[(k, L)]) if iou[(k, L)] else float('nan'):.2f}" for L in BOX_LENS)
        print(f"{k:9s} {statistics.median(cov[k]):.2f}        | {hs}   | 碰上时最贴近事件的交并比中位 {ios}")
        out["coverage"][k] = statistics.median(cov[k])
        for L in BOX_LENS:
            out["hit"][f"{k}@{L}"] = statistics.mean(hit[(k, L)])
            out["iou"][f"{k}@{L}"] = statistics.median(iou[(k, L)]) if iou[(k, L)] else None
    print("默认参数版 vs bb_v1 声明里的同种事件(按起止根完全相同算同一个):两边都有 / 只在默认版 / 只在 bb_v1")
    for k, v in mism.items():
        print(f"  {k:6s} {v[0]:5d} / {v[1]:5d} / {v[2]:5d}")
        out["mismatch"][k] = v
    (HERE / "out_overlap.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
