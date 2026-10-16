"""02 分辨力研究 · 第一步：全池逐日「普通买入」标签。

只算普通买入（每只股票每个交易日都当一次买点），不跑任何 pattern、不读任何 pattern 成绩。
标签直接复用 tune-gates-v3 的 `_daily_close_labels`（收盘首次穿越三态 + 前瞻收益 + M），
观察期 H 取几档，线距系数 k 用 v3 / eval.py 默认 5。

输出（体积大、可重生成，放 CACHE 目录，不入库）：
  CACHE/labels_H{H}_k{k}.npz：sym(int16) d(int16 交易日编号) M(float32) dir(int8 +1/0/-1) up(float32 前瞻收益)
  CACHE/meta.npz：symbols、calendar（全部股票交易日并集）

用法：uv run python .scratch/selection-pattern/scripts/02-labels.py [H ...] [--k K]
"""
from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates-v3/scripts"))
from daily import _daily_close_labels  # noqa: E402  复用 v3 标签口径

DATA = ROOT / "datasets/pkls"
CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/02cache")


def read_frame(symbol: str) -> pd.DataFrame:
    """与 DailyEvaluator._read 同口径：日期列来自索引并归一化。"""
    raw = pd.read_pickle(DATA / f"{symbol}.pkl")
    dates = pd.DatetimeIndex(pd.to_datetime(raw["date"] if "date" in raw else raw.index))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    frame = raw.reset_index(drop=True).copy()
    frame["date"] = dates.normalize()
    for c in ("high", "low", "close"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    return frame


def one(args):
    symbol, horizons, k = args
    try:
        frame = read_frame(symbol)
    except Exception as exc:  # 坏文件单列报告
        return symbol, None, repr(exc)
    if not frame["date"].is_monotonic_increasing or frame["date"].duplicated().any():
        return symbol, None, "dates not monotonic/unique"
    out = {}
    start, end = pd.Timestamp("1990-01-01"), pd.Timestamp("2100-01-01")
    for h in horizons:
        lab = _daily_close_labels(frame, symbol, start, end, h, k)
        out[h] = (pd.to_datetime(lab["date"]).to_numpy(), lab["M"].to_numpy(np.float32),
                  (lab["up"] - lab["down"]).to_numpy(np.int8), lab["upside"].to_numpy(np.float32))
    return symbol, (frame["date"].to_numpy(), out), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("horizons", nargs="*", type=int, default=[5, 20, 40, 120])
    ap.add_argument("--k", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只（试跑）")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    symbols = sorted(p.stem for p in DATA.glob("*.pkl"))
    if a.limit:
        symbols = symbols[: a.limit]
    with Pool(a.workers) as pool:
        results = pool.map(one, [(s, a.horizons, a.k) for s in symbols], chunksize=16)
    bad = [(s, e) for s, r, e in results if r is None]
    good = [(s, r) for s, r, e in results if r is not None]
    print(f"stocks ok {len(good)}  bad {len(bad)} {bad[:5]}")
    syms = [s for s, _ in good]
    calendar = np.unique(np.concatenate([r[0] for _, r in good]))
    np.savez(CACHE / ("meta.npz" if not a.limit else "meta_test.npz"),
             symbols=np.array(syms), calendar=calendar)
    for h in a.horizons:
        parts = {key: [] for key in ("sym", "d", "M", "dir", "up")}
        for code, (_, r) in enumerate(good):
            dates, M, d, up = r[1][h]
            parts["sym"].append(np.full(len(dates), code, np.int16))
            parts["d"].append(np.searchsorted(calendar, dates).astype(np.int16))
            parts["M"].append(M); parts["dir"].append(d); parts["up"].append(up)
        arr = {key: np.concatenate(v) for key, v in parts.items()}
        order = np.lexsort((arr["sym"], arr["d"]))  # 按 (日期, 股票) 排序
        arr = {key: v[order] for key, v in arr.items()}
        tag = f"labels_H{h}_k{a.k:g}" + ("_test" if a.limit else "")
        np.savez(CACHE / f"{tag}.npz", **arr)
        touched = (arr["dir"] != 0).mean()
        print(f"H={h} k={a.k:g}: rows {len(arr['d']):,}  dates {len(np.unique(arr['d']))}  "
              f"touched {touched:.3f}  up-first {(arr['dir'] == 1).mean():.3f}  "
              f"median upside {np.median(arr['up']):.4f}  "
              f"date range {pd.Timestamp(calendar[arr['d'].min()]).date()}..{pd.Timestamp(calendar[arr['d'].max()]).date()}")


if __name__ == "__main__":
    main()
