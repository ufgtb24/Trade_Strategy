"""
数据挖掘模块

提供因子的统一注册、数据管道、统计分析、
阈值优化和报告生成等功能。

核心组件:
- factor_registry: 统一因子注册表（key/name/cn_name 三名制）
- data_pipeline: 数据构建管道（build_dataframe + prepare_raw_values）
- stats_analysis: 组合统计分析引擎
- report_generator: Markdown 报告生成
- distribution_analysis: 分布形态分析
- factor_diagnosis: 因子方向诊断 + YAML 修正
- template_generator: 模板枚举 + YAML 输出
- threshold_optimizer: 全因子阈值优化（Beam Search + Optuna）
- param_writer: 参数文件生成（all_factor.yaml）
- pipeline: 全管线编排（1→2→3→4）

入口命令:
- uv run -m BreakoutStrategy.mining.data_pipeline      重建分析数据集
- uv run -m BreakoutStrategy.mining.factor_diagnosis    诊断因子方向
- uv run -m BreakoutStrategy.mining.threshold_optimizer 阈值优化
- uv run -m BreakoutStrategy.mining.template_generator  模板枚举
- uv run -m BreakoutStrategy.mining.param_writer        生成挖掘参数文件
- uv run -m BreakoutStrategy.mining.distribution_analysis 分布形态分析
- uv run -m BreakoutStrategy.mining.pipeline            全管线编排
"""

from BreakoutStrategy.factor_registry import (
    SubParamDef,
    FactorInfo,
    FACTOR_REGISTRY,
    LABEL_COL,
    get_factor,
    get_active_factors,
    get_level_cols,
    get_factor_display,
)

__all__ = [
    # 因子注册表
    'SubParamDef',
    'FactorInfo',
    'FACTOR_REGISTRY',
    'LABEL_COL',
    'get_factor',
    'get_active_factors',
    'get_level_cols',
    'get_factor_display',
]
