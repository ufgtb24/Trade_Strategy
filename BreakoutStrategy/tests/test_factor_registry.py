"""Unit tests for factor_registry public API."""

import pytest

from BreakoutStrategy.factor_registry import (
    FactorInfo,
    find_factor,
    get_factor,
)


def test_factor_info_has_description_field_default_empty():
    """FactorInfo.description defaults to empty string when not set."""
    fi = FactorInfo('xtest', 'X Test', '测试',
                    (1.0,), (1.0,))
    assert fi.description == ''


def test_factor_info_description_is_set_when_provided():
    """FactorInfo.description holds the value passed in."""
    fi = FactorInfo('xtest', 'X Test', '测试',
                    (1.0,), (1.0,),
                    description='算法：xxx\n\n意义：yyy')
    assert fi.description == '算法：xxx\n\n意义：yyy'


def test_find_factor_returns_factor_when_key_exists():
    """find_factor returns the FactorInfo for a known key."""
    fi = find_factor('age')
    assert fi is not None
    assert fi.key == 'age'


def test_find_factor_returns_none_when_key_missing():
    """find_factor returns None for unknown key (no exception)."""
    assert find_factor('not_a_real_factor') is None


def test_find_factor_handles_none_input():
    """find_factor returns None when given None (caller convenience)."""
    assert find_factor(None) is None


def test_get_factor_still_raises_on_missing():
    """get_factor (existing API) still raises KeyError for unknown keys."""
    with pytest.raises(KeyError):
        get_factor('not_a_real_factor')


def test_all_active_factors_have_description():
    """每个 active 因子必须有非空 description。"""
    from BreakoutStrategy.factor_registry import get_active_factors
    missing = [fi.key for fi in get_active_factors() if not fi.description]
    assert missing == [], f"Active factors missing description: {missing}"


def test_all_descriptions_have_two_sections():
    """description 应包含 '算法：' 和 '意义：' 两段。"""
    from BreakoutStrategy.factor_registry import FACTOR_REGISTRY
    bad = []
    for fi in FACTOR_REGISTRY:
        if not fi.description:
            continue  # description 未填的因子由 test_all_active_factors_have_description 单独覆盖
        if '算法：' not in fi.description or '意义：' not in fi.description:
            bad.append(fi.key)
    assert bad == [], f"Descriptions missing 算法/意义 section: {bad}"


def test_find_factor_by_yaml_key_returns_factor():
    """find_factor_by_yaml_key resolves yaml-style keys."""
    from BreakoutStrategy.factor_registry import find_factor_by_yaml_key
    fi = find_factor_by_yaml_key('peak_vol_factor')
    assert fi is not None
    assert fi.key == 'peak_vol'


def test_find_factor_by_yaml_key_returns_none_for_unknown():
    """find_factor_by_yaml_key returns None for non-factor names and None input."""
    from BreakoutStrategy.factor_registry import find_factor_by_yaml_key
    assert find_factor_by_yaml_key('peak_weights') is None
    assert find_factor_by_yaml_key(None) is None
