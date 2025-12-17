"""
Daily Pool 阶段转换诊断脚本

诊断信号漏斗中的瓶颈，分析失败原因分布，提供参数优化建议。

使用方法：
    python scripts/analysis/diagnose_daily_pool.py

输出：
    - 控制台输出诊断报告
    - 可选：保存详细报告到 outputs/diagnostics/
"""
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class TransitionRecord:
    """解析后的单条转换记录"""
    symbol: str
    entry_id: str
    date: str
    from_phase: str
    to_phase: str
    reason: str
    parsed_values: Dict[str, float] = field(default_factory=dict)


@dataclass
class FunnelStage:
    """漏斗阶段统计"""
    phase: str
    total_entries: int
    transitions: Dict[str, int]  # to_phase -> count

    @property
    def success_rate(self) -> float:
        """计算成功转换率（非终态）"""
        terminal = {'FAILED', 'EXPIRED', 'SIGNAL'}
        success_count = sum(c for p, c in self.transitions.items() if p not in terminal)
        return success_count / self.total_entries if self.total_entries > 0 else 0.0

    @property
    def failure_rate(self) -> float:
        """计算失败率"""
        fail_count = self.transitions.get('FAILED', 0) + self.transitions.get('EXPIRED', 0)
        return fail_count / self.total_entries if self.total_entries > 0 else 0.0


@dataclass
class FailurePattern:
    """失败模式分析"""
    transition_key: str  # e.g., "PULLBACK->FAILED"
    total_count: int
    reason_patterns: Dict[str, int]  # 原因模式 -> 计数
    value_distributions: Dict[str, List[float]]  # 变量名 -> 值列表


@dataclass
class ThresholdAnalysis:
    """阈值边界分析"""
    variable: str
    current_threshold: float
    values: List[float]
    percentiles: Dict[str, float]
    near_misses: List[Tuple[str, float]]  # (entry_id, value)
    impact_analysis: Dict[float, int]  # 新阈值 -> 可挽救数量


# =============================================================================
# 数据加载
# =============================================================================

def load_transitions_from_json(filepath: str) -> List[TransitionRecord]:
    """从 JSON 文件加载转换记录"""
    with open(filepath, 'r') as f:
        data = json.load(f)

    records = []
    for item in data:
        record = TransitionRecord(
            symbol=item['symbol'],
            entry_id=item['entry_id'],
            date=item['date'],
            from_phase=item['from_phase'],
            to_phase=item['to_phase'],
            reason=item['reason'],
            parsed_values=parse_reason_values(item['reason'])
        )
        records.append(record)

    return records


def load_stats_from_json(filepath: str) -> Dict[str, Any]:
    """从统计 JSON 加载配置和统计摘要"""
    with open(filepath, 'r') as f:
        return json.load(f)


def parse_reason_values(reason: str) -> Dict[str, float]:
    """
    从 reason 字符串解析数值

    示例:
        "Pullback too deep: 2.40 ATR > 1.5 ATR limit"
        -> {"actual": 2.40, "threshold": 1.5}

        "Entering pullback: depth=0.35 ATR >= 0.3 ATR trigger"
        -> {"depth": 0.35, "trigger": 0.3}

        "Entering consolidation: convergence=0.53 >= 0.5, support_tests=11 >= 2"
        -> {"convergence": 0.53, "convergence_threshold": 0.5,
            "support_tests": 11, "support_tests_threshold": 2}
    """
    values = {}

    # Pattern: "X.XX ATR > Y.YY ATR limit" (失败原因)
    match = re.search(r'(\d+\.?\d*) ATR > (\d+\.?\d*) ATR limit', reason)
    if match:
        values['actual'] = float(match.group(1))
        values['threshold'] = float(match.group(2))

    # Pattern: "depth=X.XX ATR >= Y.YY ATR trigger" (进入回调)
    match = re.search(r'depth=(\d+\.?\d*) ATR >= (\d+\.?\d*) ATR', reason)
    if match:
        values['depth'] = float(match.group(1))
        values['trigger'] = float(match.group(2))

    # Pattern: "convergence=X.XX >= Y.YY" (收敛分数)
    match = re.search(r'convergence=(\d+\.?\d*) >= (\d+\.?\d*)', reason)
    if match:
        values['convergence'] = float(match.group(1))
        values['convergence_threshold'] = float(match.group(2))

    # Pattern: "support_tests=X >= Y" (支撑测试)
    match = re.search(r'support_tests=(\d+) >= (\d+)', reason)
    if match:
        values['support_tests'] = int(match.group(1))
        values['support_tests_threshold'] = int(match.group(2))

    # Pattern: "volume=X.Xx >= Y.Yx" (放量)
    match = re.search(r'volume=(\d+\.?\d*)x >= (\d+\.?\d*)x', reason)
    if match:
        values['volume'] = float(match.group(1))
        values['volume_threshold'] = float(match.group(2))

    # Pattern: "after X days" (过期天数)
    match = re.search(r'after (\d+) days', reason)
    if match:
        values['days'] = int(match.group(1))

    return values


