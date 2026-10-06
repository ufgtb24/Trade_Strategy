"""收盘判穿越（v3）与框架盘中判穿越的差别核查（临时研究脚本）。

范围：fold2 搜索段的 256 只股票普通池（买点 2024-07-01..2025-04-30，标签尾部至 2025-06-30），
该范围已作为 bottom_burst v3 开发数据登记（docs/sample_usage/bottom_burst.v3.jsonl）。
行情在任何计算前裁到 2024-01-01..2025-06-30。H=40、k=5。
输出 repro/close_vs_intraday_results.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from path2.eval import daily_first_passage  # noqa: E402

DATA = ROOT / "docs/research/2026-10-02_v3-bb-training-calibration"
PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT = Path(__file__).with_name("close_vs_intraday_results.json")


def main():
    pool = pd.read_parquet(DATA / "fold2_search_baseline.parquet")
    cand = pd.read_parquet(DATA / "fold2_search_candidates.parquet")
    pool["date"] = pd.to_datetime(pool.date)
    pieces = []
    for sym in sorted(pool.symbol.unique()):
        raw = pd.read_pickle(PKL / f"{sym}.pkl")
        dates = pd.to_datetime(raw["date"] if "date" in raw else raw.index)
        dates = pd.DatetimeIndex(dates).tz_localize(None) if getattr(dates, "tz", None) else pd.DatetimeIndex(dates)
        keep = (dates >= "2024-01-01") & (dates <= "2025-06-30")
        df = raw.loc[keep].copy().reset_index(drop=True)
        df["date"] = dates[keep].normalize()
        lab = daily_first_passage(df, pd.Timestamp("2024-07-01"), pd.Timestamp("2025-04-30"), horizon=40, k=5.0)
        lab["symbol"] = sym
        pieces.append(lab[["symbol", "date", "M", "up", "down", "both", "none"]])
    intr = pd.concat(pieces, ignore_index=True)
    m = pool.merge(intr, on=["symbol", "date"], suffixes=("_c", "_i"))
    m["dir_c"] = m.up_c - m.down_c
    m["state_i"] = np.select([m.up_i == 1, m.down_i == 1, m.both_i == 1], ["up", "down", "both"], "none")
    m["state_c"] = np.select([m.up_c == 1, m.down_c == 1], ["up", "down"], "none")
    res = {
        "rows_pool": len(pool), "rows_matched": len(m),
        "M_max_abs_diff": float((m.M_c - m.M_i).abs().max()),
        "crosstab_close_rows_intraday_cols": pd.crosstab(m.state_c, m.state_i).to_dict(),
        "resolved_close": float(1 - m.none_c.mean()), "resolved_intraday": float(1 - m.none_i.mean()),
        "both_intraday": float(m.both_i.mean()),
        "opposite_sign": float(((m.state_c == "up") & (m.state_i == "down")).mean() +
                               ((m.state_c == "down") & (m.state_i == "up")).mean()),
    }
    # 同一批普通池日的方向均值（盘中 both 记 0）
    m["dir_i"] = m.up_i - m.down_i
    res["pool_dir_close"], res["pool_dir_intraday"] = float(m.dir_c.mean()), float(m.dir_i.mean())
    m["mpct"] = m.groupby("date").M_c.rank(pct=True)
    m["mq"] = np.minimum((m.mpct * 5).astype(int), 4)
    res["by_M_quintile"] = m.groupby("mq").agg(none_c=("none_c", "mean"), none_i=("none_i", "mean"),
                                               both_i=("both_i", "mean"), dir_c=("dir_c", "mean"),
                                               dir_i=("dir_i", "mean")).round(4).to_dict()
    # 候选（原参数）买点
    out = {}
    for cid in ("base", "burst.gap_max_0", "joint_08"):
        rows = cand[cand.candidate_id == cid].copy()
        rows["date"] = pd.to_datetime(rows.date)
        r = rows.merge(m[["symbol", "date", "state_i", "dir_i", "both_i", "none_i"]], on=["symbol", "date"])
        r["dir_c"] = r.up - r.down
        out[cid] = {"N": len(r), "pooled_close": float(r.dir_c.mean()), "pooled_intraday": float(r.dir_i.mean()),
                    "none_close": float(r.none.mean()), "none_intraday": float(r.none_i.mean()),
                    "both_intraday": float(r.both_i.mean())}
    res["candidates"] = out
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    print(json.dumps(res, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
