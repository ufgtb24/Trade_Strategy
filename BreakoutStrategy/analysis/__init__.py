"""
技术分析模块

基于增量式算法，核心特性：
- 增量添加价格数据，维护活跃峰值列表
- 支持价格相近的峰值共存（形成阻力区）
- 一次突破可能突破多个峰值
- 支持持久化缓存（可选）

评分系统：
- BreakoutScorer: 突破评分器（Bonus 乘法模型）

数据结构：
- Peak: 峰值
- BreakoutInfo: 突破信息（简化版，由检测器直接返回）
- Breakout: 完整突破对象（包含丰富特征）
"""

# 核心数据结构
from .breakout_detector import (
    Peak,
    BreakoutInfo,
    Breakout,
    BreakoutDetector
)

# 特征计算
from .features import FeatureCalculator

# 突破评分（Bonus 乘法模型）
from .breakout_scorer import BreakoutScorer, BonusDetail, ScoreBreakdown

# 向后兼容别名
QualityScorer = BreakoutScorer


__all__ = [
    # 数据结构
    'Peak',
    'BreakoutInfo',
    'Breakout',

    # 检测器
    'BreakoutDetector',

    # 特征计算
    'FeatureCalculator',

    # 突破评分
    'BreakoutScorer',
    'BonusDetail',
    'ScoreBreakdown',

    # 向后兼容
    'QualityScorer',
]
