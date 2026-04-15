"""
数据管道

从 scan_results JSON 构建分析用 DataFrame，提供：
- build_dataframe(): 纯计算，无 IO 副作用
- save_dataframe(): 写 CSV
- summarize_dataframe(): 返回统计摘要 dict
- get_level(): 通用阈值→level 映射
- prepare_raw_values(): 统一提取各因子原始值
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from BreakoutStrategy.factor_registry import (
    FACTOR_REGISTRY,
    LABEL_COL,
    get_active_factors,
    FactorInfo,
)


# ---------------------------------------------------------------------------
# 通用 level 计算
# ---------------------------------------------------------------------------

def get_level(value, thresholds):
    """根据阈值列表返回 level (0, 1, 2, ...)"""
    level = 0
    for i, t in enumerate(thresholds):
        if value >= t:
            level = i + 1
        else:
            break
    return level


# ---------------------------------------------------------------------------
# 核心数据管道（纯计算，无 IO）
# ---------------------------------------------------------------------------

def build_dataframe(json_path) -> pd.DataFrame:
    """
    从 scan_results JSON 构建分析用 DataFrame。

    所有因子的阈值读取、值提取、level 计算均从 FACTOR_REGISTRY 动态驱动。
    非因子辅助特征（annual_volatility, gap_up_pct, intraday_change_pct）保留手动处理。

    Args:
        json_path: scan_results JSON 文件路径

    Returns:
        清洗后的 DataFrame
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    # --- 从 metadata 动态推断 label key ---
    label_cfg = data["scan_metadata"]["feature_calculator_params"]["label_configs"][0]
    label_key = f"label_{label_cfg['max_days']}"

    # --- 从 metadata 读取阈值配置（动态，fallback 到 registry defaults）---
    scorer_params = data["scan_metadata"]["quality_scorer_params"]
    factor_thresholds = {}
    for fi in get_active_factors():
        factor_thresholds[fi.key] = (
            scorer_params.get(fi.yaml_key, {})
            .get("thresholds", list(fi.default_thresholds))
        )

    # --- 遍历所有 breakout 记录 ---
    rows = []
    for stock in data["results"]:
        symbol = stock["symbol"]

        for bo in stock.get("breakouts", []):
            label_val = bo.get("labels", {}).get(label_key)

            # 非因子辅助特征（手动）
            row = {
                "symbol": symbol,
                "date": bo["date"],
                "price": bo["price"],
                "quality_score": bo.get("quality_score", 0),
                "annual_volatility": bo.get("annual_volatility") or 0.0,
                "gap_up_pct": bo.get("gap_up_pct") or 0.0,
                "intraday_change_pct": bo.get("intraday_change_pct") or 0.0,
            }

            # 注册因子：原始值 + level（动态）
            # per-factor gate 语义：nullable 因子的 None 透传（raw 列 NaN，level=0 未触发）；
            # 非 nullable 因子沿用数据错容错（仅 buffer=0 的 age/test/height/peak_vol/streak）。
            for fi in get_active_factors():
                raw_val = bo.get(fi.key)
                if raw_val is None:
                    if fi.nullable or fi.has_nan_group:
                        level_input = 0  # None raw 透传，level 未触发
                    else:
                        raw_val = 0 if fi.is_discrete else 0.0
                        level_input = raw_val
                else:
                    level_input = raw_val
                row[fi.key] = raw_val
                row[fi.level_col] = get_level(level_input, factor_thresholds[fi.key])

            # Label
            row[LABEL_COL] = label_val
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# IO 分离
# ---------------------------------------------------------------------------

