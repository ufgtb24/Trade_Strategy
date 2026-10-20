"""13 外部信息 · FINRA 空头持仓（每月两次）对目标池的覆盖，以及修订标记有多常见。

读 scratchpad/13/dl-finra-si/si_<结算日>_<偏移>.json（FINRA 公开查询接口免 key 下载，视为不可信，只取字段），
对照最近的交易日的目标池名单。只看覆盖与修订标记，不碰任何涨跌。
输出：本目录 13-finra_si_cover_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/13-finra_si_cover.py
"""
from __future__ import annotations

import glob
import json
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
    for d in ("2024-01-12", "2026-09-15"):
        rows = []
        for f in sorted(glob.glob(str(SCR / f"13/dl-finra-si/si_{d}_*.json"))):
            try:
                x = json.loads(Path(f).read_text())
            except Exception:
                continue
            if isinstance(x, list):
                rows += x
        df = pd.DataFrame(rows)
        i = cal.get_indexer([pd.Timestamp(d)], method="ffill")[0]
        pool = set(symbols[m[:, i]])
        have = pool & set(df.symbolCode)
        w(f"结算日 {d}：接口返回 {len(df)} 行（市场分类 {df.marketClassCode.value_counts().head(6).to_dict()}）；"
          f"池内 {len(pool)} 只，有记录 {len(have)} 只（{len(have)/len(pool):.1%}）；"
          f"带修订标记的行 {int(df.revisionFlag.notna().sum())}")
    (HERE / "13-finra_si_cover_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
