"""测试信号检测器基类"""
import pytest
import pandas as pd
from datetime import date

from BreakoutStrategy.signals.detectors.base import SignalDetector
from BreakoutStrategy.signals.models import AbsoluteSignal, SignalType


class DummyDetector(SignalDetector):
    """用于测试的虚拟检测器"""

    def detect(self, df: pd.DataFrame, symbol: str):
        # 简单返回一个信号
        return [
            AbsoluteSignal(
                symbol=symbol,
                date=df.index[-1].date(),
                signal_type=SignalType.BREAKOUT,
                price=df["close"].iloc[-1],
            )
        ]


class TestSignalDetector:
    def test_detector_is_abstract(self):
        """基类不能直接实例化"""
        with pytest.raises(TypeError):
            SignalDetector()

    def test_subclass_can_detect(self):
        """子类可以正常检测"""
        detector = DummyDetector()
        df = pd.DataFrame(
            {"open": [100], "high": [105], "low": [99], "close": [103], "volume": [1000]},
            index=pd.to_datetime(["2026-01-10"]),
        )
        signals = detector.detect(df, "TEST")
        assert len(signals) == 1
        assert signals[0].symbol == "TEST"
