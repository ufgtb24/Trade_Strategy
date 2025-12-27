"""
买入时机评估器演示脚本

展示如何使用多维度买入时机评估系统：
- 四维度评估：时间窗口、价格确认、成交量验证、风险过滤
- 综合评分机制
- 与观察池系统的集成

运行方式：
    python scripts/backtest/evaluator_demo.py
"""
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakoutStrategy.observation import (
    create_backtest_pool_manager,
    PoolEntry,
    BuyConditionConfig,
    EvaluationAction,
)


def demo_single_evaluation():
    """演示单次评估"""
    print("=" * 60)
    print("演示1: 单次买入条件评估")
    print("=" * 60)

    # 创建观察池管理器
    pool_mgr = create_backtest_pool_manager(
        start_date=date(2024, 1, 1),
        config={'buy_condition_config_path': 'configs/buy_condition_config.yaml'}
    )

    # 打印配置信息
    config = pool_mgr.buy_condition_config
    print(f"\n配置信息:")
    print(f"  模式: {config.mode}")
    print(f"  最佳时间窗口: {config.time_window.optimal_windows}")
    print(f"  价格确认区间: +{config.price_confirm.min_breakout_margin*100:.0f}% ~ +{config.price_confirm.max_breakout_margin*100:.0f}%")
    print(f"  成交量比阈值: {config.volume_verify.min_volume_ratio}x")
    print(f"  买入评分阈值: 强买入>={config.scoring.strong_buy_threshold}, 普通>={config.scoring.normal_buy_threshold}")

    # 创建测试条目
    entry = PoolEntry(
        symbol='AAPL',
        add_date=date(2024, 1, 1),
        breakout_date=date(2024, 1, 1),
        quality_score=75,
        breakout_price=100.0,
        highest_peak_price=102.0,
        pool_type='realtime'
    )

    # 测试场景1: 理想买入条件
    print("\n--- 场景1: 理想买入条件 ---")
    bar1 = pd.Series({
        'open': 103.0,
        'high': 104.5,
        'low': 102.5,
        'close': 104.0,  # +1.96% 相对于峰值
        'volume': 1800000
    })
    result1 = pool_mgr.buy_evaluator.evaluate(
        entry, bar1, pool_mgr.time_provider,
        {'volume_ma20': 1000000}
    )
    print_result(result1)

    # 测试场景2: 价格回踩
    print("\n--- 场景2: 价格回踩到支撑位 ---")
    bar2 = pd.Series({
        'open': 101.0,
        'high': 102.0,
        'low': 99.5,
        'close': 100.5,  # 略低于峰值
        'volume': 1200000
    })
    result2 = pool_mgr.buy_evaluator.evaluate(
        entry, bar2, pool_mgr.time_provider,
        {'volume_ma20': 1000000}
    )
    print_result(result2)

    # 测试场景3: 跌破阈值
    print("\n--- 场景3: 跌破支撑（触发移出）---")
    bar3 = pd.Series({
        'open': 99.0,
        'high': 99.5,
        'low': 97.0,
        'close': 98.0,  # -3.9% 相对于峰值
        'volume': 2000000
    })
    result3 = pool_mgr.buy_evaluator.evaluate(
        entry, bar3, pool_mgr.time_provider,
        {'volume_ma20': 1000000}
    )
    print_result(result3)

    # 测试场景4: 缩量
    print("\n--- 场景4: 价格确认但成交量不足 ---")
    bar4 = pd.Series({
        'open': 103.0,
        'high': 104.0,
        'low': 102.5,
        'close': 103.5,
        'volume': 400000  # 缩量
    })
    result4 = pool_mgr.buy_evaluator.evaluate(
        entry, bar4, pool_mgr.time_provider,
        {'volume_ma20': 1000000}
    )
    print_result(result4)