# =============================================================================
# 漏斗分析
# =============================================================================

def build_funnel(transitions: List[TransitionRecord]) -> Dict[str, FunnelStage]:
    """构建阶段转换漏斗"""
    # 统计每个阶段的入口数和出口分布
    phase_transitions = defaultdict(lambda: defaultdict(int))

    for record in transitions:
        phase_transitions[record.from_phase][record.to_phase] += 1

    # 构建漏斗
    funnel = {}
    for phase, trans in phase_transitions.items():
        total = sum(trans.values())
        funnel[phase] = FunnelStage(
            phase=phase,
            total_entries=total,
            transitions=dict(trans)
        )

    return funnel


def format_funnel_diagram(funnel: Dict[str, FunnelStage], total_entries: int = 0) -> str:
    """生成可视化漏斗图"""
    lines = []
    lines.append("=" * 70)
    lines.append("              Daily Pool Phase Transition Funnel")
    lines.append("=" * 70)

    if total_entries > 0:
        signal_count = funnel.get('REIGNITION', FunnelStage('', 0, {})).transitions.get('SIGNAL', 0)
        lines.append(f"\nTotal Entries: {total_entries} | Signals: {signal_count} ({signal_count/total_entries*100:.1f}%)")

    lines.append("")

    phase_order = ['INITIAL', 'PULLBACK', 'CONSOLIDATION', 'REIGNITION']

    for phase in phase_order:
        if phase not in funnel:
            continue

        stage = funnel[phase]
        trans_list = sorted(stage.transitions.items(), key=lambda x: -x[1])

        # 格式化该阶段
        header = f"{phase} ({stage.total_entries})"

        for i, (to_phase, count) in enumerate(trans_list):
            pct = count / stage.total_entries * 100 if stage.total_entries > 0 else 0
            connector = "─┬→" if i == 0 else " ├→" if i < len(trans_list) - 1 else " └→"

            # 标记瓶颈
            marker = ""
            if to_phase == 'FAILED' and pct > 50:
                marker = "  ← 最大瓶颈!" if pct > 70 else "  ← 瓶颈"
            elif to_phase == 'SIGNAL':
                marker = "  ✓"
            elif to_phase == 'EXPIRED' and pct > 30:
                marker = "  ← 过期"

            if i == 0:
                lines.append(f"{header} {connector} {to_phase} ({count}, {pct:.1f}%){marker}")
            else:
                lines.append(f"{' ' * len(header)} {connector} {to_phase} ({count}, {pct:.1f}%){marker}")

        lines.append("")

    return '\n'.join(lines)


# =============================================================================
# 失败分析
# =============================================================================

def analyze_failure_patterns(transitions: List[TransitionRecord]) -> List[FailurePattern]:
    """分析失败模式"""
    # 按转换类型分组
    failure_groups = defaultdict(list)

    for record in transitions:
        if record.to_phase in ('FAILED', 'EXPIRED'):
            key = f"{record.from_phase}->{record.to_phase}"
            failure_groups[key].append(record)

    patterns = []
    for key, records in failure_groups.items():
        # 统计原因模式
        reason_counts = defaultdict(int)
        value_lists = defaultdict(list)

        for r in records:
            # 简化原因（去掉具体数值）
            simplified = re.sub(r'\d+\.?\d*', 'X', r.reason)
            reason_counts[simplified] += 1

            # 收集数值
            if 'actual' in r.parsed_values:
                value_lists['actual_pullback'].append(r.parsed_values['actual'])

        patterns.append(FailurePattern(
            transition_key=key,
            total_count=len(records),
            reason_patterns=dict(reason_counts),
            value_distributions=dict(value_lists)
        ))

    # 按数量排序
    patterns.sort(key=lambda x: -x.total_count)
    return patterns


