# -*- coding: utf-8 -*-
"""FC-001「买点日 ATR%(20)」换样本验证——feature-study 第一次完整六步跑通(验收 task 6)。

三种口径(强弱排序即机制证据):
  v_median20 — 登记簿原口径,rolling_atr_pct_nanmedian(20),买点当日
  v_wilder20 — 换平滑方式,calculate_atr(Wilder RMA, 20)/close,买点当日
  v_median10 — 换窗口长度,rolling_atr_pct_nanmedian(10),买点当日
每个比值口径的分子(TR/ATR 原始量,美元级)与分母(close_t)各留一列,供归因诊断
(坑表:比值出信号不能直接归功于分子)。买点当日 close/high/low 在决策时刻(收盘)
已知,TR[t] 用 t 的 high/low + t-1 的 close,无前瞻——与 rolling_atr_pct_nanmedian
docstring 的时点安全声明一致,故三列均不加 posthoc_ 前缀。

两轮电池(见 task-6-brief.md「陷阱」节):骨架自动注入的 c0_atr_pct(买点前一根
ATR/close,Wilder 窗14)与 FC-001 三个口径同源(都是波动率地板的变体)。
  A 轮 controls=["c0_atr_pct"]+KNOWN_SIGNALS — 验默认路径能跑通、关2 不降级
  B 轮 controls=KNOWN_SIGNALS               — FC-001 的真实判定(移出地板)
"""
import sys; sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy/.claude/skills/feature-study")
import numpy as np
import pandas as pd
from extract import build_dataset, load_adapter
from run_battery import run_battery
from path2.calc.atr import calculate_atr, rolling_atr_pct_nanmedian

adapter = load_adapter("bb_v1")
SCAN = "/home/yu/PycharmProjects/Trade_Strategy/outputs/path2_web/scans/20260908T113225.json"
# bb_v1 / 8325 只扫描 / 317 只命中 / 458 条 match / label_horizon=40 / 2025 全年严格窗

FEATURES = ["v_median20", "v_wilder20", "v_median10"]


def compute_features(win, row):
    t = int(row["entry_idx"])
    close_t = float(win["close"].iat[t])
    prev_close = win["close"].shift(1)
    tr = pd.concat([win["high"] - win["low"],
                    (win["high"] - prev_close).abs(),
                    (win["low"] - prev_close).abs()], axis=1).max(axis=1)
    tr_med20 = tr.rolling(20).apply(np.nanmedian, raw=True)
    tr_med10 = tr.rolling(10).apply(np.nanmedian, raw=True)
    atr20 = calculate_atr(win["high"], win["low"], win["close"], 20)
    m20 = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20)
    m10 = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 10)
    return dict(
        v_median20=float(m20.iat[t]),
        v_median10=float(m10.iat[t]),
        v_wilder20=float(atr20.iat[t] / close_t) if close_t > 0 else np.nan,
        tr_median_raw_20=float(tr_med20.iat[t]),   # v_median20 的分子(TR 中位数,美元)
        tr_median_raw_10=float(tr_med10.iat[t]),   # v_median10 的分子
        atr_wilder_raw_20=float(atr20.iat[t]),      # v_wilder20 的分子
        c_close_t=close_t,                          # 三者共享的分母
    )


df = build_dataset(adapter, scan=SCAN, out_csv="dataset.csv", compute_features=compute_features)

print("\n" + "=" * 78)
print("A 轮(默认路径,controls 含 c0_atr_pct 地板)")
print("=" * 78)
run_battery("dataset.csv", features=FEATURES,
            controls=["c0_atr_pct"] + adapter.KNOWN_SIGNALS, time_bucket_days=40)

print("\n" + "=" * 78)
print("B 轮(移出 c0_atr_pct 地板,FC-001 真实判定)")
print("=" * 78)
run_battery("dataset.csv", features=FEATURES,
            controls=adapter.KNOWN_SIGNALS, time_bucket_days=40)
