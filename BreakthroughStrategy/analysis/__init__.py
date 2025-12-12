"""
技术分析模块（重构版）

基于增量式算法重构，核心特性：
- 增量添加价格数据，维护活跃峰值列表
- 支持价格相近的峰值共存（形成阻力区）
- 一次突破可能突破多个峰值
- 支持持久化缓存（可选）
- 改进的质量评分系统（修复密集度评分，综合峰值质量）

主要类：
- BreakthroughDetector: 突破检测器（增量式）
- FeatureCalculator: 特征计算器
- QualityScorer: 质量评分器（改进版）

数据结构：
- Peak: 峰值（包含质量特征）
- BreakoutInfo: 突破信息（简化版，由检测器直接返回）
- Breakthrough: 完整突破对象（包含丰富特征）
"""

# 核心数据结构
from .breakthrough_detector import (
    Peak,
    BreakoutInfo,
    Breakthrough,
    BreakthroughDetector
)

# 特征计算
from .features import FeatureCalculator

# 质量评分
from .quality_scorer import QualityScorer, FeatureScoreDetail, ScoreBreakdown


__all__ = [
    # 数据结构
    'Peak',
    'BreakoutInfo',
    'Breakthrough',

    # 检测器
    'BreakthroughDetector',

    # 特征计算
    'FeatureCalculator',

    # 质量评分
    'QualityScorer',
    'FeatureScoreDetail',
    'ScoreBreakdown',
]
