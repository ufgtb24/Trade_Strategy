"""final_report.md §⑦ 表格(gap_max/scb 切片,FINAL/B where 各 8 行 = 16 个数)的落盘查询
(复审 M4 追加:这组数之前只存在于过程记录、未提交进 git,是全篇唯一无法一键复现的一组)。
直接从主口径 region_find_full.py 产出的 cells.csv 逐格布尔筛选查出,不重新跑 region_find。
用法:uv run python <本文件>(需要 cells.csv 存在于本地,该文件因 >50MB 未入 git,可用
repro/region_find_full.py 重跑复现)
"""
import subprocess, sys
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())


def main():
    cells_path = REPO / "docs/research/2026-08-25_multivar-bb_v1/cells.csv"
    df = pd.read_csv(cells_path)

    def q(final_where: bool, **kw):
        dpk = 4 if final_where else 3
        vsp = 15 if final_where else 10
        base = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "tb.big_rise_k": 5.0,
                "burst.count": 1, "burst.first_drought": 20, "burst.distinct_pk": dpk,
                "burst.max_bar_vol_ratio": vsp, "burst.peak_age_max": 0, "tb.day_drop": 0.2}
        base.update(kw)
        m = pd.Series(True, index=df.index)
        for k, v in base.items():
            m &= (df[k] == v)
        r = df[m]
        return r[["evaluable", "count_2024", "count_2025", "fp_2024", "fp_2025", "s_nb"]]

    for wname, final_where in [("FINAL", True), ("B", False)]:
        print(f"=== {wname} where,gap_max 切片(scb=2 固定) ===")
        for g in [4, 8, 12, 20]:
            r = q(final_where, **{"burst.gap_max": g, "tb.stop_confirm_bars": 2})
            print(f"gap_max={g:3d}:", r.to_string(index=False))
        print(f"=== {wname} where,scb(stop_confirm_bars) 切片(gap_max=8 固定) ===")
        for s in [0, 1, 2, 3]:
            r = q(final_where, **{"burst.gap_max": 8, "tb.stop_confirm_bars": s})
            print(f"scb={s}:", r.to_string(index=False))


main()
