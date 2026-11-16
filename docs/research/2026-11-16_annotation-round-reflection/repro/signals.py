"""一次性：在 13 只标注股 / 16 张样本 / 10 处反馈上量几种「该起疑」的信号（旧版 app，即第 1 轮改之前）。

用法：uv run python signals.py [old|new]
样本、框、反馈范围抄自 round_digest('new_step', '.../2026-11-16-1.json') 的输出（repro/digest_round1.txt）。
「真问题」的近似：按用户谈定的阶跃新认法（next-round-step-definition.md 第 2、6 条）粗算——
  终点：从旧版阶跃末根 e 往后，只要下一根最高价比前一根高就继续，停在最高价第一次回落的前一根；
  起点：从旧版阶跃起点 s 往前，只要前一根最高价比再前一根高就继续往前挪。
不实现第 4 条「停顿后续上」（会低估 KULR 2024-03、2024-11 那种）。
"""
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
WHICH = sys.argv[1] if len(sys.argv) > 1 else "old"
C = pickle.load(open(HERE / f"cache_{WHICH}.pkl", "rb"))
POS_TOL = 3

SAMPLES = [  # (股票, 样本日, 一致?, 站上新平台框起, 底部平稳框止)
    ("KULR", "2024-03-27", False, "2024-02-09", "2024-03-13"),
    ("KULR", "2024-04-01", False, "2024-02-09", "2024-03-13"),
    ("KULR", "2024-11-29", False, "2024-10-28", "2024-11-12"),
    ("KULR", "2024-12-16", False, "2024-10-22", "2024-11-12"),
    ("CAPR", "2025-12-19", True, None, None),
    ("CRNC", "2024-11-29", True, "2024-09-17", "2024-11-19"),
    ("CRNC", "2024-12-05", True, "2024-09-17", "2024-11-19"),
    ("CRNC", "2024-12-13", True, "2024-09-17", "2024-11-19"),
    ("DXYZ", "2024-11-15", True, None, None),
    ("GEVO", "2024-09-23", True, "2024-07-23", None),
    ("INDO", "2022-02-04", True, "2021-12-27", None),
    ("QBTS", "2024-11-29", True, "2024-10-23", None),
    ("QBTS", "2024-12-03", True, "2024-10-23", None),
    ("RGTI", "2024-11-29", True, "2024-11-05", None),
    ("RGTI", "2024-12-04", True, "2024-11-06", None),
    ("SMX", "2025-12-02", True, "2025-10-31", None),
]

FEEDBACK = [  # (编号, issue, 股票, 起, 止, 方式, 族起点)
    ("f-pc-90", "f-pc-90", "IXHL", "2025-08-29", "2025-09-26", "family", "2025-08-01"),
    ("f-pc-92", "f-pc-92", "QBTS", "2025-03-18", "2025-03-25", "family", "2025-02-21"),
    ("f-pc-74", "i-pc-1", "CRNC", "2025-01-07", "2025-01-30", "family", "2024-12-11"),
    ("f-pc-72", "i-pc-1", "INDO", "2022-03-08", "2022-05-03", "range", None),
    ("f-pc-89", "i-pc-1", "KULR", "2024-04-12", "2024-05-20", "range", None),
    ("f-pc-94", "i-pc-2", "IXHL", "2025-07-25", "2025-07-25", "point", None),
    ("f-pc-95", "i-pc-2", "LUMN", "2024-08-09", "2024-10-02", "family", "2024-07-16"),
    ("f-pc-104", "i-pc-3", "CAPR", "2025-12-05", "2025-12-05", "point", None),
    ("f-pc-101", "i-pc-3", "IZM", "2024-04-16", "2024-04-16", "point", None),
    ("f-pc-93", "i-pc-3", "TNXP", "2024-12-30", "2024-12-30", "point", None),
]


def arrays(sym):
    c = C[sym]
    b = c["bars"]
    return c["day"], b[:, 0], b[:, 1], b[:, 3], c["events"]


