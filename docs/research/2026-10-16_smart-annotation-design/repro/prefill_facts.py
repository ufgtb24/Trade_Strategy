"""可行性试验:从「框选段 + 买点」用确定性计算自动起草一张事实单(临时脚本,研究用)。

只读买点当天及以前的数据(读入后立刻截断,且硬性断言不晚于 2025-12-31),
不读任何买点之后的涨跌。所有阈值是默认值,待验证。

用法:uv run python docs/research/2026-10-16_smart-annotation-design/repro/prefill_facts.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from path2.runner import run, run_bundle  # noqa: E402
from path2.atoms.breakout import BODetector  # noqa: E402
from path2.atoms.distribution import DistributionDetector  # noqa: E402
from path2.atoms.platform import PlatformDetector  # noqa: E402
from path2.atoms.trend import TrendSegmentDetector  # noqa: E402
from path2.calc.volume import calculate_vol_ratio  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from docs_research_loader import load  # noqa: E402  (读入即截到买点,且不晚于 2025-12-31)

SWING_SIDE = 10          # 框内峰:两侧各至少这么多根更低(待验证)
VOL_RUN_MIN = 3.0        # 放量段:量比 ≥ 此值(待验证)
VOL_RUN_GAP = 2          # 放量段之间相隔 ≤ 此天数就合并(待验证)
STEADY_N = 20            # 「稳定上涨」看买点前多少根(待验证)


def d(df, i):
    return str(df.index[i].date())


def swing_highs(series: np.ndarray, lo: int, hi: int, side: int):
    """[lo, hi] 内的局部最高点:两侧各 side 根(不越过 hi,买点之后的数据不存在)都更低。"""
    out = []
    for i in range(lo, hi + 1):
        a, b = max(0, i - side), min(hi, i + side)
        if b - i < min(side, 3):       # 右侧根数不足:贴近买点的高点当时还不能确认是峰
            continue
        if series[i] >= series[a:b + 1].max():
            out.append(i)
    return out


def vol_runs(vr: np.ndarray, lo: int, hi: int):
    runs, cur = [], None
    for i in range(lo, hi + 1):
        if np.isfinite(vr[i]) and vr[i] >= VOL_RUN_MIN:
            if cur and i - cur[1] <= VOL_RUN_GAP + 1:
                cur[1] = i
            else:
                cur = [i, i]
                runs.append(cur)
    return runs


def facts(symbol, range_start, range_end, buy_date):
    t0 = time.time()
    buy = pd.Timestamp(buy_date)
    df = load(symbol, buy)
    n = len(df)
    ib = n - 1
    if df.index[ib] != buy:
        raise ValueError(f"{symbol} 买点 {buy_date} 不是交易日")
    rs = int(df.index.searchsorted(pd.Timestamp(range_start)))
    re_ = min(int(df.index.searchsorted(pd.Timestamp(range_end), side="right")) - 1, ib)
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    vr = calculate_vol_ratio(df["volume"], 63).to_numpy()
    out = {"symbol": symbol, "box": [d(df, rs), d(df, re_)], "buy": d(df, ib),
           "box_after_buy_days": int(max(0, (pd.Timestamp(range_end) > buy) and
                                         len(pd.bdate_range(buy, range_end)) - 1))}

    # 背景:涨前位置
    hi250 = h[max(0, ib - 249):ib + 1].max()
    out["背景"] = {
        "离一年最高价": round(c[ib] / hi250 - 1, 3),
        "近60日涨幅": round(c[ib] / c[ib - 60] - 1, 3) if ib >= 60 else None,
        "框起点前120日涨跌": round(c[rs] / c[max(0, rs - 120)] - 1, 3),
    }

    # 框内峰:按最高价与按收盘价分别找,再看买点收盘越过了哪几个
    peaks = {}
    for name, ser in (("按最高价", h), ("按收盘价", c)):
        idx = swing_highs(ser, rs, ib - 1, SWING_SIDE)
        idx = sorted(idx, key=lambda i: -ser[i])[:4]
        peaks[name] = [{"日期": d(df, i), "峰价": round(ser[i], 3),
                        "买点收盘已越过": bool(c[ib] > ser[i]),
                        "首次越过日": next((d(df, j) for j in range(i + 1, ib + 1) if c[j] > ser[i]), None)}
                       for i in sorted(idx)]
    out["框内的峰"] = peaks

    # path2 BODetector(默认参数)在框内产出的 bo,两种突破口径
    bo_out = {}
    for meas in ("high", "close"):
        bundle = run_bundle(BODetector(breakout_measure=meas), df)
        bos = [e for e in bundle["bo"] if rs <= e.start_idx <= ib]
        bo_out[f"突破看{meas}"] = [{"日期": d(df, e.start_idx), "一次越过峰数": e.pk_count,
                                    "峰最远距今根数": e.peak_age_max,
                                    "量比": None if e.vol_ratio is None else round(e.vol_ratio, 1)}
                                   for e in bos][-6:]
    out["path2突破(默认参数,框内最后几根)"] = bo_out

    # 成交量
    runs = vol_runs(vr, rs, ib)
    runs = sorted(runs, key=lambda r: -np.nanmax(vr[r[0]:r[1] + 1]))[:3]
    last3 = v[ib - 2:ib + 1].mean()
    out["成交量"] = {
        "放量段(量比≥3,最强三段)": [{"起": d(df, a), "止": d(df, b),
                                   "最大量比": round(float(np.nanmax(vr[a:b + 1])), 1),
                                   "平均量比": round(float(np.nanmean(vr[a:b + 1])), 1)}
                                  for a, b in sorted(runs)],
        "买点当天量比": None if not np.isfinite(vr[ib]) else round(float(vr[ib]), 2),
        "买点前三天均量÷最强放量段均量": (round(float(last3 / v[runs[0][0]:runs[0][1] + 1].mean()), 2)
                                    if runs else None),
    }

    # 稳定上涨:买点前 STEADY_N 根
    a = max(rs, ib - STEADY_N)
    seg = c[a:ib + 1]
    run_max = np.maximum.accumulate(seg)
    x = np.arange(len(seg))
    r2 = np.corrcoef(x, np.log(seg))[0, 1] ** 2 if len(seg) > 2 else None
    out["买点前一段走势"] = {
        "根数": int(len(seg) - 1),
        "涨幅": round(seg[-1] / seg[0] - 1, 3),
        "收阳比例": round(float((np.diff(seg) > 0).mean()), 2),
        "期间最大回撤(收盘)": round(float((seg / run_max - 1).min()), 3),
        "直线度R2": None if r2 is None else round(float(r2), 2),
    }

    # 派发:path2 派发事件 + 宽口径「放量阴线」
    dist = [e for e in run(DistributionDetector(), df) if rs <= e.start_idx <= ib]
    wide = [i for i in range(rs, ib + 1) if c[i] < o[i] and np.isfinite(vr[i]) and vr[i] >= 3]
    worst = int(np.argmin(c[rs + 1:ib + 1] / c[rs:ib] - 1)) + rs + 1 if ib > rs else None
    out["派发"] = {
        "path2派发事件(默认参数)": [{"日期": d(df, e.start_idx), "量比": round(e.vol_ratio, 1),
                                 "上影占比": round(e.upper_shadow_ratio, 2)} for e in dist],
        "放量阴线(量比≥3,宽口径)": [d(df, i) for i in wide][-6:],
        "框内单日最大跌幅": None if worst is None else {"日期": d(df, worst),
                                                    "跌幅": round(c[worst] / c[worst - 1] - 1, 3)},
    }

    # 平台段、走势区段
    plats = [e for e in run(PlatformDetector(), df) if e.end_idx >= rs and e.start_idx <= ib]
    out["平台段(默认参数)"] = [{"起": d(df, e.start_idx), "止": d(df, e.end_idx),
                             "振幅": round(e.range_pct, 3)} for e in plats][-4:]
    trs = [e for e in run(TrendSegmentDetector(), df) if e.end_idx >= rs]
    out["走势区段(框内)"] = [{"起": d(df, e.start_idx), "止": d(df, e.end_idx), "态": e.regime}
                           for e in trs][-6:]

    # 买点当天发生了什么(触发条件候选)
    trig = []
    for meas, ev_list in bo_out.items():
        if ev_list and ev_list[-1]["日期"] == d(df, ib):
            trig.append(f"当天是 path2 突破({meas})")
    for name, plist in peaks.items():
        newly = [p["日期"] for p in plist if p["首次越过日"] == d(df, ib)]
        if newly:
            trig.append(f"当天收盘首次越过框内峰({name}):{newly}")
    hh = h[max(0, ib - 10):ib].max()
    if c[ib] > c[max(0, ib - 20):ib].max():
        trig.append("收盘创 20 日新高")
    pull = l[max(0, ib - 5):ib].min() / hh - 1
    if pull < -0.05 and c[ib] > h[ib - 1]:
        trig.append(f"前 5 天从近 10 日高点回落 {pull:.0%} 后,当天收盘越过前一天最高价(回落收回)")
    gap = o[ib] / c[ib - 1] - 1
    if abs(gap) >= 0.03:
        trig.append(f"当天跳空 {gap:+.1%}")
    if np.isfinite(vr[ib]) and vr[ib] < 0.7:
        trig.append(f"当天缩量(量比 {vr[ib]:.2f})")
    out["买点当天发生了什么"] = trig or ["(没有匹配到任何预置触发条件)"]
    out["耗时秒"] = round(time.time() - t0, 3)
    return out


def main():
    cases = [("QMMM", "2025-02-28", "2025-07-14", "2025-07-14"),   # 用户第一张标注
             ("QMMM", "2025-02-28", "2025-07-08", "2025-07-08")]   # 用户提到的另一个买点
    # 再挑几条清单条目,框 = 决策日前 90 个交易日,买点 = 清单决策日(只读当天及以前)
    lst = json.load(open(ROOT / "outputs/chart_workflow/lists/r002-bigmoves-2025.json"))
    for it in lst["items"][1:9]:
        t = pd.Timestamp(it["t"])
        cases.append((it["symbol"], str((t - pd.tseries.offsets.BDay(90)).date()), it["t"], it["t"]))
    res = []
    for cs in cases:
        try:
            res.append(facts(*cs))
        except Exception as e:  # noqa: BLE001
            res.append({"case": cs, "error": repr(e)})
    outp = Path(__file__).with_name("prefill_facts_out.json")
    outp.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res[:2], ensure_ascii=False, indent=1))
    print("耗时:", [r.get("耗时秒") for r in res])
    print("各条触发候选:")
    for r in res[2:]:
        print(r.get("symbol"), r.get("buy"), r.get("买点当天发生了什么", r.get("error")))


if __name__ == "__main__":
    main()
