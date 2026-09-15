# -*- coding: utf-8 -*-
"""E0:数据覆盖抽查(只读 pkl 的日期列,不跑检测)。随机抽 150 只(seed 0),看起止日期分布。
用途:确定「还有哪些年份可以当验证样本」——数据起点决定首部缓冲之后最早可用的窗口。"""
import glob
import random

import pandas as pd

PKL = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"
fs = sorted(glob.glob(PKL)); random.seed(0); s = random.sample(fs, 150)
st, en = [], []
for f in s:
    d = pd.read_pickle(f)
    dt = pd.to_datetime(d["date"]) if "date" in d.columns else pd.to_datetime(d.index)
    st.append(dt.min()); en.append(dt.max())
st, en = pd.Series(st), pd.Series(en)
print("pkl 总数", len(fs))
print("起点分布\n", st.describe()); print("终点分布\n", en.describe())
print("起点 == 2021-08-20 的占比", round((st == pd.Timestamp("2021-08-20")).mean(), 3))
print("首部缓冲 250 交易日 ≈", (pd.Timestamp("2021-08-20") + pd.tseries.offsets.BDay(250)).date())