def demo_pool_integration():
    """演示与观察池的集成"""
    print("\n" + "=" * 60)
    print("演示2: 观察池集成 - 模拟多日回测流程")
    print("=" * 60)

    # 创建观察池管理器
    pool_mgr = create_backtest_pool_manager(
        start_date=date(2024, 1, 1),
        config={
            'buy_condition_config_path': 'configs/buy_condition_config.yaml',
            'realtime_observation_days': 1,
            'daily_observation_days': 30,
        }
    )

    # 模拟突破被添加到观察池
    print("\n[Day 1] 检测到 AAPL 突破，添加到实时池")
    entry = PoolEntry(
        symbol='AAPL',
        add_date=date(2024, 1, 1),
        breakout_date=date(2024, 1, 1),
        quality_score=80,
        breakout_price=150.0,
        highest_peak_price=152.0,
        pool_type='realtime',
        baseline_volume=5000000  # 设置基准成交量
    )
    pool_mgr.realtime_pool.add(entry)
    print(f"  实时池条目数: {len(pool_mgr.realtime_pool.get_all())}")

    # Day 2: 检查买入信号
    print("\n[Day 2] 检查买入信号")
    pool_mgr.time_provider.advance(1)

    price_data = {
        'AAPL': pd.Series({
            'open': 153.0,
            'high': 155.0,
            'low': 152.0,
            'close': 154.5,  # +1.6% 相对于峰值
            'volume': 8000000  # 放量
        })
    }

    signals = pool_mgr.check_buy_signals(price_data)
    if signals:
        for sig in signals:
            print(f"  买入信号: {sig.symbol}")
            print(f"    价格: ${sig.signal_price:.2f}")
            print(f"    强度: {sig.signal_strength:.2f}")
            print(f"    止损: ${sig.suggested_stop_loss:.2f}")
            print(f"    仓位: {sig.suggested_position_size_pct*100:.0f}%")
            print(f"    原因: {sig.reason}")
            if 'total_score' in sig.metadata:
                print(f"    评分: {sig.metadata['total_score']:.1f}")

            # 标记已买入
            pool_mgr.mark_bought(sig.symbol)
    else:
        print("  未产生买入信号")

    # 查看池状态
    print(f"\n  实时池活跃条目: {len(pool_mgr.realtime_pool.get_all('active'))}")
    print(f"  实时池已买入: {len(pool_mgr.realtime_pool.get_all('bought'))}")


def demo_risk_filter():
    """演示风险过滤功能"""
    print("\n" + "=" * 60)
    print("演示3: 风险过滤场景")
    print("=" * 60)

    pool_mgr = create_backtest_pool_manager(
        start_date=date(2024, 1, 1),
        config={'buy_condition_config_path': 'configs/buy_condition_config.yaml'}
    )

    entry = PoolEntry(
        symbol='TEST',
        add_date=date(2024, 1, 1),
        breakout_date=date(2024, 1, 1),
        quality_score=85,
        breakout_price=100.0,
        highest_peak_price=100.0,
        pool_type='realtime'
    )

    # 场景1: 跳空过高
    print("\n--- 场景: 开盘跳空 +10%（超过8%阈值）---")
    bar = pd.Series({
        'open': 110.0,  # +10% gap
        'high': 112.0,
        'low': 109.0,
        'close': 111.0,
        'volume': 3000000
    })
    result = pool_mgr.buy_evaluator.evaluate(
        entry, bar, pool_mgr.time_provider,
        {'prev_close': 100.0, 'volume_ma20': 1000000}
    )
    print_result(result)

    # 场景2: 正常跳空
    print("\n--- 场景: 开盘跳空 +3%（正常范围）---")
    bar2 = pd.Series({
        'open': 103.0,  # +3% gap
        'high': 104.0,
        'low': 102.0,
        'close': 103.5,
        'volume': 2000000
    })
    result2 = pool_mgr.buy_evaluator.evaluate(
        entry, bar2, pool_mgr.time_provider,
        {'prev_close': 100.0, 'volume_ma20': 1000000}
    )
    print_result(result2)


