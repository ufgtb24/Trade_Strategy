"""现成 detector 与用户框的对齐:平台段、走势区段各扫几档参数,看有没有哪档的输出能和框大致对齐。

对每个框报:
- 框内最大单日涨幅那天(当作阶跃日的客观读数)及其量比;
- 平台段:与框重叠的平台段(起止),分「阶跃前 / 阶跃后」;
- 走势区段:框内各态覆盖的根数占比;
- 与框交并比(IoU)最大的那个平台段 / 走势区段。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_state, load_win, d2i, i2d  # noqa: E402

from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402
from path2.calc.volume import calculate_vol_ratio  # noqa: E402


def iou(a0, a1, b0, b1):
    inter = max(0, min(a1, b1) - max(a0, b0) + 1)
    uni = (a1 - a0 + 1) + (b1 - b0 + 1) - inter
    return inter / uni


s, fname = load_state()
PLAT = [(10, 0.05), (10, 0.10), (10, 0.15), (10, 0.20), (10, 0.30), (5, 0.10), (5, 0.20), (20, 0.30), (20, 0.40)]
TREND = [(20, 0.0005), (20, 0.002), (20, 0.005), (10, 0.005), (40, 0.002)]

for c in s["charts"]:
    sym = c["symbol"]
    win = load_win(sym)
    vr = calculate_vol_ratio(win["volume"], 63)
    chg = win["close"].pct_change()
    plat_out = {k: list(PlatformDetector(window=k[0], range_thr=k[1]).detect(win)) for k in PLAT}
    trend_out = {k: list(TrendSegmentDetector(ma_period=k[0], sideways_eps=k[1]).detect(win)) for k in TREND}
    for b in c["boxes"]:
        b0, b1 = d2i(win, b["start"]), d2i(win, b["end"])
        seg = chg.iloc[b0:b1 + 1]
        step = int(seg.idxmax())
        print(f"\n## {sym} {b['id']} {fname[b['feature']]} {b['start']}..{b['end']} ({b1 - b0 + 1} 根)"
              f"  框内最大单日涨幅 {i2d(win, step)} {chg.iloc[step] * 100:+.0f}% 量比 {vr.iloc[step]:.1f}")
        for k, evs in plat_out.items():
            ov = [e for e in evs if e.end_idx >= b0 - 10 and e.start_idx <= b1 + 10]
            if not ov:
                print(f"  platform w={k[0]:2d} thr={k[1]:.2f}: 无")
                continue
            best = max(ov, key=lambda e: iou(e.start_idx, e.end_idx, b0, b1))
            desc = "; ".join(f"{i2d(win, e.start_idx)[5:]}..{i2d(win, e.end_idx)[5:]}({e.end_idx - e.start_idx + 1})"
                             f"{'前' if e.end_idx < step else ('后' if e.start_idx > step else '跨')}" for e in ov)
            print(f"  platform w={k[0]:2d} thr={k[1]:.2f}: {desc}  | 最大IoU {iou(best.start_idx, best.end_idx, b0, b1):.2f}")
        for k, evs in trend_out.items():
            cnt = {"down": 0, "sideways": 0, "up": 0}
            for i in range(b0, b1 + 1):
                for e in evs:
                    if e.start_idx <= i <= e.end_idx:
                        cnt[e.regime] += 1
                        break
            ov = [e for e in evs if e.end_idx >= b0 and e.start_idx <= b1]
            best = max(ov, key=lambda e: iou(e.start_idx, e.end_idx, b0, b1))
            n = b1 - b0 + 1
            print(f"  trend ma={k[0]:2d} eps={k[1]:.4f}: 段数 {len(ov)} 下/横/上 {cnt['down'] / n:.0%}/{cnt['sideways'] / n:.0%}/{cnt['up'] / n:.0%}"
                  f" | 最大IoU {iou(best.start_idx, best.end_idx, b0, b1):.2f} ({best.regime} {i2d(win, best.start_idx)}..{i2d(win, best.end_idx)})")