def new_def(sym, s, e):
    """按新认法第 2、6 条粗算阶跃起止。"""
    day, o, h, cl, _ = arrays(sym)
    n = len(h)
    e2 = e
    while e2 + 1 < n and h[e2 + 1] > h[e2]:
        e2 += 1
    # 旧版 e 本身最高价可能已比 e-1 低（收盘还在涨）：新认法终点取段内最高价那根之后的回落
    s2 = s
    while s2 - 1 >= 1 and h[s2 - 1] > h[s2 - 2]:
        s2 -= 1
    return s2, e2


def sig(sym, ev):
    """一个 hit 上的各信号，只用当天 t 及以前的数据（look.py 当时就看得到的）。"""
    day, o, h, cl, _ = arrays(sym)
    s, e, t = ev["s"], ev["e"], ev["t"]
    r = np.log(cl[1:] / cl[:-1]); r = np.concatenate([[np.nan], r])
    rh = np.concatenate([[np.nan], np.log(h[1:] / cl[:-1])])
    step_max = ev["step_max_ret"]
    step_top_h = h[s:e + 1].max()
    nw = range(e + 1, t)                       # 新平台 [e+1, t-1]
    old = range(ev["old_s"], s)
    out = {}
    # S1 新平台里有比阶跃最猛一根还猛的 K 线（按收盘 / 按盘中最高）
    out["S1_close"] = any(r[i] >= step_max for i in nw)
    out["S1_high"] = any(rh[i] >= step_max for i in nw)
    # S1c 新平台里的最高价比阶跃顶高出 10% 以上
    out["S1_top10"] = max((h[i] for i in nw), default=0) > 1.10 * step_top_h
    # S1d 新平台第一根最高价还在抬高（新认法下阶跃没结束）
    out["S1_first_high_up"] = h[e + 1] > h[e]
    # S2 旧平台里有比阶跃最猛一根还猛的 K 线
    out["S2_close"] = any(r[i] >= step_max for i in old)
    # S2b 阶跃起点前一根最高价也在抬高、收阳（起点可能该往前挪）
    out["S2_prev_up"] = h[s - 1] > h[s - 2] and cl[s - 1] > cl[s - 2]
    # keep_ratio > 1：新平台连同当天的最低收盘都在阶跃末根收盘之上（价格还在往上走）
    out["keep_gt1"] = (ev.get("keep_ratio") or 0) > 1.0
    s2, e2 = new_def(sym, s, e)
    out["true_end"] = e2 > e
    out["true_end_material"] = e2 > e and h[e + 1:e2 + 1].max() > 1.10 * step_top_h
    out["true_start"] = s2 < s
    out["buy_inside_new_step"] = t <= e2
    out["s2e2"] = (day[s2], day[e2])
    return out


def hits_of(sym):
    return [ev for ev in arrays(sym)[4] if ev["hit"]]


def report_all_hits():
    print("== 全部买点 hit（13 只股票）==")
    tot = defaultdict(int)
    n = 0
    cross = defaultdict(int)
    for sym in C:
        for ev in hits_of(sym):
            n += 1
            g = sig(sym, ev)
            for k, v in g.items():
                if isinstance(v, (bool, np.bool_)):
                    tot[k] += int(v)
            for k in ("S1_close", "S1_high", "S1_top10", "S1_first_high_up", "keep_gt1"):
                if g[k]:
                    cross[(k, "true_end")] += int(g["true_end"])
                    cross[(k, "true_end_material")] += int(g["true_end_material"])
            for k in ("S2_close", "S2_prev_up"):
                if g[k]:
                    cross[(k, "true_start")] += int(g["true_start"])
    print("hit 数", n)
    for k, v in tot.items():
        print(f"  {k}: {v}")
    for k, v in cross.items():
        print(f"  {k}: {v}")


