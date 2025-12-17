"""
Shadow Pool 回测引擎

简化版：使用独立计算模式，无时间驱动循环。
每个突破独立计算 MFE/MAE，支持多进程并行。
"""

import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from BreakoutStrategy.analysis import Breakout
from .models import ShadowResult
from .calculator import compute_shadow_result


# 顶层 worker 函数（ProcessPoolExecutor 需要可 pickle）
def _compute_one(args: tuple) -> Optional[ShadowResult]:
    """单个突破的计算 worker"""
    bo, df, tracking_days = args
    if df is None:
        return None
    return compute_shadow_result(bo, df, tracking_days)


@dataclass
class ShadowBacktestResult:
    """回测结果汇总"""

    # ===== 元数据 =====
    price_range: Tuple[float, float]
    tracking_days: int

    # ===== 统计 =====
    total_breakouts_input: int      # 输入的突破总数
    breakouts_processed: int        # 实际处理的突破数
    results_valid: int              # 有效结果数

    # ===== 结果 =====
    results: List[ShadowResult]

    # ===== 指标分布 =====
    mfe_mean: float
    mfe_median: float
    mfe_std: float
    mae_mean: float
    mae_median: float
    success_rate_10: float
    success_rate_20: float

    def to_dict(self) -> dict:
        """转换为字典，用于 JSON 序列化"""
        return {
            'meta': {
                'price_range': list(self.price_range),
                'tracking_days': self.tracking_days,
                'total_breakouts_input': self.total_breakouts_input,
                'breakouts_processed': self.breakouts_processed,
                'results_valid': self.results_valid,
            },
            'statistics': {
                'mfe_mean': round(self.mfe_mean, 2),
                'mfe_median': round(self.mfe_median, 2),
                'mfe_std': round(self.mfe_std, 2),
                'mae_mean': round(self.mae_mean, 2),
                'mae_median': round(self.mae_median, 2),
                'success_rate_10': round(self.success_rate_10, 4),
                'success_rate_20': round(self.success_rate_20, 4),
            },
            'results': [r.to_dict() for r in self.results],
        }


