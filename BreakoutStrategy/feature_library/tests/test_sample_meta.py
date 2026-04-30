"""Tests for sample meta.yaml builder."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import yaml

from BreakoutStrategy.feature_library.sample_meta import (
    build_meta, write_meta_yaml,
)


@pytest.fixture
def synthetic_df():
    n = 300  # 含 52 周回看
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "open": closes, "high": closes * 1.02, "low": closes * 0.98,
        "close": closes, "volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_meta_top_level_keys(synthetic_df):
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    assert meta["sample_id"] == "BO_AAPL_20240301"
    assert meta["ticker"] == "AAPL"
    assert meta["bo_date"] == "2024-03-01"
    assert meta["picked_at"] == "2026-04-27T10:30:00"
    assert "consolidation" in meta
    assert "breakout_day" in meta


def test_consolidation_block_has_6_fields(synthetic_df):
    """consolidation 字段现为 6 个（含 pivot_close 用于 prompt 归一化）。"""
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    consol = meta["consolidation"]
    assert set(consol.keys()) == {
        "consolidation_length_bars",
        "consolidation_height_pct",
        "consolidation_position_vs_52w_high",
        "consolidation_volume_ratio",
        "consolidation_tightness_atr",
        "pivot_close",
    }


def test_breakout_day_block(synthetic_df):
    meta = build_meta(
        sample_id="BO_AAPL_20240301",
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    bo = meta["breakout_day"]
    assert "open" in bo and "high" in bo and "low" in bo
    assert "close" in bo and "volume" in bo


def test_write_meta_yaml_roundtrip(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    sample_id = "BO_TEST_20240301"
    meta = build_meta(
        sample_id=sample_id, ticker="TEST",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df, bo_index=290, pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
    )
    out_path = write_meta_yaml(sample_id, meta)
    assert out_path.exists()

    loaded = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert loaded["sample_id"] == sample_id
    assert loaded["ticker"] == "TEST"
    assert "consolidation" in loaded
    assert set(loaded["consolidation"].keys()) == {
        "consolidation_length_bars",
        "consolidation_height_pct",
        "consolidation_position_vs_52w_high",
        "consolidation_volume_ratio",
        "consolidation_tightness_atr",
        "pivot_close",  # 归一化 prompt 所需基准
    }
