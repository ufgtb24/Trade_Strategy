"""02 分辨力研究 · 把股票按「走势相似」分组（只用价格），供「保留主题扎堆」的换股假 pattern 用。

走势相似度矩阵（02-diag-cross.py 生成的 corr.npy）→ 谱嵌入前 30 维 → KMeans 60 组。
同时报告：组内平均相似度；现役 pattern 相隔不到 40 天的不同股票买点对，相似度均值，
以及按「同波动档随机换股」「同组同波动档换股」两种换法换完后的相似度均值——看哪种换法保住了扎堆程度。
输出：CACHE/groups.npy、打印 + scripts/02-groups.txt
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)

K = 60


def main():
    C = np.load(core.CACHE / "corr.npy").astype(np.float64)
    w, v = np.linalg.eigh(C)
    emb = v[:, -30:] * np.sqrt(np.maximum(w[-30:], 0))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12
    groups = KMeans(K, n_init=4, random_state=0).fit_predict(emb)
    np.save(core.CACHE / "groups.npy", groups)
    out = []
    same = groups[:, None] == groups[None, :]
    np.fill_diagonal(same, False)
    out.append(f"{K} 组；组大小 中位 {np.median(np.bincount(groups)):.0f} 最小 {np.bincount(groups).min()} 最大 {np.bincount(groups).max()}")
    out.append(f"组内股票对平均相似度 {C[same].mean():.3f}；全部股票对 {C[np.triu_indices(len(C), 1)].mean():.3f}")
    pool = core.load_pool(40)
    vdec = pd.qcut(pd.Series(pool.stock_vol).rank(method="first"), 10, labels=False).to_numpy()
    rng = np.random.default_rng(0)
    for app in ("bottom_burst", "bb_v1"):
        buys = pd.read_csv(core.CACHE / f"buys_{app}.csv")
        si = pd.Index(pool.symbols).get_indexer(buys["symbol"])
        d = np.searchsorted(pool.calendar, pd.to_datetime(buys["date"]).to_numpy())
        uniq = np.unique(si)
        maps = {"原样": {s: s for s in uniq}}
        m_vol, m_grp = {}, {}
        perm = rng.permutation(K)
        for s in uniq:
            cand = np.flatnonzero(vdec == vdec[s]); m_vol[s] = rng.choice(cand)
            cg = np.flatnonzero((groups == perm[groups[s]]) & (vdec == vdec[s]))
            if not len(cg):
                cg = np.flatnonzero(groups == perm[groups[s]])
            m_grp[s] = rng.choice(cg)
        maps["同波动档随机换股"] = m_vol; maps["同组同波动档换股"] = m_grp
        order = np.argsort(d); s0, d0 = si[order], d[order]
        sub = rng.choice(len(d0), min(len(d0), 6000), replace=False)
        for name, mp in maps.items():
            s1 = np.array([mp[x] for x in s0])
            sims = []
            for i in sub:
                js = np.flatnonzero((np.abs(d0 - d0[i]) < 40) & (s0 != s0[i]))
                sims.append(C[s1[i], s1[js]])
            sims = np.concatenate(sims)
            out.append(f"{app} {name}：相隔不到 40 天的不同股票买点对 相似度均值 {sims.mean():.4f}")
    text = "\n".join(out)
    print(text)
    (HERE / "02-groups.txt").write_text(text + "\n")


if __name__ == "__main__":
    main()
