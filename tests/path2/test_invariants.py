from dataclasses import dataclass

import pytest

import path2
from path2 import (After, Any, At, Before, Detector, Event, Pattern,
                    TemporalEdge, config, run, set_runtime_checks)


def test_public_api_surface():
    for name in ("Event", "Detector", "TemporalEdge", "Before", "At",
                 "After", "Over", "Any", "Pattern", "run", "config",
                 "set_runtime_checks"):
        assert hasattr(path2, name), name


def test_end_to_end_detector_run_pattern_filter():
    @dataclass(frozen=True)
    class Vol(Event):
        ratio: float = 0.0

    class VolDetector:
        def detect(self, ratios):
            for i, r in enumerate(ratios):
                if r > 1.0:
                    yield Vol(event_id=f"v{i}", start_idx=i, end_idx=i, ratio=r)

    assert isinstance(VolDetector(), Detector)

    events = list(run(VolDetector(), [0.5, 2.0, 3.0, 0.9, 5.0]))
    assert [e.start_idx for e in events] == [1, 2, 4]

    pat = Pattern.all(lambda e: e.ratio >= 3.0)
    matched = [e for e in events if pat(e)]
    assert [e.ratio for e in matched] == [3.0, 5.0]


def test_end_to_end_checks_off_behavior_difference():
    @dataclass(frozen=True)
    class E(Event):
        pass

    class Bad:
        def detect(self, _):
            yield E(event_id="a", start_idx=5, end_idx=5)
            yield E(event_id="a", start_idx=3, end_idx=3)  # 递减+重复id

    with pytest.raises(ValueError):
        list(run(Bad(), None))

    set_runtime_checks(False)
    assert len(list(run(Bad(), None))) == 2  # 关检查后放行
