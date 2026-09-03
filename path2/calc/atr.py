"""ATR 计算 (Wilder RMA)。"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 首穿波动率尺度 M(rolling_atr_pct_nanmedian)的默认窗口。path2/eval.py 的
# match_first_passage / random_day_first_passage 与调参工具链(multivar_core.py /
# multivar_scan.py)四处都要按同一把尺子外传/内算 M——单点导出避免散落字面量 20
# 改一处不改另一处、静默分叉 FP 口径(复审 Important I-5)。
FP_ATR_WINDOW: int = 20


def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                  period: int = 14) -> pd.Series:
    """Wilder RMA 平滑的 ATR。

    返回与输入同长 Series(前 period-1 为 NaN,第 period 个为算术均;之后为 Wilder 递推)。
    TR_i = max(H_i - L_i, |H_i - C_{i-1}|, |L_i - C_{i-1}|)
    ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period
    实现:numpy 标量递推(无 pandas 逐行索引),与原 pandas 逐行实现逐值等价(1e-12)。
    NaN 语义同 pandas max(skipna):三项中的 NaN 被忽略;全 NaN 则 TR 为 NaN。
    """
    h = highs.to_numpy(dtype=float)
    l = lows.to_numpy(dtype=float)
    c = closes.to_numpy(dtype=float)
    n = len(c)
    out = np.full(n, np.nan)
    if n < period:
        return pd.Series(out, index=closes.index, dtype=float)
    pc = np.empty(n); pc[0] = np.nan; pc[1:] = c[:-1]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))   # fmax 忽略 NaN
    head = tr[:period]
    out[period - 1] = np.nanmean(head) if np.isnan(head).any() else head.mean()
    a = out[period - 1]
    k = period - 1
    for i in range(period, n):
        a = (a * k + tr[i]) / period
        out[i] = a
    return pd.Series(out, index=closes.index, dtype=float)


def rolling_atr_pct_nanmedian(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                              period: int = 20) -> pd.Series:
    """TR/close 的滚动 nanmedian —— 首次穿越的波动率尺度 M。

    M_t = nanmedian of (TR/close) over [t-period+1 .. t](含 t 当日;买点日 t 收盘
    买入,TR[t] 用 t 的 high/low + t-1 的 close,均已知 → 无前瞻)。前 period-1 个
    为 NaN(样本不足,首穿判定时跳过这些 t)。

    与 calculate_atr 的区别:后者 Wilder RMA(均值类,对一年一次的极端异动不鲁棒,
    会被撑成一把刻度过大的尺子);本函数用 nanmedian(中位数,免疫少数异动)。
    TR 含跳空(|high-prev_close| / |low-prev_close|),与首穿判定 high/low 越线
    含跳空(跳空越过算触)自洽。
    """
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr_pct = tr / closes
    return tr_pct.rolling(period).apply(np.nanmedian, raw=True)


def calculate_tr_median(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                        window: int = 14) -> pd.Series:
    """t4 波动率单元:vol[i] = median(TR) over [i-window, i-1](不含当根)。

    TR = max(high-low, |high-prev_close|, |low-prev_close|);TR[0] 显式置 NaN
    (prev_close 不存在),窗口含 TR[0] → NaN(热身)。shift(1) 避开当根自指
    (当根大 TR 会同时抬高自己的反弹阈值)。中位数而非均值:TR 右偏,burst 段
    大 TR 拉爆均值;median 表征「典型波动」(spec §1)。

    空输入(0 行)返回空 Series:下游 detector(V4 detect 预计算 vol)会遇
    preview 空窗切片,iloc[0] 赋值在空 Series 上是 IndexError。
    """
    if len(closes) == 0:
        return pd.Series([], dtype=float)
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr.rolling(window).median().shift(1)
