"""业务逻辑管理器

ScanManager 和 TemplateManager 已迁出到 analysis/scanner.py 和 mining/template_matcher.py。
此处保留重新导出只是为了向后兼容，避免破坏开发 UI 的 import 链。
新代码请直接从 BreakoutStrategy.analysis.scanner / BreakoutStrategy.mining.template_matcher 导入。
"""

from .navigation_manager import NavigationManager
from BreakoutStrategy.analysis.scanner import (
    ScanManager,
    compute_breakouts_from_dataframe,
    preprocess_dataframe,
)
from BreakoutStrategy.mining.template_matcher import TemplateManager

__all__ = [
    'NavigationManager',
    'ScanManager',
    'TemplateManager',
    'compute_breakouts_from_dataframe',
    'preprocess_dataframe',
]
