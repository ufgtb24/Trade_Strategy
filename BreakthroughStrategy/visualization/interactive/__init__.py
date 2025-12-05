"""交互式可视化模块"""

from .scan_manager import ScanManager, compute_breakthroughs_from_dataframe
from .interactive_ui import InteractiveUI
from .stock_list_panel import StockListPanel
from .parameter_panel import ParameterPanel
from .chart_canvas_manager import ChartCanvasManager

__all__ = [
    'ScanManager',
    'compute_breakthroughs_from_dataframe',
    'InteractiveUI',
    'StockListPanel',
    'ParameterPanel',
    'ChartCanvasManager'
]
