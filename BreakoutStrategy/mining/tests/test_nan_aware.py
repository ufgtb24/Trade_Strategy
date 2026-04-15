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
