"""02 分辨力研究 · 买点长相统计（只看位置）：每年多少买点、连着几天、同一只票命中几回、按日期多扎堆。

输入 CACHE/buys_<app>.csv 与 CACHE/meta.npz；输出打印 + scripts/02-structure-stats.txt（追加）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/02cache")
OUT = Path(__file__).resolve().parent / "02-structure-stats.txt"


def episodes(buys: pd.DataFrame, calendar: np.ndarray) -> pd.DataFrame:
    """把同一只股票在交易日历上相邻的买点日并成一段（run）。"""
    b = buys.copy()
    b["d"] = np.searchsorted(calendar, pd.to_datetime(b["date"]).to_numpy())
    b = b.sort_values(["symbol", "d"])
    new = (b["symbol"] != b["symbol"].shift()) | (b["d"] != b["d"].shift() + 1)
    b["run"] = new.cumsum()
    return b


def describe(app: str) -> str:
    meta = np.load(CACHE / "meta.npz", allow_pickle=True)
    calendar = meta["calendar"]
    buys = pd.read_csv(CACHE / f"buys_{app}.csv")
    b = episodes(buys, calendar)
    runs = b.groupby("run").agg(symbol=("symbol", "first"), start=("d", "min"), length=("d", "size"))
    per_stock_runs = runs.groupby("symbol").size()
    per_stock_days = b.groupby("symbol").size()
    year = pd.to_datetime(b["date"]).dt.year
    daily = b.groupby("d").size().reindex(range(len(calendar)), fill_value=0)
    month = pd.to_datetime(pd.Series(calendar[daily.index])).dt.to_period("M").to_numpy()
    monthly = daily.groupby(month).sum()
    # 买点按日期的集中度：把日期按买点数从多到少排，前 10% 的日期占全部买点的比例
    srt = np.sort(daily.to_numpy())[::-1]
    top10 = srt[: max(1, len(srt) // 10)].sum() / srt.sum()
    # 有效独立日期数（参与率）：(Σn_d)^2 / Σn_d^2
    eff_dates = srt.sum() ** 2 / (srt.astype(float) ** 2).sum()
    eff_stocks = per_stock_days.sum() ** 2 / (per_stock_days.astype(float) ** 2).sum()
    lines = [
        f"== {app} (现役参数, 全部 5778 只, 2021-10..2026-10 检测) ==",
        f"买点日 {len(b):,}  股票 {b['symbol'].nunique()}  连续段 {len(runs):,}",
        "每年买点日: " + ", ".join(f"{y}:{n}" for y, n in year.value_counts().sort_index().items()),
        f"连续段长度(天): 均值 {runs['length'].mean():.2f}  中位 {runs['length'].median():.0f}  "
        f"p90 {runs['length'].quantile(.9):.0f}  max {runs['length'].max()}  "
        f"按买点日加权的平均段长 {(runs['length'] ** 2).sum() / runs['length'].sum():.2f}",
        f"每只股票: 段数均值 {per_stock_runs.mean():.2f} 中位 {per_stock_runs.median():.0f} p90 {per_stock_runs.quantile(.9):.0f} max {per_stock_runs.max()}; "
        f"买点日均值 {per_stock_days.mean():.1f} 中位 {per_stock_days.median():.0f} p90 {per_stock_days.quantile(.9):.0f} max {per_stock_days.max()}",
        f"有效股票数 (Σn)^2/Σn^2 = {eff_stocks:.0f}",
        f"日期: 有买点的交易日占比 {(daily > 0).mean():.2f}；买点最多的 10% 日期占全部买点 {top10:.2f}；"
        f"有效日期数 {eff_dates:.0f} / {len(calendar)}",
        f"月度买点数: 中位 {monthly.median():.0f}  p10 {monthly.quantile(.1):.0f}  p90 {monthly.quantile(.9):.0f}  max {monthly.max()}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    text = "\n\n".join(describe(app) for app in sys.argv[1:])
    print(text)
    with OUT.open("a") as f:
        f.write(text + "\n\n")