def format_failure_analysis(patterns: List[FailurePattern]) -> str:
    """格式化失败分析报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("                    Failure Pattern Analysis")
    lines.append("=" * 70)

    for pattern in patterns:
        lines.append(f"\n=== {pattern.transition_key} ({pattern.total_count} cases) ===")
        lines.append("\n失败原因分布:")

        for reason, count in sorted(pattern.reason_patterns.items(), key=lambda x: -x[1]):
            pct = count / pattern.total_count * 100
            lines.append(f"  [{pct:5.1f}%] {reason}")

        # 数值分布
        if 'actual_pullback' in pattern.value_distributions:
            values = pattern.value_distributions['actual_pullback']
            if values:
                lines.append(f"\n回调深度分布 (n={len(values)}):")
                lines.append(f"  ├─ Min:  {min(values):.2f} ATR")
                lines.append(f"  ├─ P25:  {np.percentile(values, 25):.2f} ATR")
                lines.append(f"  ├─ P50:  {np.percentile(values, 50):.2f} ATR (中位数)")
                lines.append(f"  ├─ P75:  {np.percentile(values, 75):.2f} ATR")
                lines.append(f"  └─ Max:  {max(values):.2f} ATR")

    return '\n'.join(lines)


# =============================================================================
# 阈值分析
# =============================================================================

def analyze_thresholds(
    transitions: List[TransitionRecord],
    current_thresholds: Dict[str, float]
) -> List[ThresholdAnalysis]:
    """分析关键阈值的影响"""
    analyses = []

    # 1. 分析 max_drop_from_breakout_atr
    pullback_failures = [
        r for r in transitions
        if r.to_phase == 'FAILED' and 'actual' in r.parsed_values
    ]

    if pullback_failures:
        values = [r.parsed_values['actual'] for r in pullback_failures]
        current = current_thresholds.get('max_drop_from_breakout_atr', 1.5)

        # 边界案例（超出不超过 0.5 ATR）
        near_misses = [
            (r.entry_id, r.parsed_values['actual'])
            for r in pullback_failures
            if r.parsed_values['actual'] <= current + 0.5
        ]
        near_misses.sort(key=lambda x: x[1])

        # 影响分析：不同阈值能挽救多少
        impact = {}
        for new_threshold in [1.8, 2.0, 2.5, 3.0]:
            saved = sum(1 for v in values if v <= new_threshold)
            impact[new_threshold] = saved

        analyses.append(ThresholdAnalysis(
            variable='max_drop_from_breakout_atr',
            current_threshold=current,
            values=values,
            percentiles={
                'P25': np.percentile(values, 25),
                'P50': np.percentile(values, 50),
                'P75': np.percentile(values, 75),
                'P90': np.percentile(values, 90),
            },
            near_misses=near_misses[:10],  # 只取前10个
            impact_analysis=impact
        ))

    return analyses


def format_threshold_analysis(analyses: List[ThresholdAnalysis]) -> str:
    """格式化阈值分析报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("                    Threshold Impact Analysis")
    lines.append("=" * 70)

    for analysis in analyses:
        lines.append(f"\n=== {analysis.variable} (当前: {analysis.current_threshold}) ===")

        lines.append(f"\n失败案例值分布 (n={len(analysis.values)}):")
        for name, val in analysis.percentiles.items():
            lines.append(f"  ├─ {name}: {val:.2f} ATR")

        lines.append(f"\n假设放宽阈值的影响:")
        lines.append(f"  ┌─────────┬───────────────┬────────────┐")
        lines.append(f"  │ 新阈值  │ 可挽救数量    │ 占比       │")
        lines.append(f"  ├─────────┼───────────────┼────────────┤")
        for threshold, count in sorted(analysis.impact_analysis.items()):
            pct = count / len(analysis.values) * 100 if analysis.values else 0
            lines.append(f"  │ {threshold:.1f} ATR │ {count:>6} cases  │ {pct:>6.1f}%    │")
        lines.append(f"  └─────────┴───────────────┴────────────┘")

        if analysis.near_misses:
            lines.append(f"\n边界案例 ({analysis.current_threshold} < depth <= {analysis.current_threshold + 0.3} ATR):")
            for entry_id, val in analysis.near_misses[:5]:
                diff = val - analysis.current_threshold
                lines.append(f"  • {entry_id}: {val:.2f} ATR (超出 {diff:.2f})")
            if len(analysis.near_misses) > 5:
                lines.append(f"  ... 共 {len(analysis.near_misses)} 个边界案例")

    return '\n'.join(lines)


# =============================================================================
# 参数建议
# =============================================================================