def same_day_prefixes():
    """S3 同一天被同一段阶跃的几个前缀各买一次；S4 hit 用的是短前缀、新平台里夹着同段阶跃剩下的根。"""
    print("== S3/S4 前缀成族 ==")
    days_multi = 0
    days_tot = 0
    short_prefix_hits = 0
    hits_tot = 0
    detail = []
    for sym in C:
        day, *_ , evs = arrays(sym)
        seg_end = defaultdict(int)          # s -> 段尾 e'（所有候选里最大的 e）
        for ev in evs:
            seg_end[ev["s"]] = max(seg_end[ev["s"]], ev["e"])
        by_t = defaultdict(set)
        for ev in hits_of(sym):
            hits_tot += 1
            by_t[(ev["t"], ev["s"])].add(ev["e"])
            if ev["e"] < seg_end[ev["s"]]:
                short_prefix_hits += 1
        days = defaultdict(int)
        for (t, s), es in by_t.items():
            days[t] = max(days[t], len(es))
        days_tot += len(days)
        for t, k in days.items():
            if k >= 2:
                days_multi += 1
                detail.append((sym, day[t], k))
    print(f"  买点日 {days_tot}，其中同一段阶跃的 ≥2 个前缀同天都买的 {days_multi}")
    print(f"  hit {hits_tot}，其中用的是短前缀（新平台里夹着同段阶跃剩下的根）的 {short_prefix_hits}")
    for d in detail[:40]:
        print("   ", d)


def report_samples():
    print("== 16 张样本 ==")
    for sym, d, ok, box_s, bot_e in SAMPLES:
        day, o, h, cl, evs = arrays(sym)
        i = day.index(d)
        hs = [ev for ev in hits_of(sym) if abs(ev["t"] - i) <= POS_TOL]
        pick = sorted(hs, key=lambda ev: (abs(ev["t"] - i), -ev["e"]))
        if not pick:   # 没买到：取当天的候选
            pick = sorted([ev for ev in evs if ev["t"] == i], key=lambda ev: -ev["s"])
        if not pick:
            print(f"  {sym} {d} 一致={ok} 没有候选"); continue
        ev = pick[0]
        g = sig(sym, ev)
        flags = [k for k, v in g.items() if isinstance(v, (bool, np.bool_)) and v]
        bs = ""
        if box_s:
            bs = f" 框起-旧平台起={i_gap(day, box_s, day[ev['old_s']])}根"
        if bot_e:
            bs += f" 底部平稳框止→阶跃起={i_gap(day, bot_e, day[ev['s']])}根 →新认法起={i_gap(day, bot_e, g['s2e2'][0])}根"
        print(f"  {sym} {d} 一致={ok} hit={int(ev['hit'])} step={day[ev['s']]}..{day[ev['e']]} "
              f"new={day[ev['e']+1]}..{day[ev['t']-1]} t={day[ev['t']]} 新认法step={g['s2e2'][0]}..{g['s2e2'][1]}{bs}")
        print(f"      信号: {flags}")


def i_gap(day, a, b):
    """b 相对 a 晚几根（交易日）。"""
    def idx(x):
        return next(k for k, dd in enumerate(day) if dd >= x)
    return idx(b) - idx(a)


def report_feedback():
    print("== 10 处反馈 ==")
    for fid, iss, sym, a, b, mode, fam in FEEDBACK:
        day, o, h, cl, evs = arrays(sym)
        hs = [ev for ev in hits_of(sym) if a <= day[ev["t"]] <= b]
        if mode == "family":
            hs = [ev for ev in hs if day[ev["old_s"]] == fam] or hs
        agg = defaultdict(int)
        steps = set()
        for ev in hs:
            g = sig(sym, ev)
            steps.add((day[ev["s"]], day[ev["e"]], g["s2e2"]))
            for k, v in g.items():
                if isinstance(v, (bool, np.bool_)):
                    agg[k] += int(v)
        print(f"  {fid}({iss}) {sym} {a}..{b} {mode}: hit {len(hs)}；阶跃 {sorted(steps)}")
        print(f"      信号计数: {dict(agg)}")


if __name__ == "__main__":
    report_samples()
    report_feedback()
    report_all_hits()
    same_day_prefixes()
