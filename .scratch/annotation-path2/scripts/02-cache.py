"""训练段用多长 —— 第一步：逐只股票算一次日线摘要，存成缓存，后面所有统计只读这份缓存。

只读截到 2025-12-31 的副本（经 chart_workflow.loader，正式模式；读出后再断言最后一天不晚于 2025-12-31）。
不读任何面板缓存（outputs/**/cache/panel_*.parquet）。后续涨跌全部由本脚本在训练段内自己算，
观察期走不完的（靠近 2025-12-31 的决策日）标签为空，不拿后面的数据补。

每个普通股股票日一行（float32 为主）：
  基础：date, sym, close, M(20 日 TR/close 中位), dv(20 日成交额中位), dollar(当日成交额)
  当日：r1(收盘涨跌), gap(开盘/昨收−1), intra(收盘/开盘−1), rng((高−低)/昨收)
  回看（只用 t 及以前）：r5, r20, r60, vm(量 / 前 63 日均量), dd120, dd250(离 120/250 日最高),
        hi120(收盘创 120 日收盘新高), hi20, w40(40 日高低宽度/收盘), shell(往前 120 天内有 SPAC 壳期)
  标签（买入价 = 次日开盘 P）：
        d40 = 观察 40 日、线距 k=5（上线 P(1+5M)、下线 P/(1+5M)）按收盘先碰哪条：+1/−1/0；无效 −9
        m40 = 40 日内最高价 / P − 1（幅度，项目口径）
        d10 = 观察 10 日、线距 k=2.5（按 √(10/40) 缩放）的方向
        f10 = 第 10 个观察日收盘 / P − 1
  pool：推荐池（普通股、收盘≤20、20 日成交额中位 200 万~1 亿、M≥0.01、次日开盘>0、无 SPAC 壳期）
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from chart_workflow import loader                       # noqa: E402
from chart_workflow.config import load_config           # noqa: E402
from chart_workflow.labels import compute_labels        # noqa: E402
from chart_workflow.panel import _after_spac_shell      # noqa: E402
from chart_workflow.securities import classify_universe, is_common, local_symbols  # noqa: E402

OUT = Path(__file__).resolve().parent / "02-cache.parquet"
HARD_END = pd.Timestamp("2025-12-31")
CFG = load_config(override={"train_start": "2021-10-08", "train_end": "2025-12-31"})


def nanmedian_rolling(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out[w - 1:] = np.nanmedian(sliding_window_view(x, w), axis=1)
    return out


def one(symbol: str) -> pd.DataFrame | None:
    df = loader.read_bars(CFG, symbol)
    if len(df) == 0:
        return None
    assert df.index.max() <= HARD_END, symbol
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    o, h, l, c, v = (df[k].to_numpy() for k in ["open", "high", "low", "close", "volume"])
    pc = np.r_[np.nan, c[:-1]]
    with np.errstate(all="ignore"):
        tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0) / c
        tr[0] = (h[0] - l[0]) / c[0]
        M = nanmedian_rolling(tr, 20)
        dollar = c * v
        dv = pd.Series(dollar).rolling(20, min_periods=20).median().to_numpy()
        cs = pd.Series(c)
        hs, ls_, vs = pd.Series(h), pd.Series(l), pd.Series(v)
        r1 = c / pc - 1
        gap = o / pc - 1
        intra = c / o - 1
        rng = (h - l) / pc
        r5 = (cs / cs.shift(5) - 1).to_numpy()
        r20 = (cs / cs.shift(20) - 1).to_numpy()
        r60 = (cs / cs.shift(60) - 1).to_numpy()
        vbase = vs.rolling(63, min_periods=63).mean().shift(1)
        vm = (vs / vbase).replace([np.inf, -np.inf], np.nan).to_numpy()
        dd120 = (cs / hs.rolling(120, min_periods=120).max() - 1).to_numpy()
        dd250 = (cs / hs.rolling(250, min_periods=250).max() - 1).to_numpy()
        hi120 = (cs > cs.shift(1).rolling(120, min_periods=120).max()).to_numpy()
        hi20 = (cs > cs.shift(1).rolling(20, min_periods=20).max()).to_numpy()
        w40 = ((hs.rolling(40, min_periods=40).max() - ls_.rolling(40, min_periods=40).min()) / cs).to_numpy()
    shell = _after_spac_shell(df, CFG["pool"]["spac_shell"])
    lab40 = compute_labels(o, h, l, c, M, 5.0, 40)
    lab10 = compute_labels(o, h, l, c, M, 2.5, 10)
    P = lab10["P"]
    f10 = np.full(len(c), np.nan)
    if len(c) > 10:
        f10[:-10] = c[10:] / P[:-10] - 1
    f10[~lab10["valid"]] = np.nan
    d40 = np.where(lab40["valid"], lab40["dir"], -9).astype(np.int8)
    d10 = np.where(lab10["valid"], lab10["dir"], -9).astype(np.int8)
    next_open = np.r_[o[1:], np.nan]
    pool = CFG["pool"]
    with np.errstate(invalid="ignore"):
        in_pool = ((c <= pool["price_max"]) & (dv >= pool["dv_min"]) & (dv <= pool["dv_max"])
                   & np.isfinite(M) & (M >= pool["m_min"]) & (next_open > 0) & ~shell)
    out = pd.DataFrame({
        "date": df.index.values, "close": c, "M": M, "dv": dv, "dollar": dollar,
        "r1": r1, "gap": gap, "intra": intra, "rng": rng, "r5": r5, "r20": r20, "r60": r60,
        "vm": vm, "dd120": dd120, "dd250": dd250, "w40": w40,
        "m40": np.where(lab40["valid"], lab40["mag"], np.nan), "f10": f10,
    })
    for col in out.columns[1:]:
        out[col] = out[col].astype(np.float32)
    out["hi120"] = hi120
    out["hi20"] = hi20
    out["shell"] = shell
    out["pool"] = in_pool
    out["d40"] = d40
    out["d10"] = d10
    out["sym"] = symbol
    out = out[np.isfinite(out["M"].to_numpy())]
    return out


def main() -> None:
    syms = local_symbols(CFG)
    classes = classify_universe(CFG, syms)
    common = [s for s in syms if is_common(classes[s], CFG["pool"]["common_classes"])]
    print(f"本地 {len(syms)} 只，普通股（含 ADR、MLP）{len(common)} 只", flush=True)
    parts = []
    with ProcessPoolExecutor(max_workers=12) as ex:
        for i, p in enumerate(ex.map(one, common, chunksize=16)):
            if p is not None and len(p):
                parts.append(p)
            if i % 1000 == 0:
                print(i, flush=True)
    panel = pd.concat(parts, ignore_index=True)
    panel["sym"] = panel["sym"].astype("category")
    assert panel["date"].max() <= HARD_END
    panel.to_parquet(OUT, index=False, compression="zstd")
    print(f"{len(panel)} 行，{panel['sym'].nunique()} 只 → {OUT}")


if __name__ == "__main__":
    main()
