"""回应 skeptic / framework 的两个核对:
A. 窗口起点敏感:同一只股票,K 线从不同日子开始截,app 买没买样本会不会变?阶跃那根突破越过的峰有多老?
B. 反事实(只在研究代码里改企稳状态机,不动正式代码):
   B1. 「追涨」倍数放宽到 3.1(参数层能不能凑过 CRNC a / RGTI a);
   B2. 支撑取「新平台最低收盘」且收段不上抬(给状态机加一种支撑取法能不能救 CRNC c)。
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402

import path2_apps.new_step as app  # noqa: E402
from path2.eval import _resolve_end_events  # noqa: E402
from path2.calc.atr import calculate_tr_median  # noqa: E402

s, _ = load_state()
p = app.load_params()
meta = app.eval_meta(p)


def bought(win, params):
    res = app.analyze(win, params)
    days = set()
    for h in res.hits:
        for e in _resolve_end_events(h, meta["end_node"]):
            days.update(str(win["date"].iloc[i].date()) for i in range(e.start_idx, e.end_idx + 1))
    return res, days


print("## A. 窗口起点敏感(全段 = compare 口径)")
full = {}
for c in s["charts"]:
    sym = c["symbol"]
    W = load_win(sym)
    smp = [x["date"] for x in c["samples"] if (sym, x["date"]) not in EXCLUDED_SAMPLES]
    first_box = min(b["start"] for b in c["boxes"])
    starts = {"全段": None}
    for lab, days in (("框起点前100天", 100), ("框起点前200天", 200), ("框起点前1年", 365), ("框起点前2年", 730)):
        starts[lab] = str((pd.Timestamp(first_box) - pd.Timedelta(days=days)).date())
    line = []
    for lab, st in starts.items():
        win = W if st is None else W[W["date"] >= pd.Timestamp(st)].reset_index(drop=True)
        res, days = bought(win, p)
        if st is None:
            full[sym] = (res, win)
        got = "".join("买" if d in days else "空" for d in smp)
        line.append(f"{lab}:{got}")
    print(f"{sym} 样本 {smp}: " + " | ".join(line))

print("\n## A2. 全段口径下,进 hit 的阶跃突破越过的峰有多老(根数,对照首部缓冲 %d 根)" % meta["head_buffer_trading_days"])
for sym, (res, win) in full.items():
    seen = set()
    for h in res.hits:
        for bo in h.node_index["burst"].members:
            if bo.instance_id in seen:
                continue
            seen.add(bo.instance_id)
            ages = [bo.end_idx - pk.peak_idx for pk in bo.broken_refs]
            regs = [bo.end_idx - pk.start_idx for pk in bo.broken_refs]
            print(f"  {sym} bo {i2d(win, bo.end_idx)} 越过峰 {len(ages)} 个:峰位距今 {ages} 根,峰登记距今 {regs} 根")

print("\n## B1. 追涨倍数 max_rise_k 1.5 → 3.1(全段口径)")
p31 = dataclasses.replace(p, tb=dataclasses.replace(p.tb, max_rise_k=3.1))
tot0 = tot1 = 0
for c in s["charts"]:
    sym = c["symbol"]
    win = full[sym][1]
    smp = [x["date"] for x in c["samples"] if (sym, x["date"]) not in EXCLUDED_SAMPLES]
    _, d0 = bought(win, p)
    _, d1 = bought(win, p31)
    tot0 += len(d0); tot1 += len(d1)
    print(f"  {sym}: 样本 {''.join('买' if d in d0 else '空' for d in smp)} → {''.join('买' if d in d1 else '空' for d in smp)};"
          f" 全历史买入日 {len(d0)} → {len(d1)}")
print(f"  合计全历史买入日 {tot0} → {tot1}")


print("\n## B2. CRNC c:支撑取新平台最低收盘(11-26 收 6.47)、收段不上抬,逐根重放 11-21 那台机器")


def machine(closes, opens, vol, bo_idx, gbot, k=1.5, K=1, max_span=60, ratchet=True):
    """照 enumerate_segments_v4 的分支(同 tb_trace.py),多一个开关:ratchet=False 时收段不抬支撑。"""
    n = len(closes); end = min(bo_idx + max_span, n - 1)
    state, peak, trough, cnt, enter, buys = "UP", closes[bo_idx], np.inf, 0, -1, []
    for i in range(bo_idx + 1, end + 1):
        c = closes[i]; v = vol[i]
        if c < gbot:
            break
        if state == "UP":
            peak = max(peak, c)
            if c < opens[i] or c < closes[i - 1]:
                state, trough, cnt = "DOWN", c, 0
        elif state == "DOWN":
            if c < trough:
                trough, cnt = c, 0
            elif v == v and c > trough + k * v:
                state = "UP"
            else:
                cnt += 1
                if cnt >= K:
                    state = "STABLE"
        else:
            if (v == v and c > trough + k * v) and c > peak:
                if ratchet:
                    gbot = trough
                state = "UP"; peak = max(peak, c)
            elif c < trough:
                state, trough, cnt = "DOWN", c, 0
        if state == "STABLE":
            buys.append(i)
    return buys


win = full["CRNC"][1]
cl = win["close"].values.astype(float); op = win["open"].values.astype(float)
vol = calculate_tr_median(win["high"], win["low"], win["close"], 14).values
bo = d2i(win, "2024-11-21")
low = cl[d2i(win, "2024-11-26")]  # 用实际收盘值,避免 6.47 浮点比较误判跌破
for lab, g, r in (("原版:支撑=阶跃前一根收盘、收段上抬", cl[bo - 1], True),
                  ("支撑=新平台最低收盘 6.47、收段上抬", low, True),
                  ("支撑=新平台最低收盘 6.47、收段不上抬", low, False)):
    b = machine(cl, op, vol, bo, g, ratchet=r)
    ds = [i2d(win, i) for i in b]
    print(f"  {lab}: 买入日 {len(ds)} 个;样本 11-29/12-05/12-13 → "
          f"{''.join('买' if d in ds else '空' for d in ('2024-11-29', '2024-12-05', '2024-12-13'))};末个买入日 {ds[-1] if ds else '-'}")
