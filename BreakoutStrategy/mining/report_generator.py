"""
Markdown 报告生成

从 stats_analysis.run_analysis() 的结果生成完整的 Markdown 分析报告。
IO 已分离：generate_report() 返回报告内容字符串，由调用者决定写入路径。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from BreakoutStrategy.factor_registry import get_level_cols, get_factor_display, LABEL_COL
from BreakoutStrategy.mining.stats_analysis import MIN_COMBO_SAMPLES


# =========================================================================
# 格式化工具
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
    headers = list(df.columns)
    lines.append('| ' + ' | '.join(str(h) for h in headers) + ' |')
    lines.append('| ' + ' | '.join('---' for _ in headers) + ' |')
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


# =========================================================================
# 关键发现提取
# =========================================================================

def _extract_key_findings(results: dict) -> list:
    """从分析结果中自动提取关键发现"""
    findings = []

    corr = results['single_factor']['correlations']
    if not corr.empty:
        best = corr.loc[corr['spearman_r'].abs().idxmax()]
        findings.append(
            f"**Strongest single factor**: {best['factor']} "
            f"(Spearman r = {best['spearman_r']:.4f}, p = {best['p_value']:.4g})"
        )

    top10 = results['combination']['top10']
    if not top10.empty:
        best_combo = top10.iloc[0]
        findings.append(
            f"**Best combination**: {best_combo['combination']} "
            f"(median = {best_combo['median']:.4f}, n = {int(best_combo['count'])})"
        )

    by_n = results['combination']['by_n_triggered']
    if not by_n.empty and len(by_n) >= 3:
        best_n = by_n.loc[by_n['median'].idxmax()]
        findings.append(
            f"**Optimal trigger count**: {int(best_n['n_triggered'])} factors triggered "
            f"(median label = {best_n['median']:.4f})"
        )

    inter = results['interaction']['top_interactions']
    if not inter.empty and len(inter[inter['effect'] > 0]) > 0:
        best_inter = inter.iloc[0]
        findings.append(
            f"**Strongest positive interaction**: {best_inter['factor_a']} + {best_inter['factor_b']} "
            f"(effect = {best_inter['effect']:.4f})"
        )

    rf_imp = results['importance']['rf_importance']
    if not rf_imp.empty:
        top_feat = rf_imp.iloc[0]
        findings.append(
            f"**Most important feature (RF)**: {top_feat['feature']} "
            f"(importance = {top_feat['importance']:.4f})"
        )

    dt_r2 = results['importance']['dt_score']
    rf_r2 = results['importance']['rf_score']
    findings.append(
        f"**Model R-squared**: DecisionTree = {dt_r2:.4f}, RandomForest = {rf_r2:.4f} "
        f"(factor levels alone explain {'limited' if rf_r2 < 0.1 else 'moderate' if rf_r2 < 0.3 else 'substantial'} variance)"
    )

    # 高相关因子对（可能冗余）
    if 'factor_correlation' in results:
        top_pairs = results['factor_correlation']['top_pairs']
        if not top_pairs.empty:
            high_corr = top_pairs[
                (top_pairs['spearman_r'].abs() > 0.5) & (top_pairs['p_value'] < 0.01)
            ]
            if not high_corr.empty:
                pair = high_corr.iloc[0]
                n_high = len(high_corr)
                findings.append(
                    f"**Highly correlated factor pairs**: {n_high} pair(s) with |r| > 0.5. "
                    f"Strongest: {pair['factor_a']} & {pair['factor_b']} "
                    f"(r = {pair['spearman_r']:.4f}) — consider redundancy"
                )

    return findings


# =========================================================================
# 报告生成
# =========================================================================

def generate_report(results: dict, output_path: str | Path | None = None) -> str:
    """
    生成 Markdown 格式的分析报告

    Args:
        results: run_analysis() 的返回值
        output_path: 可选，写入路径。为 None 时仅返回内容。

    Returns:
        报告内容字符串
    """
    level_cols = get_level_cols()
    factor_display = get_factor_display()

    lines = []
    lines.append('# Factor Combination Analysis Report\n')
    lines.append(f"Sample size: **{results['n_samples']}** breakout events\n")
    lines.append('> 本报告分析各种 Factor（评分因子）对突破后股价表现的影响。'
                 '每个 Factor 代表突破发生时的一个有利特征（如放量、历史阻力密集等），'
                 'level 越高表示该特征越突出。'
                 '我们想知道：哪些特征真正预示了更好的突破后涨幅？哪些组合效果最佳？\n')

    # 基础统计
    ls = results['label_stats']
    lines.append('## 0. Label Overview\n')
    lines.append('> **label** 是突破后的实际涨幅，具体含义是突破后指定观察窗口内的'
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

    # 1. 单因子分析
    lines.append('## 1. Single Factor Analysis\n')
    lines.append('> **目的**：逐个考察每个 Factor 因子，看它单独对涨幅有没有影响、影响有多大。'
                 '就像体检逐项检查一样，先弄清每个因子的"单兵作战能力"。\n')

    lines.append('### 1.1 Spearman Correlation (factor level vs label)\n')
    lines.append('> **Spearman 相关系数**衡量两个变量之间的单调关系（即"一个变大，另一个是否也倾向于变大"），'
                 '不要求两者是线性关系，适合我们这种 level 是离散等级的数据。\n'
                 '> - **spearman_r**：相关系数，范围 -1 到 1。正值表示 factor level 越高，涨幅越好；'
                 '负值表示反而越差。绝对值越大关联越强\n'
                 '> - **p_value**：这个关联"碰巧出现"的概率。p 值越小，说明结果越可信。'
                 '带星号 \\* 的表示统计上显著（不太可能是偶然）\n'
                 '> - 实操参考：r > 0 且带 \\*\\*\\* 的因子是值得关注的正面信号\n')
    corr = results['single_factor']['correlations'].copy()
    corr['significance'] = corr['p_value'].apply(_significance_stars)
    corr = corr.sort_values('spearman_r', ascending=False).reset_index(drop=True)
    lines.append(_df_to_md_table(corr))
    lines.append('> \\* p<0.05, \\*\\* p<0.01, \\*\\*\\* p<0.001\n')

    # Direction Alert: 仅在 mining_report 中检查 level Spearman < 0
    if 'threshold_profile' in results:
        neg_corr = corr[corr['spearman_r'] < 0]
        if not neg_corr.empty:
            profile = results['threshold_profile']['profile']
            dir_map = dict(zip(profile['factor'], profile['direction']))
            lines.append('> **Direction Alert**: 以下因子的 level Spearman < 0，'
                         '即被触发的样本（level=1）表现反而更差，'
                         '挖掘方向可能与因子最佳作用方向相反：\n'
                         '>\n'
                         '> | factor | spearman_r | current direction |\n'
                         '> | --- | --- | --- |')
            for _, row in neg_corr.iterrows():
                d = dir_map.get(row['factor'], '?')
                lines.append(f"> | {row['factor']} | {_fmt(row['spearman_r'])} | {d} |")
            lines.append('>\n'
                         '> 建议检查这些因子在 `factor_registry.py` 中的 `mining_mode` 设置。\n')

    lines.append('### 1.2 Label Distribution by Factor Level\n')
    lines.append('> 下面逐个展示每个 Factor 在不同 level 下的涨幅分布。每张表的列含义：\n'
                 '> - **level**：该 Factor 的等级（0 = 未触发，1/2/3 = 逐级增强）\n'
                 '> - **count**：该等级的样本数量\n'
                 '> - **mean / median**：该等级下突破后涨幅的平均值和中位数。'
                 '重点看 median，它不受极端值干扰\n'
                 '> - **q25 / q75**：25% 分位和 75% 分位，表示"中间 50% 的突破"涨幅区间。'
                 '区间越窄说明结果越稳定\n'
                 '>\n'
                 '> **怎么看**：如果某个 Factor 的 level 从 0 → 1 → 2 时 median 明显递增，'
                 '说明这个因子越强、突破后表现越好。\n')
    for col in level_cols:
        display_name = factor_display.get(col, col)
        level_df = results['single_factor']['by_level'][col]
        lines.append(f'#### {display_name}\n')
        lines.append(_df_to_md_table(level_df))
        lines.append('')

    # 1.3 非单调性检测（仅 raw_report，mining_report 跳过）
    if 'non_monotonicity' in results and 'threshold_profile' not in results:
        nm = results['non_monotonicity']
        summary = nm['summary']
        lines.append('### 1.3 Non-Monotonicity Detection (raw value vs label)\n')
        lines.append('> 按因子原始值的三分位切段，各段分别计算 Spearman 相关系数。'
                     '若段间符号翻转（如低段为负、高段为正），说明因子与收益的关系不是单调的，'
                     '单一 gte/lte 方向可能无法完整捕捉其作用模式。\n')
        if not summary.empty:
            lines.append(_df_to_md_table(summary))
            lines.append('')
        else:
            lines.append('*All factors show monotonic behavior.*\n')

    # 2. 组合分析
    lines.append('## 2. Combination Analysis (Core)\n')
    lines.append('> **目的**：这是报告的核心部分。单个因子的影响可能不大，'
                 '但多个因子同时出现时可能产生"共振"效应。这里把每个 Factor 简化为'
                 '"有/无"（level > 0 即算触发），然后统计每种触发组合对应的涨幅表现。\n')

    combo = results['combination']
    lines.append(f"Total unique combinations: {combo['total_combos']}\n")
    lines.append(f"Combinations with n >= {MIN_COMBO_SAMPLES}: {combo['filtered_combos']}\n")

    lines.append('### 2.1 Label by Number of Triggered Factors\n')
    lines.append('> 最简单的问题："触发的 Factor 越多，表现是否越好？"'
                 '下表按触发数量汇总涨幅。如果 median 随触发数量递增，'
                 '说明"多因子共振"确实有效。\n')
    lines.append(_df_to_md_table(combo['by_n_triggered']))
    lines.append('')

    lines.append('### 2.2 Top 10 Best Combinations (by median label, n>=20)\n')
    lines.append('> 在所有至少出现 20 次的组合中，中位数涨幅最高的前 10 个。'
                 '这些是历史上表现最好的 Factor 搭配模式。\n'
                 '> - **combination**：触发的 Factor 列表（如 "volume+day_str" 表示这两个同时触发）\n'
                 '> - **n_triggered**：触发了几个 Factor\n'
                 '> - **count**：这种组合出现了多少次（样本量越大越可信）\n')
    if not combo['top10'].empty:
        lines.append(_df_to_md_table(combo['top10']))
    else:
        lines.append('*No combinations with sufficient sample size.*\n')
    lines.append('')

    lines.append('### 2.3 All Combinations (n>=20, sorted by median)\n')
    lines.append('> 满足最小样本量要求的所有组合完整列表，按中位数涨幅从高到低排序。\n')
    if not combo['combo_stats'].empty:
        lines.append(_df_to_md_table(combo['combo_stats']))
    else:
        lines.append('*No combinations with sufficient sample size.*\n')
    lines.append('')

    # 3. 交互效应分析
    lines.append('## 3. Interaction Effects\n')
    lines.append('> **目的**：检验两个 Factor 之间是否存在"1+1>2"（正交互）或"1+1<2"（负交互）效应。'
                 '比如 Volume 和 DayStr 单独看都不错，但同时出现时效果是相加还是相乘？\n'
                 '>\n'
                 '> **计算方法**：用"A和B同时触发"时的平均涨幅，'
                 '减去"只有A或只有B触发"时的平均涨幅。\n'
                 '> - 正值 → 两者搭配有增益效果（协同增强）\n'
                 '> - 负值 → 两者搭配反而不如单独出现（互相抵消）\n'
                 '> - 接近 0 → 没有明显交互，各自独立发挥作用\n')

    inter = results['interaction']

    lines.append('### 3.1 Interaction Matrix\n')
    lines.append('> 矩阵中每个格子是对应两个 Factor 的交互效应值。'
                 '正值越大说明协同越强，负值越大说明互相抵消越严重。\n')
    matrix = inter['matrix']
    if not matrix.empty:
        fmt_matrix = matrix.map(lambda x: _fmt(x, 4) if not pd.isna(x) else '-')
        lines.append(_df_to_md_table(fmt_matrix.reset_index().rename(columns={'index': 'Factor'}), float_fmt=4))
    lines.append('')

    lines.append('### 3.2 Top Positive Interactions\n')
    lines.append('> 协同效应最强的组合——这些 Factor 搭配在一起时表现远超单独出现。\n'
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

    lines.append('### 3.3 Top Negative Interactions\n')
    lines.append('> 互相抵消效应最强的组合——这些 Factor 同时出现时反而不如单独出现。\n')
    if not top_inter.empty:
        top_neg = top_inter[top_inter['effect'] < 0].tail(10).sort_values('effect')
        if not top_neg.empty:
            lines.append(_df_to_md_table(top_neg))
        else:
            lines.append('*No negative interaction effects found.*\n')
    else:
        lines.append('*Insufficient data for interaction analysis.*\n')
    lines.append('')

    # 4. 决策树特征重要性
    lines.append('## 4. Feature Importance (Tree Models)\n')
    lines.append('> **目的**：用机器学习模型自动判断哪些 Factor 因子对预测涨幅最重要。'
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
                 '> **R-squared（R-squared）**：模型用这些 Factor levels 能解释多少涨幅的变化。'
                 '0 = 完全没有解释力，1 = 完美预测。'
                 '通常低于 0.1 说明这些因子单独来看解释力有限（但不代表没用，'
                 '它们仍可作为筛选信号）\n')

    imp = results['importance']

    lines.append('### 4.1 DecisionTree (max_depth=4)\n')
    lines.append(f"R-squared: {_fmt(imp['dt_score'])}\n")
    lines.append(_df_to_md_table(imp['dt_importance']))
    lines.append('')

    lines.append('### 4.2 RandomForest (n_estimators=100, max_depth=4)\n')
    lines.append(f"R-squared: {_fmt(imp['rf_score'])}\n")
    lines.append(_df_to_md_table(imp['rf_importance']))
    lines.append('')

    # 5. 因子间相关性分析
    if 'factor_correlation' in results:
        lines.append('## 5. Factor Correlation Analysis\n')
        lines.append('> **目的**：检查因子之间的统计关联性，识别信息高度重叠的因子对（可能冗余）。\n'
                     '>\n'
                     '> - **Spearman 相关系数**衡量两个因子之间的单调关系，范围 -1 到 1\n'
                     '> - |r| > 0.7：高度相关，很可能冗余（保留区分力更强的一个即可）\n'
                     '> - |r| 0.5~0.7：中度相关，需关注是否提供增量信息\n'
                     '> - |r| < 0.3：低相关，信息维度独立\n'
                     '> - 注意：与第 3 章交互效应不同——相关性度量的是因子之间的统计关联，'
                     '交互效应度量的是因子组合对收益率的联合影响\n')

        lines.append('### 5.1 Correlation Matrix\n')
        corr_matrix = results['factor_correlation']['matrix']
        if not corr_matrix.empty:
            fmt_matrix = corr_matrix.map(lambda x: _fmt(x, 3) if not pd.isna(x) else '-')
            lines.append(_df_to_md_table(
                fmt_matrix.reset_index().rename(columns={'index': 'Factor'}), float_fmt=3))
        else:
            lines.append('*No data*\n')
        lines.append('')

        lines.append('### 5.2 Top Correlated Pairs\n')
        lines.append('> 按 |r| 降序排列的因子对，带显著性标记。\n')
        top_pairs = results['factor_correlation']['top_pairs']
        if not top_pairs.empty:
            display_pairs = top_pairs.head(15).copy()
            display_pairs['significance'] = display_pairs['p_value'].apply(_significance_stars)
            lines.append(_df_to_md_table(display_pairs))
        else:
            lines.append('*No data*\n')
        lines.append('')

    # 6. 挖掘阈值画像（仅在有阈值数据时输出）
    if 'threshold_profile' in results:
        profile = results['threshold_profile']['profile']
        lines.append('## 6. Mined Threshold Profile\n')
        lines.append('> **目的**：展示每个因子被挖掘到的最优阈值处于原始数据分布中的什么位置，'
                     '以及该阈值对应的激活率（有多少样本满足条件）。\n'
                     '>\n'
                     '> - **threshold**：挖掘到的最优阈值\n'
                     '> - **direction**：触发方向（gte = 大于等于阈值才算触发，lte = 小于等于）\n'
                     '> - **percentile**：严格低于阈值的样本占比'
                     '（例如 75.0 表示 75% 的样本严格小于此阈值）\n'
                     '> - **activation_rate**：满足阈值条件的样本占比\n')
        if not profile.empty:
            lines.append(_df_to_md_table(profile))
        else:
            lines.append('*No threshold data available.*\n')
        lines.append('')

    # 7. 关键发现与结论
    lines.append('## 7. Key Findings\n')
    lines.append('> 以下是算法从上述分析中自动提取的要点摘要。\n')

    findings = _extract_key_findings(results)
    for i, finding in enumerate(findings, 1):
        lines.append(f"{i}. {finding}")
    lines.append('')

    content = '\n'.join(lines)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[Report] Written to {output_path}")

    return content