def save_dataframe(df: pd.DataFrame, output_path) -> Path:
    """将 DataFrame 写入 CSV"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def summarize_dataframe(df: pd.DataFrame) -> dict:
    """返回 DataFrame 统计摘要（替代原 print 逻辑）

    Returns:
        dict: {total, filtered, unique_symbols, date_range, label_describe, level_distributions}
    """
    level_cols = [c for c in df.columns if c.endswith("_level")]
    level_dists = {}
    for col in level_cols:
        level_dists[col] = df[col].value_counts().sort_index().to_dict()

    return {
        'total': len(df),
        'unique_symbols': df['symbol'].nunique(),
        'date_range': (df['date'].min(), df['date'].max()),
        'label_describe': df[LABEL_COL].describe().to_dict(),
        'level_distributions': level_dists,
    }


# ---------------------------------------------------------------------------
# 统一 prepare_raw_values（合并 3 个版本）
# ---------------------------------------------------------------------------


def prepare_raw_values(df: pd.DataFrame, factors=None) -> dict[str, np.ndarray]:
    """
    统一提取各因子原始值，所有因子都通过 key 直接读取 DataFrame 列。

    Args:
        df: factor_analysis_data DataFrame
        factors: 可选，要提取的因子列表（FactorInfo 或 key 字符串）。
                 默认 None 表示所有已注册因子。

    Returns:
        {key: 原始值 numpy 数组}；nullable 因子的 NaN 保留（per-factor gate 语义），
        下游函数（build_triggered_matrix/TPE bounds/greedy beam）通过 ~np.isnan 过滤。
    """
    if factors is None:
        factor_list = get_active_factors()
    else:
        from BreakoutStrategy.factor_registry import get_factor
        factor_list = []
        for f in factors:
            if isinstance(f, FactorInfo):
                factor_list.append(f)
            else:
                factor_list.append(get_factor(f))

    raw = {}
    for fi in factor_list:
        # per-factor gate: 保留 NaN，下游统计各自决策（NaN-aware filter）
        raw[fi.key] = df[fi.key].values.astype(np.float64)

    return raw


def apply_binary_levels(df: pd.DataFrame, thresholds: dict,
                        negative_factors=frozenset()) -> pd.DataFrame:
    """用单阈值重算 *_level 列为二值 0/1。

    TPE 优化产出每因子单个阈值，与 build_dataframe 的多级阈值不同。
    此函数将 level 列覆写为二值，使后续 run_analysis 反映优化后的分布。

    Args:
        df: 含 key 列和 level_col 列的 DataFrame（会被原地修改）
        thresholds: {key: threshold_value}
        negative_factors: 反向因子集合（使用 <= 触发）
    """
    for fi in get_active_factors():
        key = fi.key
        if key in thresholds:
            raw = df[fi.key].fillna(0)
            if key in negative_factors:
                df[fi.level_col] = (raw <= thresholds[key]).astype(int)
            else:
                df[fi.level_col] = (raw >= thresholds[key]).astype(int)
        else:
            df[fi.level_col] = 0
    return df


def compute_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """保留接口兼容性（衍生列已在源头计算，无需额外处理）"""
    return df.copy()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(json_path, output_csv, report_name=None):
    df = build_dataframe(json_path)
    save_dataframe(df, output_csv)

    summary = summarize_dataframe(df)
    print(f"=== Data Pipeline Summary ===")
    print(f"Total rows: {summary['total']}")
    print(f"Unique symbols: {summary['unique_symbols']}")
    print(f"Date range: {summary['date_range'][0]} ~ {summary['date_range'][1]}")
    print(f"\nLabel stats:")
    for k, v in summary['label_describe'].items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
    print(f"\nFactor level distributions:")
    for col, dist in summary['level_distributions'].items():
        print(f"  {col}: {dist}")
    print(f"\nSaved to: {output_csv}")

    if report_name is not None:
        from BreakoutStrategy.mining.stats_analysis import run_analysis
        from BreakoutStrategy.mining.report_generator import generate_report
        results = run_analysis(df)
        generate_report(results, output_path=report_name)


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    main(
        json_path=PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json",
        output_csv=PROJECT_ROOT / "outputs" / "analysis" / "factor_analysis_data.csv",
        report_name=PROJECT_ROOT / "docs" / "statistics" / "factor_combination_all.md",
    )
