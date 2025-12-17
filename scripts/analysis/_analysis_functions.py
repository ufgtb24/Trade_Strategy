"""
Bonus 组合统计分析函数

提供 run_analysis(df) 和 generate_report(results) 两个核心函数，
由 bonus_combination_analysis.py 的 main() 调用。

分析维度：
1. 单因子分析 — 每个 bonus level vs label 的统计量 + Spearman 相关
2. 模式分析 — pattern_label 分组统计 + 非参数显著性检验
3. 组合分析 — 二值化 triggered 组合枚举，找出最佳组合
4. 交互效应 — 两两 bonus 交互效应矩阵
5. 决策树特征重要性 — DecisionTree + RandomForest
"""

import numpy as np
import pandas as pd
from itertools import combinations
from scipy.stats import spearmanr, mannwhitneyu, kruskal
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor

# =========================================================================
# 常量定义
# =========================================================================

BONUS_COLS = [
    'age_level', 'test_level', 'volume_level', 'pk_mom_level',
    'streak_level', 'pbm_level', 'overshoot_level', 'day_str_level',
    'peak_vol_level', 'drought_level', 'height_level'
]

# 显示友好名
BONUS_DISPLAY = {
    'age_level': 'Age',
    'test_level': 'Tests',
    'volume_level': 'Volume',
    'pk_mom_level': 'PK-Mom',
    'streak_level': 'Streak',
    'pbm_level': 'PBM',
    'overshoot_level': 'Overshoot',
    'day_str_level': 'DayStr',
    'peak_vol_level': 'PeakVol',
    'drought_level': 'Drought',
    'height_level': 'Height',
}

LABEL_COL = 'label_10_40'
MIN_COMBO_SAMPLES = 20


# =========================================================================
# 1. 单因子分析
# =========================================================================

def _single_factor_analysis(df: pd.DataFrame) -> dict:
    """
    每个 bonus 按 level 分组，计算 label 统计量 + Spearman 相关系数

    Returns:
        {
            'by_level': {bonus_col: DataFrame(level, count, mean, median, std, q25, q75)},
            'correlations': DataFrame(bonus, spearman_r, p_value)
        }
    """
    by_level = {}
    corr_rows = []

    for col in BONUS_COLS:
        # 按 level 分组统计
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

        # Spearman 相关
        valid = df[[col, LABEL_COL]].dropna()
        if len(valid) > 2:
            r, p = spearmanr(valid[col], valid[LABEL_COL])
        else:
            r, p = np.nan, np.nan
        corr_rows.append({
            'bonus': BONUS_DISPLAY.get(col, col),
            'spearman_r': r,
            'p_value': p,
        })

    correlations = pd.DataFrame(corr_rows)
    return {'by_level': by_level, 'correlations': correlations}


# =========================================================================
# 2. 模式分析
# =========================================================================

def _pattern_analysis(df: pd.DataFrame) -> dict:
    """
    按 pattern_label 分组统计，以及组间显著性检验

    Returns:
        {
            'stats': DataFrame(pattern, count, mean, median, std, q25, q75),
            'kruskal_stat': float,
            'kruskal_p': float,
            'pairwise': DataFrame(pattern_a, pattern_b, u_stat, p_value) — 样本量>=20的模式间两两比较
        }
    """
    if 'pattern_label' not in df.columns:
        return {'stats': pd.DataFrame(), 'kruskal_stat': np.nan, 'kruskal_p': np.nan, 'pairwise': pd.DataFrame()}

    stats = df.groupby('pattern_label')[LABEL_COL].agg(
        count='count',
        mean='mean',
        median='median',
        std='std',
        q25=lambda x: x.quantile(0.25),
        q75=lambda x: x.quantile(0.75),
    ).reset_index()
    stats.columns = ['pattern', 'count', 'mean', 'median', 'std', 'q25', 'q75']
    stats = stats.sort_values('median', ascending=False).reset_index(drop=True)

    # Kruskal-Wallis 检验（全局非参数 ANOVA）
    groups = [g[LABEL_COL].values for _, g in df.groupby('pattern_label') if len(g) >= 5]
    if len(groups) >= 2:
        kstat, kp = kruskal(*groups)
    else:
        kstat, kp = np.nan, np.nan

    # 两两 Mann-Whitney U（仅样本量 >= 20 的模式）
    valid_patterns = stats[stats['count'] >= 20]['pattern'].tolist()
    pairwise_rows = []
    for pa, pb in combinations(valid_patterns, 2):
        ga = df[df['pattern_label'] == pa][LABEL_COL].dropna()
        gb = df[df['pattern_label'] == pb][LABEL_COL].dropna()
        if len(ga) >= 5 and len(gb) >= 5:
            u, p = mannwhitneyu(ga, gb, alternative='two-sided')
            pairwise_rows.append({
                'pattern_a': pa,
                'pattern_b': pb,
                'u_stat': u,
                'p_value': p,
            })
    pairwise = pd.DataFrame(pairwise_rows)

    return {
        'stats': stats,
        'kruskal_stat': kstat,
        'kruskal_p': kp,
        'pairwise': pairwise,
    }


