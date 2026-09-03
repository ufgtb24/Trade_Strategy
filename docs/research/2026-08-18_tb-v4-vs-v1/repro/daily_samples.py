# -*- coding: utf-8 -*-
"""pkl 重算逐日买点样本 → daily_samples.json(任务3/4 的数据底座)。

切窗:slice_window(df, '2024-09-19', '2026-03-08') —— 与两 scan 的 win_start/win_end
逐字相同(两 app head_buffer 同=63),start_idx 直接可比、零换算。
样本截窗:lo/hi = searchsorted('2025-01-01'/'2026-01-01')(与 scan worker 同式)。

每样本 (gen, symbol, t):
  mfr40 = max(high[t+1..t+40])/close[t]-1   (越界跳过)
  mfd40 = min(low[t+1..t+40])/close[t]-1    (越界跳过)
  ep40  = close[t+40]/close[t]-1            (端点口径,越界跳过)
  fp    = first-passage 四态(k=5, h=40, M=rolling_atr_pct_nanmedian(20))
  元数据:dist_from_burst_end / seg_ord / 段内位置 offset / seg_len / outcome

对齐校验(写完打印):
  ① match 级 mfr40 均值 vs scan 落盘 forward_return(逐 match,容差 1e-9)
  ② fp 四态总计数 vs scan match_fp_counts(v4: 664/1147/0/921;v1: 123/46/0/58)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from path2.eval import _first_passage_at          # noqa: E402
from path2.calc.atr import rolling_atr_pct_nanmedian  # noqa: E402
from path2_web.data import slice_window           # noqa: E402

WIN_START, WIN_END = "2024-09-19", "2026-03-08"
SCAN_START, SCAN_END = "2025-01-01", "2026-01-01"
H, K = 40, 5.0

D = json.loads((HERE / "extracted.json").read_text())
V4_SEGS = json.loads((HERE / "v4_segs.json").read_text())
V1_TBS = json.loads((HERE / "v1_tbs.json").read_text())


def load_win(symbol):
    p = REPO / "datasets/pkls" / f"{symbol}.pkl"
    df = pd.read_pickle(p)
    return slice_window(df, WIN_START, WIN_END)


CACHE: dict = {}


def win_of(sym):
    if sym not in CACHE:
        win = load_win(sym)
        lo = int(win["date"].searchsorted(pd.to_datetime(SCAN_START), "left"))
        hi = int(win["date"].searchsorted(pd.to_datetime(SCAN_END), "right")) - 1
        M = rolling_atr_pct_nanmedian(
            win["high"], win["low"], win["close"], 20).values
        CACHE[sym] = {"win": win, "lohi": (lo, hi), "M": M}
    return CACHE[sym]


def compute_daily():
    """逐日样本计算,返回 (samples, match_sums, fp_tot) —— match_sums 供对齐校验。"""
    samples = []
    match_sums = {"v4": {}, "v1": {}}   # match_id -> [sum_mfr, n_valid]
    fp_tot = {"v4": {"up": 0, "down": 0, "both": 0, "none": 0},
              "v1": {"up": 0, "down": 0, "both": 0, "none": 0}}

    def emit(gen, sym, t, meta):
        entry = win_of(sym)
        win = entry["win"]
        hi = win["high"].values
        lo = win["low"].values
        cl = win["close"].values
        M = entry["M"]
        row = {"gen": gen, "symbol": sym, "t": t,
               "date": str(win["date"].iat[t])[:10], **meta}
        if t + H < len(win):
            row["mfr40"] = float(hi[t + 1:t + H + 1].max()) / float(cl[t]) - 1.0
            row["mfd40"] = float(lo[t + 1:t + H + 1].min()) / float(cl[t]) - 1.0
            row["ep40"] = float(cl[t + H]) / float(cl[t]) - 1.0
            m = match_sums[gen].setdefault(meta["match_id"], [0.0, 0])
            m[0] += row["mfr40"]
            m[1] += 1
        st = _first_passage_at(hi, lo, cl, M, t, H, K)
        if st is not None:
            fp_tot[gen][st] += 1
            row["fp"] = st
        samples.append(row)

    for r in V4_SEGS:
        sym = r["symbol"]
        win_of(sym)
        lo_i, hi_i = CACHE[sym]["lohi"]
        seg_len = r["end"] - r["start"] + 1
        for t in range(r["start"], r["end"] + 1):
            if not (lo_i <= t <= hi_i):
                continue
            emit("v4", sym, t, {
                "match_id": r["match_id"], "seg_iid": r["seg_iid"],
                "seg_ord": r["seg_ord"], "n_segs": r["n_segs"],
                "seg_off": t - r["start"], "seg_len": seg_len,
                "seg_outcome": r["outcome"],
                "dist_burst_end": t - r["burst_end"],
                "dist_burst_end_enter": r["start"] - r["burst_end"],
                "fr_match": r["fr"],
            })
    for r in V1_TBS:
        sym = r["symbol"]
        win_of(sym)
        lo_i, hi_i = CACHE[sym]["lohi"]
        span_len = r["end"] - r["start"] + 1
        for t in range(r["start"], r["end"] + 1):
            if not (lo_i <= t <= hi_i):
                continue
            emit("v1", sym, t, {
                "match_id": r["match_id"], "tb_iid": r["tb_iid"],
                "seg_ord": 0, "n_segs": 1, "seg_off": t - r["start"],
                "seg_len": span_len, "seg_outcome": r["outcome"],
                "dist_burst_end": t - r["burst_end"],
                "dist_burst_end_enter": r["start"] - r["burst_end"],
                "fr_match": r["fr"],
            })
    return samples, match_sums, fp_tot


def main():
    # lo/hi 预计算
    D_ = D
    syms = sorted(set(D_["v4"]) | set(D_["v1"]))
    # 注意 v4_segs/v1_tbs 已带 burst_end;先补进 JSON 不改原文件,运行期注入
    bs4 = {}
    for sym, v in D_["v4"].items():
        for m in v["matches"]:
            b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
            bs4[m["match_id"]] = b[2]
    bs1 = {}
    for sym, v in D_["v1"].items():
        for m in v["matches"]:
            b = next(x for x in v["burst"] if x[0] == m["burst_iid"])
            bs1[m["match_id"]] = b[2]
    for r in V4_SEGS:
        r["burst_end"] = bs4[r["match_id"]]
    for r in V1_TBS:
        r["burst_end"] = bs1[r["match_id"]]

    for s in syms:
        win_of(s)

    samples, match_sums, fp_tot = compute_daily()
    (HERE / "daily_samples.json").write_text(
        json.dumps({"samples": samples}, ensure_ascii=False))

    # ── 对齐校验 ──
    n_bad = 0
    max_err = 0.0
    for gen, data in (("v4", D_["v4"]), ("v1", D_["v1"])):
        for sym, v in data.items():
            for m in v["matches"]:
                got = match_sums[gen].get(m["match_id"])
                if got is None or got[1] == 0:
                    if m["fr"] is not None:
                        n_bad += 1
                    continue
                mine = got[0] / got[1]
                if m["fr"] is None:
                    n_bad += 1
                    continue
                err = abs(mine - m["fr"])
                max_err = max(max_err, err)
                if err > 1e-9:
                    n_bad += 1
    print(f"对齐校验① match 级 mfr 均值: n_bad={n_bad} max_err={max_err:.3e}")
    exp = {"v4": {"up": 664, "down": 1147, "both": 0, "none": 921},
           "v1": {"up": 123, "down": 46, "both": 0, "none": 58}}
    for gen in ("v4", "v1"):
        ok = all(fp_tot[gen][k] == exp[gen][k] for k in exp[gen])
        print(f"对齐校验② fp {gen}: {fp_tot[gen]} match={exp[gen]} -> {'OK' if ok else 'MISMATCH'}")
    n4 = sum(1 for s in samples if s["gen"] == "v4")
    n1 = sum(1 for s in samples if s["gen"] == "v1")
    print(f"样本数(截窗后): v4={n4} v1={n1} (scan fp n_bars: 2732 / 227)")


if __name__ == "__main__":
    main()
