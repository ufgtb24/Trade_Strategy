"""x1：用 2026-09-13 研究的现存产物，估「参数改动 × 年份」交互的典型量级 τ_a。

模型：同一改动在年 y 上的配对差 diff_y = g + a_y + e_y，a_y ~ N(0, τ²) 各年独立，e_y 的 SE 已知（按股去簇）。
则 d = diff24 − diff25 的方差 = 2τ² + se24² + se25²。对多个改动做矩估计：τ² = mean(d² − se24² − se25²) / 2。
另读 13 个 40 日窗的随机效应 τ（窗内异质性），对照「年内窗」与「年间」两个尺度。
只读 CSV / JSON，不碰仓库其他文件。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path("/home/yu/PycharmProjects/Trade_Strategy/docs/research/2026-09-13_pattern-tuning-workflow-redesign/repro/stats")


def main():
    rows = pd.read_csv(SRC / "e4_oat_rows.csv")
    wide = rows.pivot_table(index=["base", "axis", "move"], columns="fold", values=["diff_pt", "se_pt", "keep_ratio"])
    d = wide["diff_pt"][2024] - wide["diff_pt"][2025]
    s2 = wide["se_pt"][2024] ** 2 + wide["se_pt"][2025] ** 2
    excess = (d ** 2 - s2) / 2
    out = pd.DataFrame({
        "d24": wide["diff_pt"][2024], "d25": wide["diff_pt"][2025],
        "se24": wide["se_pt"][2024], "se25": wide["se_pt"][2025],
        "keep24": wide["keep_ratio"][2024],
        "diffgap": d, "z_int": d / np.sqrt(s2), "tau2_mom": excess,
    }).round(2)
    pd.set_option("display.width", 200)
    print(out.to_string())
    for base, g in out.groupby(level=0):
        t2 = g["tau2_mom"].mean()
        print(f"\n[{base}] n={len(g)} 改动；mean(z_int²)={np.mean(g['z_int']**2):.2f}（零假设 1）；"
              f"τ²_mom={t2:.2f} → τ≈{np.sqrt(max(t2, 0)):.2f}pt；中位 SE_flip={np.median(np.r_[g['se24'], g['se25']]):.2f}pt；"
              f"中位 |年均效应|={np.median(np.abs((g['d24']+g['d25'])/2)):.2f}pt")
        big = g[g["keep24"].sub(1).abs() > 0.1]
        if len(big):
            t2b = big["tau2_mom"].mean()
            print(f"   其中买点变动 >10% 的 {len(big)} 个：mean(z_int²)={np.mean(big['z_int']**2):.2f}，τ≈{np.sqrt(max(t2b, 0)):.2f}pt，"
                  f"中位 SE={np.median(np.r_[big['se24'], big['se25']]):.2f}pt")

    print("\n== 13 个 40 日窗上的随机效应 τ（窗间，年内+年间混合）==")
    het = json.loads((SRC / "e2_heterogeneity.json").read_text())
    for h in het:
        print(f"{h['contrast']:>10s} Q_p={h['Q_p']:.3f} τ={h['tau_pt']:.2f}pt μ_re={h['mu_re_pt']:+.2f}±{h['se_re_pt']:.2f} "
              f"窗 SE 中位={np.median(h['per_bucket_se_pt']):.1f}pt")

    print("\n== 自由度与 τ 可估性：用 m 个独立时段估方差，χ²_{m-1} 的 95% 区间给出 SD 的上下界之比 ==")
    from scipy.stats import chi2
    for m in (2, 3, 4, 7, 13):
        lo, hi = chi2.ppf([0.025, 0.975], m - 1)
        print(f"m={m:>2d} 个时段：SD 95% 区间上/下界之比 = {np.sqrt(hi/lo):.1f}")


if __name__ == "__main__":
    main()
