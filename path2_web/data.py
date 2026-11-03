"""读行情 read_bars() + 唯一权威切片 slice_window() + OHLC 序列化。

扫描 worker 与 /ohlc 共用 slice_window,保证 bars[i] ↔ start_idx==i 严格对齐
(同一 (symbol,start,end) 下,K 线第 i 根 == detector 看到的第 i 个位置)。

数据墙(用户定的红线):2026-01-01 起的行情一律不给用户看。网页的 K 线、诊断、单股预览、扫描都只经
read_bars 读行情,它把行截到训练段末日 TRAIN_END(含)。TRAIN_END 是代码常量,配置改不了——
配置里的数据目录即使误指到完整行情,也读不出 2026 年的 bar。读的目录本身应是截到训练段末日的那份副本
(scripts/data/make_train_snapshot.py 生成)。
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

TRAIN_END = "2025-12-31"     # 训练段末日:网页读行情的硬上限(代码常量,不从配置读)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,14}$")


def check_symbol(symbol) -> str:
    """代码名格式校验:不合格(含路径分隔符、..、空白等,防路径穿越)→ ValueError。返回原样的代码名。"""
    if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol) or ".." in symbol:
        raise ValueError(f"非法代码: {symbol!r}")
    return symbol


def read_bars(data_dir, symbol: str) -> pd.DataFrame:
    """网页读一只股票行情的唯一入口:校验代码名,读 data_dir/<symbol>.pkl,去 tz、按日期排序,
    只留日期 ≤ TRAIN_END 的行。探测器预热要的更早的行情照常在内(调用方再用 slice_window 切窗)。

    代码名不合格 → ValueError;文件不存在 → FileNotFoundError。
    """
    check_symbol(symbol)
    df = pd.read_pickle(Path(data_dir) / f"{symbol}.pkl")
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df[df.index <= pd.Timestamp(TRAIN_END)]


def slice_window(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """按日期双端含端点切片,返回 0-based 行位置的 DataFrame(保留 date 列,不改行序)。

    前提:df.index 是 DatetimeIndex(index.name=="date",沿用既有 pkl 事实)。
    tz-aware 先去 tz;空/非法区间返回空 df。
    """
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    win = df.loc[str(start_date):str(end_date)]
    return win.reset_index()      # DatetimeIndex(name='date') → 'date' 列;行号 0-based


def serialize_ohlc(symbol: str, win_df: pd.DataFrame) -> dict:
    """把 slice_window 的结果序列化成 {symbol, bars:[{date,o,h,l,c,v,rv}]}。
    bars[i] 对应 win_df.iloc[i](即 detector 的 start_idx==i)。

    rv (相对成交量) 口径同 dev UI: volume[d] / mean(volume[d-63:d])
    实现 rolling(63, min_periods=1).mean().shift(1); inf/nan 清零。
    """
    avg_vol = win_df["volume"].rolling(63, min_periods=1).mean().shift(1)
    rv_series = (win_df["volume"] / avg_vol).replace([np.inf, -np.inf], 0).fillna(0)
    bars = []
    for i, (_, row) in enumerate(win_df.iterrows()):
        bars.append({
            "date": str(row["date"])[:10],
            "o": float(row["open"]),
            "h": float(row["high"]),
            "l": float(row["low"]),
            "c": float(row["close"]),
            "v": float(row["volume"]),
            "rv": float(rv_series.iloc[i]),
        })
    return {"symbol": symbol, "bars": bars}


def list_symbols(data_dir) -> list[str]:
    """股票列表:data_dir 里每个 <代码>.pkl 取文件名去后缀,只留过得了 check_symbol 的,按字母序返回。

    data_dir 应是训练段副本:截完为空的股票(2026 年才上市的)生成副本时已经跳过,所以不在列表里。
    不是 .pkl 的文件(副本的指纹清单、说明文件等)不算股票;不读文件内容。
    """
    out = []
    for p in Path(data_dir).glob("*.pkl"):
        if not p.is_file():
            continue
        try:
            out.append(check_symbol(p.stem))
        except ValueError:
            continue
    return sorted(out)
