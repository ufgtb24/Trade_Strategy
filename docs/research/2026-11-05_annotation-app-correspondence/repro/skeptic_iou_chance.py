"""skeptic 临时脚本:「扫十几档参数、挑交并比最高的那档」碰巧能有多高。
对每个框:在 sweep_detectors.py 同一组 14 档参数(平台段 9 档 + 走势区段 5 档)的全部输出里取最大交并比;
再把同宽的框随机挪 40 次(种子 = 框起点序号),同样取最大交并比,报真框在随机框里排第几(百分位)。只读。"""
import random
import numpy as np
from common import load_state, load_win, d2i
from path2.atoms.platform import PlatformDetector
from path2.atoms.trend import TrendSegmentDetector

PLAT = [(10, 0.05), (10, 0.10), (10, 0.15), (10, 0.20), (10, 0.30), (5, 0.10), (5, 0.20), (20, 0.30), (20, 0.40)]
TREND = [(20, 0.0005), (20, 0.002), (20, 0.005), (10, 0.005), (40, 0.002)]
def iou(a0, a1, b0, b1):
    inter = max(0, min(a1, b1) - max(a0, b0) + 1)
    return inter / ((a1 - a0 + 1) + (b1 - b0 + 1) - inter)
s, fname = load_state()
for c in s["charts"]:
    w = load_win(c["symbol"]); n = len(w)
    spans = []
    for k in PLAT:
        spans += [(e.start_idx, e.end_idx) for e in PlatformDetector(window=k[0], range_thr=k[1]).detect(w)]
    for k in TREND:
        spans += [(e.start_idx, e.end_idx) for e in TrendSegmentDetector(ma_period=k[0], sideways_eps=k[1]).detect(w)]
    spans = np.array(spans)
    def best(b0, b1):
        return max(iou(a, z, b0, b1) for a, z in spans if z >= b0 and a <= b1) if ((spans[:, 1] >= b0) & (spans[:, 0] <= b1)).any() else 0.0
    for b in c["boxes"]:
        b0, b1 = d2i(w, b["start"]), d2i(w, b["end"]); L = b1 - b0
        real = best(b0, b1)
        rng = random.Random(b0)
        rnd = [best(x, x + L) for x in (rng.randint(63, n - L - 1) for _ in range(40))]
        pct = np.mean([r < real for r in rnd])
        print(f"{c['symbol']} {b['id']} {fname[b['feature']]} 长{L+1} 真框最大交并比 {real:.2f}  随机框中位数 {np.median(rnd):.2f}  "
              f"随机框 90% 分位 {np.quantile(rnd, .9):.2f}  真框高过 {pct:.0%} 的随机框")
