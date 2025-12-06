"""
UI 模块 (原 UI)

提供交互式UI用于突破检测结果的可视化和分析
"""

# 主UI接口
from .main import InteractiveUI

# 业务管理器 (被外部脚本使用)
from .managers import ScanManager, NavigationManager

# 配置加载器 (被外部脚本使用)
from .config import get_ui_config_loader, get_ui_param_loader

# UI样式配置
from .styles import configure_global_styles

# 图表组件 (高级用户可能需要)
from .charts import ChartCanvasManager
from .charts.components import CandlestickComponent, MarkerComponent, PanelComponent

# 工具函数
from .utils import (
    quality_to_color,
    ensure_datetime_index,
    format_date,
    format_price,
    filter_date_range,
    show_error_dialog,
)

__version__ = '2.0.0'

__all__ = [
    # === 主要接口 (常用) ===
    'InteractiveUI',
    'ScanManager',
    'configure_global_styles',
    'get_ui_config_loader',
    'get_ui_param_loader',

    # === 高级接口 ===
    # 图表管理器
    'ChartCanvasManager',
    'NavigationManager',

    # 绘图组件
    'CandlestickComponent',
    'MarkerComponent',
    'PanelComponent',

    # 工具函数
    'quality_to_color',
    'ensure_datetime_index',
    'format_date',
    'format_price',
    'filter_date_range',
    'show_error_dialog',
]
