"""09 目标池票 · 第二步：几种候选池子各年有多少只股票、多少个股票日（不读任何买点之后的涨跌）。

池子 = 当天就知道的条件：
  非普通股剔除：按证券名称（09-securities.py）判为票据债券、优先股、结构化信托、认股权证、单位、权利的整只剔除；
               封闭式基金与 SPAC 壳另作一档（ext），看剔不剔差多少。
  成交额下限：20 日成交额中位 ≥ 100 万 / 200 万 / 500 万美元。
  价格上限：收盘 ≤ 20 / ≤ 10 美元。当时价格还原不了，这里用复权收盘近似（偏差方向见研究文件）。
  成交额上限（去大盘股）：20 日成交额中位 ≤ 1 亿美元，另给 5000 万一档。
另核对：「平时波动」极低能不能代替名称规则认出非普通股。

输出：scratchpad/09/pool_masks.npz（每个池子一张 [股票, 交易日] 布尔表）与本目录 09-pools_out.txt
运行：uv run python .scratch/selection-pattern/scripts/09-pools.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(__file__).resolve().parent
USER_EXCL = {"debt", "preferred", "structured", "warrant", "unit", "right"}
EXT_EXCL = {"cef", "spac_shell"}


def pool_defs():
    """(名称, 成交额下限, 价格上限, 成交额上限, 剔除集合)。"""
    defs = []
    for lo in (1e6, 2e6, 5e6):
        defs.append((f"dv{lo/1e6:g}M", lo, None, None, "ext"))
        defs.append((f"dv{lo/1e6:g}M_cap100M", lo, None, 1e8, "ext"))
        for px in (20, 10):
            defs.append((f"dv{lo/1e6:g}M_px{px}", lo, px, None, "ext"))
            for hi in (1e8, 5e7):
                defs.append((f"dv{lo/1e6:g}M_px{px}_cap{hi/1e6:g}M", lo, px, hi, "ext"))
    defs.append(("dv1M_px20_cap100M_userexcl", 1e6, 20, 1e8, "user"))
    defs.append(("dv2M_px20_cap100M_userexcl", 2e6, 20, 1e8, "user"))
    defs.append(("all_ext", 0, None, None, "ext"))
    defs.append(("all", 0, None, None, "none"))
    return defs


def main():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, calendar = z["symbols"], pd.DatetimeIndex(z["calendar"])
    close, dv, M, Mh = z["close"], z["dv20"], z["M"], z["Mh"]
    sec = pd.read_csv(SCR / "09/securities.csv").set_index("symbol").reindex(symbols)
    cls = sec["cls"].fillna("unknown").to_numpy()
    excl = {"none": np.zeros(len(symbols), bool),
            "user": np.isin(cls, list(USER_EXCL)),
            "ext": np.isin(cls, list(USER_EXCL | EXT_EXCL))}
    have = np.isfinite(dv) & np.isfinite(M) & (M > 0)
    lines = []
    w = lines.append

    # —— 核对：平时波动能否认出非普通股（最新一天、Mh 有值的股票）
    last = np.isfinite(Mh[:, -1])
    w("== 核对：「平时波动」（过去 250 天当天波动尺度 M 的中位数）按证券类别的分布，最新一天 ==")
    df = pd.DataFrame({"cls": cls[last], "Mh": Mh[last, -1], "dv": dv[last, -1], "px": close[last, -1]})
    w(df.groupby("cls")["Mh"].describe(percentiles=[.1, .5, .9]).round(4).to_string())
    for thr in (0.005, 0.0075, 0.01):
        low = df["Mh"] < thr
        w(f"  平时波动 < {thr:.2%}：{low.sum()} 只，其中名称判为非普通股（含基金与 SPAC 壳）"
          f" {df.loc[low, 'cls'].isin(USER_EXCL | EXT_EXCL).sum()}；"
          f"非普通股里被它认出的比例 {low[df['cls'].isin(USER_EXCL | EXT_EXCL)].mean():.0%}；"
          f"误伤的普通股 / ADR / MLP {df.loc[low, 'cls'].isin(['common', 'adr', 'mlp', 'unknown']).sum()}")
    w("")

    # —— 各池子按年计数
    years = calendar.year.to_numpy()
    masks = {}
    rows = []
    for name, lo, px, hi, ex in pool_defs():
        m = have & (dv >= lo) & ~excl[ex][:, None]
        if px is not None:
            m &= close <= px
        if hi is not None:
            m &= dv <= hi
        masks[name] = m
        for y in range(2021, 2027):
            cols = years == y
            if not cols.any():
                continue
            sub = m[:, cols]
            per_day = sub.sum(0)
            rows.append(dict(pool=name, year=y, days=int(cols.sum()), stocks_per_day=float(per_day.mean()),
                             distinct=int(sub.any(1).sum()), stock_days=int(sub.sum())))
    t = pd.DataFrame(rows)
    np.savez_compressed(SCR / "09/pool_masks.npz", **masks)
    w("== 各池子：每天平均几只 / 当年出现过几只不同股票 / 股票日（2021 只含 10-08 起，2026 截到 10-05）==")
    piv = t.pivot(index="pool", columns="year", values="stocks_per_day").round(0)
    w("每天平均只数：\n" + piv.to_string())
    w("当年出现过的不同股票：\n" + t.pivot(index="pool", columns="year", values="distinct").to_string())
    w("股票日（千）：\n" + (t.pivot(index="pool", columns="year", values="stock_days") / 1000).round(0).to_string())
    w("")

    # —— 剔除了什么：在 dv1M_px20 口径下，各类非普通股占的股票日
    base = have & (dv >= 1e6) & (close <= 20)
    sd = pd.Series(base.sum(1), index=cls).groupby(level=0).sum()
    w("== 成交额 ≥100 万、复权收盘 ≤20 的股票日里，各证券类别占比 ==")
    w((sd / sd.sum()).round(4).sort_values(ascending=False).to_string())
    w("")
    # —— 上限去掉了谁：最新一天被 1 亿上限挡掉的 ≤20 美元股票
    lastm = base[:, -1] & (dv[:, -1] > 1e8) & ~excl["ext"]
    w(f"最新一天复权收盘 ≤20、成交额 >1 亿美元（被上限挡掉）的有 {lastm.sum()} 只，例："
      + ", ".join(symbols[lastm][:40]))
    out = "\n".join(lines)
    print(out)
    (HERE / "09-pools_out.txt").write_text(out + "\n")
    t.to_csv(HERE / "09-pools_counts.csv", index=False)


if __name__ == "__main__":
    main()
