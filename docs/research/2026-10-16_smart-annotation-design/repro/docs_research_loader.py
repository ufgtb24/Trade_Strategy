"""研究用小工具:读一只股票并立刻截到给定日期(且硬性不晚于 2025-12-31)。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HARD_END = pd.Timestamp("2025-12-31")


def load(symbol: str, cut: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_pickle(ROOT / "datasets" / "pkls" / f"{symbol}.pkl")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df = df[df.index <= min(cut, HARD_END)].copy()
    assert df.index.max() <= HARD_END
    return df
