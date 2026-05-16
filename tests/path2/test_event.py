import math
from dataclasses import dataclass

import pytest

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class _Vol(Event):
    ratio: float = 0.0
    flag: bool = False


def test_valid_construction():
    e = _Vol(event_id="v_1", start_idx=5, end_idx=5, ratio=2.3)
    assert e.event_id == "v_1"
    assert e.start_idx == 5 and e.end_idx == 5
    assert e.ratio == 2.3


def test_non_frozen_subclass_raises():
    with pytest.raises(TypeError):
        @dataclass  # 缺 frozen=True — Python 3.12 raises at class definition time
        class _Bad(Event):
            x: int = 0


def test_start_gt_end_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=9, end_idx=3)


def test_negative_start_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=-1, end_idx=0)


def test_non_int_idx_raises():
    with pytest.raises(TypeError):
        _Vol(event_id="v", start_idx=1.5, end_idx=2)


def test_nan_float_field_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=0, end_idx=0, ratio=math.nan)


def test_features_default_extracts_numeric_excludes_bool_and_str():
    e = _Vol(event_id="v_1", start_idx=2, end_idx=4, ratio=2.5, flag=True)
    feats = e.features
    assert feats == {"start_idx": 2, "end_idx": 4, "ratio": 2.5}
    assert "flag" not in feats          # bool 排除
    assert "event_id" not in feats      # str 排除


def test_subclass_post_init_calling_super_still_enforces():
    @dataclass(frozen=True)
    class _Checked(Event):
        ratio: float = 0.0

        def __post_init__(self):
            super().__post_init__()

    with pytest.raises(ValueError):
        _Checked(event_id="c", start_idx=5, end_idx=1)


def test_checks_off_allows_invalid():
    config.set_runtime_checks(False)
    e = _Vol(event_id="v", start_idx=9, end_idx=3, ratio=math.nan)
    assert e.start_idx == 9 and e.end_idx == 3   # 未抛错
