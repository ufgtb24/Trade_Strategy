"""训练挑选能否认出「唯一真有改善」的候选（临时研究脚本）。

在零假设世界（所有候选真实改善为 0，保留按股重抽的真实噪声相关结构）里，给其中一个候选
植入真实改善 δ，看按 v3 规则（同一组下限内取方向主分最高）选中它的概率；对每个候选轮流植入后平均。
对照：在可行候选里随机挑一个的命中率。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from selection_sim import RNG, N_BOOT, EPS, prepare, key_of, feasible

OUT = Path(__file__).with_name("planted_sim_results.json")


def planted(fold: str, deltas=(0.03, 0.05, 0.10, 0.20, 0.40)) -> dict:
    plan, cands, symbols, mats, orig = prepare(fold, "search")
    seen, ids = set(), []
    for cid, rows in cands.items():
        k = key_of(rows)
        if k not in seen:
            seen.add(k)
            ids.append(cid)
    m = RNG.multinomial(len(symbols), np.full(len(symbols), 1 / len(symbols)), size=N_BOOT).astype(float)
    boot = {cid: mats[cid].stats(m) for cid in ids}
    ref = boot["base"]
    others = [c for c in ids if c != "base"]
    dZ = np.vstack([boot[c]["Z"] - ref["Z"] for c in others]).T
    dZ0 = np.array([orig[c]["Z"] - orig["base"]["Z"] for c in others])
    noise = dZ - dZ0[None, :]
    out = {}
    for delta in deltas:
        hits, chance, sel_rate = [], [], []
        for k in range(len(others)):
            shift = np.zeros(len(others))
            shift[k] = delta
            diff = noise + shift[None, :]
            ok = np.vstack([feasible({**boot[c], "Z": ref["Z"] + diff[:, i]}, ref)
                            for i, c in enumerate(others)]).T
            s = np.where(ok & np.isfinite(diff), diff, -np.inf)
            j = np.argmax(s, axis=1)
            best = s[np.arange(len(s)), j]
            sel = np.isfinite(best) & (best > EPS)
            hits.append(float(((j == k) & sel).mean()))
            sel_rate.append(float(sel.mean()))
            nfeas = ok.sum(axis=1)
            chance.append(float(np.mean(np.where(nfeas > 0, ok[:, k] / np.maximum(nfeas, 1), 0))))
        out[str(delta)] = {"p_pick_true": float(np.mean(hits)), "p_pick_if_random_feasible": float(np.mean(chance)),
                           "any_selected": float(np.mean(sel_rate))}
    return out


def main():
    res = {fold: planted(fold) for fold in ("fold1", "fold2")}
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
