"""
组合统计分析引擎

提供 run_analysis(df) 入口，执行 5 个维度的统计分析：
1. 单因子分析 — 每个 factor level vs label 的统计量 + Spearman 相关
2. 组合分析 — 二值化 triggered 组合枚举，找出最佳组合
3. 交互效应 — 两两 factor 交互效应矩阵
4. 决策树特征重要性 — DecisionTree + RandomForest
5. 因子间相关性 — Spearman 相关矩阵 + 高相关因子对
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor

from BreakoutStrategy.factor_registry import (
    get_level_cols, get_factor_display, get_active_factors, LABEL_COL,
)
from BreakoutStrategy.mining.data_pipeline import prepare_raw_values
from BreakoutStrategy.mining.factor_diagnosis import detect_non_monotonicity

MIN_COMBO_SAMPLES = 20


# =========================================================================
# 1. 单因子分析
# =========================================================================

def _single_factor_analysis(df: pd.DataFrame) -> dict:
    """
    每个 factor 按 level 分组，计算 label 统计量 + Spearman 相关系数

    Returns:
        {
            'by_level': {level_col: DataFrame(level, count, mean, median, std, q25, q75)},
            'correlations': DataFrame(factor, spearman_r, p_value)
        }
    """
    level_cols = get_level_cols()
    factor_display = get_factor_display()
    by_level = {}
    corr_rows = []

    for col in level_cols:
        grouped = df.groupby(col)[LABEL_COL].agg(
            count='count',
            mean='mean',
            median='median',
            std='std',
            q25=lambda x: x.quantile(0.25),
            q75=lambda x: x.quantile(0.75),
        ).reset_index()
        grouped.columns = ['level', 'count', 'mean', 'median', 'std', 'q25', 'q75']
        by_level[col] = grouped

        valid = df[[col, LABEL_COL]].dropna()
        if len(valid) > 2:
            r, p = spearmanr(valid[col], valid[LABEL_COL])
        else:
            r, p = np.nan, np.nan
        corr_rows.append({
            'factor': factor_display.get(col, col),
            'spearman_r': r,
            'p_value': p,
        })

    correlations = pd.DataFrame(corr_rows)
    return {'by_level': by_level, 'correlations': correlations}


# =========================================================================
# 2. 组合分析（核心）
# =========================================================================

def _combination_analysis(df: pd.DataFrame) -> dict:
    """
    将 factor 二值化为 triggered/not_triggered，枚举所有出现过的组合

    Returns:
        {
            'combo_stats': DataFrame,
            'top10': DataFrame,
            'by_n_triggered': DataFrame,
            'total_combos': int,
            'filtered_combos': int,
        }
    """
    level_cols = get_level_cols()
    factor_display = get_factor_display()

    triggered = pd.DataFrame()
    for col in level_cols:
        triggered[col] = (df[col] > 0).astype(int)

    short_names = [factor_display.get(c, c) for c in level_cols]

    def make_combo_name(row):
        parts = []
        for i, col in enumerate(level_cols):
            if row[col] == 1:
                parts.append(short_names[i])
        return '+'.join(parts) if parts else 'None'

    combo_labels = triggered.apply(make_combo_name, axis=1)
    n_triggered = triggered.sum(axis=1)

    analysis_df = pd.DataFrame({
        'combination': combo_labels,
        'n_triggered': n_triggered,
        LABEL_COL: df[LABEL_COL].values,
    })

    combo_stats = analysis_df.groupby('combination').agg(
        n_triggered=('n_triggered', 'first'),
        count=(LABEL_COL, 'count'),
        mean=(LABEL_COL, 'mean'),
        median=(LABEL_COL, 'median'),
        std=(LABEL_COL, 'std'),
        q25=(LABEL_COL, lambda x: x.quantile(0.25)),
        q75=(LABEL_COL, lambda x: x.quantile(0.75)),
    ).reset_index()

    combo_stats_filtered = combo_stats[combo_stats['count'] >= MIN_COMBO_SAMPLES].copy()
    combo_stats_filtered = combo_stats_filtered.sort_values('median', ascending=False).reset_index(drop=True)

    top10 = combo_stats_filtered.head(10).copy()

    by_n_triggered = analysis_df.groupby('n_triggered')[LABEL_COL].agg(
        count='count',
        mean='mean',
        median='median',
    ).reset_index()

    return {
        'combo_stats': combo_stats_filtered,
        'top10': top10,
        'by_n_triggered': by_n_triggered,
        'total_combos': len(combo_stats),
        'filtered_combos': len(combo_stats_filtered),
    }


# =========================================================================
# 3. 交互效应分析
# =========================================================================

def _interaction_analysis(df: pd.DataFrame) -> dict:
    """
    两两 factor 交互效应矩阵

    交互效应 = mean(A触发 & B触发) - mean(仅A触发或仅B触发)
    """
    level_cols = get_level_cols()
    factor_display = get_factor_display()
    n = len(level_cols)
    matrix = pd.DataFrame(
        np.full((n, n), np.nan),
        index=[factor_display[c] for c in level_cols],
        columns=[factor_display[c] for c in level_cols],
    )

    triggered = {}
    for col in level_cols:
        triggered[col] = (df[col] > 0)

    interaction_rows = []

    for i in range(n):
        for j in range(i + 1, n):
            col_a, col_b = level_cols[i], level_cols[j]
            a_on = triggered[col_a]
            b_on = triggered[col_b]

            both = a_on & b_on
            only_one = (a_on ^ b_on)

            label_both = df.loc[both, LABEL_COL]
            label_one = df.loc[only_one, LABEL_COL]

            if len(label_both) >= 5 and len(label_one) >= 5:
                effect = label_both.mean() - label_one.mean()
            else:
                effect = np.nan

            name_a = factor_display[col_a]
            name_b = factor_display[col_b]
            matrix.loc[name_a, name_b] = effect
            matrix.loc[name_b, name_a] = effect

            if not np.isnan(effect):
                interaction_rows.append({
                    'factor_a': name_a,
                    'factor_b': name_b,
                    'effect': effect,
                    'n_both': int(both.sum()),
                    'n_one_only': int(only_one.sum()),
                })

    for i in range(n):
        name = factor_display[level_cols[i]]
        matrix.loc[name, name] = 0.0

    interaction_df = pd.DataFrame(interaction_rows)
    if not interaction_df.empty:
        interaction_df = interaction_df.sort_values('effect', ascending=False).reset_index(drop=True)

    return {
        'matrix': matrix,
        'top_interactions': interaction_df,
    }


# =========================================================================
# 4. 决策树特征重要性
# =========================================================================

def _feature_importance_analysis(df: pd.DataFrame) -> dict:
    """DecisionTree + RandomForest 拟合 factor levels -> label"""
    level_cols = get_level_cols()
    factor_display = get_factor_display()

    X = df[level_cols].fillna(0)
    y = df[LABEL_COL].fillna(0)

    feature_names = [factor_display.get(c, c) for c in level_cols]

    dt = DecisionTreeRegressor(max_depth=4, random_state=42)
    dt.fit(X, y)
    dt_imp = pd.DataFrame({
        'feature': feature_names,
        'importance': dt.feature_importances_,
    }).sort_values('importance', ascending=False).reset_index(drop=True)

    rf = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    rf_imp = pd.DataFrame({
        'feature': feature_names,
        'importance': rf.feature_importances_,
    }).sort_values('importance', ascending=False).reset_index(drop=True)

    return {
        'dt_importance': dt_imp,
        'rf_importance': rf_imp,
        'dt_score': dt.score(X, y),
        'rf_score': rf.score(X, y),
    }


# =========================================================================
# 5. 因子间相关性分析
# =========================================================================

def _factor_correlation_analysis(df: pd.DataFrame) -> dict:
    """
    因子间 Spearman 相关性矩阵 + 高相关因子对提取。

    使用原始值（raw key 列）而非 level 列，避免离散化损失信息。

    Returns:
        {
            'matrix': DataFrame(n×n, index/columns=factor key),
            'top_pairs': DataFrame(factor_a, factor_b, spearman_r, p_value),
        }
    """
    raw_values = prepare_raw_values(df)
    keys = list(raw_values.keys())

    # 构建原始值 DataFrame
    raw_df = pd.DataFrame(raw_values)

    # Spearman 相关矩阵
    corr_matrix = raw_df.corr(method='spearman')

    # 提取上三角所有因子对（含 p_value）
    pair_rows = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            valid = raw_df[[keys[i], keys[j]]].dropna()
            if len(valid) > 2:
                r, p = spearmanr(valid[keys[i]], valid[keys[j]])
            else:
                r, p = np.nan, np.nan
            pair_rows.append({
                'factor_a': keys[i],
                'factor_b': keys[j],
                'spearman_r': r,
                'p_value': p,
            })

    top_pairs = pd.DataFrame(pair_rows)
    if not top_pairs.empty:
        top_pairs = (top_pairs
                     .assign(abs_r=lambda x: x['spearman_r'].abs())
                     .sort_values('abs_r', ascending=False)
                     .drop(columns='abs_r')
                     .reset_index(drop=True))

    return {'matrix': corr_matrix, 'top_pairs': top_pairs}


# =========================================================================
# 6. 非单调性检测
# =========================================================================

def _non_monotonicity_analysis(df: pd.DataFrame) -> dict:
    """
    对每个因子做分段 Spearman 非单调性检测（raw value vs label）。

    Returns:
        {'factors': {key: detect_non_monotonicity() 结果}, 'summary': DataFrame}
    """
    raw_values = prepare_raw_values(df)
    labels = df[LABEL_COL].values

    factors = {}
    rows = []
    for fi in get_active_factors():
        key = fi.key
        if key not in raw_values:
            continue
        raw = raw_values[key]
        valid = ~np.isnan(raw) & ~np.isnan(labels)
        result = detect_non_monotonicity(raw[valid], labels[valid])
        factors[key] = result
        if result['is_non_monotonic']:
            seg_strs = [f"Q{s['quantile_range'][0]:.0%}-{s['quantile_range'][1]:.0%}: "
                        f"r={s['spearman_r']:+.4f}"
                        for s in result['segments']]
            rows.append({
                'factor': key,
                'segments': ' / '.join(seg_strs),
            })

    summary = pd.DataFrame(rows)
    return {'factors': factors, 'summary': summary}


# =========================================================================
# 7. 挖掘阈值画像
# =========================================================================

def _threshold_position_analysis(
    df: pd.DataFrame,
    thresholds: dict[str, float],
    negative_factors: frozenset,
) -> dict:
    """
    统计每个因子的挖掘阈值在 raw value 分布中的位置和激活率。

    对每个因子计算：
    - percentile: 严格低于阈值的样本占比（0~100）
    - activation_rate: 满足阈值条件的样本占比

    Args:
        df: 含因子原始值列的 DataFrame
        thresholds: {factor_key: threshold_value}
        negative_factors: 反向因子集合（lte 触发）

    Returns:
        {'profile': DataFrame(factor, threshold, direction, percentile,
                              activation_rate, activated_n, total_n)}
    """
    from scipy.stats import percentileofscore

    raw_values = prepare_raw_values(df)
    rows = []

    for fi in get_active_factors():
        key = fi.key
        if key not in thresholds:
            continue

        thresh = thresholds[key]
        raw = raw_values[key]
        direction = 'lte' if key in negative_factors else 'gte'

        # 百分位：阈值在全样本 raw value 中的位置
        if len(raw) > 0:
            pct = float(percentileofscore(raw, thresh, kind='strict'))
        else:
            pct = np.nan

        # 激活率：全样本中满足条件的比例
        if direction == 'lte':
            activated = int((raw <= thresh).sum())
        else:
            activated = int((raw >= thresh).sum())
        total = len(raw)
        rate = activated / total if total > 0 else 0.0

        rows.append({
            'factor': key,
            'threshold': round(thresh, 4),
            'direction': direction,
            'percentile': round(pct, 1),
            'activation_rate': round(rate, 4),
            'activated_n': activated,
            'total_n': total,
        })

    profile = pd.DataFrame(rows)
    if not profile.empty:
        profile = profile.sort_values('activation_rate', ascending=False).reset_index(drop=True)

    return {'profile': profile}


# =========================================================================
# run_analysis: 汇总入口
# =========================================================================

def run_analysis(
    df: pd.DataFrame,
    thresholds: dict[str, float] | None = None,
    negative_factors: frozenset = frozenset(),
) -> dict:
    """
    执行统计分析（6 个基础维度 + 可选的阈值画像）

    Args:
        df: 包含 factor levels + label 的 DataFrame
        thresholds: 挖掘阈值 {factor_key: value}，为 None 时跳过阈值画像
        negative_factors: 反向因子集合（lte 触发）

    Returns:
        results dict，包含各维度分析结果 + 基础统计
    """
    print(f"[Analysis] DataFrame shape: {df.shape}")
    print(f"[Analysis] Label column stats: mean={df[LABEL_COL].mean():.4f}, "
          f"median={df[LABEL_COL].median():.4f}, std={df[LABEL_COL].std():.4f}")

    results = {
        'n_samples': len(df),
        'label_stats': {
            'mean': df[LABEL_COL].mean(),
            'median': df[LABEL_COL].median(),
            'std': df[LABEL_COL].std(),
            'min': df[LABEL_COL].min(),
            'max': df[LABEL_COL].max(),
        },
    }

    print("[Analysis] 1/6 Single factor analysis...")
    results['single_factor'] = _single_factor_analysis(df)

    print("[Analysis] 2/6 Combination analysis...")
    results['combination'] = _combination_analysis(df)

    print("[Analysis] 3/6 Interaction analysis...")
    results['interaction'] = _interaction_analysis(df)

    print("[Analysis] 4/6 Feature importance analysis...")
    results['importance'] = _feature_importance_analysis(df)

    print("[Analysis] 5/6 Factor correlation analysis...")
    results['factor_correlation'] = _factor_correlation_analysis(df)

    print("[Analysis] 6/6 Non-monotonicity analysis...")
    results['non_monotonicity'] = _non_monotonicity_analysis(df)

    if thresholds is not None:
        print("[Analysis] +1 Threshold position analysis...")
        results['threshold_profile'] = _threshold_position_analysis(
            df, thresholds, negative_factors,
        )

    print("[Analysis] Done.")
    return results
