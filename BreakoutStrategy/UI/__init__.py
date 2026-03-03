"""
UI 模块 - 信号扫描可视化界面

提供交互式 UI 用于绝对信号扫描结果的可视化和分析
"""

# 主UI接口
from .main import InteractiveUI

# 配置加载器
from .config import get_ui_config_loader

# UI样式配置
from .styles import configure_global_styles

# 图表组件
from .charts import ChartCanvasManager

# 面板组件
from .panels import OutputPanel, ParameterPanel, StockListPanel

# 编辑器组件
from .editors import SignalConfigEditor

# 工具函数
from .utils import show_error_dialog

__version__ = '3.0.0'

__all__ = [
    # 主要接口
    'InteractiveUI',
    'configure_global_styles',
    'get_ui_config_loader',

    # 图表
    'ChartCanvasManager',

    # 面板
    'OutputPanel',
    'ParameterPanel',
    'StockListPanel',

    # 编辑器
    'SignalConfigEditor',

    # 工具
    'show_error_dialog',
]
