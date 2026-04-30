"""Sample ID 生成。

样本 ID 形如 BO_AAPL_20230115，作为 feature_library/samples/ 子目录名
+ 后续 ObservationLog / cooccurrence 引用主键。
"""

from datetime import date, datetime

import pandas as pd


def generate_sample_id(ticker: str, bo_date) -> str:
    """从 ticker 和突破日期生成稳定的 sample ID。

    Args:
        ticker: 股票代码（自动转大写，点号替换为下划线）
        bo_date: 突破日期，可以是 date / datetime / pandas.Timestamp

    Returns:
        形如 "BO_AAPL_20230115" 的字符串
    """
    if isinstance(bo_date, pd.Timestamp):
        date_str = bo_date.strftime("%Y%m%d")
    elif isinstance(bo_date, (date, datetime)):
        date_str = bo_date.strftime("%Y%m%d")
    else:
        raise TypeError(f"bo_date 类型不支持：{type(bo_date)}")

    safe_ticker = ticker.upper().replace(".", "_")
    return f"BO_{safe_ticker}_{date_str}"
