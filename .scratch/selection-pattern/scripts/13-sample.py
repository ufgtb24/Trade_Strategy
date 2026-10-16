"""13 外部信息 · 第一步：从目标池里抽样本股票（不读任何涨跌）。

目标池沿用「目标池里的分辨力和幸存者偏差有多大」的默认池：普通股（另剔封闭式基金与 SPAC 壳）、
20 日成交额中位 200 万～1 亿美元、收盘 ≤ 20 美元（复权价近似）。池子表来自那张票留下的 scratchpad/09/pool_masks.npz。
注意：抽样时误用了不剔封闭式基金与 SPAC 壳的那版池子（POOL），已下载的样本保持不变；
另写出正确池子（POOL_EXT）的曾在池名单，后续统计一律只算落在正确池子里的样本（正确池子是抽样池子的子集，
子集上的随机样本仍是随机样本）。

产出：
  scratchpad/13/pool_ever.csv —— 2024-01-02 起任何一天在池里的股票，及在池天数
  scratchpad/13/sample_*.txt —— 三个日期各抽 8 只（随机种子固定）、以及「在池股票」随机 150 只（覆盖率普查用）
  本目录 13-sample_out.txt
运行：uv run python .scratch/selection-pattern/scripts/13-sample.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(__file__).resolve().parent
POOL = "dv2M_px20_cap100M_userexcl"
POOL_EXT = "dv2M_px20_cap100M"


def main():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, cal = z["symbols"], pd.DatetimeIndex(z["calendar"])
    m = np.load(SCR / "09/pool_masks.npz", allow_pickle=True)[POOL]
    rng = np.random.default_rng(13)
    out = []
    w = out.append
    since = cal >= "2024-01-02"
    days_in = m[:, since].sum(1)
    ever = days_in > 0
    pe = pd.DataFrame({"symbol": symbols[ever], "days_in_pool": days_in[ever]})
    pe.to_csv(SCR / "13/pool_ever.csv", index=False)
    w(f"池子 {POOL}：2024-01-02 至 {cal[-1].date()} 曾在池的股票 {ever.sum()} 只")
    for d in ("2024-01-02", "2025-06-02", "2026-09-01"):
        i = cal.get_indexer([pd.Timestamp(d)], method="bfill")[0]
        syms = symbols[m[:, i]]
        pick = sorted(rng.choice(syms, 8, replace=False))
        (SCR / f"13/sample_{d}.txt").write_text("\n".join(pick))
        w(f"{cal[i].date()} 在池 {len(syms)} 只，抽样：{', '.join(pick)}")
    big = sorted(rng.choice(pe["symbol"].to_numpy(), 150, replace=False))
    (SCR / "13/sample_census150.txt").write_text("\n".join(big))
    w(f"普查样本：从曾在池股票里随机 150 只")
    mx = np.load(SCR / "09/pool_masks.npz", allow_pickle=True)[POOL_EXT]
    dx = mx[:, since].sum(1)
    pd.DataFrame({"symbol": symbols[dx > 0], "days_in_pool": dx[dx > 0]}).to_csv(SCR / "13/pool_ever_ext.csv", index=False)
    cen = set(big)
    w(f"正确池子 {POOL_EXT}（剔封闭式基金与 SPAC 壳）曾在池 {(dx > 0).sum()} 只；普查样本中落在其中的 {len(cen & set(symbols[dx > 0]))} 只")
    (HERE / "13-sample_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
