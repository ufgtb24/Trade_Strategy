"""11 同日对照配对票 · 第三步：偶然波动（判据分母）与对照本身的抖动（代价）。

无偏好随机池内股票日、分散长相（同股 40 个交易日内不重复买）、每年 1000 个买点：
  1. 在随机放置的 1 年 / 2 年时段上抽一批买点（40 次放置）；
  2. 买点侧偶然波动：整只股票有放回重抽 200 次、对照不动，取领先的标准差（每种配对都算）；
  3. 对照侧抖动：买点不动，对照成员各乘一个 Poisson(1) 重抽权重，100 次，取领先的标准差；
  4. 另记每次放置的领先本身（不重抽），40 次放置间的标准差 = 「换一批买点」的偶然波动，作口径核对；
  5. 买点所在格（或近邻）的对照个数 < 10、< 20 的比例。
输出：scripts/11-noise.csv.gz（逐次放置）、scripts/11-noise_out.txt（汇总）
运行：uv run python .scratch/selection-pattern/scripts/11-noise.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core11", HERE / "11-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core11"] = core; spec.loader.exec_module(core)

G: dict = {}
N_PLACE, B_HIT, B_CTRL = 40, 200, 100


def task(args):
    Y_len, rep = args
    P, mts, S = G["P"], G["mts"], G["S"]
    rng = np.random.default_rng(1_000_000 * Y_len + rep)
    span = int(round(252 * Y_len))
    nd = len(P["calendar"])
    D0 = int(rng.integers(0, nd - span + 1)); D1 = D0 + span - 1
    cand = np.arange(P["day_start"][D0], P["day_end"][D1])
    rows = core.dispersed_sample(P, cand, 1000 * Y_len, rng)
    schemes = list(mts) if Y_len == 2 else [s for s in mts if s == "M5"]
    out = []
    for s in schemes:
        mt = mts[s]
        base = core.leads(mt, S, rows)
        rec = {"Y": Y_len, "rep": rep, "D0": D0, "scheme": s, "n": len(rows),
               "n_stocks": int(len(np.unique(P["sym"][rows]))),
               "lt10": float(np.mean(mt.size[rows] < 10)), "lt20": float(np.mean(mt.size[rows] < 20))}
        hb = {m: [] for m in core.METRICS}
        brng = np.random.default_rng(rep * 7919 + 17)
        for _ in range(B_HIT):
            w = core.stock_boot_weights(P, rows, brng)
            keep = w > 0
            r = core.leads(mt, S, rows[keep], w[keep])
            for m in core.METRICS:
                hb[m].append(r[m])
        cb = {m: [] for m in core.METRICS}
        if Y_len == 2:
            crng = np.random.default_rng(rep * 104729 + 3)
            lo, hi = P["day_start"][D0], P["day_end"][D1]
            for _ in range(B_CTRL):
                pw = np.zeros(P["N"])
                pw[lo:hi] = crng.poisson(1.0, hi - lo)
                r = core.leads(mt, S, rows, pw=pw)
                for m in core.METRICS:
                    cb[m].append(r[m])
        for m in core.METRICS:
            rec[f"lead_{m}"] = base[m]
            rec[f"hsd_{m}"] = float(np.std(hb[m], ddof=1))
            rec[f"csd_{m}"] = float(np.std(cb[m], ddof=1)) if cb[m] else np.nan
        out.append(rec)
    return out


def main():
    t0 = time.time()
    schemes = sys.argv[1:] or core.SCHEMES
    suffix = "" if not sys.argv[1:] else "-" + "-".join(schemes)
    P, Y, hold, mts, S = core.load_all(schemes)
    G.update(P=P, mts=mts, S=S)
    print(f"loaded {time.time() - t0:.0f}s", flush=True)
    tasks = [(y, r) for y in ((2, 1) if not suffix else (2,)) for r in range(N_PLACE)]
    with get_context("fork").Pool(12) as mp:
        res = mp.map(task, tasks, chunksize=1)
    df = pd.DataFrame([r for ch in res for r in ch])
    df.to_csv(HERE / f"11-noise{suffix}.csv.gz", index=False)
    lines = [f"无偏好随机、分散长相、每年 1000 个买点；放置 {N_PLACE} 次；买点侧重抽 {B_HIT} 次，对照侧 {B_CTRL} 次。"]
    for Y_len in ((1, 2) if not suffix else ()):
        d = df[(df.Y == Y_len) & (df.scheme == "M5")]
        lines.append(f"\n== {Y_len} 年，现行 M5：买点侧偶然波动（整只股票重抽，均方根） / 换一批买点的标准差 / 平均买点数、股票数 "
                     f"{d.n.mean():.0f}、{d.n_stocks.mean():.0f}")
        for m in core.METRICS:
            scale = 100 if m != "dir" else 1
            lines.append(f"  {m:8s} {np.sqrt((d[f'hsd_{m}'] ** 2).mean()) * scale:8.4f}  {d[f'lead_{m}'].std(ddof=1) * scale:8.4f}"
                         f"   (单位：{'方向值' if m == 'dir' else '百分点'})")
    lines.append("\n== 2 年：各配对的买点侧偶然波动 / 对照侧抖动 / 两者之比（方向值或百分点） ==")
    d2 = df[df.Y == 2]
    for s in mts:
        d = d2[d2.scheme == s]
        lines.append(f"-- {s}：买点所在格对照 <10 的占 {d.lt10.mean():.4f}，<20 的占 {d.lt20.mean():.4f}")
        for m in core.METRICS:
            scale = 100 if m != "dir" else 1
            h = np.sqrt((d[f'hsd_{m}'] ** 2).mean()) * scale
            c = np.sqrt((d[f'csd_{m}'] ** 2).mean()) * scale
            lines.append(f"   {m:8s} 买点侧 {h:7.4f}  对照侧 {c:7.4f}  比 {c / h:5.2f}  合计放大 {np.sqrt(1 + (c / h) ** 2):5.3f}")
    lines.append(f"\n耗时 {time.time() - t0:.0f}s")
    txt = "\n".join(lines)
    print(txt)
    (HERE / f"11-noise{suffix}_out.txt").write_text(txt + "\n")


if __name__ == "__main__":
    main()
