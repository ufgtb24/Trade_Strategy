"""可行性试验:「买点这一天和这只股票自己过去 60 天比,最不寻常的三件事」(临时脚本,研究用)。

只读买点当天及以前(读入后立刻截断,断言不晚于 2025-12-31),不读任何后来的涨跌。
每项指标对本股过去 60 天(不含当天)标准化,按偏离程度排名。指标与窗口均为默认值,待验证。

用法:uv run python docs/research/2026-10-16_smart-annotation-design/repro/anomaly_rank.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from docs_research_loader import load  # noqa: E402  (读入即截到买点,且不晚于 2025-12-31)

LOOK = 60


def daily_measures(df: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c, v = (df[k] for k in ("open", "high", "low", "close", "volume"))
    rng = (h - l).replace(0, np.nan)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    m = pd.DataFrame({
        "成交量(取对数)": np.log(v.replace(0, np.nan)),
        "当天振幅(真实波幅/收盘)": tr / c,
        "当天涨跌": c / pc - 1,
        "开盘跳空": o / pc - 1,
        "实体占全天振幅": (c - o).abs() / rng,
        "收在当天区间的位置(1=最高)": (c - l) / rng,
        "上影占比": (h - np.maximum(o, c)) / rng,
        "下影占比": (np.minimum(o, c) - l) / rng,
        "离20日均线": c / c.rolling(20).mean() - 1,
        "离50日均线": c / c.rolling(50).mean() - 1,
        "近5日振幅÷近60日平均振幅": (h.rolling(5).max() - l.rolling(5).min()) / c
                                  / ((h - l) / c).rolling(60).mean() / 5,
        "离20日最高收盘": c / c.rolling(20).max() - 1,
    })
    return m


def rank(symbol, buy_date, top=3):
    df = load(symbol, pd.Timestamp(buy_date))
    m = daily_measures(df)
    hist = m.iloc[-LOOK - 1:-1]
    today = m.iloc[-1]
    z = (today - hist.mean()) / hist.std().replace(0, np.nan)
    z = z.dropna()
    order = z.abs().sort_values(ascending=False).index[:top]
    return [{"指标": k, "当天值": round(float(today[k]), 3),
             "过去60天均值": round(float(hist[k].mean()), 3),
             "偏离几个标准差": round(float(z[k]), 1)} for k in order]


def main():
    cases = [("QMMM", "2025-07-14"), ("QMMM", "2025-07-08")]
    lst = json.load(open(ROOT / "outputs/chart_workflow/lists/r002-bigmoves-2025.json"))
    cases += [(it["symbol"], it["t"]) for it in lst["items"][1:9]]
    for s, b in cases:
        print(s, b)
        for r in rank(s, b):
            print("   ", r)


if __name__ == "__main__":
    main()
