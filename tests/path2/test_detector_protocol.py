from dataclasses import dataclass

from path2.core import Detector, Event


@dataclass(frozen=True)
class _E(Event):
    pass


def test_conforming_class_is_detector():
    class Good:
        def detect(self, source):
            yield _E(event_id="e", start_idx=0, end_idx=0)

    assert isinstance(Good(), Detector)


def test_non_conforming_class_is_not_detector():
    class Bad:
        def scan(self, source):
            return []

    assert not isinstance(Bad(), Detector)
