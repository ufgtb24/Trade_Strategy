"""
测试凸点质量纳入突破评分的改进效果

对比改进前后的突破质量评分变化
"""

import pickle
import sys
sys.path.insert(0, '/')

from BreakthroughStrategy.analysis import PeakDetector, BreakoutDetector, QualityScorer

# 加载数据
df = pickle.load(open('../../../datasets/process_pkls/AAPL.pkl', 'rb'))

# 识别凸点和突破
peak_detector = PeakDetector()
peaks = peak_detector.detect_peaks(df, symbol='AAPL')

breakout_detector = BreakoutDetector()
breakthroughs = breakout_detector.detect_breakthroughs(df, peaks)

# 先对凸点评分
scorer = QualityScorer()
scorer.score_peaks_batch(peaks)

print('='*80)
print('凸点质量纳入突破评分 - 改进效果测试')
print('='*80)
print()

# 模拟改进前的评分（不考虑凸点质量）
print('[改进前] 使用旧权重评分（不考虑凸点质量）')
old_scorer = QualityScorer(config={
    'bt_weight_change': 0.25,
    'bt_weight_gap': 0.15,
    'bt_weight_volume': 0.25,
    'bt_weight_continuity': 0.20,
    'bt_weight_stability': 0.15,
    'bt_weight_peak_quality': 0.00  # 旧版本：凸点质量不参与评分
})

old_scores = []
for bt in breakthroughs:
    old_score = old_scorer.score_breakthrough(bt)
    old_scores.append((bt, old_score))

# 改进后的评分（考虑凸点质量）
print('[改进后] 使用新权重评分（考虑凸点质量）')
new_scorer = QualityScorer()  # 使用默认权重（包含凸点质量）

new_scores = []
for bt in breakthroughs:
    new_score = new_scorer.score_breakthrough(bt)
    new_scores.append((bt, new_score))

print()
print('='*80)
print('评分对比（按改进后分数排序，显示前10个）')
print('='*80)
print()

# 按新分数排序
sorted_results = sorted(zip(old_scores, new_scores), key=lambda x: x[1][1], reverse=True)

for i, ((bt_old, old_score), (bt_new, new_score)) in enumerate(sorted_results[:10], 1):
    score_change = new_score - old_score
    change_symbol = '↑' if score_change > 0 else '↓' if score_change < 0 else '='

    print(f'[{i}] {bt_new.date}')
    print(f'    突破价格: ${bt_new.price:.2f}')
    print(f'    突破类型: {bt_new.breakthrough_type}, 涨幅: {bt_new.price_change_pct*100:.2f}%')
    print(f'    凸点质量: {bt_new.peak.quality_score:.1f}/100')
    print(f'    ---')
    print(f'    改进前评分: {old_score:.1f}/100')
    print(f'    改进后评分: {new_score:.1f}/100')
    print(f'    分数变化: {change_symbol} {abs(score_change):.1f}分')
    print()

# 统计分析
print('='*80)
print('统计分析')
print('='*80)
print()

old_scores_only = [score for _, score in old_scores]
new_scores_only = [score for _, score in new_scores]

print(f'改进前:')
print(f'  平均分: {sum(old_scores_only)/len(old_scores_only):.1f}')
print(f'  最高分: {max(old_scores_only):.1f}')
print(f'  最低分: {min(old_scores_only):.1f}')
print()

print(f'改进后:')
print(f'  平均分: {sum(new_scores_only)/len(new_scores_only):.1f}')
print(f'  最高分: {max(new_scores_only):.1f}')
print(f'  最低分: {min(new_scores_only):.1f}')
print()

# 分析高质量凸点的突破是否得到更高评分
high_quality_peaks = [bt for bt in breakthroughs if bt.peak.quality_score > 50]
low_quality_peaks = [bt for bt in breakthroughs if bt.peak.quality_score <= 50]

if high_quality_peaks:
    high_peak_old_avg = sum(old_scorer.score_breakthrough(bt) for bt in high_quality_peaks) / len(high_quality_peaks)
    high_peak_new_avg = sum(new_scorer.score_breakthrough(bt) for bt in high_quality_peaks) / len(high_quality_peaks)

    print(f'高质量凸点突破（凸点质量>50分，共{len(high_quality_peaks)}个）:')
    print(f'  改进前平均分: {high_peak_old_avg:.1f}')
    print(f'  改进后平均分: {high_peak_new_avg:.1f}')
    print(f'  平均提升: +{high_peak_new_avg - high_peak_old_avg:.1f}分')
    print()

if low_quality_peaks:
    low_peak_old_avg = sum(old_scorer.score_breakthrough(bt) for bt in low_quality_peaks) / len(low_quality_peaks)
    low_peak_new_avg = sum(new_scorer.score_breakthrough(bt) for bt in low_quality_peaks) / len(low_quality_peaks)

    print(f'低质量凸点突破（凸点质量≤50分，共{len(low_quality_peaks)}个）:')
    print(f'  改进前平均分: {low_peak_old_avg:.1f}')
    print(f'  改进后平均分: {low_peak_new_avg:.1f}')
    print(f'  平均变化: {low_peak_new_avg - low_peak_old_avg:+.1f}分')
    print()

print('='*80)
print('✓ 改进验证完成！')
print()
print('预期结果：')
print('- 高质量凸点的突破得分提升')
print('- 低质量凸点的突破得分降低或保持')
print('- 评分更合理地反映突破的实际意义')
print('='*80)
