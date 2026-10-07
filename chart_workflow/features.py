"""分组用的几个简单特征:只用决策日 t 及以前的数据(全部是向后看的滚动量)。

  dd250   = close[t] / max(high[t-249..t]) − 1
  r60     = close[t] / close[t-60] − 1
  width40 = (max(high[t-39..t]) − min(low[t-39..t])) / close[t]
  涨前状态 pre_state:dd250 ≤ 深跌线 → 深跌;否则 r60 ≥ 已涨线 → 已在涨;
                     否则 width40 ≤ 横盘倍数 × M_t → 横盘;否则 → 其他
  当日跳空 gap:open[t] / close[t-1] − 1 ≥ 跳空倍数 × M_t
  当日量倍数 vol_mult = volume[t] / mean(volume[t-63..t-1])

回看窗口不满时该特征为 NaN(不拿不足的历史凑数);NaN 参与比较一律不成立,
所以历史太短的股票日落到「其他」、不跳空,量倍数标签为空。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRE_STATES = ("深跌", "已在涨", "横盘", "其他")


def feature_frame(df: pd.DataFrame, M, fcfg: dict) -> pd.DataFrame:
    """返回与 df 行对齐的特征表:dd250、r60、width40、gap、vol_mult、pre_state、tags。

    df:列 open/high/low/close/volume,按日期升序。M:与 df 同长的波动尺度。
    fcfg:config 的 features 子树。
    """
    M = pd.Series(np.asarray(M, dtype=float), index=df.index)
    high, low, close = df["high"], df["low"], df["close"]
    dd250 = close / high.rolling(250, min_periods=250).max() - 1.0
    r60 = close / close.shift(60) - 1.0
    width40 = (high.rolling(40, min_periods=40).max()
               - low.rolling(40, min_periods=40).min()) / close
    gap_ret = df["open"] / close.shift(1) - 1.0
    gap = (gap_ret >= fcfg["gap_m"] * M).fillna(False).astype(bool)
    vol_base = df["volume"].rolling(63, min_periods=63).mean().shift(1)
    vol_mult = (df["volume"] / vol_base).replace([np.inf, -np.inf], np.nan)

    pre_state = np.where(dd250 <= fcfg["deep_drop_dd250"], "深跌",
                np.where(r60 >= fcfg["rising_r60"], "已在涨",
                np.where(width40 <= fcfg["flat_width40_m"] * M, "横盘", "其他")))

    lo, hi = fcfg["vol_bins"]
    vol_tag = np.where(vol_mult.isna(), "",
              np.where(vol_mult < lo, f"量<{lo:g}倍",
              np.where(vol_mult < hi, f"量{lo:g}–{hi:g}倍", f"量≥{hi:g}倍")))
    out = pd.DataFrame({
        "dd250": dd250, "r60": r60, "width40": width40,
        "gap": gap, "vol_mult": vol_mult,
        "pre_state": pre_state, "vol_tag": vol_tag,
    }, index=df.index)
    return out


def tags_of(gap: bool, vol_tag: str) -> list:
    """一条记录的标签:跳空 / 不跳空 + 量倍数档(无档时不写)。"""
    tags = ["跳空" if gap else "不跳空"]
    if vol_tag:
        tags.append(vol_tag)
    return tags