def generate_suggestions(
    funnel: Dict[str, FunnelStage],
    failure_patterns: List[FailurePattern],
    threshold_analyses: List[ThresholdAnalysis]
) -> str:
    """生成参数优化建议"""
    lines = []
    lines.append("=" * 70)
    lines.append("                  Parameter Optimization Suggestions")
    lines.append("=" * 70)

    # 找到最大的阈值分析
    for analysis in threshold_analyses:
        if analysis.variable == 'max_drop_from_breakout_atr':
            # 找到能挽救最多案例的合理阈值
            best_threshold = None
            best_saved = 0
            for threshold, saved in analysis.impact_analysis.items():
                if threshold <= 2.5 and saved > best_saved:  # 限制在合理范围
                    best_threshold = threshold
                    best_saved = saved

            total_failures = len(analysis.values)
            pct = best_saved / total_failures * 100 if total_failures > 0 else 0

            lines.append(f"""
┌─────────────────────────────────────────────────────────────────┐
│ 1. max_drop_from_breakout_atr                                   │
├─────────────────────────────────────────────────────────────────┤
│ 当前值: {analysis.current_threshold} ATR                                                  │
│ 建议值: {best_threshold} ATR                                                  │
│                                                                 │
│ 理由:                                                           │
│ - {total_failures} 个失败案例中，{pct:.0f}% 的回调深度 <= {best_threshold} ATR             │
│ - 放宽到 {best_threshold} 可挽救 {best_saved} 个案例                              │
│ - 当前 P50={analysis.percentiles['P50']:.2f} ATR，说明多数失败仅略超阈值              │
│                                                                 │
│ 风险:                                                           │
│ - 可能引入更多真正失败的"死猫跳"                                │
│ - 建议配合更严格的企稳条件验证                                  │
└─────────────────────────────────────────────────────────────────┘
""")

    # 下一步建议
    lines.append("""
┌─────────────────────────────────────────────────────────────────┐
│ 下一步验证                                                      │
├─────────────────────────────────────────────────────────────────┤
│ 1. 使用 aggressive 配置重新回测:                                │
│    config = DailyPoolConfig.aggressive()                        │
│    # max_drop_from_breakout_atr = 2.0                           │
│                                                                 │
│ 2. 对比信号率变化和信号质量                                     │
│                                                                 │
│ 3. 如需更细粒度调参，修改 configs/daily_pool/default.yaml       │
└─────────────────────────────────────────────────────────────────┘
""")

    return '\n'.join(lines)


# =============================================================================
# 主入口
# =============================================================================

def diagnose(
    transitions_file: str,
    stats_file: Optional[str] = None,
    output_file: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    诊断 Daily Pool 阶段转换

    Args:
        transitions_file: 转换记录 JSON 路径
        stats_file: 统计摘要 JSON 路径（可选）
        output_file: 输出报告路径（可选）
        verbose: 是否打印详细输出

    Returns:
        诊断结果字典
    """
    # 1. 加载数据
    transitions = load_transitions_from_json(transitions_file)

    stats = None
    if stats_file and Path(stats_file).exists():
        stats = load_stats_from_json(stats_file)

    # 获取当前配置阈值
    current_thresholds = {
        'max_drop_from_breakout_atr': 1.5,
        'min_convergence_score': 0.5,
        'min_support_tests': 2,
        'min_volume_expansion': 1.5,
    }
    if stats and 'config' in stats:
        current_thresholds.update(stats['config'])

    # 2. 构建漏斗
    funnel = build_funnel(transitions)
    total_entries = stats['statistics']['total_entries'] if stats else sum(f.total_entries for f in funnel.values())

    # 3. 分析失败模式
    failure_patterns = analyze_failure_patterns(transitions)

    # 4. 分析阈值影响
    threshold_analyses = analyze_thresholds(transitions, current_thresholds)

    # 5. 生成报告
    report_parts = []

    # 漏斗图
    funnel_report = format_funnel_diagram(funnel, total_entries)
    report_parts.append(funnel_report)

    # 失败分析
    failure_report = format_failure_analysis(failure_patterns)
    report_parts.append(failure_report)

    # 阈值分析
    threshold_report = format_threshold_analysis(threshold_analyses)
    report_parts.append(threshold_report)

    # 参数建议
    suggestions = generate_suggestions(funnel, failure_patterns, threshold_analyses)
    report_parts.append(suggestions)

    full_report = '\n\n'.join(report_parts)

    if verbose:
        print(full_report)

    # 6. 保存报告
    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(full_report)
        if verbose:
            print(f"\n报告已保存到: {output_file}")

    return {
        'funnel': funnel,
        'failure_patterns': failure_patterns,
        'threshold_analyses': threshold_analyses,
        'total_entries': total_entries,
        'report': full_report
    }


def main():
    """主入口，参数声明在函数起始位置"""
    # ===== 配置参数 =====
    # 输入数据（使用最新的回测结果）
    transitions_file = 'outputs/backtest/daily/daily_transitions_2024-01-01_2024-06-30.json'
    stats_file = 'outputs/backtest/daily/daily_stats_2024-01-01_2024-06-30.json'

    # 输出配置
    save_report = True
    output_dir = 'outputs/diagnostics'

    # ===== 执行诊断 =====
    print("\n" + "=" * 70)
    print("           Daily Pool Phase Transition Diagnostic Tool")
    print("=" * 70 + "\n")

    output_file = f"{output_dir}/diagnosis_report.txt" if save_report else None

    result = diagnose(
        transitions_file=transitions_file,
        stats_file=stats_file,
        output_file=output_file,
        verbose=True
    )

    return result


if __name__ == '__main__':
    main()
