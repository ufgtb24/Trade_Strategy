# -*- coding: utf-8 -*-
"""learner 方法实验 E1b:闸式指示变量(阈值切分 0/1)在首次穿越标签下,现电池 vs 全样本簇稳健回归。

数据与 E1-E3 相同(FC-007..010 的发现样本,只做方法对照)。
看两件事:
  1. 现电池二元路径用「中位数差」当效应方向;首次穿越占比是离散量,中位数差常为 0,方向符号失效;
  2. 关3 子抽样去簇(每股留首条 / 每时间桶留首条)丢掉的样本量与功效,对照全样本簇稳健 t
     (股簇 / 时间簇 / 双向 + 时间簇 Webb wild cluster bootstrap)。
回归:y = 逐 match 首次穿越占比,权重 = up+down+both,X = [1, 指示变量, rank(atr_pct)(, 年份哑变量)]。
"""
import contextlib
import io
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import e1_e3_gate_vs_continuous as E  # noqa: E402

BIN = {"dpk_ge3": ("distinct_pk", 3), "dpk_ge4": ("distinct_pk", 4), "fd_ge40": ("first_drought", 40),
       "fd_ge114": ("first_drought", 114), "pa_ge60": ("peak_age", 60), "pa_ge120": ("peak_age", 120),
       "vs_ge3": ("vol_spike", 3)}


def run(d, label, controls):
    for b, (f, t) in BIN.items():
        d[b] = (d[f] >= t).astype(int)
    tmp = OUT / f"_tmp_e1b_{label}.csv"
    d[["symbol", "entry_date", "p"] + controls + list(BIN)].rename(columns={"p": "label"}) \
        .assign(entry_date=lambda x: x.entry_date.dt.strftime("%Y-%m-%d")).to_csv(tmp, index=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        v = E.run_battery(tmp, features=[], binaries=list(BIN), controls=controls, time_bucket_days=40)
    (OUT / f"e1b_battery_{label}_{E.UNIT}.txt").write_text(buf.getvalue())
    tmp.unlink()
    raw_lines = [ln for ln in buf.getvalue().splitlines() if "[二元]" in ln]
    print(f"\n######## E1b [{label}] n={len(d)} 股={d.symbol.nunique()} controls={controls}")
    print("现电池关1 原始行:"); print("\n".join(raw_lines))
    rows = []
    for b in BIN:
        r = E.e1_regression(d, b, controls)
        vb = v[b]
        rows.append(dict(gate=b, keep=int(d[b].sum()), battery=vb["verdict"][:30], t_ctrl=vb["t_ctrl"],
                         p3a=vb["declust_p"], p3b=vb["declust_time_p"],
                         t_sym=r["t_sym"], t_time=r["t_time"], t_two=r["t_two"], p_wcb_time=r["p_wcb_time"],
                         G_time=r["G_time"]))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:+.3g}"))


def main():
    d24, d25 = E.load("w2024"), E.load("w2025")
    run(d24.copy(), "w2024", ["atr_pct"])
    run(d25.copy(), "w2025", ["atr_pct"])
    both = pd.concat([d24, d25], ignore_index=True)
    both["is2025"] = (both.year == "w2025").astype(int)
    run(both, "w2024+w2025", ["atr_pct", "is2025"])


if __name__ == "__main__":
    main()
