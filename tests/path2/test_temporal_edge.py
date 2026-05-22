import dataclasses
import math

import pytest

from path2 import config
from path2.core import TemporalEdge


def test_defaults():
    e = TemporalEdge(earlier="a", later="b")
    assert e.min_gap == 0
    assert e.max_gap == math.inf


def test_negative_min_gap_raises():
    with pytest.raises(ValueError):
        TemporalEdge(earlier="a", later="b", min_gap=-1)


def test_min_gap_gt_max_gap_raises():
    with pytest.raises(ValueError):
        TemporalEdge(earlier="a", later="b", min_gap=10, max_gap=5)


def test_frozen_cannot_mutate():
    e = TemporalEdge(earlier="a", later="b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.min_gap = 3


def test_usable_as_dict_key():
    e = TemporalEdge(earlier="a", later="b", min_gap=0, max_gap=5)
    d = {e: "x"}
    assert d[TemporalEdge(earlier="a", later="b", min_gap=0, max_gap=5)] == "x"


def test_checks_off_bypasses_validation():
    config.set_runtime_checks(False)
    e = TemporalEdge(earlier="a", later="b", min_gap=10, max_gap=5)
    assert e.min_gap == 10  # 未抛错
