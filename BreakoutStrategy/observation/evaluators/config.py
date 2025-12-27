"""
买入条件配置数据类

定义四维度评估系统的所有配置参数，支持 YAML 配置文件加载。
"""
from dataclasses import dataclass, field
from datetime import time
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import yaml


@dataclass
class TimeWindowConfig:
    """
    时间窗口配置

    控制买入时机的时间维度评估：
    - 最佳买入窗口：10:00-11:30 AM ET
    - 避开开盘30分钟的高波动期
    - 盘后/盘前默认不允许买入
    """
    # 最佳买入时间窗口 (ET时区)
    optimal_windows: List[Tuple[time, time]] = field(default_factory=lambda: [
        (time(10, 0), time(11, 30)),
    ])
    # 开盘避开时间 (分钟)
    open_avoid_minutes: int = 30
    # 盘后/盘前是否允许买入
    allow_extended_hours: bool = False
    # 时间窗口评分映射 (时段类型 -> 评分 0-1)
    window_scores: Dict[str, float] = field(default_factory=lambda: {
        'optimal': 1.0,      # 最佳时段
        'acceptable': 0.7,   # 可接受时段 (10:00-15:00 非最优)
        'marginal': 0.4,     # 边际时段 (尾盘)
        'avoid': 0.0,        # 避开时段 (开盘30分钟, 盘后/盘前)
    })


@dataclass
class PriceConfirmConfig:
    """
    价格确认配置

    控制价格维度的评估逻辑：
    - 确认区间：突破价上方 1%-2%
    - 回踩容忍：不跌破突破价 3%
    - 移出阈值：跌破突破价 3% 则移出观察池
    """
    # 最小突破确认比例 (高于突破价)
    min_breakout_margin: float = 0.01  # 1%
    # 最大突破确认比例 (超过此值可能追高)
    max_breakout_margin: float = 0.02  # 2%
    # 回踩不破阈值 (跌破此值降低评分但不移出)
    pullback_tolerance: float = 0.03   # 3%
    # 跌破移出阈值 (跌破此值从观察池移出)
    remove_threshold: float = 0.03     # 3%
    # 最大追高比例 (超过此值放弃买入)
    max_chase_pct: float = 0.05        # 5%


@dataclass
class VolumeVerifyConfig:
    """
    成交量验证配置

    控制成交量维度的评估逻辑：
    - 5分钟成交量比需达到基准的 1.5 倍
    - 基准可选：MA20 或前日平均
    """
    # 最小成交量比阈值
    min_volume_ratio: float = 1.5
    # 成交量计算窗口 (分钟)
    volume_window_minutes: int = 5
    # 基准成交量类型: 'ma20' | 'prev_day_avg'
    baseline_type: str = 'ma20'


@dataclass
class RiskFilterConfig:
    """
    风险过滤配置

    控制风险维度的评估逻辑（门槛条件，不参与加权）：
    - 跌破 3%：移出观察池
    - 跳空 > 8%：当日跳过
    - 最大观察天数：30天
    """
    # 跌破移出阈值
    drop_remove_threshold: float = 0.03  # 3%
    # 跳空过高跳过阈值
    gap_skip_threshold: float = 0.08     # 8%
    # 最大观察天数 (超过后过期)
    max_holding_days: int = 30
    # 连续阴线数量限制 (超过此值暂停买入)
    consecutive_red_limit: int = 3


@dataclass
class ScoringConfig:
    """
    综合评分配置

    控制各维度权重和买入阈值：
    - 权重分配：时间20%, 价格30%, 成交量25%, 质量25%
    - 强买入：>= 70分
    - 普通买入：>= 50分
    """
    # 各维度权重
    time_weight: float = 0.20
    price_weight: float = 0.30
    volume_weight: float = 0.25
    quality_weight: float = 0.25
    # 买入阈值
    strong_buy_threshold: float = 70
    normal_buy_threshold: float = 50


