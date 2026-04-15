"""Per-Factor Gating Spec 2: mining NaN-aware behavior tests."""
import json
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.mining.data_pipeline import (
    build_dataframe,
    prepare_raw_values,
    apply_binary_levels,
)


def _write_synthetic_scan_json(tmp_path):
    """Write a minimal scan_results JSON with 2 BO: BO1 normal, BO2 has volume=None."""
    data = {
        "scan_metadata": {
            "feature_calculator_params": {
                "label_configs": [{"max_days": 20}],
            },
            "quality_scorer_params": {
                "volume_factor": {"thresholds": [5.0, 10.0]},
                "pbm_factor": {"thresholds": [0.7, 1.45]},
                "age_factor": {"thresholds": [42, 63]},
            },
        },
        "results": [
            {
                "symbol": "TEST",
                "breakouts": [
                    {
                        "date": "2024-01-10", "price": 10.0,
                        "volume": 2.5, "pbm": 1.3, "age": 100,
                        "labels": {"label_20": 0.05},
                    },
                    {
                        "date": "2024-02-10", "price": 11.0,
                        "volume": None,   # lookback insufficient
                        "pbm": None,
                        "age": 60,
                        "labels": {"label_20": 0.03},
                    },
                ],
            },
        ],
    }
    p = tmp_path / "scan.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_build_dataframe_preserves_none_as_nan(tmp_path):
    """build_dataframe 读 JSON 里 volume=None 应保留为 NaN，不变成 0。"""
    json_path = _write_synthetic_scan_json(tmp_path)
    df = build_dataframe(json_path)
    assert len(df) == 2
    # BO1 row (normal)
    assert df.iloc[0]['volume'] == 2.5
    # BO2 row (None values preserved as NaN)
    assert pd.isna(df.iloc[1]['volume'])
    assert pd.isna(df.iloc[1]['pbm'])
    # age (non-nullable buffer=0 factor) is preserved as int
    assert df.iloc[1]['age'] == 60


def test_prepare_raw_values_preserves_nan():
    """prepare_raw_values 不再 fillna(0)；NaN 自然承载。"""
    df = pd.DataFrame({
        'symbol': ['A', 'B'],
        'date': ['2024-01-01', '2024-01-02'],
        'volume': [2.5, np.nan],      # volume nullable 因子
        'volume_level': [0, 0],
        'age': [100, 60],              # buffer=0 非 nullable 因子
        'age_level': [1, 0],
        'label': [0.05, 0.03],
    })
    raw = prepare_raw_values(df, factors=['volume', 'age'])
    # volume 保留 NaN
    assert np.isnan(raw['volume'][1])
    assert raw['volume'][0] == 2.5
    # age 无 NaN（buffer=0 因子原始数据无 None）
    assert raw['age'][0] == 100
    assert raw['age'][1] == 60


def test_apply_binary_levels_reverse_factor_nan_not_triggered():
    """反向因子（如 overshoot mode=lte）+ NaN 样本不应被判为触发。"""
    df = pd.DataFrame({
        'overshoot': [2.0, np.nan, 10.0],       # 样本1 低触发；样本2 NaN；样本3 高不触发
        'overshoot_level': [0, 0, 0],
        'label': [0.05, 0.03, 0.02],
    })
    # 反向因子：overshoot <= 5.0 触发
    apply_binary_levels(df, {'overshoot': 5.0}, negative_factors={'overshoot'})
    # 样本1 (2.0 <= 5.0): triggered=1
    assert df['overshoot_level'].iloc[0] == 1
    # 样本2 (NaN): 绝不应被判为 triggered（即使 lte 且 threshold>0）
    assert df['overshoot_level'].iloc[1] == 0
    # 样本3 (10.0 > 5.0): triggered=0
    assert df['overshoot_level'].iloc[2] == 0


def test_apply_binary_levels_positive_factor_nan_not_triggered():
    """正向因子 + NaN 样本不触发。"""
    df = pd.DataFrame({
        'volume': [2.5, np.nan, 10.0],
        'volume_level': [0, 0, 0],
        'label': [0.05, 0.03, 0.02],
    })
    apply_binary_levels(df, {'volume': 5.0}, negative_factors=frozenset())
    assert df['volume_level'].iloc[0] == 0
    assert df['volume_level'].iloc[1] == 0  # NaN
    assert df['volume_level'].iloc[2] == 1
