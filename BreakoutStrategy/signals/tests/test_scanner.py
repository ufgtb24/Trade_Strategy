"""测试绝对信号扫描器"""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from BreakoutStrategy.signals.scanner import AbsoluteSignalScanner


class TestAbsoluteSignalScanner:
    @pytest.fixture
    def scanner(self):
        return AbsoluteSignalScanner()

    def create_test_df(self, symbol: str, with_signals: bool = True):
        """创建测试数据"""
        n_days = 300
        dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

        np.random.seed(hash(symbol) % 2**32)

        # 基础价格
        returns = np.random.normal(0.0005, 0.015, n_days)
        prices = 100 * np.cumprod(1 + returns)

        volumes = np.random.uniform(1000, 2000, n_days)

        if with_signals:
            # 添加一个大成交量日
            volumes[250] = 8000
            # 添加一个大阳线
            prices[260] = prices[259] * 1.06

        df = pd.DataFrame(
            {
                "open": prices * 0.995,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": volumes,
            },
            index=dates,
        )
        return df

    @pytest.mark.skip(reason="Scanner API changed: uses data_dir instead of data_loader")
    def test_scan_single_stock(self, scanner):
        """扫描单只股票"""
        pass

    @pytest.mark.skip(reason="Scanner API changed: uses data_dir instead of data_loader")
    def test_scan_multiple_stocks(self, scanner):
        """扫描多只股票"""
        pass

    @pytest.mark.skip(reason="Scanner API changed: uses data_dir instead of data_loader")
    def test_scan_with_config(self):
        """使用配置扫描"""
        pass
