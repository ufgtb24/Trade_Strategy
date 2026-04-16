from datetime import date
import pytest
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec


def _make_spec(**overrides):
    """辅助：构造一个默认 spec，调用方按需覆盖字段。"""
    defaults = dict(
        scan_start_ideal=date(2024, 1, 1),
        scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 1, 1),
        scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2023, 11, 13),
        display_start=date(2022, 1, 1),
        display_end=date(2024, 12, 31),
        pkl_start=date(2020, 1, 1),
        pkl_end=date(2024, 12, 31),
    )
    defaults.update(overrides)
    return ChartRangeSpec(**defaults)


def test_no_degradation_when_actual_equals_ideal():
    spec = _make_spec()
    assert spec.scan_start_degraded is False
    assert spec.scan_end_degraded is False
    assert spec.compute_buffer_degraded is False


def test_scan_start_degraded_when_actual_later():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
    )
    assert spec.scan_start_degraded is True


def test_scan_end_degraded_when_actual_earlier():
    spec = _make_spec(
        scan_end_ideal=date(2024, 12, 31),
        scan_end_actual=date(2024, 10, 15),
    )
    assert spec.scan_end_degraded is True


def test_compute_buffer_degraded_when_actual_later():
    spec = _make_spec(
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2024, 2, 1),
    )
    assert spec.compute_buffer_degraded is True


def test_spec_is_frozen():
    spec = _make_spec()
    with pytest.raises((AttributeError, TypeError)):
        spec.scan_start_actual = date(2020, 1, 1)
