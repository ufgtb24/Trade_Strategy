"""Tests for sample ID generation."""
from datetime import date

import pandas as pd

from BreakoutStrategy.feature_library.sample_id import generate_sample_id


def test_generate_from_ticker_and_date_object():
    sample_id = generate_sample_id(ticker="AAPL", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_AAPL_20230115"


def test_generate_from_ticker_and_pandas_timestamp():
    ts = pd.Timestamp("2024-12-03")
    sample_id = generate_sample_id(ticker="MSFT", bo_date=ts)
    assert sample_id == "BO_MSFT_20241203"


def test_ticker_uppercased():
    sample_id = generate_sample_id(ticker="aapl", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_AAPL_20230115"


def test_strips_dot_in_ticker():
    """部分美股 ticker 含点号（如 BRK.B），需替换为下划线以适配文件系统。"""
    sample_id = generate_sample_id(ticker="BRK.B", bo_date=date(2023, 1, 15))
    assert sample_id == "BO_BRK_B_20230115"
