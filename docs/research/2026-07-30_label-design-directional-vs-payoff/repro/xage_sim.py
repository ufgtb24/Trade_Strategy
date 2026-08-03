"""XAGE tb_208_213 的 strategy_return 实测 repro(纯分析验证,非正式代码)。

目的:回答 skeptic 必答题——固定外生参数(8/20/10)下,payoff 对这个暴跌 match
输出什么?会不会还是正的?同时取 mfr 做对照。

口径与原 plan Task6 Step3 一致:
  - win_start=2024-09-19, win_end=2026-03-08, label_horizon=40
  - tb_208_213 = start_idx=208, end_idx=213(切窗后 df 的 0-based 行位置)
  - stop_loss=0.08, take_profit=0.20, trailing=0.10

不依赖 match_strategy_return(尚未实现),内联实现 simulation 双线退出 + mfr。
"""
from __future__ import annotations

import pandas as pd

PKL = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/XAGE.pkl"
WIN_START, WIN_END = pd.Timestamp("2024-09-19"), pd.Timestamp("2026-03-08")
TB_START, TB_END = 208, 213
HORIZON = 40
SL, TP, TRAIL = 0.08, 0.20, 0.10


def load_window() -> pd.DataFrame:
    df = pd.read_pickle(PKL)
    # 日期列可能是 'date' 或索引;统一成 date 列 + 按日期切窗
    if "date" not in df.columns:
        df = df.reset_index().rename(columns={df.index.name or "index": "date"})
    df["date"] = pd.to_datetime(df["date"])
    win = df[(df["date"] >= WIN_START) & (df["date"] <= WIN_END)].reset_index(drop=True)
    return win


def mfr(win: pd.DataFrame, start: int, end: int, horizon: int) -> float | None:
    """max_forward_return:买点窗内逐进场日 max(high[t+1..t+N])/close[t]-1 的均值。"""
    close, high, n = win["close"], win["high"], len(win)
    rets = []
    for t in range(start, end + 1):
        if t + horizon >= n:
            continue
        rets.append(float(high.iloc[t + 1 : t + horizon + 1].max()) / float(close.iat[t]) - 1.0)
    return sum(rets) / len(rets) if rets else None


def endpoint_return(win: pd.DataFrame, start: int, end: int, horizon: int) -> float | None:
    """directional 候选:close[t+N]/close[t]-1 的均值(对称、路径无关)。"""
    close, n = win["close"], len(win)
    rets = []
    for t in range(start, end + 1):
        if t + horizon >= n:
            continue
        rets.append(float(close.iat[t + horizon]) / float(close.iat[t]) - 1.0)
    return sum(rets) / len(rets) if rets else None


def strategy_return(win: pd.DataFrame, start: int, end: int, horizon: int,
                    sl: float, tp: float, trail: float) -> float | None:
    """静态止损 + 跟踪止盈双线退出,span 遍历取均值(内联实现,与 plan 口径一致)。"""
    high, low, close, n = win["high"], win["low"], win["close"], len(win)
    rets = []
    per_entry = []
    for t in range(start, end + 1):
        if t + horizon >= n:
            continue
        entry = float(close.iat[t])
        sl_line = entry * (1.0 - sl)
        tp_trigger = entry * (1.0 + tp)
        peak = entry
        exit_price = None
        for i in range(t + 1, t + horizon + 1):
            activated = peak >= tp_trigger
            protect = max(sl_line, peak * (1.0 - trail)) if activated else sl_line
            if float(low.iat[i]) <= protect:
                exit_price = protect
                break
            h = float(high.iat[i])
            if h > peak:
                peak = h
        if exit_price is None:
            exit_price = float(close.iat[t + horizon])
        r = exit_price / entry - 1.0
        rets.append(r)
        per_entry.append((t, exit_price, r, exit_price is not None))
    mean = sum(rets) / len(rets) if rets else None
    return mean, per_entry


def main() -> None:
    win = load_window()
    print(f"切窗后行数: {len(win)}  日期范围: {win['date'].iat[0].date()} .. {win['date'].iat[-1].date()}")
    # 进场日 close / 对应日期,便于核对
    for t in range(TB_START, TB_END + 1):
        if t < len(win):
            print(f"  进场日 t={t}  date={win['date'].iat[t].date()}  close={float(win['close'].iat[t]):.4f}")
    # 窗口内最低价 / 出现位置(看暴跌何时击穿止损)
    lo_idx = win["low"].iloc[TB_START + 1 : TB_START + HORIZON + 1].idxmin()
    print(f"  买点后 {HORIZON} 日内最低 low={float(win['low'].iat[lo_idx]):.4f} @ t={lo_idx} ({win['date'].iat[lo_idx].date()})")

    m = mfr(win, TB_START, TB_END, HORIZON)
    e = endpoint_return(win, TB_START, TB_END, HORIZON)
    s, per_entry = strategy_return(win, TB_START, TB_END, HORIZON, SL, TP, TRAIL)
    print("\n=== 结果(默认外生先验 8/20/10)===")
    print(f"  mfr (max_forward_return)     = {m:+.4f}  ({m*100:+.2f}%)")
    print(f"  endpoint_return (directional)= {e:+.4f}  ({e*100:+.2f}%)")
    print(f"  strategy_return (payoff,8/20/10) = {s:+.4f}  ({s*100:+.2f}%)")
    print(f"\n  逐进场日 exit:")
    for t, ep, r, _ in per_entry:
        print(f"    t={t}: exit_price={ep:.4f}  ret={r*100:+.2f}%")

    # === 参数敏感性扫描(证明 sim 是「外生先验下的投影」、非客观读数)===
    # 注意:这不是「扫参选优」(那是前瞻偏差),而是诚实披露 sim 值随先验变动。
    print("\n=== 参数敏感性:sim 随外生先验变动(披露用,非选优)===")
    print(f"  {'sl/tpp/trail':<16} {'sim':>10}")
    for sl, tp, trail in [
        (0.08, 0.20, 0.10),  # 默认
        (0.05, 0.15, 0.08),  # 更保守
        (0.03, 0.005, 0.005),  # 极紧止盈门槛+紧跟踪:峰值 +1.3% 一摸到就锁利
        (0.08, 0.005, 0.005),  # 默认止损 + 极紧止盈
        (0.15, 0.20, 0.10),  # 宽止损
        (0.08, 0.40, 0.10),  # 高止盈门槛(永不激活跟踪)
    ]:
        sv, _ = strategy_return(win, TB_START, TB_END, HORIZON, sl, tp, trail)
        tag = ""
        if sv is not None and sv > 0:
            tag = "  <-- 翻正!"
        print(f"  {sl*100:>4.1f}/{tp*100:>4.1f}/{trail*100:>4.1f}        {sv*100:>+9.2f}%{tag}")


if __name__ == "__main__":
    main()
