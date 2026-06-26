import os
import tempfile

import pytest

from path2_apps.bottom_breakout_burst.params import (
    Params, BoParams, BurstParams, TbParams, EdgesParams, load_params, DEFAULT_YAML_PATH,
)


def test_default_returns_nested_instances():
    p = Params.default()
    assert isinstance(p.bo, BoParams)
    assert isinstance(p.burst, BurstParams)
    assert isinstance(p.tb, TbParams)
    assert isinstance(p.edges, EdgesParams)


def test_default_bo_defaults():
    bo = Params.default().bo
    assert bo.total_window == 10
    assert bo.min_side_bars == 2
    assert bo.min_relative_height == 0.05
    assert bo.exceed_threshold == 0.005
    assert bo.peak_supersede_threshold == 0.03
    assert bo.vol_baseline_period == 63
    assert bo.peak_measure == "high"
    assert bo.breakout_measure == "high"


def test_default_burst_defaults():
    burst = Params.default().burst
    assert burst.gap_max == 5
    assert burst.vol_baseline_period == 63
    assert burst.min_bos == 2
    assert burst.first_drought_min == 20
    assert burst.distinct_pk_min == 4
    assert burst.vol_spike_min == 8.0


def test_default_tb_defaults():
    tb = Params.default().tb
    assert tb.max_start_gap == 5
    assert tb.max_window == 5
    assert tb.atr_window == 14
    assert tb.big_rise_k == 1.5
    assert tb.pullback_min_atr == 1.0
    assert tb.anchor_measure == "high"
    assert tb.support_measure == "low"


def test_params_frozen_top_and_nested():
    p = Params.default()
    with pytest.raises(Exception):
        p.bo = BoParams()
    with pytest.raises(Exception):
        p.bo.total_window = 99


def test_kwargs_slices_against_detector_signatures():
    """bo_kwargs/burst_kwargs/throwback_kwargs 返回与各 detector __init__ 一一对应的 dict。"""
    p = Params.default()
    bo = p.bo_kwargs()
    assert set(bo) == {'total_window', 'min_side_bars', 'min_relative_height',
                       'exceed_threshold', 'peak_supersede_threshold',
                       'vol_baseline_period', 'peak_measure', 'breakout_measure'}
    assert bo['total_window'] == 10
    burst = p.burst_kwargs()
    assert set(burst) == {'gap_max', 'min_bos', 'vol_baseline_period'}, (
        "burst_kwargs() 必须精确匹配 BurstDetector 签名;阈值走 where 不进 detector"
    )
    assert burst['min_bos'] == 2 and burst['gap_max'] == 5
    tb = p.throwback_kwargs()
    assert set(tb) == {'max_start_gap', 'max_window', 'atr_window',
                       'big_rise_k', 'pullback_min_atr',
                       'anchor_measure', 'support_measure'}


def test_from_yaml_partial_override_at_section_level():
    """yaml 局部 section + section 内局部字段 → 缺失字段用子 dataclass default 兜底。"""
    yaml_text = """
burst:
  first_drought_min: 80
  gap_max: 8
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        p = Params.from_yaml(path)
        assert p.burst.first_drought_min == 80   # yaml 覆盖
        assert p.burst.gap_max == 8              # yaml 覆盖
        assert p.burst.min_bos == 2              # yaml 未提及,用 default
        assert p.bo.total_window == 10           # 整 bo section 缺失,用 default
        assert p.tb.max_start_gap == 5           # 整 tb section 缺失,用 default
    finally:
        os.unlink(path)


def test_from_yaml_rejects_unknown_top_section():
    """yaml 顶层含未知 section → ValueError。"""
    yaml_text = """
bo: { total_window: 20 }
typoooo: { foo: 1 }
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        with pytest.raises(ValueError, match="typoooo"):
            Params.from_yaml(path)
    finally:
        os.unlink(path)


def test_from_yaml_rejects_unknown_section_field():
    """yaml section 内含未知字段 → ValueError(嵌套校验,堵 yaml 弱类型静默无效陷阱)。"""
    yaml_text = """
burst:
  first_drought_min: 30
  bo_typooo: 99
"""
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
        f.write(yaml_text)
        path = f.name
    try:
        with pytest.raises(ValueError, match="bo_typooo"):
            Params.from_yaml(path)
    finally:
        os.unlink(path)


def test_load_params_reads_default_yaml_path():
    """load_params() 真去读 DEFAULT_YAML_PATH (app 同目录 params.yaml)。
    端到端 wiring 测试,防 path 计算错(__file__/相对路径)在重构中断裂。"""
    assert DEFAULT_YAML_PATH.exists(), f"app 目录下应有 params.yaml: {DEFAULT_YAML_PATH}"
    p = load_params()
    assert isinstance(p, Params)
    # yaml 现役为 V3.3 B 方案严值;dataclass default 是宽松值。两者必须分叉,
    # 否则证明 load_params 没真去读 yaml。
    assert p.bo.total_window != Params.default().bo.total_window, (
        "load_params() 读到的 bo.total_window 与 dataclass default 相同;"
        "yaml 应是 V3.3 B 方案严值与 dataclass 宽松默认不同,二者相等暗示 yaml 未真读"
    )
