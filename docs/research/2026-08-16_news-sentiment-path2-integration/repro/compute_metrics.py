# -*- coding: utf-8 -*-
"""② 区分度试验 · 指标重算: 每行 fr(mfr_high 口径, 对齐校验) + 首穿四态(k=4/5/6)。

输入 full_scores_*.json → 输出 full_metrics_*.json。
口径: preregistration.md; FPR 直调 path2.eval._first_passage_at,
M=rolling_atr_pct_nanmedian(high,low,close,20) 的 M[t]; 买点锚 t=buy_date 行号。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from path2.eval import _first_passage_at  # noqa: E402
from path2.calc.atr import rolling_atr_pct_nanmedian  # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
OUT_DIR = Path(__file__).resolve().parent
HORIZON = 40
KS = (4, 5, 6)


def main():
    # === 参数配置 ===
    scores_path = sorted(OUT_DIR.glob("full_scores_*.json"))[-1]
    align_tol = 1e-9

    rows = json.loads(scores_path.read_text())
    print(f"loaded {len(rows)} rows from {scores_path.name}")

    out, misaligned, missing = [], [], 0
    for r in rows:
        pkl = PKL_DIR / f"{r['symbol']}.pkl"
        if not pkl.exists():
            missing += 1
            continue
        df = pd.read_pickle(pkl)
        # 原始 pkl: date 为 datetime64 索引(非列)
        pos = np.where(df.index == pd.Timestamp(r["buy_date"]))[0]
        if len(pos) == 0:
            misaligned.append((r["symbol"], r["buy_date"], "date-not-found"))
            continue
        t = int(pos[0])
        hi, lo, cl = (df[c].values for c in ("high", "low", "close"))
        if t + 1 + HORIZON > len(df):
            misaligned.append((r["symbol"], r["buy_date"], "tail-too-short"))
            continue

        # fr = mfr_high 口径, 与 eval JSON fr40 对齐校验
        fr = float(np.max(hi[t + 1: t + 1 + HORIZON])) / float(cl[t]) - 1.0
        if abs(fr - r["fr40"]) > align_tol:
            # 日期匹配但值不齐 → 记录并沿用重算值(报告披露)
            misaligned.append((r["symbol"], r["buy_date"], f"fr-diff={fr - r['fr40']:.2e}"))

        M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], 20).values
        rec = dict(r)
        rec["fr_recalc"] = fr
        rec["fp"] = {}
        for k in KS:
            state = _first_passage_at(hi, lo, cl, M, t, HORIZON, float(k))
            rec["fp"][str(k)] = state  # up/down/both/none 或 None(跳过)
        out.append(rec)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT_DIR / f"full_metrics_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    ok_fp6 = sum(1 for r in out if r["fp"]["6"] is not None)
    print(f"saved: {path}")
    print(f"metrics rows: {len(out)} | pkl missing: {missing} | misaligned: {len(misaligned)}")
    for m in misaligned[:10]:
        print("  misaligned:", m)
    print(f"FPR k=6 valid: {ok_fp6}/{len(out)}")


if __name__ == "__main__":
    main()
