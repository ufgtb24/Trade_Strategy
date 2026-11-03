"""找图:大涨段清单(rally)与随机给一段图(random),都从股票池(stock_pool.py)里出图。

只决定给用户看哪些图,不进任何成绩;看过什么一律不记(本模块只写下面的缓存,不写任何看图记录)。
行情只经 data.read_bars 读(训练段副本,截到训练段末日),再截到训练段设置的终点:
涨幅、进不进清单、图窗,都只用截止前的行情算,截止后的行情读不到。

**大涨段清单**(参数在配置 finder.rally):
1. 候选:每个进池的股票日 t。买入价 P = 次日开盘价;止损线 D = P ÷ (1 + k·M_t)。
   观察期 = t 之后最多 horizon 根,截到训练段终点(截止前不够 horizon 根就只看有的那几根);
   观察期里第一次收盘 ≤ D 就截在那天。拿得到的涨幅 rise = 截取段里的最高价 ÷ P − 1,
   最高价那天是 peak_date;相对涨幅 rel = ln(1 + rise) ÷ ln(1 + k·M_t),单位是「几倍止损距离」。
2. 门槛:rel ≥ rel_min。
3. 同一段行情只取一次:每只股票按 rel 从大到小贪心取,和已取中的同一只股票的各段相隔超过
   suppress_bars 根才取。
4. 每周限量:同一 ISO 周(按 t)最多 per_week_max 段,取 rel 大的。
5. 总量:全部按 rel 从大到小取前 top 段。
每段的图窗从 t 往前 before_bars 根,到观察期的末根:停在那段涨之前,同时看得见那段涨。

**random**:在全部进池的股票日里均匀抽一个 t,图窗是以 t 为中心的 random_window_bars 根,
两端截到这只股票有行情的范围和训练段终点,截掉的不往另一端补。

**缓存**:进池的股票日和清单一起存成 <缓存目录>/finder-<键>.npz。键覆盖训练段设置、副本指纹、
股票池与清单参数、名称表内容、数据错误登记与本模块版本 FINDER_VERSION,任一变化都重算;
写新缓存时删掉同目录的旧缓存。整池算一遍是逐只读、单进程。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from path2_web import stock_pool
from path2_web.config import repo_path
from path2_web.data import list_symbols, read_bars
from path2_web.snapshot_fingerprint import read_fingerprint

FINDER_VERSION = 1
_CACHE_PREFIX = "finder-"
_RALLY_FIELDS = ("symbol", "date", "peak_date", "rise", "rel", "view_start", "view_end")

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinderIndex:
    """整池算一遍的结果。

    symbols:有进池股票日的股票(字母序);pool_sym / pool_date:每个进池股票日的股票序号(指 symbols)
    与日期;rally:大涨段清单(按 rel 从大到小),每段 {symbol, date, peak_date, rise, rel, view_start,
    view_end};skipped:读不了而跳过的股票。
    """
    key: str
    symbols: tuple[str, ...]
    pool_sym: np.ndarray
    pool_date: np.ndarray
    rally: list[dict]
    skipped: tuple[str, ...]


def rally_labels(open_, high, low, close, M, k: float, horizon: int) -> dict[str, np.ndarray]:
    """逐日的拿得到的涨幅(口径见模块说明第 1 步)。输入是同长的 1-D 数组,已截到训练段终点。

    返回同长数组:valid(bool,次日开盘价与 M_t 都是有限正数)、rise、rel(无效处 NaN)、
    peak_off(最高价那天相对 t 的根数 1..horizon,无效为 -1)、end_off(观察期末根相对 t 的根数)。
    """
    open_, high, low, close, M = (np.asarray(a, dtype=float) for a in (open_, high, low, close, M))
    n = len(close)
    H = int(horizon)
    pad = np.full(H, np.nan)
    # 第 t 行 = 观察日 t+1 .. t+H;截止后没有的位置是 NaN
    cw = sliding_window_view(np.concatenate([close[1:], pad]), H)[:n]
    hw = sliding_window_view(np.concatenate([high[1:], pad]), H)[:n]
    P = np.concatenate([open_[1:], [np.nan]])
    with np.errstate(invalid="ignore", divide="ignore"):
        valid = np.isfinite(M) & (M > 0) & np.isfinite(P) & (P > 0)
        D = P / (1.0 + k * np.where(valid, M, 0.0))
        down = cw <= D[:, None]                       # NaN 比较为 False
    has_down = down.any(1)
    cut = np.where(has_down, down.argmax(1), H - 1)   # 截取段末位(含)
    in_w = (np.arange(H)[None, :] <= cut[:, None]) & np.isfinite(hw)
    hw_cut = np.where(in_w, hw, -np.inf)
    peak = hw_cut.argmax(1)                           # 同价取最早那天
    valid &= in_w.any(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rise = hw_cut.max(1) / P - 1.0
        rel = np.log1p(rise) / np.log1p(k * M)
    avail = np.minimum(H, n - 1 - np.arange(n))       # 截止前有几根观察日
    return {
        "valid": valid,
        "rise": np.where(valid, rise, np.nan),
        "rel": np.where(valid, rel, np.nan),
        "peak_off": np.where(valid, peak + 1, -1),
        "end_off": np.maximum(avail, 0),
    }


def stock_rows(df: pd.DataFrame, symbol: str, *, segment: tuple[str, str], settings: dict,
               errors: list[dict]) -> tuple[np.ndarray, pd.DataFrame]:
    """一只普通股:返回 (进池股票日的日期数组, 大涨段候选表)。df 已截到训练段终点;
    errors 是这只股票的数据错误登记。

    候选表列:symbol、date、bar_idx(在 df 里的行号)、rise、rel、peak_date、view_start、view_end。
    """
    pool, rally = settings["pool"], settings["rally"]
    M = stock_pool.volatility_scale(df, int(pool["m_period"]))
    in_pool = stock_pool.pool_mask(df, common=True, segment=segment, pool=pool, errors=errors, M=M)
    dates = df.index
    if not in_pool.any():
        return dates.values[:0].astype("datetime64[D]"), _empty_candidates()
    lab = rally_labels(df["open"], df["high"], df["low"], df["close"], M,
                       float(rally["k"]), int(rally["horizon"]))
    with np.errstate(invalid="ignore"):
        cand = in_pool & lab["valid"] & (lab["rel"] >= float(rally["rel_min"]))
    idx = np.flatnonzero(cand)
    before = int(rally["before_bars"])
    cands = pd.DataFrame({
        "symbol": symbol,
        "date": dates.values[idx],
        "bar_idx": idx,
        "rise": lab["rise"][idx],
        "rel": lab["rel"][idx],
        "peak_date": dates.values[idx + lab["peak_off"][idx]],
        "view_start": dates.values[np.maximum(idx - before, 0)],
        "view_end": dates.values[idx + lab["end_off"][idx]],
    })
    return dates.values[in_pool].astype("datetime64[D]"), cands


def _empty_candidates() -> pd.DataFrame:
    return pd.DataFrame({"symbol": pd.Series(dtype=str), "date": pd.Series(dtype="datetime64[ns]"),
                         "bar_idx": pd.Series(dtype=int), "rise": pd.Series(dtype=float),
                         "rel": pd.Series(dtype=float),
                         "peak_date": pd.Series(dtype="datetime64[ns]"),
                         "view_start": pd.Series(dtype="datetime64[ns]"),
                         "view_end": pd.Series(dtype="datetime64[ns]")})


def select_rally(cands: pd.DataFrame, rally: dict) -> pd.DataFrame:
    """候选 → 清单(模块说明第 3~5 步),按 rel 从大到小。"""
    if len(cands) == 0:
        return cands
    gap = int(rally["suppress_bars"])
    ordered = cands.sort_values(["symbol", "rel", "date"], ascending=[True, False, True])
    taken: dict[str, list[int]] = defaultdict(list)
    keep = []
    for row_pos, (sym, bar) in enumerate(zip(ordered["symbol"].to_numpy(), ordered["bar_idx"].to_numpy())):
        if all(abs(int(bar) - b) > gap for b in taken[sym]):
            taken[sym].append(int(bar))
            keep.append(row_pos)
    picked = ordered.iloc[keep]
    iso = pd.DatetimeIndex(picked["date"]).isocalendar()
    week = (iso["year"].astype(str) + "-" + iso["week"].astype(str)).to_numpy()
    picked = (picked.assign(_week=week)
              .sort_values(["rel", "date", "symbol"], ascending=[False, True, True])
              .groupby("_week", sort=False).head(int(rally["per_week_max"]))
              .drop(columns="_week"))
    return (picked.sort_values(["rel", "date", "symbol"], ascending=[False, True, True])
            .head(int(rally["top"])).reset_index(drop=True))


def _day(v) -> str:
    return str(np.datetime64(v, "D"))


def rally_items(sel: pd.DataFrame) -> list[dict]:
    """清单表 → 路由返回的条目:日期写成 YYYY-MM-DD,rise 保留 4 位小数、rel 保留 3 位。"""
    return [{"symbol": r.symbol, "date": _day(r.date), "peak_date": _day(r.peak_date),
             "rise": round(float(r.rise), 4), "rel": round(float(r.rel), 3),
             "view_start": _day(r.view_start), "view_end": _day(r.view_end)}
            for r in sel.itertuples()]


def cache_key(*, segment: tuple[str, str], fingerprint: str, settings: dict,
              names: dict[str, str], errors: list[dict]) -> str:
    """缓存键:训练段设置、副本指纹、股票池与清单参数、名称表、数据错误登记、FINDER_VERSION 的指纹。
    random 的窗口长度不影响缓存内容,不进键。"""
    payload = {
        "v": FINDER_VERSION,
        "segment": list(segment),
        "fingerprint": fingerprint,
        "pool": settings["pool"],
        "rally": settings["rally"],
        "names": hashlib.sha256(json.dumps(sorted(names.items())).encode()).hexdigest(),
        "errors": errors,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_index(data_dir, *, key: str, segment: tuple[str, str], settings: dict,
                names: dict[str, str], errors: list[dict]) -> FinderIndex:
    """整池算一遍:逐只经 read_bars 读、截到训练段终点,单进程。"""
    common_classes = set(settings["pool"]["common_classes"])
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for e in errors:
        by_symbol[e["symbol"]].append(e)
    end = pd.Timestamp(segment[1])
    symbols, pool_sym, pool_date, parts, skipped = [], [], [], [], []
    for sym in list_symbols(data_dir):
        if stock_pool.security_class(sym, names.get(sym)) not in common_classes:
            continue
        try:
            df = read_bars(data_dir, sym)
            df = df[df.index <= end]
            days, cands = stock_rows(df, sym, segment=segment, settings=settings,
                                     errors=by_symbol.get(sym, []))
        except Exception as e:      # noqa: BLE001 —— 一只坏数据不拖垮整池,记下跳过的代码
            log.warning("找图跳过 %s: %s: %s", sym, type(e).__name__, e)
            skipped.append(sym)
            continue
        if len(days) == 0:
            continue
        pool_sym.append(np.full(len(days), len(symbols), dtype=np.int32))
        pool_date.append(days)
        symbols.append(sym)
        if len(cands):
            parts.append(cands)
    cands = pd.concat(parts, ignore_index=True) if parts else _empty_candidates()
    return FinderIndex(
        key=key, symbols=tuple(symbols),
        pool_sym=np.concatenate(pool_sym) if pool_sym else np.zeros(0, dtype=np.int32),
        pool_date=np.concatenate(pool_date) if pool_date else np.zeros(0, dtype="datetime64[D]"),
        rally=rally_items(select_rally(cands, settings["rally"])),
        skipped=tuple(skipped),
    )


def _cache_path(cache_dir, key: str) -> Path:
    return Path(cache_dir) / f"{_CACHE_PREFIX}{key}.npz"


def save_index(index: FinderIndex, cache_dir) -> Path:
    """写缓存(先写临时文件再换名),再删掉同目录的旧缓存。"""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, index.key)
    tmp = cache_dir / f".{path.name}.tmp"
    cols = {f: [r[f] for r in index.rally] for f in _RALLY_FIELDS}
    with tmp.open("wb") as f:
        np.savez_compressed(
            f, key=np.array(index.key), symbols=np.array(index.symbols, dtype=str),
            pool_sym=index.pool_sym, pool_date=index.pool_date.astype("datetime64[D]"),
            skipped=np.array(index.skipped, dtype=str),
            **{f"rally_{k}": np.array(v, dtype=float if k in ("rise", "rel") else str)
               for k, v in cols.items()})
    tmp.replace(path)
    for old in cache_dir.glob(f"{_CACHE_PREFIX}*.npz"):
        if old != path:
            old.unlink(missing_ok=True)
    return path


def load_index(cache_dir, key: str) -> FinderIndex | None:
    """读缓存;没有这个键的缓存 → None。"""
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as z:
        n = len(z["rally_symbol"])
        rally = [{"symbol": str(z["rally_symbol"][i]), "date": str(z["rally_date"][i]),
                  "peak_date": str(z["rally_peak_date"][i]), "rise": float(z["rally_rise"][i]),
                  "rel": float(z["rally_rel"][i]), "view_start": str(z["rally_view_start"][i]),
                  "view_end": str(z["rally_view_end"][i])} for i in range(n)]
        return FinderIndex(key=str(z["key"]), symbols=tuple(str(s) for s in z["symbols"]),
                           pool_sym=z["pool_sym"], pool_date=z["pool_date"], rally=rally,
                           skipped=tuple(str(s) for s in z["skipped"]))


class Finder:
    """进程内的找图入口:按键记住最近一次的结果;没有就读缓存,缓存也没有就整池算一遍并写缓存。
    同一时刻只算一遍(加锁),并发的请求等它算完。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._index: FinderIndex | None = None

    def index(self, data_dir, *, segment: tuple[str, str], settings: dict, cache_dir) -> FinderIndex:
        """data_dir:训练段副本目录(要有指纹清单,没有 → snapshot_fingerprint.ManifestMissing)。"""
        names = stock_pool.load_security_names(repo_path(settings["security_names_file"]))
        errors = stock_pool.load_data_errors(repo_path(settings["data_errors_file"]))
        key = cache_key(segment=segment, fingerprint=read_fingerprint(data_dir), settings=settings,
                        names=names, errors=errors)
        with self._lock:
            if self._index is not None and self._index.key == key:
                return self._index
            idx = load_index(cache_dir, key)
            if idx is None:
                idx = build_index(data_dir, key=key, segment=segment, settings=settings,
                                  names=names, errors=errors)
                save_index(idx, cache_dir)
            self._index = idx
            return idx


def random_window(index: FinderIndex, data_dir, *, segment: tuple[str, str], window_bars: int,
                  rng: np.random.Generator) -> dict:
    """在全部进池股票日里均匀抽一个,给以它为中心的 window_bars 根图窗 {symbol, start, end}
    (两端截到这只股票有行情的范围与训练段终点,不往另一端补)。股票池为空 → LookupError。"""
    if len(index.pool_date) == 0:
        raise LookupError("股票池是空的")
    i = int(rng.integers(len(index.pool_date)))
    sym = index.symbols[int(index.pool_sym[i])]
    df = read_bars(data_dir, sym)
    dates = df.index[df.index <= pd.Timestamp(segment[1])]
    pos = int(dates.searchsorted(pd.Timestamp(index.pool_date[i])))
    half = int(window_bars) // 2
    start = max(0, pos - half)
    end = min(len(dates) - 1, pos + int(window_bars) - 1 - half)
    return {"symbol": sym, "start": _day(dates[start]), "end": _day(dates[end])}
