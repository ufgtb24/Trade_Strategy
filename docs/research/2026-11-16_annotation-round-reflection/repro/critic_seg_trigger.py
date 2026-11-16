"""critic 一次性核对：「段切得不像用户说的那种东西」这类触发，在第 1 轮的旧版 app 上能不能分开好坏。

旧版 app = HEAD 的 path2_apps/new_step（复制在 repro/critic_pkg/new_step_old，PYTHONPATH 指向 repro 运行）。
对 13 只标注股：跑旧版 detector，取 where 全过的 plateau 事件（零边 pattern，过 where 即 hit），
按买点日分三组：贴着正样本（±3 根，即 compare 判 matched 的那些）、落在反馈范围里、其余（没标过）。
每个 hit 量两个触发：
  T1 新平台里有一根「阶跃级」的大阳：新平台内最大单根对数涨幅 >= 0.5 × 阶跃段内最大单根涨幅
  T2 新平台又抬高了半个阶跃：ln(新平台最高收盘 / 阶跃末根收盘) >= 0.5 × ln(阶跃末根收盘 / 阶跃前一根收盘)
数据只读训练段副本（load_bars 走 path2_web 配置的 view 目录）。
"""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "docs/research/2026-11-16_annotation-round-reflection/repro")

from critic_pkg.new_step_old import dag_spec as old  # noqa: E402
from path2_web.app_run import load_bars  # noqa: E402
from path2_web.config import load_config  # noqa: E402
from path2_web.data import TRAIN_END, slice_window  # noqa: E402

POS = {
    "KULR": ["2024-03-27", "2024-04-01", "2024-11-29", "2024-12-16"],
    "CAPR": ["2025-12-19"], "CRNC": ["2024-11-29", "2024-12-05", "2024-12-13"],
    "DXYZ": ["2024-11-15"], "GEVO": ["2024-09-23"], "INDO": ["2022-02-04"],
    "QBTS": ["2024-11-29", "2024-12-03"], "RGTI": ["2024-11-29", "2024-12-04"], "SMX": ["2025-12-02"],
}
SPOTS = {
    "IXHL": [("2025-08-29", "2025-09-26"), ("2025-07-25", "2025-07-25")],
    "QBTS": [("2025-03-18", "2025-03-25")], "CRNC": [("2025-01-07", "2025-01-30")],
    "INDO": [("2022-03-08", "2022-05-03")], "KULR": [("2024-04-12", "2024-05-20")],
    "LUMN": [("2024-08-09", "2024-10-02")], "CAPR": [("2025-12-05", "2025-12-05")],
    "IZM": [("2024-04-16", "2024-04-16")], "TNXP": [("2024-12-30", "2024-12-30")],
}
SYMS = sorted(set(POS) | set(SPOTS))


def main():
    cfg = load_config()
    params = old.load_params()
    spec = old.build_pattern(params)
    node = next(n for n in spec.nodes if n.node_id == "plateau")
    det = node.detector
    rows = []
    for sym in SYMS:
        df = slice_window(load_bars(cfg, sym), "1900-01-01", TRAIN_END)
        day = [str(d)[:10] for d in df.index] if "date" not in df.columns else [str(d)[:10] for d in df["date"]]
        close = df["close"].to_numpy(float)
        r = np.full(len(close), np.nan)
        r[1:] = np.log(close[1:] / close[:-1])
        pos_idx = [day.index(d) for d in POS.get(sym, []) if d in day]
        spot_rng = [(day.index(a), day.index(b)) for a, b in SPOTS.get(sym, []) if a in day and b in day]
        for ev in det.detect(df):
            if not all(fn(ev) for _, fn in node.where):
                continue
            t = ev.today.start_idx
            s, e = ev.step.start_idx, ev.step.end_idx
            n0, n1 = ev.new.start_idx, ev.new.end_idx
            step_max = float(np.nanmax(r[s:e + 1]))
            new_max = float(np.nanmax(r[n0:n1 + 1]))
            t1 = new_max >= 0.5 * step_max
            step_rise = float(np.log(close[e] / close[s - 1]))
            t2 = float(np.log(close[n0:n1 + 1].max() / close[e])) >= 0.5 * step_rise
            grp = "pos" if any(abs(t - p) <= 3 for p in pos_idx) else (
                "spot" if any(a <= t <= b for a, b in spot_rng) else "other")
            rows.append((sym, day[t], day[s], day[e], grp, t1, t2, new_max, step_max))
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for sym, d, sd, ed, grp, t1, t2, *_ in rows:
        a = agg[grp]
        a[0] += 1; a[1] += t1; a[2] += t2; a[3] += (t1 or t2)
    print("组 | hit 天数 | T1 触发 | T2 触发 | 任一")
    for g in ("pos", "spot", "other"):
        a = agg[g]
        print(g, a)
    print("\n贴着正样本 / 落在反馈范围里的 hit 明细（触发的）：")
    for row in rows:
        sym, d, sd, ed, grp, t1, t2, nm, sm = row
        if grp != "other" and (t1 or t2):
            print(f"{grp:4s} {sym} 买 {d} 阶跃 {sd}~{ed} T1={t1} T2={t2} 新平台最大单根 {nm:.3f} 阶跃最大单根 {sm:.3f}")
    # 按「标过的地方」去重：每张正样本 / 每处反馈有没有至少一个触发的 hit
    print("\n按处去重：")
    seen = defaultdict(lambda: [False, False])
    for sym, d, sd, ed, grp, t1, t2, *_ in rows:
        if grp == "other":
            continue
        key = (grp, sym, d if grp == "pos" else None)
        seen[(grp, sym)][0] = True
        seen[(grp, sym)][1] |= (t1 or t2)
    for k, v in sorted(seen.items()):
        print(k, "有 hit" if v[0] else "", "触发" if v[1] else "不触发")


if __name__ == "__main__":
    main()
