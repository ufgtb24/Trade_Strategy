"""Tests for preprocess orchestrator (chart + meta + nl_description)."""
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.preprocess import preprocess_sample


@pytest.fixture
def synthetic_df():
    n = 300
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "open": closes, "high": closes * 1.02, "low": closes * 0.98,
        "close": closes, "volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_preprocess_creates_three_artifacts(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = "GLM-4V 返回的描述文本"

    sample_id = preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    assert sample_id == "BO_AAPL_20240301"
    assert paths.chart_png_path(sample_id).exists()
    assert paths.meta_yaml_path(sample_id).exists()
    nl_path = paths.nl_description_path(sample_id)
    assert nl_path.exists()
    assert nl_path.read_text().strip() == "GLM-4V 返回的描述文本"


def test_preprocess_calls_backend_with_chart_and_message(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = "ok"

    preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    fake_backend.describe_chart.assert_called_once()
    call_kwargs = fake_backend.describe_chart.call_args.kwargs
    assert call_kwargs["chart_path"] == paths.chart_png_path("BO_AAPL_20240301")
    # 脱敏后 user_message 不含 ticker / bo_date / 绝对价，含相对 % 描述
    assert "AAPL" not in call_kwargs["user_message"]
    assert "2024-03-01" not in call_kwargs["user_message"]
    assert "%" in call_kwargs["user_message"]


def test_preprocess_skips_nl_when_backend_returns_empty(tmp_path, synthetic_df, monkeypatch):
    """backend 返回空字符串（GLM call 失败）时，仍写 chart + meta，但 nl_description.md 含 fallback 标记。"""
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    fake_backend = MagicMock()
    fake_backend.describe_chart.return_value = ""

    sample_id = preprocess_sample(
        ticker="AAPL",
        bo_date=pd.Timestamp("2024-03-01"),
        df_window=synthetic_df,
        bo_index=290,
        pk_index=260,
        picked_at=datetime(2026, 4, 27, 10, 30),
        backend=fake_backend,
    )

    nl_text = paths.nl_description_path(sample_id).read_text()
    assert "PREPROCESS_FAILED" in nl_text
    assert paths.chart_png_path(sample_id).exists(), "chart.png should be written even on backend failure"
    assert paths.meta_yaml_path(sample_id).exists(), "meta.yaml should be written even on backend failure"
