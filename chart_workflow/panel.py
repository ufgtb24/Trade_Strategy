"""池内「股票日面板」:逐只读 pkl,算 M、成交额中位、池子成员、全部标签与分组特征。

每只股票先截到训练段末日(之后的行一律丢弃、不被任何计算读到),再算:
  M_t      = rolling_atr_pct_nanmedian(high, low, close, m_period)(第 t 日收盘已知)
  dv_t     = median(close·volume over [t-19..t])
  标签     = labels.label_frame(要求 t+H 存在 ⇒ t+H 不晚于训练段末日)
  分组特征 = features.feature_frame(只用 t 及以前)
一个股票日 (symbol, t) 进面板要同时满足:t ∈ [train_start, train_end];是普通股
(证券分类 ∈ pool.common_classes);close[t] ≤ price_max;dv_t ∈ [dv_min, dv_max];
M_t 有限且 ≥ m_min(剔除平时几乎不动的股票);open[t+1] > 0;标签有效。

另存一列数据核对量 max_jump:从 t − lookback_bars 到 t+H 这些天里,单日收盘 / 前日收盘
的最大倍数(跌按倒数算,恒 ≥ 1)。它读到了决策日之后(仍在训练段内)的价格,只用来把
疑似数据出错的大涨段挑出来待核对,不是分组特征,不得用于选股规则。

面板缓存到 <root>/cache/panel_<参数指纹>.parquet。指纹覆盖:训练段、k、H、M 回看、
池子与特征参数、跳变回看天数、池内普通股名单、行情文件(名称 / 大小 / 修改时间)与本模块版本,
任一变化都会重算。
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.config import dataset_dir, root_dir
from chart_workflow.features import feature_frame
from chart_workflow.labels import label_frame
from chart_workflow.securities import classify_universe, local_symbols
from path2.calc.atr import rolling_atr_pct_nanmedian

PANEL_VERSION = 2

PANEL_COLUMNS = [
    "symbol", "date", "bar_idx", "entry_date", "close", "M", "dv",
    "P", "U", "D", "dir", "mag", "dd", "rise", "rel", "peak_date", "stop_date",
    "dd250", "r60", "width40", "gap", "vol_mult", "pre_state", "vol_tag", "max_jump",
]


def read_stock(cfg: dict, symbol: str) -> pd.DataFrame:
    """读一只股票并截到训练段末日(含)。tz-aware 先去 tz。"""
    df = pd.read_pickle(dataset_dir(cfg) / f"{symbol}.pkl")
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df[df.index <= pd.Timestamp(cfg["train_end"])]


def stock_panel(df: pd.DataFrame, symbol: str, cfg: dict, common: bool) -> pd.DataFrame:
    """一只股票的池内股票日(df 应已截到训练段末日;这里再截一次兜底)。"""
    df = df[df.index <= pd.Timestamp(cfg["train_end"])]
    if not common or len(df) == 0:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    pool = cfg["pool"]
    M = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], period=cfg["m_period"])
    dv = (df["close"] * df["volume"]).rolling(pool["dv_window"],
                                              min_periods=pool["dv_window"]).median()
    lab = label_frame(df, M, cfg["k"], cfg["H"])
    feat = feature_frame(df, M, cfg["features"])
    next_open = df["open"].shift(-1)
    # 单日跳变倍数:|ln(close_i / close_{i-1})| 在 [t − lookback, t+H] 上的最大值,再取 exp
    look = int(cfg["bigmoves"]["anomaly"]["lookback_bars"])
    with np.errstate(divide="ignore", invalid="ignore"):
        jump = np.abs(np.log(df["close"] / df["close"].shift(1)))
    max_jump = np.exp(jump.rolling(cfg["H"] + look + 1, min_periods=1).max().shift(-cfg["H"]))

    with np.errstate(invalid="ignore"):
        in_pool = (
            (df.index >= pd.Timestamp(cfg["train_start"]))
            & (df["close"] <= pool["price_max"]).values
            & (dv >= pool["dv_min"]).values & (dv <= pool["dv_max"]).values
            & np.isfinite(M.values) & (M.values > 0) & (M.values >= pool["m_min"])
            & (next_open > 0).values
            & lab["valid"].values
        )
    if not in_pool.any():
        return pd.DataFrame(columns=PANEL_COLUMNS)
    out = pd.DataFrame({
        "symbol": symbol,
        "date": df.index,
        "bar_idx": np.arange(len(df)),
        "close": df["close"].values,
        "M": M.values,
        "dv": dv.values,
    })
    for c in ("entry_date", "P", "U", "D", "dir", "mag", "dd", "rise", "rel",
              "peak_date", "stop_date"):
        out[c] = lab[c].values
    for c in ("dd250", "r60", "width40", "gap", "vol_mult", "pre_state", "vol_tag"):
        out[c] = feat[c].values
    out["max_jump"] = max_jump.values
    out = out[in_pool].reset_index(drop=True)
    out["dir"] = out["dir"].astype(int)
    return out[PANEL_COLUMNS]


def _worker(args) -> pd.DataFrame:
    cfg, symbol, common = args
    try:
        return stock_panel(read_stock(cfg, symbol), symbol, cfg, common)
    except Exception as e:      # noqa: BLE001 —— 单股坏数据不拖垮整批
        print(f"[panel] 跳过 {symbol}: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=PANEL_COLUMNS)


def _fingerprint(cfg: dict, syms: list[str], classes: dict[str, str]) -> str:
    ddir = dataset_dir(cfg)
    files = []
    for s in syms:
        st = (ddir / f"{s}.pkl").stat()
        files.append((s, st.st_size, st.st_mtime_ns))
    common = sorted(s for s in syms if classes[s] in cfg["pool"]["common_classes"])
    key = {
        "v": PANEL_VERSION,
        "cfg": {k: cfg[k] for k in ("train_start", "train_end", "k", "H", "m_period",
                                    "pool", "features")},
        "jump_lookback": cfg["bigmoves"]["anomaly"]["lookback_bars"],
        "common": common,
        "files": files,
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_panel(cfg: dict, refresh: bool = False, symbols=None, verbose: bool = True
                ) -> pd.DataFrame:
    """返回池内股票日面板(按 date、symbol 排序)。有同指纹缓存就直接读。

    symbols:只算这些代码(测试用);None = 数据目录下全部 pkl。
    """
    syms = sorted(symbols) if symbols is not None else local_symbols(cfg)
    classes = classify_universe(cfg, syms)
    fp = _fingerprint(cfg, syms, classes)
    cache = root_dir(cfg) / "cache" / f"panel_{fp}.parquet"
    if cache.exists() and not refresh:
        if verbose:
            print(f"[panel] 读缓存 {cache}")
        return pd.read_parquet(cache)
    common_set = set(cfg["pool"]["common_classes"])
    jobs = [(cfg, s, classes[s] in common_set) for s in syms]
    if verbose:
        print(f"[panel] 计算 {len(jobs)} 只股票(普通股 {sum(j[2] for j in jobs)} 只)…")
    workers = max(1, int(cfg.get("workers", 1)))
    if workers == 1 or len(jobs) < 50:
        parts = [_worker(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_worker, jobs, chunksize=16))
    parts = [p for p in parts if len(p)]
    panel = (pd.concat(parts, ignore_index=True) if parts
             else pd.DataFrame(columns=PANEL_COLUMNS))
    panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(cache, index=False)
    if verbose:
        print(f"[panel] {len(panel)} 个池内股票日,{panel['symbol'].nunique()} 只股票 → {cache}")
    return panel


@lru_cache(maxsize=4096)
def _dates_cached(ddir: str, train_end: str, symbol: str) -> pd.DatetimeIndex:
    df = pd.read_pickle(Path(ddir) / f"{symbol}.pkl")
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    idx = idx.sort_values()
    return idx[idx <= pd.Timestamp(train_end)]


def trading_dates(cfg: dict, symbol: str) -> pd.DatetimeIndex:
    """一只股票截到训练段末日的交易日序列(图窗按交易日偏移时用)。"""
    return _dates_cached(str(dataset_dir(cfg)), str(cfg["train_end"]), symbol)
