"""
Daily Pool 信号质量评估工具

用于消融实验的量化标准，评估 Daily Pool 信号的买点质量。
使用 MFE/MAE/Time-to-MFE 三指标，避免交易逻辑（止损/止盈）污染。

核心指标：
- MFE (Maximum Favorable Excursion): 信号后观察窗口内的最大涨幅
- MAE_before_MFE: 达到 MFE 之前经历的最大回撤
- Time_to_MFE: 达到 MFE 的天数

综合评分公式：
    score = MFE - 0.3 * max(0, MAE - 5) - 0.1 * max(0, Time - 30)

使用方法：
    python scripts/analysis/signal_quality_evaluator.py

配置参数在 main() 函数起始位置设置。

输出：
    - 控制台输出评估报告
    - 可选：保存详细结果到 outputs/diagnostics/
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class SignalQuality:
    """
    单个信号的质量评估结果

    评估维度:
    - MFE (Maximum Favorable Excursion): 信号后观察窗口内的最大涨幅
    - MAE_before_MFE: 达到 MFE 之前的最大回撤
    - Time_to_MFE: 达到 MFE 的天数
    - composite_score: 综合评分
    """
    # ===== 信号标识 =====
    symbol: str
    signal_date: str
    entry_price: float

    # ===== 核心指标 =====
    mfe: float                    # 最大涨幅百分比
    mae_before_mfe: float         # 达到 MFE 前的最大回撤百分比
    time_to_mfe: int              # 达到 MFE 的天数

    # ===== 派生指标 =====
    composite_score: float        # 综合评分

    # ===== 元数据 =====
    valid: bool = True            # 评估是否有效（数据完整）
    actual_horizon: int = 0       # 实际观察天数（可能少于目标）
    error_message: str = ''       # 如果无效，记录错误原因


@dataclass
class QualityReport:
    """
    批量评估的统计报告

    包含:
    - 总体统计（信号数、有效率）
    - 各指标的分布统计
    - 低质量信号列表
    """
    # ===== 总体统计 =====
    total_signals: int
    valid_signals: int
    invalid_signals: int

    # ===== MFE 分布 =====
    mfe_mean: float
    mfe_median: float
    mfe_std: float
    mfe_p25: float
    mfe_p75: float

    # ===== MAE 分布 =====
    mae_mean: float
    mae_median: float
    mae_std: float
    mae_p25: float
    mae_p75: float

    # ===== Time-to-MFE 分布 =====
    time_mean: float
    time_median: float
    time_std: float
    time_p25: float
    time_p75: float

    # ===== 综合评分分布 =====
    score_mean: float
    score_median: float
    score_std: float
    score_p25: float
    score_p75: float

    # ===== 低质量信号 =====
    low_quality_signals: List[SignalQuality] = field(default_factory=list)

    # ===== 所有评估结果 =====
    all_results: List[SignalQuality] = field(default_factory=list)


# =============================================================================
# 数据加载
# =============================================================================

def load_signals_from_json(filepath: str) -> List[Dict[str, Any]]:
    """
    从 JSON 文件加载信号数据

    预期格式 (来自 daily_pool_backtest.py):
    [
        {
            "symbol": "AAPL",
            "signal_date": "2024-01-20",
            "entry_price": 185.25,
            ...
        },
        ...
    ]

    Args:
        filepath: 信号 JSON 文件路径

    Returns:
        信号字典列表
    """
    with open(filepath, 'r') as f:
        signals = json.load(f)

    print(f"Loaded {len(signals)} signals from {filepath}")
    return signals


def load_price_data(symbol: str, data_dir: str) -> Optional[pd.DataFrame]:
    """
    加载股票价格数据

    预期格式:
    - DatetimeIndex 索引
    - 列: open, high, low, close, volume

    Args:
        symbol: 股票代码
        data_dir: 数据目录路径

    Returns:
        价格 DataFrame，加载失败返回 None
    """
    pkl_path = Path(data_dir) / f"{symbol}.pkl"

    if not pkl_path.exists():
        return None

    try:
        df = pd.read_pickle(pkl_path)
        # 标准化列名（支持大小写混合）
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        print(f"Error loading {symbol}: {e}")
        return None


# =============================================================================
# 核心评估
# =============================================================================

def evaluate_signal_quality(
    signal: Dict[str, Any],
    price_df: pd.DataFrame,
    horizon_days: int = 42
) -> SignalQuality:
    """
    评估单个信号的质量

    计算逻辑:
    1. 从 signal_date 的下一个交易日开始观察
    2. 在 horizon_days 内找到最高价位置 (MFE)
    3. 计算 MFE 之前的最大回撤 (MAE_before_MFE)
    4. 计算达到 MFE 的天数 (Time_to_MFE)
    5. 计算综合评分

    综合评分公式:
        score = MFE - 0.3 * max(0, MAE - 5) - 0.1 * max(0, Time - 30)

    Args:
        signal: 信号字典，需包含 symbol, signal_date, entry_price
        price_df: 价格 DataFrame
        horizon_days: 观察窗口天数（默认42，约2个月）

    Returns:
        SignalQuality 评估结果
    """
    symbol = signal['symbol']
    signal_date_str = signal['signal_date']
    entry_price = signal['entry_price']

    # 转换日期
    signal_date = pd.Timestamp(signal_date_str)

    # 创建无效结果的辅助函数
    def make_invalid(error_msg: str) -> SignalQuality:
        return SignalQuality(
            symbol=symbol,
            signal_date=signal_date_str,
            entry_price=entry_price,
            mfe=0.0,
            mae_before_mfe=0.0,
            time_to_mfe=0,
            composite_score=0.0,
            valid=False,
            actual_horizon=0,
            error_message=error_msg
        )

    try:
        # 找到信号日期在 DataFrame 中的位置
        if signal_date not in price_df.index:
            # 尝试找最近的日期
            mask = price_df.index <= signal_date
            if not mask.any():
                return make_invalid("Signal date before data start")
            signal_idx = mask.sum() - 1
        else:
            signal_idx = price_df.index.get_loc(signal_date)

        # 从信号日期的下一天开始
        start_idx = signal_idx + 1
        end_idx = min(start_idx + horizon_days, len(price_df))

        if start_idx >= len(price_df):
            return make_invalid("No price data after signal date")

        # 提取观察窗口内的价格数据
        window_df = price_df.iloc[start_idx:end_idx]
        actual_horizon = len(window_df)

        if actual_horizon == 0:
            return make_invalid("Empty price window")

    except Exception as e:
        return make_invalid(f"Error: {str(e)}")

    # 计算 MFE（最大涨幅）
    highs = window_df['high'].values
    max_high = np.max(highs)
    mfe = (max_high - entry_price) / entry_price * 100  # 百分比

    # 找到 MFE 发生的位置（第一次达到最高价的位置）
    mfe_idx = int(np.argmax(highs))
    time_to_mfe = mfe_idx + 1  # 从1开始计数

    # 计算 MAE_before_MFE（达到 MFE 前的最大回撤）
    if mfe_idx > 0:
        lows_before_mfe = window_df['low'].values[:mfe_idx + 1]
        min_low = np.min(lows_before_mfe)
        mae_before_mfe = (entry_price - min_low) / entry_price * 100
        mae_before_mfe = max(0.0, mae_before_mfe)  # 确保非负
    else:
        # MFE 在第一天就达到，检查当天最低价
        first_low = window_df['low'].values[0]
        mae_before_mfe = max(0.0, (entry_price - first_low) / entry_price * 100)

    # 计算综合评分
    # score = MFE - 0.3 * max(0, MAE - 5) - 0.1 * max(0, Time - 30)
    mae_penalty = 0.3 * max(0, mae_before_mfe - 5)
    time_penalty = 0.1 * max(0, time_to_mfe - 30)
    composite_score = mfe - mae_penalty - time_penalty

    return SignalQuality(
        symbol=symbol,
        signal_date=signal_date_str,
        entry_price=entry_price,
        mfe=round(mfe, 2),
        mae_before_mfe=round(mae_before_mfe, 2),
        time_to_mfe=time_to_mfe,
        composite_score=round(composite_score, 2),
        valid=True,
        actual_horizon=actual_horizon,
        error_message=''
    )


def evaluate_batch(
    signals: List[Dict[str, Any]],
    data_dir: str,
    horizon_days: int = 42,
    verbose: bool = False
) -> List[SignalQuality]:
    """
    批量评估信号质量

    Args:
        signals: 信号列表
        data_dir: 价格数据目录
        horizon_days: 观察窗口天数
        verbose: 是否打印进度

    Returns:
        SignalQuality 列表
    """
    results = []
    price_cache: Dict[str, Optional[pd.DataFrame]] = {}

    total = len(signals)
    for i, signal in enumerate(signals):
        symbol = signal['symbol']

        # 缓存价格数据
        if symbol not in price_cache:
            price_cache[symbol] = load_price_data(symbol, data_dir)

        price_df = price_cache[symbol]

        if price_df is None:
            result = SignalQuality(
                symbol=symbol,
                signal_date=signal.get('signal_date', 'unknown'),
                entry_price=signal.get('entry_price', 0),
                mfe=0.0,
                mae_before_mfe=0.0,
                time_to_mfe=0,
                composite_score=0.0,
                valid=False,
                actual_horizon=0,
                error_message=f"Price data not found for {symbol}"
            )
        else:
            result = evaluate_signal_quality(signal, price_df, horizon_days)

        results.append(result)

        if verbose and (i + 1) % 50 == 0:
            print(f"  Evaluated {i + 1}/{total} signals...")

    return results


# =============================================================================
# 报告生成
# =============================================================================

def generate_report(
    results: List[SignalQuality],
    mfe_threshold: float = 5.0,
    mae_threshold: float = 15.0
) -> QualityReport:
    """
    生成质量评估报告

    Args:
        results: SignalQuality 列表
        mfe_threshold: MFE 低于此值视为低质量
        mae_threshold: MAE 高于此值视为低质量

    Returns:
        QualityReport 统计报告
    """
    valid_results = [r for r in results if r.valid]
    invalid_results = [r for r in results if not r.valid]

    if not valid_results:
        # 返回空报告
        return QualityReport(
            total_signals=len(results),
            valid_signals=0,
            invalid_signals=len(invalid_results),
            mfe_mean=0, mfe_median=0, mfe_std=0, mfe_p25=0, mfe_p75=0,
            mae_mean=0, mae_median=0, mae_std=0, mae_p25=0, mae_p75=0,
            time_mean=0, time_median=0, time_std=0, time_p25=0, time_p75=0,
            score_mean=0, score_median=0, score_std=0, score_p25=0, score_p75=0,
            low_quality_signals=[],
            all_results=results
        )

    # 提取各指标数组
    mfes = np.array([r.mfe for r in valid_results])
    maes = np.array([r.mae_before_mfe for r in valid_results])
    times = np.array([r.time_to_mfe for r in valid_results])
    scores = np.array([r.composite_score for r in valid_results])

    # 筛选低质量信号
    low_quality = [
        r for r in valid_results
        if r.mfe < mfe_threshold or r.mae_before_mfe > mae_threshold
    ]

    return QualityReport(
        total_signals=len(results),
        valid_signals=len(valid_results),
        invalid_signals=len(invalid_results),
        # MFE 分布
        mfe_mean=float(np.mean(mfes)),
        mfe_median=float(np.median(mfes)),
        mfe_std=float(np.std(mfes)),
        mfe_p25=float(np.percentile(mfes, 25)),
        mfe_p75=float(np.percentile(mfes, 75)),
        # MAE 分布
        mae_mean=float(np.mean(maes)),
        mae_median=float(np.median(maes)),
        mae_std=float(np.std(maes)),
        mae_p25=float(np.percentile(maes, 25)),
        mae_p75=float(np.percentile(maes, 75)),
        # Time 分布
        time_mean=float(np.mean(times)),
        time_median=float(np.median(times)),
        time_std=float(np.std(times)),
        time_p25=float(np.percentile(times, 25)),
        time_p75=float(np.percentile(times, 75)),
        # Score 分布
        score_mean=float(np.mean(scores)),
        score_median=float(np.median(scores)),
        score_std=float(np.std(scores)),
        score_p25=float(np.percentile(scores, 25)),
        score_p75=float(np.percentile(scores, 75)),
        # 低质量信号
        low_quality_signals=low_quality,
        all_results=results
    )


def format_report(report: QualityReport, horizon_days: int) -> str:
    """
    格式化质量报告为可读文本

    Args:
        report: QualityReport 对象
        horizon_days: 观察窗口天数

    Returns:
        格式化的报告字符串
    """
    lines = []
    lines.append("=" * 70)
    lines.append("          Signal Quality Evaluation Report")
    lines.append("          (MFE/MAE/Time-to-MFE Analysis)")
    lines.append("=" * 70)

    # 总体统计
    lines.append(f"\n=== Summary ===")
    lines.append(f"Observation horizon: {horizon_days} trading days")
    lines.append(f"Total signals: {report.total_signals}")
    valid_pct = report.valid_signals / report.total_signals * 100 if report.total_signals > 0 else 0
    lines.append(f"Valid evaluations: {report.valid_signals} ({valid_pct:.1f}%)")
    lines.append(f"Invalid (missing data): {report.invalid_signals}")

    if report.valid_signals == 0:
        lines.append("\nNo valid signals to analyze.")
        return '\n'.join(lines)

    # MFE 分布
    lines.append(f"\n=== MFE Distribution (Maximum Favorable Excursion) ===")
    lines.append(f"  Mean:   {report.mfe_mean:6.2f}%")
    lines.append(f"  Median: {report.mfe_median:6.2f}%")
    lines.append(f"  Std:    {report.mfe_std:6.2f}%")
    lines.append(f"  P25:    {report.mfe_p25:6.2f}%")
    lines.append(f"  P75:    {report.mfe_p75:6.2f}%")

    # MAE 分布
    lines.append(f"\n=== MAE Distribution (Max Adverse Excursion before MFE) ===")
    lines.append(f"  Mean:   {report.mae_mean:6.2f}%")
    lines.append(f"  Median: {report.mae_median:6.2f}%")
    lines.append(f"  Std:    {report.mae_std:6.2f}%")
    lines.append(f"  P25:    {report.mae_p25:6.2f}%")
    lines.append(f"  P75:    {report.mae_p75:6.2f}%")

    # Time-to-MFE 分布
    lines.append(f"\n=== Time-to-MFE Distribution (Days) ===")
    lines.append(f"  Mean:   {report.time_mean:6.1f} days")
    lines.append(f"  Median: {report.time_median:6.1f} days")
    lines.append(f"  Std:    {report.time_std:6.1f} days")
    lines.append(f"  P25:    {report.time_p25:6.1f} days")
    lines.append(f"  P75:    {report.time_p75:6.1f} days")

    # 综合评分分布
    lines.append(f"\n=== Composite Score Distribution ===")
    lines.append(f"  Formula: MFE - 0.3*max(0, MAE-5) - 0.1*max(0, Time-30)")
    lines.append(f"  Mean:   {report.score_mean:6.2f}")
    lines.append(f"  Median: {report.score_median:6.2f}")
    lines.append(f"  Std:    {report.score_std:6.2f}")
    lines.append(f"  P25:    {report.score_p25:6.2f}")
    lines.append(f"  P75:    {report.score_p75:6.2f}")

    # 低质量信号
    if report.low_quality_signals:
        lines.append(f"\n=== Low Quality Signals ({len(report.low_quality_signals)} found) ===")
        lines.append(f"  Criteria: MFE < 5% OR MAE > 15%")
        lines.append("")
        lines.append(f"  {'Symbol':<8} {'Date':<12} {'MFE':>8} {'MAE':>8} {'Time':>6} {'Score':>8}")
        lines.append(f"  {'-'*8} {'-'*12} {'-'*8} {'-'*8} {'-'*6} {'-'*8}")

        # 按综合评分排序（最低的排前面）
        sorted_low = sorted(report.low_quality_signals, key=lambda x: x.composite_score)
        for r in sorted_low[:20]:  # 只显示前20个
            lines.append(
                f"  {r.symbol:<8} {r.signal_date:<12} "
                f"{r.mfe:>7.2f}% {r.mae_before_mfe:>7.2f}% "
                f"{r.time_to_mfe:>5}d {r.composite_score:>7.2f}"
            )

        if len(sorted_low) > 20:
            lines.append(f"  ... and {len(sorted_low) - 20} more")

    lines.append("")
    lines.append("=" * 70)

    return '\n'.join(lines)


def save_results_to_json(
    report: QualityReport,
    output_file: str,
    horizon_days: int
) -> None:
    """
    保存评估结果到 JSON

    Args:
        report: QualityReport 对象
        output_file: 输出文件路径
        horizon_days: 观察窗口天数
    """
    # 转换 dataclass 为字典
    def signal_to_dict(s: SignalQuality) -> Dict:
        return {
            'symbol': s.symbol,
            'signal_date': s.signal_date,
            'entry_price': s.entry_price,
            'mfe': s.mfe,
            'mae_before_mfe': s.mae_before_mfe,
            'time_to_mfe': s.time_to_mfe,
            'composite_score': s.composite_score,
            'valid': s.valid,
            'actual_horizon': s.actual_horizon,
            'error_message': s.error_message
        }

    data = {
        'meta': {
            'horizon_days': horizon_days,
            'total_signals': report.total_signals,
            'valid_signals': report.valid_signals,
            'invalid_signals': report.invalid_signals,
        },
        'statistics': {
            'mfe': {
                'mean': round(report.mfe_mean, 2),
                'median': round(report.mfe_median, 2),
                'std': round(report.mfe_std, 2),
                'p25': round(report.mfe_p25, 2),
                'p75': round(report.mfe_p75, 2),
            },
            'mae': {
                'mean': round(report.mae_mean, 2),
                'median': round(report.mae_median, 2),
                'std': round(report.mae_std, 2),
                'p25': round(report.mae_p25, 2),
                'p75': round(report.mae_p75, 2),
            },
            'time_to_mfe': {
                'mean': round(report.time_mean, 1),
                'median': round(report.time_median, 1),
                'std': round(report.time_std, 1),
                'p25': round(report.time_p25, 1),
                'p75': round(report.time_p75, 1),
            },
            'composite_score': {
                'mean': round(report.score_mean, 2),
                'median': round(report.score_median, 2),
                'std': round(report.score_std, 2),
                'p25': round(report.score_p25, 2),
                'p75': round(report.score_p75, 2),
            },
        },
        'low_quality_signals': [signal_to_dict(s) for s in report.low_quality_signals],
        'all_results': [signal_to_dict(s) for s in report.all_results],
    }

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)


# =============================================================================
# 主入口
# =============================================================================

def main():
    """
    主入口，参数声明在函数起始位置

    用途：评估 Daily Pool 信号的买点质量，
    使用 MFE/MAE/Time-to-MFE 指标，避免交易逻辑污染。
    """
    # ===== 配置参数 =====
    # 输入数据
    signals_file = 'outputs/backtest/daily/daily_signals_2024-01-01_2024-06-30.json'
    data_dir = 'datasets/pkls'

    # 评估参数
    horizon_days = 42  # 观察窗口：约2个月

    # 低质量阈值
    mfe_threshold = 5.0    # MFE 低于此值视为低质量 (%)
    mae_threshold = 15.0   # MAE 高于此值视为低质量 (%)

    # 输出配置
    save_results = True
    output_dir = 'outputs/diagnostics'
    output_filename = 'signal_quality_report.json'

    # 控制台输出
    verbose = True

    # ===== 执行评估 =====
    print("\n" + "=" * 70)
    print("       Signal Quality Evaluator (MFE/MAE/Time Analysis)")
    print("=" * 70 + "\n")

    # 1. 加载信号
    print(f"Loading signals from: {signals_file}")
    try:
        signals = load_signals_from_json(signals_file)
    except FileNotFoundError:
        print(f"Error: Signal file not found: {signals_file}")
        print("Please run daily_pool_backtest.py first to generate signals.")
        return None

    if not signals:
        print("No signals found in the file.")
        return None

    # 2. 批量评估
    print(f"\nEvaluating {len(signals)} signals with {horizon_days}-day horizon...")
    results = evaluate_batch(signals, data_dir, horizon_days, verbose)

    # 3. 生成报告
    report = generate_report(results, mfe_threshold, mae_threshold)

    # 4. 打印报告
    if verbose:
        formatted = format_report(report, horizon_days)
        print("\n" + formatted)

    # 5. 保存结果
    if save_results:
        output_file = f"{output_dir}/{output_filename}"
        save_results_to_json(report, output_file, horizon_days)
        print(f"\nResults saved to: {output_file}")

    return report


if __name__ == '__main__':
    main()