class ShadowBacktestEngine:
    """
    Shadow Mode 回测引擎（独立计算模式）

    核心职责:
    - 遍历突破列表，独立计算每个突破的 MFE/MAE
    - 无时间驱动循环，无状态管理
    - 支持进度回调

    与 DailyBacktestEngine 的区别:
    - 无状态机，无阶段转换
    - 每个突破独立计算，可并行
    - 更简单、更快速
    """

    def __init__(self,
                 tracking_days: int = 30,
                 price_range: Tuple[float, float] = (0.5, 3.0),
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        """
        初始化引擎

        Args:
            tracking_days: 跟踪天数
            price_range: 价格筛选范围 (min, max)，设为 None 禁用价格过滤
            progress_callback: 进度回调 (current, total)
        """
        self.tracking_days = tracking_days
        self.price_range = price_range
        self.progress_callback = progress_callback

    def run(self,
            breakouts: List[Breakout],
            price_data: Dict[str, pd.DataFrame],
            parallel: bool = True) -> ShadowBacktestResult:
        """
        运行回测

        Args:
            breakouts: 突破列表（已完成过滤）
            price_data: {symbol: DataFrame} 价格数据
            parallel: 是否使用多进程并行（默认 True）

        Returns:
            ShadowBacktestResult
        """
        if parallel:
            return self._run_parallel(breakouts, price_data)
        else:
            return self._run_serial(breakouts, price_data)

    def _run_serial(self,
                    breakouts: List[Breakout],
                    price_data: Dict[str, pd.DataFrame]) -> ShadowBacktestResult:
        """串行计算"""
        total = len(breakouts)
        results: List[ShadowResult] = []
        processed = 0

        for i, bo in enumerate(breakouts):
            # 进度回调
            if self.progress_callback and (i + 1) % 100 == 0:
                self.progress_callback(i + 1, total)

            # 检查价格数据是否存在
            if bo.symbol not in price_data:
                continue

            # 计算指标
            result = compute_shadow_result(
                bo,
                price_data[bo.symbol],
                self.tracking_days
            )

            processed += 1
            if result:
                results.append(result)

        # 最终进度回调
        if self.progress_callback:
            self.progress_callback(total, total)

        return self._create_result(
            results=results,
            total_input=total,
            processed=processed,
        )

    def _run_parallel(self,
                      breakouts: List[Breakout],
                      price_data: Dict[str, pd.DataFrame]) -> ShadowBacktestResult:
        """多进程并行计算"""
        total = len(breakouts)
        workers = max(1, (os.cpu_count() or 4) - 2)

        # 准备任务参数
        tasks = []
        for bo in breakouts:
            df = price_data.get(bo.symbol)
            tasks.append((bo, df, self.tracking_days))

        processed = len([t for t in tasks if t[1] is not None])

        # 并行计算
        print(f"  Using {workers} workers for parallel computation...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            raw_results = list(executor.map(_compute_one, tasks))

        # 过滤有效结果
        results = [r for r in raw_results if r is not None]

        # 最终进度回调
        if self.progress_callback:
            self.progress_callback(total, total)

        return self._create_result(
            results=results,
            total_input=total,
            processed=processed,
        )

    def _create_result(self,
                       results: List[ShadowResult],
                       total_input: int,
                       processed: int) -> ShadowBacktestResult:
        """创建回测结果"""
        valid_results = [r for r in results if r.tracking_days > 0]

        if not valid_results:
            return ShadowBacktestResult(
                price_range=self.price_range or (0, float('inf')),
                tracking_days=self.tracking_days,
                total_breakouts_input=total_input,
                breakouts_processed=processed,
                results_valid=0,
                results=results,
                mfe_mean=0.0,
                mfe_median=0.0,
                mfe_std=0.0,
                mae_mean=0.0,
                mae_median=0.0,
                success_rate_10=0.0,
                success_rate_20=0.0,
            )

        # 计算统计
        mfes = [r.mfe for r in valid_results]
        maes = [r.mae for r in valid_results]

        mfe_mean = float(np.mean(mfes))
        mfe_median = float(np.median(mfes))
        mfe_std = float(np.std(mfes))
        mae_mean = float(np.mean(maes))
        mae_median = float(np.median(maes))

        success_10_count = sum(1 for r in valid_results if r.success_10)
        success_20_count = sum(1 for r in valid_results if r.success_20)

        success_rate_10 = success_10_count / len(valid_results)
        success_rate_20 = success_20_count / len(valid_results)

        return ShadowBacktestResult(
            price_range=self.price_range or (0, float('inf')),
            tracking_days=self.tracking_days,
            total_breakouts_input=total_input,
            breakouts_processed=processed,
            results_valid=len(valid_results),
            results=results,
            mfe_mean=mfe_mean,
            mfe_median=mfe_median,
            mfe_std=mfe_std,
            mae_mean=mae_mean,
            mae_median=mae_median,
            success_rate_10=success_rate_10,
            success_rate_20=success_rate_20,
        )


def save_results(result: ShadowBacktestResult,
                 output_dir: str,
                 prefix: str = 'shadow_results') -> Tuple[str, str]:
    """
    保存结果到 JSON 和 CSV

    Args:
        result: 回测结果
        output_dir: 输出目录
        prefix: 文件名前缀

    Returns:
        (json_path, csv_path)
    """
    from datetime import datetime

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # JSON 输出
    json_path = output_path / f'{prefix}_{timestamp}.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    # CSV 输出
    csv_path = output_path / f'{prefix}_{timestamp}.csv'
    if result.results:
        rows = [r.to_dict() for r in result.results]
        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False)

    return str(json_path), str(csv_path)
