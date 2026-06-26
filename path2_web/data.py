"""唯一权威切片 slice_window() + OHLC 序列化。

扫描 worker 与 /ohlc 共用 slice_window,保证 bars[i] ↔ start_idx==i 严格对齐
(同一 (symbol,start,end) 下,K 线第 i 根 == detector 看到的第 i 个位置)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


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
