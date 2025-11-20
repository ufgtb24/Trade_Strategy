"""
可视化模块

提供突破检测、回测结果等的可视化功能
"""
from .plotters import BasePlotter, BreakthroughPlotter
from .components import CandlestickComponent, MarkerComponent, PanelComponent
from .utils import (
    quality_to_color,
    ensure_datetime_index,
    format_date,
    format_price,
    filter_date_range
)

__version__ = '1.0.0'

__all__ = [
    # 绘图器
    'BasePlotter',
    'BreakthroughPlotter',

    # 组件
    'CandlestickComponent',
    'MarkerComponent',
    'PanelComponent',

    # 工具函数
    'quality_to_color',
    'ensure_datetime_index',
    'format_date',
    'format_price',
    'filter_date_range',
]
