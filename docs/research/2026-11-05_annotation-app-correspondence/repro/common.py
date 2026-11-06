"""研究用临时代码(不入正式代码):读标注 + 读训练段行情 + 跑 new_step app 的公共函数。

只经 path2_web 的读数函数读训练段副本;只经 read_annotations 读标注。
"""
from __future__ import annotations

import pandas as pd

from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END

EXCLUDED_SAMPLES = {("SMX", "2025-11-24")}   # 疑似合股未复权的假台阶,用户已同意去掉

_cfg = load_config()


def load_state():
    s = read_annotations(_cfg)["state"]
    fname = {f["id"]: f["name"] for f in s["features"]}
    return s, fname


def load_win(symbol: str) -> pd.DataFrame:
    """与 compare 同口径:这只股票截到训练段末日的全部 K 线,0-based + date 列。"""
    return slice_window(read_bars(view_dataset_dir(_cfg), symbol), "1900-01-01", TRAIN_END)


def d2i(win: pd.DataFrame, date: str, side: str = "left") -> int:
    return int(win["date"].searchsorted(pd.Timestamp(date), side))


def i2d(win: pd.DataFrame, i: int) -> str:
    return str(win["date"].iloc[i].date())
