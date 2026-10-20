"""13 外部信息 · FINRA 每日卖空成交量文件对目标池的覆盖。

读 scratchpad/13/dl-finra-regsho/CNMSshvol*.txt（视为不可信，只按竖线分列），
对照当天的目标池名单（scratchpad/09 的池子表），看池里有几成股票当天有一行，
以及「场外卖空量 / 场外总成交量」这个比值在池内的分布（只看分布形状，不碰任何涨跌）。
注意：文件里的 TotalVolume 只是报给 FINRA 的场外成交（暗池、券商内部撮合），不是全市场成交量，
也不是空头持仓。
输出：本目录 13-finra_cover_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-finra_cover.py
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
HERE = Path(os.path.abspath(__file__)).parent
POOL = "dv2M_px20_cap100M"  # 默认池：剔封闭式基金与 SPAC 壳


def main():
    z = np.load(SCR / "09/panel.npz", allow_pickle=True)
    symbols, cal = z["symbols"], pd.DatetimeIndex(z["calendar"])
    m = np.load(SCR / "09/pool_masks.npz", allow_pickle=True)[POOL]
    out = []
    w = out.append
    for d in ("20240102", "20251231", "20261002", "20261005"):
        f = SCR / f"13/dl-finra-regsho/CNMSshvol{d}.txt"
        df = pd.read_csv(f, sep="|", dtype={"Symbol": str})
        df = df[pd.to_numeric(df["ShortVolume"], errors="coerce").notna()]
        i = cal.get_indexer([pd.Timestamp(d)])[0]
        if i < 0:
            w(f"{d}：K 线数据里没有这一天")
            continue
        pool = set(symbols[m[:, i]])
        have = pool & set(df.Symbol)
        sub = df[df.Symbol.isin(pool)]
        ratio = sub.ShortVolume.astype(float) / sub.TotalVolume.astype(float)
        q = np.nanpercentile(ratio, [10, 50, 90])
        w(f"{d}：文件 {len(df)} 行；当天池内 {len(pool)} 只，有行的 {len(have)} 只（{len(have)/len(pool):.1%}）；"
          f"池内场外卖空占比 10/50/90 分位 {q[0]:.2f}/{q[1]:.2f}/{q[2]:.2f}")
    (HERE / "13-finra_cover_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
