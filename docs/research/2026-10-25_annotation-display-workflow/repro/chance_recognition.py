"""临时实验：随手画一个框，被各现成 detector「认出」的概率（偶然基线）。

目的：对照环节若用「有交叠就算认出」，长事件 / 密事件会把随便画的框也判成认出。
量：随机抽股票，在训练段里均匀撒宽度 w 的框，算两种判据下被判认出的比例：
  any  —— 框与该种类任一事件有至少一天交叠（点事件：落在框内，框外各放宽 2 天）
  half —— 该种类事件合计盖住框的一半以上（点事件不适用，记 nan）
  mutual —— 存在某个事件，它和框的交叠 ≥ 两者中较短那个的一半（短事件看「事件大半在框内」，长事件看「框大半被盖住」）
走势区段按下跌 / 横盘 / 上涨分开算（用户标「横盘」时只该和横盘段比）。
另记各种类每 250 根的事件数（密度）。只读截到 2025-12-31 的副本。
"""
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from chart_workflow.loader import load_bars  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb  # noqa: E402
from path2.atoms.breakout import BODetector, BurstDetector  # noqa: E402
from path2.atoms.throwback_v1 import ThrowbackDetectorV1  # noqa: E402
from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402
from path2.atoms.distribution import DistributionDetector  # noqa: E402

SNAP = ROOT / "datasets/pkls_until_20251231"
N_STOCK = 150
N_BOX = 200
WIDTHS = [1, 5, 10, 20, 40]
POINT_TOL = 2


def spans_of(df, params):
    out = defaultdict(list)          # kind -> [(s, e)]
    bo_det = BODetector(**params.bo_kwargs())
    bos = [e for (name, e) in bo_det.detect(df) if name == "bo"]
    out["突破(点)"] = [(e.start_idx, e.end_idx) for e in bos]
    bursts = list(BurstDetector(**params.burst_kwargs()).detect(bos, df))
    out["burst"] = [(e.start_idx, e.end_idx) for e in bursts]
    tbs = list(ThrowbackDetectorV1(**params.throwback_kwargs()).detect(bursts, df))
    out["回踩"] = [(e.start_idx, e.end_idx) for e in tbs]
    out["平台段"] = [(e.start_idx, e.end_idx) for e in PlatformDetector().detect(df)]
    for e in TrendSegmentDetector().detect(df):
        out["走势区段·" + {"down": "下跌", "sideways": "横盘", "up": "上涨"}.get(e.regime, e.regime)].append((e.start_idx, e.end_idx))
    out["派发(点)"] = [(e.start_idx, e.end_idx) for e in DistributionDetector().detect(df)]
    return out


def main():
    rng = random.Random(11)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    rng.shuffle(syms)
    params = bb.load_params()
    any_hit = defaultdict(list)      # (kind, w) -> [0/1]
    half_hit = defaultdict(list)
    mut_hit = defaultdict(list)
    dens = defaultdict(list)
    done = 0
    for sym in syms:
        if done >= N_STOCK:
            break
        try:
            df = slice_window(load_bars(SNAP, sym, "2025-12-31"), "2021-10-08", "2025-12-31")
        except Exception:
            continue
        if len(df) < 500:
            continue
        sp = spans_of(df, params)
        n = len(df)
        kinds = ["突破(点)", "burst", "回踩", "平台段", "走势区段·下跌", "走势区段·横盘", "走势区段·上涨", "派发(点)"]
        cov = {}
        for k in kinds:
            c = np.zeros(n, dtype=bool)
            for s, e in sp.get(k, []):
                c[s:e + 1] = True
            cov[k] = c
            dens[k].append(len(sp.get(k, [])) * 250 / n)
        for w in WIDTHS:
            for _ in range(N_BOX):
                s = rng.randrange(60, n - w)
                e = s + w - 1
                for k in kinds:
                    point = k.endswith("(点)")
                    lo, hi = (max(0, s - POINT_TOL), min(n - 1, e + POINT_TOL)) if point else (s, e)
                    any_hit[(k, w)].append(int(cov[k][lo:hi + 1].any()))
                    half_hit[(k, w)].append(np.nan if point else int(cov[k][s:e + 1].mean() > 0.5))
                    if not point:
                        ok = 0
                        for a, b in sp.get(k, []):
                            ov = min(b, e) - max(a, s) + 1
                            if ov > 0 and ov >= 0.5 * min(b - a + 1, w):
                                ok = 1
                                break
                        mut_hit[(k, w)].append(ok)
        done += 1
    print(f"股票 {done} 只，每只每种宽度 {N_BOX} 个随机框；训练段 2021-10-08~2025-12-31\n")
    print("每 250 根的事件数（中位数 / 75 分位 / 90 分位）")
    for k, v in dens.items():
        print(f"  {k:<12} {np.median(v):6.1f} {np.percentile(v, 75):6.1f} {np.percentile(v, 90):6.1f}")
    print("\n随手画的框被判『认出』的比例：any = 有一天交叠就算；half = 盖住框一半以上")
    print("  种类           " + "".join(f"  w={w:<3} any/half " for w in WIDTHS))
    for k in dens:
        row = ""
        for w in WIDTHS:
            a = np.mean(any_hit[(k, w)]); h = np.nanmean(half_hit[(k, w)]) if not k.endswith("(点)") else float("nan")
            row += f"  {a:5.0%} / {h:4.0%}    " if h == h else f"  {a:5.0%} /  -      "
        print(f"  {k:<14}{row}")

    print("\nmutual 判法（交叠 ≥ 较短者一半）下随手的框被判认出的比例")
    for k in dens:
        if k.endswith("(点)"):
            continue
        print(f"  {k:<14}" + "".join(f"  w={w}:{np.mean(mut_hit[(k, w)]):5.0%}" for w in WIDTHS))


if __name__ == "__main__":
    main()
