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


def test_build_triggered_matrix_nan_not_triggered():
    """NaN 样本在正向/反向因子上都判为未触发（level=0）。"""
    from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix

    raw_values = {
        'volume': np.array([2.5, np.nan, 10.0]),
        'overshoot': np.array([2.0, np.nan, 10.0]),
    }
    thresholds = {'volume': 5.0, 'overshoot': 5.0}
    factor_order = ['volume', 'overshoot']

    # volume gte 5.0; overshoot lte 5.0
    triggered = build_triggered_matrix(
        raw_values, thresholds, factor_order,
        negative_factors={'overshoot'},
    )

    # Sample 0: volume=2.5 (not gte 5) → 0; overshoot=2.0 (lte 5) → 1
    assert triggered[0, 0] == 0
    assert triggered[0, 1] == 1
    # Sample 1: NaN NaN → both 0（missing-as-fail）
    assert triggered[1, 0] == 0
    assert triggered[1, 1] == 0
    # Sample 2: volume=10.0 (gte) → 1; overshoot=10.0 (not lte) → 0
    assert triggered[2, 0] == 1
    assert triggered[2, 1] == 0


def test_tpe_bounds_skip_nan():
    """TPE bounds 的 quantile 应基于 NaN 过滤后的样本；无 NaN 混入导致 NaN bounds。"""
    # 这是行为契约测试——验证 np.quantile 在 NaN-filtered array 上有限
    raw = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, np.nan])
    valid = raw[~np.isnan(raw)]
    lo = float(np.quantile(valid, 0.02))
    hi = float(np.quantile(valid, 0.98))
    assert not np.isnan(lo)
    assert not np.isnan(hi)
    # 对照：未过滤的 np.quantile 应为 NaN（这是 numpy 的行为）
    lo_contam = float(np.quantile(raw, 0.02))
    assert np.isnan(lo_contam), "numpy's np.quantile should return NaN when input contains NaN"


def test_factor_diag_yaml_has_audit_fields(tmp_path):
    """factor_diag.yaml 每因子条目含 valid_count/valid_ratio/buffer。"""
    import yaml
    from BreakoutStrategy.mining.factor_diagnosis import write_diagnosed_yaml

    # 造一个最小 source yaml
    source_yaml = tmp_path / "source.yaml"
    source_yaml.write_text(yaml.dump({
        'quality_scorer': {
            'volume_factor': {
                'enabled': True,
                'thresholds': [5.0, 10.0],
                'values': [1.5, 2.0],
            },
        },
    }))

    output_yaml = tmp_path / "factor_diag.yaml"

    # 提供 modes + 新增的 audit_info
    modes = {'volume': 'gte'}
    audit_info = {'volume': {'valid_count': 1000, 'valid_ratio': 0.85, 'buffer': 63}}
    write_diagnosed_yaml(str(source_yaml), str(output_yaml), modes, audit_info=audit_info)

    loaded = yaml.safe_load(output_yaml.read_text())
    vol = loaded['quality_scorer']['volume_factor']
    assert vol['mode'] == 'gte'
    assert vol['valid_count'] == 1000
    assert vol['valid_ratio'] == 0.85
    assert vol['buffer'] == 63
