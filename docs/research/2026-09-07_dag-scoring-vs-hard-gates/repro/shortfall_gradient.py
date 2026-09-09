"""C2(截断加权和 ≡ 总亏欠预算)的判据检验:亏欠幅度到底带不带信息。

C2 的形式:μᵢ = min(1, xᵢ/tᵢ)(各项封顶 1),准入条件 Σμᵢ ≥ θ,
等价于总亏欠 S = Σ(1−μᵢ) ≤ 4−θ。它比「删闸」多出来的东西,全在
「S 小的样本比 S 大的样本好」这个假设上——若 label 沿 S 无梯度,
C2 相对「直接删掉那道闸」就没有增量,只是把同一批样本换个说法放进来。

两个检验:
  ① 全池:label 沿总亏欠 S 分档看,有没有单调梯度;
  ② 只差一闸的天然对照组(恰好一个 μᵢ<1):按**该闸自身的相对亏欠** 1−μ
     分 <10% / 10~25% / 25~50% / >50% 四档(与 team-lead 的边界密度同档),
     看「只差一点点」是不是真的更接近「四闸全过」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from boundary_and_aggregation import SSOT, FEATS, prep, stat, line, paired_diff  # noqa: E402


def add_shortfall(d):
    mu = {}
    for f in FEATS:
        mu[f] = np.minimum(1.0, d[f].values / SSOT[f])
    M = pd.DataFrame(mu, index=d.index)
    d = d.copy()
    d["S"] = (1.0 - M).sum(axis=1)                 # 总亏欠 ∈ [0,4]
    d["n_fail"] = (M < 1.0).sum(axis=1)            # 未过闸数
    # 只差一闸时,那道闸的相对亏欠
    lack = (1.0 - M)
    d["only_gate"] = np.where(d.n_fail == 1, lack.idxmax(axis=1), "")
    d["only_lack"] = np.where(d.n_fail == 1, lack.max(axis=1), np.nan)
    return d


def main():
    for tag in ["w2025", "w2024"]:
        d, base = prep(tag)
        d = add_shortfall(d)
        allpass = d.n_fail == 0
        print(f"\n{'='*104}\n════ {tag} · n={len(d)} · SSoT 阈值 {SSOT} ════")
        print(line("四闸全过 (S=0)", stat(d[allpass], base)))
        print(f"  未过闸数分布: {d.n_fail.value_counts().sort_index().to_dict()}")

        print("\n  【①】label 沿总亏欠 S 分档(C2 的准入就是 S ≤ 预算)")
        edges = [0, 1e-9, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 4.01]
        labs = ["S=0(全过)", "0<S≤0.1", "0.1<S≤0.25", "0.25<S≤0.5",
                "0.5<S≤1.0", "1.0<S≤1.5", "1.5<S≤2.0", "S>2.0"]
        for i, nm in enumerate(labs):
            g = d[(d.S > edges[i] - (1e-12 if i == 0 else 0)) & (d.S <= edges[i + 1])] \
                if i > 0 else d[allpass]
            if len(g) == 0:
                continue
            print(line(nm, stat(g, base, ci=(len(g) >= 30))))
        # 梯度检验:S 小的一批 vs S 大的一批(都在"未全过"里,排除 S=0)
        nz = d[~allpass]
        lo = nz[nz.S <= nz.S.quantile(1 / 3)]
        hi = nz[nz.S >= nz.S.quantile(2 / 3)]
        paired_diff(lo, hi, base, "亏欠小 − 亏欠大(未全过样本内)")
        print(f"    spearman(S, fr) = {d.S.corr(d.fr, method='spearman'):+.4f}")

        print("\n  【②】只差一闸(恰好一个 μ<1)· 按该闸自身相对亏欠分档")
        one = d[d.n_fail == 1]
        print(f"    只差一闸合计 n={len(one)}(四闸全过 n={int(allpass.sum())});"
              f"按闸拆 {one.only_gate.value_counts().to_dict()}")
        bands = [(0, 0.10, "<10%"), (0.10, 0.25, "10~25%"),
                 (0.25, 0.50, "25~50%"), (0.50, 1.01, ">50%")]
        for a, b, nm in bands:
            g = one[(one.only_lack > a) & (one.only_lack <= b)]
            r = stat(g, base, ci=(len(g) >= 30))
            print(line(f"  亏欠 {nm}", r))
        near = one[one.only_lack <= 0.25]
        far = one[one.only_lack > 0.25]
        if len(near) >= 30 and len(far) >= 30:
            paired_diff(near, far, base, "只差一闸·近(≤25%) − 远(>25%)")
        if len(near) >= 30:
            paired_diff(near, d[allpass], base, "只差一闸·近(≤25%) − 四闸全过")
        # 逐闸:近 vs 全过
        for f in FEATS:
            g = one[(one.only_gate == f) & (one.only_lack <= 0.25)]
            if len(g) >= 30:
                print(line(f"  只差{f}·近(≤25%)", stat(g, base)))


if __name__ == "__main__":
    main()
