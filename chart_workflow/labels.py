"""统一口径:单只股票的逐日标签(纯函数,按 numpy 数组向量化)。

对第 t 个交易日(决策日,收盘后出名单):
  买入价 P = open[t+1](名单盘后才出,只能次日开盘买)
  波动尺度 M = M_t(不是有限正数就不产标签)
  上线 U = P·(1+k·M),下线 D = P/(1+k·M),买入时固定
  观察日 t+1 .. t+H(共 H 天,含买入当日),t+H 必须是数据里存在的行
  方向值 dir:观察日里按收盘价最早达到或越过哪条线 → +1 / −1,都没有 → 0
  幅度 mag = max(high[观察日]) / P − 1
  回撤 dd  = min(low[观察日]) / P − 1(只报告)
  拿得到的涨幅 rise:s = 观察日里第一个 close ≤ D 的日子,窗口 W = [t+1 .. s]
      (没有 s 就取整个观察日),rise = max(high[W]) / P − 1;最高点日 = W 内最高价那天
  相对涨幅 rel = ln(1+rise) / ln(1+k·M),单位是「几倍止损距离」

训练段截断:`label_frame(..., train_end=...)` 先把行情截到训练段末日再算,于是
「t+H 必须存在」自动等价于「t+H 不晚于训练段末日」,标签不可能读到验证段价格。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def compute_labels(open_, high, low, close, M, k: float, H: int) -> dict:
    """逐日标签。输入为同长 1-D 数组(一只股票,已按日期升序、已截到训练段末日)。

    返回同长数组的 dict:
      valid(bool)、P、U、D、dir、mag、dd、rise、rel(float,无效处 NaN)、
      stop_off(观察日里第一个 close≤D 的偏移 1..H,没有为 -1)、
      peak_off(拿得到的涨幅窗口里最高价那天相对 t 的偏移 1..H,无效为 -1)。
    """
    open_ = np.asarray(open_, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    M = np.asarray(M, dtype=float)
    n = len(close)
    out = {name: np.full(n, np.nan) for name in
           ("P", "U", "D", "dir", "mag", "dd", "rise", "rel")}
    out["valid"] = np.zeros(n, dtype=bool)
    out["stop_off"] = np.full(n, -1, dtype=np.int64)
    out["peak_off"] = np.full(n, -1, dtype=np.int64)
    m = n - H                      # 只有 t ∈ [0, n-H-1] 的 t+H 存在
    if m <= 0:
        return out

    # 行 t = 观察日 t+1 .. t+H
    cw = sliding_window_view(close[1:], H)[:m]
    hw = sliding_window_view(high[1:], H)[:m]
    lw = sliding_window_view(low[1:], H)[:m]
    P = open_[1:m + 1]
    Mt = M[:m]
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(Mt) & (Mt > 0) & np.isfinite(P) & (P > 0)
    ok &= np.isfinite(cw).all(1) & np.isfinite(hw).all(1) & np.isfinite(lw).all(1)

    step = 1.0 + k * np.where(ok, Mt, 0.0)
    U = P * step
    D = P / step
    with np.errstate(invalid="ignore"):
        up_hit = cw >= U[:, None]
        dn_hit = cw <= D[:, None]
    has_up = up_hit.any(1)
    has_dn = dn_hit.any(1)
    first_up = np.where(has_up, up_hit.argmax(1), H)
    first_dn = np.where(has_dn, dn_hit.argmax(1), H)
    direction = np.where(first_up < first_dn, 1.0, np.where(first_dn < first_up, -1.0, 0.0))

    s = np.where(has_dn, first_dn, H - 1)               # 窗口末位(含)
    in_w = np.arange(H)[None, :] <= s[:, None]
    hw_cut = np.where(in_w, hw, -np.inf)
    peak = hw_cut.argmax(1)                             # 同价取最早那天
    with np.errstate(divide="ignore", invalid="ignore"):   # 无效行(P≤0 等)稍后整体置 NaN
        mag = hw.max(1) / P - 1.0
        dd = lw.min(1) / P - 1.0
        rise = hw_cut.max(1) / P - 1.0
        rel = np.log1p(rise) / np.log1p(k * Mt)

    sl = slice(0, m)
    out["valid"][sl] = ok
    for name, arr in (("P", P), ("U", U), ("D", D), ("dir", direction), ("mag", mag),
                      ("dd", dd), ("rise", rise), ("rel", rel)):
        out[name][sl] = np.where(ok, arr, np.nan)
    out["stop_off"][sl] = np.where(ok & has_dn, first_dn + 1, -1)
    out["peak_off"][sl] = np.where(ok, peak + 1, -1)
    return out


def label_frame(df: pd.DataFrame, M, k: float, H: int, train_end=None) -> pd.DataFrame:
    """对一只股票的日线算全部标签,返回与(截断后)df 行对齐的 DataFrame。

    df:列 open/high/low/close,DatetimeIndex 升序。M:与 df 同长的波动尺度序列。
    train_end:给了就先把 df 与 M 截到该日(含),之后的行不出现、也不被读。
    额外列:entry_date(买入日 t+1)、peak_date(最高点日)、stop_date(先碰下线那天,没有为 NaT)。
    """
    M = pd.Series(np.asarray(M, dtype=float), index=df.index)
    if train_end is not None:
        keep = df.index <= pd.Timestamp(train_end)
        df, M = df[keep], M[keep]
    lab = compute_labels(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, M.values, k, H)
    dates = df.index
    n = len(dates)
    idx = np.arange(n)

    def _date_at(off):
        pos = idx + off
        good = (off > 0) & (pos < n)
        res = pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]")
        res[good] = dates.values[pos[good]]
        return res

    out = pd.DataFrame({name: lab[name] for name in
                        ("valid", "P", "U", "D", "dir", "mag", "dd", "rise", "rel")},
                       index=dates)
    out["entry_date"] = _date_at(np.where(lab["valid"], 1, 0))
    out["peak_date"] = _date_at(lab["peak_off"])
    out["stop_date"] = _date_at(lab["stop_off"])
    return out