@dataclass
class BuyConditionConfig:
    """
    买入条件完整配置

    整合所有维度配置，支持从 YAML 文件加载。
    """
    time_window: TimeWindowConfig = field(default_factory=TimeWindowConfig)
    price_confirm: PriceConfirmConfig = field(default_factory=PriceConfirmConfig)
    volume_verify: VolumeVerifyConfig = field(default_factory=VolumeVerifyConfig)
    risk_filter: RiskFilterConfig = field(default_factory=RiskFilterConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

    # 运行模式: 'realtime' | 'backtest'
    mode: str = 'backtest'

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'BuyConditionConfig':
        """
        从 YAML 配置文件加载

        Args:
            yaml_path: YAML 文件路径

        Returns:
            BuyConditionConfig 实例
        """
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'BuyConditionConfig':
        """
        从字典创建配置

        Args:
            data: 配置字典

        Returns:
            BuyConditionConfig 实例
        """
        config = cls()

        # 解析时间窗口配置
        if 'time_window' in data:
            tw_data = data['time_window']
            if 'optimal_windows' in tw_data:
                # 解析时间字符串 ["10:00", "11:30"] -> (time(10,0), time(11,30))
                windows = []
                for window in tw_data['optimal_windows']:
                    start = cls._parse_time(window[0])
                    end = cls._parse_time(window[1])
                    windows.append((start, end))
                config.time_window.optimal_windows = windows
            if 'open_avoid_minutes' in tw_data:
                config.time_window.open_avoid_minutes = tw_data['open_avoid_minutes']
            if 'allow_extended_hours' in tw_data:
                config.time_window.allow_extended_hours = tw_data['allow_extended_hours']
            if 'window_scores' in tw_data:
                config.time_window.window_scores = tw_data['window_scores']

        # 解析价格确认配置
        if 'price_confirm' in data:
            pc_data = data['price_confirm']
            if 'min_breakout_margin' in pc_data:
                config.price_confirm.min_breakout_margin = pc_data['min_breakout_margin']
            if 'max_breakout_margin' in pc_data:
                config.price_confirm.max_breakout_margin = pc_data['max_breakout_margin']
            if 'pullback_tolerance' in pc_data:
                config.price_confirm.pullback_tolerance = pc_data['pullback_tolerance']
            if 'remove_threshold' in pc_data:
                config.price_confirm.remove_threshold = pc_data['remove_threshold']
            if 'max_chase_pct' in pc_data:
                config.price_confirm.max_chase_pct = pc_data['max_chase_pct']

        # 解析成交量配置
        if 'volume_verify' in data:
            vv_data = data['volume_verify']
            if 'min_volume_ratio' in vv_data:
                config.volume_verify.min_volume_ratio = vv_data['min_volume_ratio']
            if 'volume_window_minutes' in vv_data:
                config.volume_verify.volume_window_minutes = vv_data['volume_window_minutes']
            if 'baseline_type' in vv_data:
                config.volume_verify.baseline_type = vv_data['baseline_type']

        # 解析风险过滤配置
        if 'risk_filter' in data:
            rf_data = data['risk_filter']
            if 'drop_remove_threshold' in rf_data:
                config.risk_filter.drop_remove_threshold = rf_data['drop_remove_threshold']
            if 'gap_skip_threshold' in rf_data:
                config.risk_filter.gap_skip_threshold = rf_data['gap_skip_threshold']
            if 'max_holding_days' in rf_data:
                config.risk_filter.max_holding_days = rf_data['max_holding_days']
            if 'consecutive_red_limit' in rf_data:
                config.risk_filter.consecutive_red_limit = rf_data['consecutive_red_limit']

        # 解析评分配置
        if 'scoring' in data:
            sc_data = data['scoring']
            if 'time_weight' in sc_data:
                config.scoring.time_weight = sc_data['time_weight']
            if 'price_weight' in sc_data:
                config.scoring.price_weight = sc_data['price_weight']
            if 'volume_weight' in sc_data:
                config.scoring.volume_weight = sc_data['volume_weight']
            if 'quality_weight' in sc_data:
                config.scoring.quality_weight = sc_data['quality_weight']
            if 'strong_buy_threshold' in sc_data:
                config.scoring.strong_buy_threshold = sc_data['strong_buy_threshold']
            if 'normal_buy_threshold' in sc_data:
                config.scoring.normal_buy_threshold = sc_data['normal_buy_threshold']

        # 解析运行模式
        if 'mode' in data:
            config.mode = data['mode']

        return config

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """解析时间字符串 (HH:MM 格式)"""
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))

    def is_backtest_mode(self) -> bool:
        """是否为回测模式"""
        return self.mode == 'backtest'

    def is_realtime_mode(self) -> bool:
        """是否为实时模式"""
        return self.mode == 'realtime'
