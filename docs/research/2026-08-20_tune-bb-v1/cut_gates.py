"""cut_gates · 在宽表 dataset.csv 上对「事后可切」闸逐档切,产出 plateau.py 输入宽表。

第 3 步事后切档审计的数据准备:每档 = 保留 gate_col 满足条件的样本,
算 (fr_median, FP, match)。fr = median(label);FP = sum(up)/(sum(up)+sum(down)+sum(both)),
与 tune-gates 指标契约一致(none 不进分母)。

保留方向按各闸语义:
  - 下界闸(阈值越高越严):first_drought / distinct_pk / vol_spike / peak_age —— 保留 col >= x;
  - 上界闸(阈值越低越严):day_drop(毒药闸,单日跌幅超限删事件)—— 保留 col < x。

分年列(2024 vs 2025)一并产出,供 plateau.py 判「分年平台交集」稳健性。

用法:参数在 main() 起始声明(无 argparse,承 CLAUDE.md 入口规范):
    uv run python docs/research/2026-08-20_tune-bb-v1/cut_gates.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).parent
CSV = OUT_DIR / "dataset.csv"                 # extract_wide_base.py 产出
GATES_OUT = OUT_DIR / "gates.csv"             # plateau.py 输入
# 简单 --csv= --gates= override(250 底座重做用)
import sys
for _a in [a for a in sys.argv[1:] if a.startswith("--csv=")]:
    CSV = Path(_a.split("=", 1)[1])
for _a in [a for a in sys.argv[1:] if a.startswith("--gates=")]:
    GATES_OUT = Path(_a.split("=", 1)[1])

# 每闸:(列名, 档位, 保留方向 ge=col>=x / lt=col<x)
# 档位覆盖「宽进下限 → 当前收闸值 → 数据实际最大值」的完整取值空间(2026-08-20 补全:
# 首轮只测到部分范围,上界普遍截断——first_drought 漏下界 0(首簇样本)、多闸上界未测到
# p90~max。档位按 dataset 实际分布扩展):
#   first_drought: min=0(p10=0,首簇 499 个) / p90=143 / max=442 → 补 0 下界 + 150/250 上界
#   distinct_pk:   min=1 / p90=4 / max=13 → 补 6/8/10
#   vol_spike:     min=0 / p90=10.7 / max=5552(爆量长尾) → 补 30/50
#   peak_age:      min=7 / p90=209 / max=507 → 补 250/350
#   day_drop:      min=0 / p90=0.08 / max=0.51 → 补 0.50(≈不设闸对照)
GATES = {
    "first_drought": ("burst_first_drought", [0, 9, 10, 20, 30, 40, 60, 100, 150, 250], "ge"),
    "distinct_pk": ("burst_distinct_pk", [1, 2, 3, 4, 5, 6, 8, 10], "ge"),
    "vol_spike": ("burst_max_bar_vol_ratio", [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0], "ge"),
    "peak_age": ("burst_peak_age_max", [0, 30, 60, 90, 125, 180, 250, 350], "ge"),
    "day_drop": ("day_drop", [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50], "lt"),
}


def main() -> None:
    df = pd.read_csv(CSV, keep_default_na=False, na_values=[""])
    df["year"] = pd.to_datetime(df["tb_date"]).dt.year
    rows = []
    for gate, (col, xs, direction) in GATES.items():
        for x in xs:
            if direction == "ge":
                sub = df[df[col] >= x]
            else:  # lt
                sub = df[df[col] < x]
            n = len(sub)
            if n == 0:
                continue
            fr = sub["label"].median()
            up = sub["fp_up"].sum()
            dn = sub["fp_down"].sum()
            bt = sub["fp_both"].sum()
            fp = up / (up + dn + bt) if (up + dn + bt) > 0 else float("nan")
            # 注:暂不输出分年列——plateau.load() 对「部分档位缺某年」的行键不一致会崩
            # (NaN 写 CSV 变空串又被跳过)。分年一致性单独查(见笔记/后续脚本)。
            row = {"gate": gate, "x": x, "fr": fr, "fp": fp, "match": n}
            rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(GATES_OUT, index=False)
    print(f"{len(out)} 行 -> {GATES_OUT}")
    # 每闸一眼看 match 递减 + fr/fp(人工粗筛)
    for gate, g in out.groupby("gate"):
        print(f"\n[{gate}]")
        print(g[["x", "fr", "fp", "match"]].to_string(index=False))


if __name__ == "__main__":
    main()