# =========================================================================
# 3. 组合分析（核心）
# =========================================================================

def _combination_analysis(df: pd.DataFrame) -> dict:
    """
    将 bonus 二值化为 triggered/not_triggered，枚举所有出现过的组合

    Returns:
        {
            'combo_stats': DataFrame(combination, n_triggered, count, mean, median, std, q25, q75),
            'top10': DataFrame — 按 median 排序的前 10
            'overall_stats': dict — 全局统计
        }
    """
    # 二值化
    triggered = pd.DataFrame()
    for col in BONUS_COLS:
        triggered[col] = (df[col] > 0).astype(int)

    # 生成组合名称
    short_names = [BONUS_DISPLAY.get(c, c) for c in BONUS_COLS]

    def make_combo_name(row):
        parts = []
        for i, col in enumerate(BONUS_COLS):
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

    # 按组合分组统计
    combo_stats = analysis_df.groupby('combination').agg(
        n_triggered=('n_triggered', 'first'),
        count=(LABEL_COL, 'count'),
        mean=(LABEL_COL, 'mean'),
        median=(LABEL_COL, 'median'),
        std=(LABEL_COL, 'std'),
        q25=(LABEL_COL, lambda x: x.quantile(0.25)),
        q75=(LABEL_COL, lambda x: x.quantile(0.75)),
    ).reset_index()

    # 筛选样本量 >= MIN_COMBO_SAMPLES
    combo_stats_filtered = combo_stats[combo_stats['count'] >= MIN_COMBO_SAMPLES].copy()
    combo_stats_filtered = combo_stats_filtered.sort_values('median', ascending=False).reset_index(drop=True)

    top10 = combo_stats_filtered.head(10).copy()

    # 按触发数量汇总
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
# 4. 交互效应分析
# =========================================================================

def _interaction_analysis(df: pd.DataFrame) -> dict:
    """
    两两 bonus 交互效应矩阵

    交互效应 = mean(A触发 & B触发) - mean(仅A触发或仅B触发)

    Returns:
        {
            'matrix': DataFrame — bonus×bonus 交互效应矩阵
            'top_interactions': list of dict — 排序后的交互对
        }
    """
    n = len(BONUS_COLS)
    matrix = pd.DataFrame(
        np.full((n, n), np.nan),
        index=[BONUS_DISPLAY[c] for c in BONUS_COLS],
        columns=[BONUS_DISPLAY[c] for c in BONUS_COLS],
    )

    # 预计算每个 bonus 的触发状态
    triggered = {}
    for col in BONUS_COLS:
        triggered[col] = (df[col] > 0)

    interaction_rows = []

    for i in range(n):
        for j in range(i + 1, n):
            col_a, col_b = BONUS_COLS[i], BONUS_COLS[j]
            a_on = triggered[col_a]
            b_on = triggered[col_b]

            # 两者都触发
            both = a_on & b_on
            # 仅 A 或仅 B 触发（不含两者都触发）
            only_one = (a_on ^ b_on)

            label_both = df.loc[both, LABEL_COL]
            label_one = df.loc[only_one, LABEL_COL]

            if len(label_both) >= 5 and len(label_one) >= 5:
                effect = label_both.mean() - label_one.mean()
            else:
                effect = np.nan

            name_a = BONUS_DISPLAY[col_a]
            name_b = BONUS_DISPLAY[col_b]
            matrix.loc[name_a, name_b] = effect
            matrix.loc[name_b, name_a] = effect

            if not np.isnan(effect):
                interaction_rows.append({
                    'bonus_a': name_a,
                    'bonus_b': name_b,
                    'effect': effect,
                    'n_both': int(both.sum()),
                    'n_one_only': int(only_one.sum()),
                })

    # 对角线设为 0
    for i in range(n):
        name = BONUS_DISPLAY[BONUS_COLS[i]]
        matrix.loc[name, name] = 0.0

    interaction_df = pd.DataFrame(interaction_rows)
    if not interaction_df.empty:
        interaction_df = interaction_df.sort_values('effect', ascending=False).reset_index(drop=True)

    return {
        'matrix': matrix,
        'top_interactions': interaction_df,
    }


