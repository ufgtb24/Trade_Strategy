from path2.atoms.trend import TrendSegment, TrendSegmentDetector
from path2.atoms.breakout import BOEvent, BODetector
from path2.atoms.throwback import ThrowbackEvent, ThrowbackDetector
from path2.atoms.platform import Platform, PlatformDetector
from path2.atoms.distribution import Distribution, DistributionDetector


def test_detector_declares_event_cls():
    assert TrendSegmentDetector.event_cls is TrendSegment
    assert BODetector.event_cls is BOEvent
    assert ThrowbackDetector.event_cls is ThrowbackEvent
    assert PlatformDetector.event_cls is Platform
    assert DistributionDetector.event_cls is Distribution


def test_event_cls_class_id():
    assert TrendSegmentDetector.event_cls.class_id == "trend"
    assert BODetector.event_cls.class_id == "bo"
    assert ThrowbackDetector.event_cls.class_id == "tb"
    assert PlatformDetector.event_cls.class_id == "platform"
    assert DistributionDetector.event_cls.class_id == "dist"
