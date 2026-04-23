"""Map a calendar-date cutoff to a bar index in a DatetimeIndex."""
from __future__ import annotations

import datetime
from typing import Union

import pandas as pd


def compute_left_idx(
    df_index: pd.DatetimeIndex,
    cutoff: Union[pd.Timestamp, datetime.date, datetime.datetime, str],
) -> int:
    """Return index of the first df_index element >= cutoff.

    If all elements are < cutoff, returns len(df_index).
    If all elements are >= cutoff, returns 0.
    """
    cutoff_ts = pd.Timestamp(cutoff)
    return int(df_index.searchsorted(cutoff_ts, side="left"))
