"""共享 UI 基础设施 (shared UI infrastructure).

提供 dev / live 两个应用共用的纯 UI 组件：
- charts/: K 线图画布、范围规范、坐标轴交互等
- styles.py: 字体、颜色常量、tkinter ttk 样式配置

本包不含任何业务逻辑或策略参数，只承载与具体应用无关的界面原语。
"""

from .charts import ChartCanvasManager
from .charts.components import CandlestickComponent, MarkerComponent, PanelComponent
from .styles import configure_global_styles

__all__ = [
    "ChartCanvasManager",
    "CandlestickComponent",
    "MarkerComponent",
    "PanelComponent",
    "configure_global_styles",
]
