"""构建 samples/<id>/meta.yaml 内容。

meta.yaml 含：sample_id / ticker / bo_date / picked_at /
breakout_day OHLCV / consolidation 6 项（5 个无量纲字段 + pivot_close）。
后续可扩展（factor 原值 / 用户备注 / archetype tag 等）。
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.consolidation_fields import (
    compute_consolidation_fields,
)


def build_meta(
    sample_id: str,
    ticker: str,
    bo_date: pd.Timestamp,
    df_window: pd.DataFrame,
    bo_index: int,
    pk_index: int,
    picked_at: datetime,
) -> dict[str, Any]:
    """构建 meta.yaml 的 dict 内容。

    Args:
        sample_id: 形如 BO_AAPL_20240301
        ticker: 股票代码（已 upper）
        bo_date: 突破日期
        df_window: 包含 bo_index / pk_index 上下文的 OHLCV 切片
        bo_index: 突破日在 df_window 中的位置
        pk_index: 盘整起点在 df_window 中的位置
        picked_at: 用户挑选时间

    Returns:
        可直接 yaml.safe_dump 的 dict
    """
    bo_row = df_window.iloc[bo_index]
    consol = compute_consolidation_fields(df_window, bo_index, pk_index)

    return {
        "sample_id": sample_id,
        "ticker": ticker,
        "bo_date": bo_date.strftime("%Y-%m-%d"),
        "picked_at": picked_at.isoformat(timespec="seconds"),
        "breakout_day": {
            "open": float(bo_row["open"]),
            "high": float(bo_row["high"]),
            "low": float(bo_row["low"]),
            "close": float(bo_row["close"]),
            "volume": float(bo_row["volume"]),
        },
        "consolidation": consol,
    }


def write_meta_yaml(sample_id: str, meta: dict[str, Any]) -> Path:
    """将 meta dict 写入 samples/<id>/meta.yaml，返回写入路径。"""
    paths.ensure_sample_dir(sample_id)
    out_path = paths.meta_yaml_path(sample_id)
    out_path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out_path
