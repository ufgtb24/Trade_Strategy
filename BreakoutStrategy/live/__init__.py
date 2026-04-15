"""实盘 UI 模块 (Live Trading UI).

独立于开发 UI（BreakoutStrategy/UI/）的产品，专注于日常选股工作流：
数据新鲜度检查 → 数据更新 → 全市场扫描 → 模板过滤 → 情感分析 → 展示。

入口: uv run python -m BreakoutStrategy.live
"""

__version__ = "0.1.0"