# =========================================================================
# 5. 决策树特征重要性
# =========================================================================

def _feature_importance_analysis(df: pd.DataFrame) -> dict:
    """
    DecisionTree + RandomForest 拟合 bonus levels -> label

    Returns:
        {
            'dt_importance': DataFrame(feature, importance) — DecisionTree
            'rf_importance': DataFrame(feature, importance) — RandomForest
            'dt_score': float — R^2
            'rf_score': float — R^2
        }
    """
    X = df[BONUS_COLS].fillna(0)
    y = df[LABEL_COL].fillna(0)

    feature_names = [BONUS_DISPLAY.get(c, c) for c in BONUS_COLS]

    # DecisionTree
    dt = DecisionTreeRegressor(max_depth=4, random_state=42)
    dt.fit(X, y)
    dt_imp = pd.DataFrame({
        'feature': feature_names,
        'importance': dt.feature_importances_,
    }).sort_values('importance', ascending=False).reset_index(drop=True)

    # RandomForest
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
# run_analysis: 汇总入口
# =========================================================================

def run_analysis(df: pd.DataFrame) -> dict:
    """
    执行全部 5 个维度的统计分析

    Args:
        df: 包含 bonus levels + label_10_40 的 DataFrame

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

    print("[Analysis] 1/5 Single factor analysis...")
    results['single_factor'] = _single_factor_analysis(df)

    print("[Analysis] 2/5 Pattern analysis...")
    results['pattern'] = _pattern_analysis(df)

    print("[Analysis] 3/5 Combination analysis...")
    results['combination'] = _combination_analysis(df)

    print("[Analysis] 4/5 Interaction analysis...")
    results['interaction'] = _interaction_analysis(df)

    print("[Analysis] 5/5 Feature importance analysis...")
    results['importance'] = _feature_importance_analysis(df)

    print("[Analysis] Done.")
    return results


# =========================================================================
# generate_report: Markdown 报告生成
# =========================================================================

def _fmt(val, decimals=4):
    """格式化数值"""
    if pd.isna(val):
        return '-'
    if isinstance(val, (int, np.integer)):
        return str(val)
    return f"{val:.{decimals}f}"


def _df_to_md_table(df: pd.DataFrame, float_fmt: int = 4) -> str:
    """将 DataFrame 转为 Markdown 表格"""
    if df.empty:
        return "*No data*\n"

    lines = []
    # header
    headers = list(df.columns)
    lines.append('| ' + ' | '.join(str(h) for h in headers) + ' |')
    lines.append('| ' + ' | '.join('---' for _ in headers) + ' |')
    # rows
    for _, row in df.iterrows():
        cells = []
        for h in headers:
            val = row[h]
            if isinstance(val, float):
                cells.append(_fmt(val, float_fmt))
            else:
                cells.append(str(val))
        lines.append('| ' + ' | '.join(cells) + ' |')

    return '\n'.join(lines) + '\n'


def _significance_stars(p: float) -> str:
    """将 p 值转为显著性星号"""
    if pd.isna(p):
        return ''
    if p < 0.001:
        return '***'
    if p < 0.01:
        return '**'
    if p < 0.05:
        return '*'
    return ''


def generate_report(results: dict, report_name: str = "bonus_combination_report.md") -> str:
    """
    生成 Markdown 格式的分析报告

    Args:
        results: run_analysis() 的返回值
        report_name: 报告文件名，输出到 docs/research/ 目录下

    Returns:
        报告文件路径
    """
    lines = []
    lines.append('# Bonus Combination Analysis Report\n')
    lines.append(f"Sample size: **{results['n_samples']}** breakout events\n")
    lines.append('> 本报告分析各种 Bonus（加分因子）对突破后股价表现的影响。'
                 '每个 Bonus 代表突破发生时的一个有利特征（如放量、历史阻力密集等），'
                 'level 越高表示该特征越突出。'
                 '我们想知道：哪些特征真正预示了更好的突破后涨幅？哪些组合效果最佳？\n')

    # 基础统计
    ls = results['label_stats']
    lines.append('## 0. Label Overview (label_10_40)\n')
    lines.append('> **label_10_40** 是突破后的实际涨幅，具体含义是突破后第10~40个交易日内的'
                 '最大收益（相对突破价格的倍数）。它是我们衡量"突破质量好不好"的标尺。'
                 '下方表格展示了所有突破事件涨幅的基本统计：\n'
                 '> - **Mean（均值）**：所有突破的平均涨幅\n'
                 '> - **Median（中位数）**：排在正中间的涨幅，比均值更能反映"典型"水平（不受极端值影响）\n'
                 '> - **Std（标准差）**：涨幅的波动程度，越大说明结果越分散、不确定性越高\n'
                 '> - **Min / Max**：最差和最好的情况\n')
    lines.append(f"| Metric | Value |")
    lines.append(f"| --- | --- |")
    lines.append(f"| Mean | {_fmt(ls['mean'])} |")
    lines.append(f"| Median | {_fmt(ls['median'])} |")
    lines.append(f"| Std | {_fmt(ls['std'])} |")
    lines.append(f"| Min | {_fmt(ls['min'])} |")
    lines.append(f"| Max | {_fmt(ls['max'])} |")
    lines.append('')

    # =================================================================
    # 1. 单因子分析
    # =================================================================
    lines.append('## 1. Single Factor Analysis\n')
    lines.append('> **目的**：逐个考察每个 Bonus 因子，看它单独对涨幅有没有影响、影响有多大。'
                 '就像体检逐项检查一样，先弄清每个因子的"单兵作战能力"。\n')

    # 1a. Spearman 相关
    lines.append('### 1.1 Spearman Correlation (bonus level vs label)\n')
    lines.append('> **Spearman 相关系数**衡量两个变量之间的单调关系（即"一个变大，另一个是否也倾向于变大"），'
                 '不要求两者是线性关系，适合我们这种 level 是离散等级的数据。\n'
                 '> - **spearman_r**：相关系数，范围 -1 到 1。正值表示 bonus level 越高，涨幅越好；'
                 '负值表示反而越差。绝对值越大关联越强\n'
                 '> - **p_value**：这个关联"碰巧出现"的概率。p 值越小，说明结果越可信。'
                 '带星号 \\* 的表示统计上显著（不太可能是偶然）\n'
                 '> - 实操参考：r > 0 且带 \\*\\*\\* 的因子是值得关注的正面信号\n')
    corr = results['single_factor']['correlations'].copy()
    corr['significance'] = corr['p_value'].apply(_significance_stars)
    corr = corr.sort_values('spearman_r', ascending=False).reset_index(drop=True)
    lines.append(_df_to_md_table(corr))
    lines.append('> \\* p<0.05, \\*\\* p<0.01, \\*\\*\\* p<0.001\n')

    # 1b. 各 bonus 按 level 分组
    lines.append('### 1.2 Label Distribution by Bonus Level\n')
    lines.append('> 下面逐个展示每个 Bonus 在不同 level 下的涨幅分布。每张表的列含义：\n'
                 '> - **level**：该 Bonus 的等级（0 = 未触发，1/2/3 = 逐级增强）\n'
                 '> - **count**：该等级的样本数量\n'
                 '> - **mean / median**：该等级下突破后涨幅的平均值和中位数。'
                 '重点看 median，它不受极端值干扰\n'
                 '> - **q25 / q75**：25% 分位和 75% 分位，表示"中间 50% 的突破"涨幅区间。'
                 '区间越窄说明结果越稳定\n'
                 '>\n'
                 '> **怎么看**：如果某个 Bonus 的 level 从 0 → 1 → 2 时 median 明显递增，'
                 '说明这个因子越强、突破后表现越好。\n')
    for col in BONUS_COLS:
        display_name = BONUS_DISPLAY.get(col, col)
        level_df = results['single_factor']['by_level'][col]
        lines.append(f'#### {display_name}\n')
        lines.append(_df_to_md_table(level_df))
        lines.append('')

    # =================================================================
    # 2. 模式分析
    # =================================================================
    lines.append('## 2. Pattern Analysis\n')
    lines.append('> **目的**：看不同"突破模式"（pattern）之间表现有没有差异。'
                 '每次突破会被自动归类为一种模式（如 power_historical、momentum 等），'
                 '这里检验这些分类是否真的对应不同的涨幅水平。\n')

    pat = results['pattern']
    if not pat['stats'].empty:
        lines.append('### 2.1 Label by Pattern\n')
        lines.append('> 各模式按中位数涨幅从高到低排列。重点关注 count 较大'
                     '（样本充足）且 median 较高的模式。\n')
        lines.append(_df_to_md_table(pat['stats']))
        lines.append('')

        lines.append('### 2.2 Kruskal-Wallis Test (global non-parametric ANOVA)\n')
        lines.append('> **Kruskal-Wallis 检验**回答一个问题："这些模式之间的涨幅差异是真实的，'
                     '还是随机波动造成的假象？"\n'
                     '> - **H statistic**：差异程度的量化值，越大说明组间差距越明显\n'
                     '> - **p-value**：如果 p < 0.05（带 \\*），说明至少有两个模式之间存在'
                     '统计上显著的差异；如果 p > 0.05，则各模式的差异可能只是噪音\n')
        lines.append(f"- H statistic: {_fmt(pat['kruskal_stat'])}")
        lines.append(f"- p-value: {_fmt(pat['kruskal_p'])} {_significance_stars(pat['kruskal_p'])}")
        lines.append('')

        if not pat['pairwise'].empty:
            lines.append('### 2.3 Pairwise Mann-Whitney U Tests (patterns with n>=20)\n')
            lines.append('> 上面是"整体有没有差异"，这里进一步两两比较，找出具体是哪两个模式之间不同。\n'
                         '> - **Mann-Whitney U 检验**：比较两组数据谁的值倾向于更大，'
                         '不需要数据服从正态分布\n'
                         '> - p_value 带 \\* 的行表示这两个模式之间的涨幅差异是显著的\n')
            pw = pat['pairwise'].copy()
            pw['significance'] = pw['p_value'].apply(_significance_stars)
            pw = pw.sort_values('p_value').reset_index(drop=True)
            lines.append(_df_to_md_table(pw))
            lines.append('')
    else:
        lines.append('*No pattern_label data available.*\n')

    # =================================================================
    # 3. 组合分析
    # =================================================================
    lines.append('## 3. Combination Analysis (Core)\n')
    lines.append('> **目的**：这是报告的核心部分。单个因子的影响可能不大，'
                 '但多个因子同时出现时可能产生"共振"效应。这里把每个 Bonus 简化为'
                 '"有/无"（level > 0 即算触发），然后统计每种触发组合对应的涨幅表现。\n')

    combo = results['combination']
    lines.append(f"Total unique combinations: {combo['total_combos']}\n")
    lines.append(f"Combinations with n >= {MIN_COMBO_SAMPLES}: {combo['filtered_combos']}\n")

    # 3a. 按触发数量汇总
    lines.append('### 3.1 Label by Number of Triggered Bonuses\n')
    lines.append('> 最简单的问题："触发的 Bonus 越多，表现是否越好？"'
                 '下表按触发数量汇总涨幅。如果 median 随触发数量递增，'
                 '说明"多因子共振"确实有效。\n')
    lines.append(_df_to_md_table(combo['by_n_triggered']))
    lines.append('')

    # 3b. Top 10 最佳组合
    lines.append('### 3.2 Top 10 Best Combinations (by median label, n>=20)\n')
    lines.append('> 在所有至少出现 20 次的组合中，中位数涨幅最高的前 10 个。'
                 '这些是历史上表现最好的 Bonus 搭配模式。\n'
                 '> - **combination**：触发的 Bonus 列表（如 "Volume+DayStr" 表示这两个同时触发）\n'
                 '> - **n_triggered**：触发了几个 Bonus\n'
                 '> - **count**：这种组合出现了多少次（样本量越大越可信）\n')
    if not combo['top10'].empty:
        lines.append(_df_to_md_table(combo['top10']))
    else:
        lines.append('*No combinations with sufficient sample size.*\n')
    lines.append('')

    # 3c. 完整列表（按 median 排序）
    lines.append('### 3.3 All Combinations (n>=20, sorted by median)\n')
    lines.append('> 满足最小样本量要求的所有组合完整列表，按中位数涨幅从高到低排序。\n')
    if not combo['combo_stats'].empty:
        lines.append(_df_to_md_table(combo['combo_stats']))
    else:
        lines.append('*No combinations with sufficient sample size.*\n')
    lines.append('')

    # =================================================================
    # 4. 交互效应分析
    # =================================================================
    lines.append('## 4. Interaction Effects\n')
    lines.append('> **目的**：检验两个 Bonus 之间是否存在"1+1>2"（正交互）或"1+1<2"（负交互）效应。'
                 '比如 Volume 和 DayStr 单独看都不错，但同时出现时效果是相加还是相乘？\n'
                 '>\n'
                 '> **计算方法**：用"A和B同时触发"时的平均涨幅，'
                 '减去"只有A或只有B触发"时的平均涨幅。\n'
                 '> - 正值 → 两者搭配有增益效果（协同增强）\n'
                 '> - 负值 → 两者搭配反而不如单独出现（互相抵消）\n'
                 '> - 接近 0 → 没有明显交互，各自独立发挥作用\n')

    inter = results['interaction']

    # 4a. 交互效应矩阵
    lines.append('### 4.1 Interaction Matrix\n')
    lines.append('> 矩阵中每个格子是对应两个 Bonus 的交互效应值。'
                 '正值越大说明协同越强，负值越大说明互相抵消越严重。\n')
    matrix = inter['matrix']
    if not matrix.empty:
        # 格式化矩阵
        fmt_matrix = matrix.map(lambda x: _fmt(x, 4) if not pd.isna(x) else '-')
        lines.append(_df_to_md_table(fmt_matrix.reset_index().rename(columns={'index': 'Bonus'}), float_fmt=4))
    lines.append('')

    # 4b. Top 交互对
    lines.append('### 4.2 Top Positive Interactions\n')
    lines.append('> 协同效应最强的组合——这些 Bonus 搭配在一起时表现远超单独出现。\n'
                 '> - **n_both**：两者同时触发的样本数（越多越可信）\n'
                 '> - **n_one_only**：只有其中一个触发的样本数\n')
    top_inter = inter['top_interactions']
    if not top_inter.empty:
        top_pos = top_inter[top_inter['effect'] > 0].head(10)
        if not top_pos.empty:
            lines.append(_df_to_md_table(top_pos))
        else:
            lines.append('*No positive interaction effects found.*\n')
    else:
        lines.append('*Insufficient data for interaction analysis.*\n')
    lines.append('')

    lines.append('### 4.3 Top Negative Interactions\n')
    lines.append('> 互相抵消效应最强的组合——这些 Bonus 同时出现时反而不如单独出现。\n')
    if not top_inter.empty:
        top_neg = top_inter[top_inter['effect'] < 0].tail(10).sort_values('effect')
        if not top_neg.empty:
            lines.append(_df_to_md_table(top_neg))
        else:
            lines.append('*No negative interaction effects found.*\n')
    else:
        lines.append('*Insufficient data for interaction analysis.*\n')
    lines.append('')

    # =================================================================
    # 5. 决策树特征重要性
    # =================================================================
    lines.append('## 5. Feature Importance (Tree Models)\n')
    lines.append('> **目的**：用机器学习模型自动判断哪些 Bonus 因子对预测涨幅最重要。'
                 '这是对前面人工分析的补充——让算法"自己说"哪些因子最有用。\n'
                 '>\n'
                 '> 使用了两种树模型：\n'
                 '> - **DecisionTree（决策树）**：像流程图一样逐步判断，'
                 '每一步选一个最有区分力的因子来分组。简单直观但可能不稳定\n'
                 '> - **RandomForest（随机森林）**：同时训练 100 棵不同的决策树，'
                 '综合它们的意见来判断。结果更稳定可靠\n'
                 '>\n'
                 '> **importance（重要性）**：该因子对预测的贡献占比，所有因子加起来 = 1.0。'
                 '越高说明模型越依赖这个因子来做判断\n'
                 '>\n'
                 '> **R-squared（R²）**：模型用这些 Bonus levels 能解释多少涨幅的变化。'
                 '0 = 完全没有解释力，1 = 完美预测。'
                 '通常低于 0.1 说明这些因子单独来看解释力有限（但不代表没用，'
                 '它们仍可作为筛选信号）\n')

    imp = results['importance']

    lines.append('### 5.1 DecisionTree (max_depth=4)\n')
    lines.append(f"R-squared: {_fmt(imp['dt_score'])}\n")
    lines.append(_df_to_md_table(imp['dt_importance']))
    lines.append('')

    lines.append('### 5.2 RandomForest (n_estimators=100, max_depth=4)\n')
    lines.append(f"R-squared: {_fmt(imp['rf_score'])}\n")
    lines.append(_df_to_md_table(imp['rf_importance']))
    lines.append('')

    # =================================================================
    # 6. 关键发现与结论
    # =================================================================
    lines.append('## 6. Key Findings\n')
    lines.append('> 以下是算法从上述分析中自动提取的要点摘要。\n')

    # 自动提取关键发现
    findings = _extract_key_findings(results)
    for i, finding in enumerate(findings, 1):
        lines.append(f"{i}. {finding}")
    lines.append('')

    # 写出报告
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent.parent
    report_path = project_root / "docs" / "statistics" / report_name
    content = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[Report] Written to {report_path}")
    return report_path


def _extract_key_findings(results: dict) -> list:
    """
    从分析结果中自动提取关键发现

    Returns:
        发现列表（字符串）
    """
    findings = []

    # 1. 最强相关的 bonus
    corr = results['single_factor']['correlations']
    if not corr.empty:
        best = corr.loc[corr['spearman_r'].abs().idxmax()]
        findings.append(
            f"**Strongest single factor**: {best['bonus']} "
            f"(Spearman r = {best['spearman_r']:.4f}, p = {best['p_value']:.4g})"
        )

    # 2. 最佳组合
    top10 = results['combination']['top10']
    if not top10.empty:
        best_combo = top10.iloc[0]
        findings.append(
            f"**Best combination**: {best_combo['combination']} "
            f"(median = {best_combo['median']:.4f}, n = {int(best_combo['count'])})"
        )

    # 3. 触发数量与表现
    by_n = results['combination']['by_n_triggered']
    if not by_n.empty and len(by_n) >= 3:
        best_n = by_n.loc[by_n['median'].idxmax()]
        findings.append(
            f"**Optimal trigger count**: {int(best_n['n_triggered'])} bonuses triggered "
            f"(median label = {best_n['median']:.4f})"
        )

    # 4. 最强正交互效应
    inter = results['interaction']['top_interactions']
    if not inter.empty and len(inter[inter['effect'] > 0]) > 0:
        best_inter = inter.iloc[0]
        findings.append(
            f"**Strongest positive interaction**: {best_inter['bonus_a']} + {best_inter['bonus_b']} "
            f"(effect = {best_inter['effect']:.4f})"
        )

    # 5. 最重要特征 (RF)
    rf_imp = results['importance']['rf_importance']
    if not rf_imp.empty:
        top_feat = rf_imp.iloc[0]
        findings.append(
            f"**Most important feature (RF)**: {top_feat['feature']} "
            f"(importance = {top_feat['importance']:.4f})"
        )

    # 6. 模式差异
    pat = results['pattern']
    if not pat['stats'].empty and len(pat['stats']) >= 2:
        best_pat = pat['stats'].iloc[0]
        worst_pat = pat['stats'].iloc[-1]
        findings.append(
            f"**Best pattern**: {best_pat['pattern']} "
            f"(median = {best_pat['median']:.4f}, n = {int(best_pat['count'])}); "
            f"**Worst**: {worst_pat['pattern']} "
            f"(median = {worst_pat['median']:.4f}, n = {int(worst_pat['count'])})"
        )

    # 7. 模型拟合度
    dt_r2 = results['importance']['dt_score']
    rf_r2 = results['importance']['rf_score']
    findings.append(
        f"**Model R-squared**: DecisionTree = {dt_r2:.4f}, RandomForest = {rf_r2:.4f} "
        f"(bonus levels alone explain {'limited' if rf_r2 < 0.1 else 'moderate' if rf_r2 < 0.3 else 'substantial'} variance)"
    )

    return findings