def print_result(result):
    """打印评估结果"""
    action_emoji = {
        'strong_buy': '🟢',
        'normal_buy': '🟡',
        'hold': '⚪',
        'remove': '🔴',
        'transfer': '🔵',
    }
    emoji = action_emoji.get(result.action.value, '❓')

    print(f"  {emoji} 动作: {result.action.value}")
    print(f"  总评分: {result.total_score:.1f}")
    print(f"  是否买入: {'是' if result.is_buy_signal else '否'}")
    print(f"  原因: {result.reason}")

    if result.suggested_entry_price:
        print(f"  建议入场: ${result.suggested_entry_price:.2f}")
    if result.suggested_stop_loss:
        print(f"  建议止损: ${result.suggested_stop_loss:.2f}")

    print(f"  维度评分:")
    for ds in result.dimension_scores:
        status = "✓" if ds.passed else "✗"
        print(f"    [{status}] {ds.dimension}: {ds.score:.0f} (权重 {ds.weight:.0%})")


def demo_config_customization():
    """演示配置自定义"""
    print("\n" + "=" * 60)
    print("演示4: 自定义配置")
    print("=" * 60)

    # 创建自定义配置
    from BreakoutStrategy.observation.evaluators import (
        BuyConditionConfig,
        PriceConfirmConfig,
        ScoringConfig,
    )

    custom_config = BuyConditionConfig()
    # 调整价格确认阈值
    custom_config.price_confirm.min_breakout_margin = 0.005  # 降低到 0.5%
    custom_config.price_confirm.max_breakout_margin = 0.03   # 提高到 3%
    # 调整买入阈值
    custom_config.scoring.strong_buy_threshold = 80  # 更严格
    custom_config.scoring.normal_buy_threshold = 60

    print(f"\n自定义配置:")
    print(f"  价格确认区间: +{custom_config.price_confirm.min_breakout_margin*100:.1f}% ~ +{custom_config.price_confirm.max_breakout_margin*100:.1f}%")
    print(f"  强买入阈值: {custom_config.scoring.strong_buy_threshold}")
    print(f"  普通买入阈值: {custom_config.scoring.normal_buy_threshold}")

    # 使用自定义配置创建管理器
    pool_mgr = create_backtest_pool_manager(
        start_date=date(2024, 1, 1),
        config={'buy_condition_config': custom_config}
    )

    entry = PoolEntry(
        symbol='TEST',
        add_date=date(2024, 1, 1),
        breakout_date=date(2024, 1, 1),
        quality_score=70,
        breakout_price=100.0,
        highest_peak_price=100.0,
        pool_type='realtime'
    )

    bar = pd.Series({
        'open': 100.5,
        'high': 101.5,
        'low': 100.0,
        'close': 101.0,  # +1%
        'volume': 1500000
    })

    print("\n使用自定义配置评估:")
    result = pool_mgr.buy_evaluator.evaluate(
        entry, bar, pool_mgr.time_provider,
        {'volume_ma20': 1000000}
    )
    print_result(result)


def main():
    """主入口"""
    print("\n" + "=" * 60)
    print("买入时机评估器演示")
    print("=" * 60)
    print("""
此演示展示多维度买入时机评估系统的功能：

  四维度评估:
    1. 时间窗口 - 最佳买入时段 10:00-11:30 AM ET
    2. 价格确认 - 突破价上方 1%-2%
    3. 成交量验证 - 量比 >= 1.5x
    4. 风险过滤 - 跌破3%移出，跳空>8%跳过

  综合评分:
    - 强买入: >= 70分
    - 普通买入: >= 50分
    - 继续观察: < 50分
    - 移出: 触发风险红线
""")

    demo_single_evaluation()
    demo_pool_integration()
    demo_risk_filter()
    demo_config_customization()

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
