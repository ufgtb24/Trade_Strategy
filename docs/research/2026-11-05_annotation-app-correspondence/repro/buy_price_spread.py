"""app 买入日落在什么价位:以用户样本日收盘价的中位数当作「新平台价位」,看 app 的买入日有多少落在它附近、多少已经远离。
只统计显示窗内(plot_overlay.VIEW)的买入日;±30% 这条带是拍的,只为数清楚「一长串」里有多少不在用户说的那个平台上。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402
import path2_apps.new_step as app  # noqa: E402
from path2.eval import _resolve_end_events  # noqa: E402

VIEW = {"CRNC": ("2024-08-01", "2025-04-04"), "GEVO": ("2024-06-20", "2024-11-15"), "INDO": ("2021-11-20", "2022-04-29"),
        "QBTS": ("2024-09-20", "2025-01-15"), "RGTI": ("2024-10-01", "2025-01-10"), "SMX": ("2025-09-25", "2025-12-31")}
s, _ = load_state()
p = app.load_params()
meta = app.eval_meta(p)
print("| 图 | 显示窗内 hit 数 | 买入日(去重) | 新平台价位(样本日收盘中位数) | 买入价 / 新平台价位 最低~最高 | 落在 ±30% 内 | 高出 30% 以上 | 低于 30% 以上 | 样本日被买 |")
print("|---|---|---|---|---|---|---|---|---|")
for c in s["charts"]:
    sym = c["symbol"]
    win = load_win(sym)
    v0, v1 = d2i(win, VIEW[sym][0]), d2i(win, VIEW[sym][1], "right") - 1
    smp = [d2i(win, x["date"]) for x in c["samples"] if (sym, x["date"]) not in EXCLUDED_SAMPLES]
    ref = float(np.median(win["close"].values[smp]))
    res = app.analyze(win, p)
    hits = [h for h in res.hits if h.end_idx >= v0 and h.start_idx <= v1]
    buy = set()
    for h in hits:
        for e in _resolve_end_events(h, meta["end_node"]):
            buy.update(i for i in range(e.start_idx, e.end_idx + 1) if v0 <= i <= v1)
    r = np.array([win["close"].iloc[i] / ref for i in sorted(buy)]) if buy else np.array([])
    hitd = sum(1 for t in smp if t in buy)
    if len(r):
        print(f"| {sym} | {len(hits)} | {len(buy)} | {ref:.2f} | {r.min():.2f}~{r.max():.2f} | {np.sum((r >= 1 / 1.3) & (r <= 1.3))} |"
              f" {np.sum(r > 1.3)} | {np.sum(r < 1 / 1.3)} | {hitd}/{len(smp)} |")
    else:
        print(f"| {sym} | 0 | 0 | {ref:.2f} | - | 0 | 0 | 0 | 0/{len(smp)} |")
