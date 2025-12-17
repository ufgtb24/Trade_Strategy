# AI 辅助 Daily Pool 逻辑优化工作流 (v2)

> 基于消融实验方法论，系统性简化 Daily Pool 分析器逻辑
>
> 核心原则：**先逻辑后参数**，使用**等效初始参数**保证比较纯粹性

---

## 工作流总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Phase 0: 准备阶段                                │
│  [人类] 数据划分 + [AI] 复杂度分析 + [人类] 确认简化候选                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Phase 1: 等效参数计算                               │
│  [AI] 开发计算脚本 + [人类] 运行脚本 + [人类] 审核结果                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Phase 2: 消融实验执行                               │
│  [AI] 实现简化逻辑 + [人类] 运行回测 + [AI] 生成对比报告                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Phase 3: 逻辑决策                                   │
│  [人类] 解读报告 + [人类] 决定采用哪些简化                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Phase 4: 参数优化（可选）                            │
│  [AI] 开发调参脚本 + [人类] 运行优化 + [人类] 验证结果                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Phase 5: 最终验证与合并                              │
│  [人类] 测试集验证 + [人类] 代码合并                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: 准备阶段

### Step 0.1 数据划分 [人类]

**目的**：划分 train/valid/test 数据集，避免过拟合

**操作**：
```bash
# 确认数据范围
ls datasets/pkls/ | head -5

# 建议划分（根据实际数据调整）：
# - 训练集: 2023-01-01 ~ 2024-06-30 (用于等效参数计算、消融实验)
# - 验证集: 2024-07-01 ~ 2024-12-31 (用于参数优化)
# - 测试集: 2025-01-01 ~ 至今 (最终验证，仅看一次)
```

**输出**：在配置文件或笔记中记录划分方案

---

### Step 0.2 复杂度分析 [AI]

**目的**：识别 Daily Pool 中过于复杂的逻辑

**AI 提示词**：
```
分析 Daily Pool 分析器的代码复杂度，标记可疑的过拟合逻辑。

请分析以下文件：
- BreakoutStrategy/daily_pool/analyzers/price_pattern.py
- BreakoutStrategy/daily_pool/analyzers/volatility.py
- BreakoutStrategy/daily_pool/analyzers/volume.py

对每个文件：
1. 运行 radon cc 获取圈复杂度
2. 找出复杂度 > 10 的方法
3. 标记包含"魔法数字"（硬编码权重/阈值）的公式
4. 判断该复杂性是"本质复杂性"还是"过拟合复杂性"

输出格式：
| 文件 | 方法 | 复杂度 | 可疑逻辑 | 简化建议 |
```

**输出**：复杂度分析报告，列出简化候选

---

### Step 0.3 确认简化候选 [人类]

**目的**：审核 AI 的分析，确定要进行消融实验的逻辑

**操作**：
1. 阅读 AI 的复杂度分析报告
2. 根据业务理解，确认哪些逻辑值得简化
3. 为每个候选定义简化方案

**预期的简化候选**：
```
A1: PricePatternAnalyzer._calculate_support_strength
    原始: strength = 0.4*(count/5) + 0.3*(span/15) + 0.3*bounce
    简化: strength = 1.0 if count >= T else 0.0

A2: VolatilityAnalyzer._calculate_convergence_score
    原始: score = slope_score*0.5 + ratio_score*0.3 + stability_score*0.2
    简化: score = 1.0 if atr_ratio <= T else 0.0

A3: VolumeAnalyzer._determine_volume_trend
    原始: 比较 MA5 vs MA20，判断 increasing/decreasing/neutral
    简化: 移除趋势判断，只保留 surge_detected

A4: 组合简化 (A1 + A2 + A3)
```

**输出**：确认的简化方案列表

---

## Phase 1: 等效参数计算

### Step 1.1 开发等效参数计算脚本 [AI]

**目的**：创建脚本计算各简化逻辑的等效初始参数

**AI 提示词**：
```
创建脚本 scripts/analysis/calculate_equivalent_params.py

功能：
1. 加载训练集数据，运行 Baseline 逻辑
2. 统计各分析器的输出分布（support_strength, convergence_score 等）
3. 对每个简化逻辑，计算使其通过率匹配原逻辑的参数

具体计算方法：
- A1 (支撑强度): 统计 original_strength >= 0.5 的比例 P，
  找 T 使 count >= T 的比例 ≈ P
- A2 (收敛分数): 统计 original_score >= min_convergence_score 的比例 P，
  找 T 使 atr_ratio <= T 的比例 ≈ P
- A3 (成交量): 不需要参数，直接移除 trend 逻辑

输入：
- 训练集时间范围 (命令行参数或配置)
- 数据目录路径

输出：
- 控制台打印各简化逻辑的等效参数
- 保存到 outputs/ablation/equivalent_params.json

参考现有脚本风格：scripts/analysis/diagnose_daily_pool.py
```

**输出**：`scripts/analysis/calculate_equivalent_params.py`

---

### Step 1.2 运行等效参数计算 [人类]

**操作**：
```bash
# 运行脚本（待开发）
uv run python scripts/analysis/calculate_equivalent_params.py \
    --start-date 2023-01-01 \
    --end-date 2024-06-30 \
    --data-dir datasets/pkls

# 预期输出示例：
# ===== Equivalent Parameters =====
# A1 (support_strength): count >= 3 (match rate: 42% vs 41%)
# A2 (convergence_score): atr_ratio <= 0.85 (match rate: 38% vs 39%)
# A3 (volume_trend): N/A (boolean simplification)
# Saved to: outputs/ablation/equivalent_params.json
```

**输出**：`outputs/ablation/equivalent_params.json`

---

### Step 1.3 审核等效参数 [人类]

**操作**：
1. 检查各简化逻辑的等效参数是否合理
2. 确认通过率匹配度（差异应 < 5%）
3. 如有问题，调整后重新运行

---

## Phase 2: 消融实验执行

### Step 2.1 创建实验分支 [人类]

**操作**：
```bash
# 从当前分支创建实验分支
git checkout -b analysis/ablation-v1

# 确保工作区干净
git status
```

---

### Step 2.2 实现简化逻辑变体 [AI]

**目的**：在分析器中实现可切换的简化逻辑

**AI 提示词**：
```
为 Daily Pool 分析器实现简化逻辑变体，支持通过配置切换。

修改文件：
1. BreakoutStrategy/daily_pool/config/config.py
   - 添加 ablation_mode 字段: Literal["baseline", "A1", "A2", "A3", "A4"]
   - 添加对应的等效参数字段

2. BreakoutStrategy/daily_pool/analyzers/price_pattern.py
   - 在 _calculate_support_strength 中添加简化分支
   - if config.ablation_mode in ("A1", "A4"):
         return 1.0 if count >= config.a1_count_threshold else 0.0

3. BreakoutStrategy/daily_pool/analyzers/volatility.py
   - 在 _calculate_convergence_score 中添加简化分支
   - if config.ablation_mode in ("A2", "A4"):
         return 1.0 if atr_ratio <= config.a2_atr_threshold else 0.0

4. BreakoutStrategy/daily_pool/analyzers/volume.py
   - 在 _determine_volume_trend 中添加简化分支
   - if config.ablation_mode in ("A3", "A4"):
         return "neutral"  # 跳过趋势判断

设计要求：
- 保持原有逻辑不变（ablation_mode="baseline"）
- 简化逻辑通过配置开关控制
- 代码改动最小化，便于后续清理

使用等效参数：
（从 outputs/ablation/equivalent_params.json 读取）
```

**输出**：修改后的分析器代码

---

### Step 2.3 运行消融实验回测 [人类]

**操作**：
```bash
# 创建 5 个配置文件（待开发/手动创建）
# configs/daily_pool/ablation_baseline.yaml
# configs/daily_pool/ablation_A1.yaml
# configs/daily_pool/ablation_A2.yaml
# configs/daily_pool/ablation_A3.yaml
# configs/daily_pool/ablation_A4.yaml

# 运行 5 组回测
for mode in baseline A1 A2 A3 A4; do
    echo "Running ablation: $mode"
    uv run python scripts/backtest/daily_pool_backtest.py \
        --config configs/daily_pool/ablation_${mode}.yaml \
        --start-date 2023-01-01 \
        --end-date 2024-06-30 \
        --output-dir outputs/ablation/${mode}
done

# 运行诊断和质量评估
for mode in baseline A1 A2 A3 A4; do
    echo "Evaluating: $mode"

    # 漏斗诊断
    uv run python scripts/analysis/diagnose_daily_pool.py \
        --transitions outputs/ablation/${mode}/daily_transitions_*.json \
        --output outputs/ablation/${mode}/diagnosis.txt

    # 信号质量评估
    uv run python scripts/analysis/signal_quality_evaluator.py \
        --signals outputs/ablation/${mode}/daily_signals_*.json \
        --output outputs/ablation/${mode}/quality_report.json
done
```

**输出**：每个变体的回测结果、诊断报告、质量报告

---

### Step 2.4 生成消融对比报告 [AI]

**目的**：汇总 5 组实验结果，生成可读的对比报告

**AI 提示词**：
```
创建脚本 scripts/analysis/ablation_comparison_report.py

功能：
1. 读取 5 组实验的结果：
   - outputs/ablation/{baseline,A1,A2,A3,A4}/quality_report.json
   - outputs/ablation/{baseline,A1,A2,A3,A4}/diagnosis.txt

2. 计算相对变化：
   - signal_rate_change = (variant - baseline) / baseline * 100%
   - mfe_mean_change = (variant - baseline) / baseline * 100%
   - mae_mean_change = ...
   - composite_score_change = ...

3. 添加统计显著性检验：
   - 使用 Welch's t-test 比较 MFE 分布
   - 输出 p-value 和置信区间
   - 标记是否显著 (p < 0.05)

4. 生成报告，包含：
   - 汇总表格（各变体 vs Baseline）
   - 漏斗对比图（ASCII 或建议可视化）
   - 统计显著性结论
   - 简化建议

输出格式示例：
======================================
     Ablation Experiment Summary
======================================

| Variant | Signal Rate | MFE Mean | MAE Mean | Score  | Significant? |
|---------|-------------|----------|----------|--------|--------------|
| Baseline| 3.2%        | 15.3%    | 6.2%     | 12.1   | -            |
| A1      | 4.1% (+28%) | 14.1%(-8%)| 6.8%    | 10.8   | Yes (p=0.03) |
| A2      | 3.0% (-6%)  | 16.0%(+5%)| 5.9%    | 13.2   | No (p=0.42)  |
| A3      | 3.3% (+3%)  | 15.5%(+1%)| 6.1%    | 12.4   | No (p=0.78)  |
| A4      | 4.5% (+41%) | 12.8%(-16%)| 7.2%   | 9.5    | Yes (p=0.01) |

======================================
     Recommendation
======================================
- A3 (移除成交量趋势): 可采用 (性能无显著变化)
- A2 (简化收敛分数): 可采用 (性能略有提升，但不显著)
- A1 (简化支撑强度): 谨慎 (性能显著下降 8%)
- A4 (全部简化): 不推荐 (性能显著下降 16%)
```

**输出**：`scripts/analysis/ablation_comparison_report.py`

---

### Step 2.5 运行对比报告生成 [人类]

**操作**：
```bash
# 运行对比报告脚本（待开发）
uv run python scripts/analysis/ablation_comparison_report.py \
    --results-dir outputs/ablation \
    --output outputs/ablation/comparison_report.txt

# 查看报告
cat outputs/ablation/comparison_report.txt
```

**输出**：`outputs/ablation/comparison_report.txt`

---

## Phase 3: 逻辑决策

### Step 3.1 解读报告 [人类]

**操作**：
1. 阅读 `outputs/ablation/comparison_report.txt`
2. 关注以下指标：
   - 性能变化幅度（MFE、综合评分）
   - 统计显著性（p-value）
   - 信号数量变化

**决策框架**：
```
| 性能变化 | p-value | 决策 |
|---------|---------|------|
| < -5%   | < 0.05  | 保留原逻辑（显著下降） |
| < -5%   | >= 0.05 | 可考虑简化（下降不显著） |
| -5% ~ +5% | any   | 采用简化（基本等效） |
| > +5%   | < 0.05  | 采用简化（显著提升，原逻辑可能过拟合） |
```

---

### Step 3.2 记录决策 [人类]

**操作**：在 `docs/research/` 下记录决策结果

```markdown
# Daily Pool 消融实验决策记录

日期: YYYY-MM-DD

## 实验结论

| 简化方案 | 决策 | 理由 |
|---------|------|------|
| A1 (支撑强度) | 保留原逻辑 | MFE 下降 8%，p=0.03 显著 |
| A2 (收敛分数) | 采用简化 | MFE 上升 5%，p=0.42 不显著，简化无害 |
| A3 (成交量趋势) | 采用简化 | 变化 < 3%，不显著 |

## 最终采用配置

ablation_mode: "A2+A3"  # 简化收敛分数 + 移除成交量趋势
保留: 支撑强度三因素加权
```

---

## Phase 4: 参数优化（可选）

> 仅当采用了简化逻辑且需要微调参数时执行

### Step 4.1 开发参数优化脚本 [AI]

**AI 提示词**：
```
创建脚本 scripts/analysis/optimize_daily_pool_params.py

功能：
使用 Optuna 优化 Daily Pool 的关键参数

优化目标：
- 主目标: composite_score_mean (综合评分均值)
- 约束: signal_rate >= 2% (保证足够的信号数量)

优化参数（根据采用的逻辑调整）：
- a2_atr_threshold: [0.7, 0.95] (收敛分数简化阈值)
- min_support_tests: [1, 5] (最小支撑测试次数)
- max_drop_from_breakout_atr: [1.0, 2.5] (最大回调深度)

使用数据：验证集 (2024-07-01 ~ 2024-12-31)

输出：
- 最优参数组合
- 优化过程可视化 (Optuna 默认)
- 保存到 outputs/optimization/best_params.json
```

**输出**：`scripts/analysis/optimize_daily_pool_params.py`

---

### Step 4.2 运行参数优化 [人类]

**操作**：
```bash
# 运行优化（待开发）
uv run python scripts/analysis/optimize_daily_pool_params.py \
    --config configs/daily_pool/adopted_simplified.yaml \
    --start-date 2024-07-01 \
    --end-date 2024-12-31 \
    --n-trials 50 \
    --output outputs/optimization

# 查看结果
cat outputs/optimization/best_params.json
```

---

### Step 4.3 验证优化结果 [人类]

**操作**：
```bash
# 使用最优参数在验证集上运行
uv run python scripts/backtest/daily_pool_backtest.py \
    --config outputs/optimization/best_params.yaml \
    --start-date 2024-07-01 \
    --end-date 2024-12-31 \
    --output-dir outputs/optimization/validation

# 与优化前对比
uv run python scripts/analysis/signal_quality_evaluator.py \
    --signals outputs/optimization/validation/daily_signals_*.json
```

---

## Phase 5: 最终验证与合并

### Step 5.1 测试集验证 [人类]

**操作**：
```bash
# 在测试集上运行一次（仅此一次！）
uv run python scripts/backtest/daily_pool_backtest.py \
    --config configs/daily_pool/final_simplified.yaml \
    --start-date 2025-01-01 \
    --end-date 2025-12-31 \
    --output-dir outputs/final_test

# 评估
uv run python scripts/analysis/signal_quality_evaluator.py \
    --signals outputs/final_test/daily_signals_*.json

# 检查过拟合
# 对比验证集和测试集的性能差异
# 若差异 > 10%，需要重新审视
```

---

### Step 5.2 清理实验代码 [AI]

**AI 提示词**：
```
清理 Daily Pool 分析器中的消融实验代码。

根据最终决策（假设采用 A2 + A3）：
1. 移除 ablation_mode 配置开关
2. 将 A2 简化逻辑设为默认（删除原复杂逻辑）
3. 将 A3 简化逻辑设为默认（删除成交量趋势判断）
4. 保留 A1 原逻辑（支撑强度三因素加权）
5. 更新相关 docstring 和注释
6. 清理不再使用的配置字段

确保代码简洁，无残留的实验分支。
```

---

### Step 5.3 代码合并 [人类]

**操作**：
```bash
# 提交清理后的代码
git add -A
git commit -m "Simplify Daily Pool analyzers based on ablation study

- Simplify convergence_score: use atr_ratio threshold (A2)
- Remove volume_trend detection, keep only surge_detected (A3)
- Retain support_strength 3-factor weighting (proven valuable)

Based on ablation experiment results:
- A2: MFE +5% (not significant, simplification acceptable)
- A3: MFE +1% (not significant, simplification acceptable)
- A1: MFE -8% (significant, retain original logic)
"

# 合并到主分支
git checkout pure_daily
git merge analysis/ablation-v1

# 清理实验分支
git branch -d analysis/ablation-v1
```

---

## 附录 A: 待开发脚本清单

| 脚本 | 状态 | 用途 |
|------|------|------|
| `scripts/analysis/diagnose_daily_pool.py` | ✅ 已存在 | 漏斗诊断 |
| `scripts/analysis/signal_quality_evaluator.py` | ✅ 已存在 | 信号质量评估 |
| `scripts/analysis/calculate_equivalent_params.py` | ❌ 待开发 | 等效参数计算 |
| `scripts/analysis/ablation_comparison_report.py` | ❌ 待开发 | 消融对比报告 |
| `scripts/analysis/optimize_daily_pool_params.py` | ❌ 待开发 | 参数优化 |

---

## 附录 B: AI 提示词速查

### 复杂度分析
```
分析 Daily Pool 分析器的代码复杂度，标记可疑的过拟合逻辑...
```

### 等效参数脚本开发
```
创建脚本 scripts/analysis/calculate_equivalent_params.py...
```

### 简化逻辑实现
```
为 Daily Pool 分析器实现简化逻辑变体，支持通过配置切换...
```

### 对比报告生成
```
创建脚本 scripts/analysis/ablation_comparison_report.py...
```

### 参数优化脚本
```
创建脚本 scripts/analysis/optimize_daily_pool_params.py...
```

### 代码清理
```
清理 Daily Pool 分析器中的消融实验代码...
```

---

## 附录 C: 决策阈值参考

| 指标 | 阈值 | 含义 |
|------|------|------|
| 性能变化显著 | p < 0.05 | 拒绝原假设（两组无差异） |
| 性能下降可接受 | < 3% | 简化带来的效率收益大于性能损失 |
| 性能下降需权衡 | 3% ~ 5% | 根据代码维护成本判断 |
| 性能下降不可接受 | > 5% | 保留原逻辑 |
| 过拟合警告 | valid-test差异 > 10% | 需要重新审视优化过程 |

---

*文档版本: v2.0*
*创建时间: 2026-01-05*
*基于: Tom/Tommy 代理深度分析*
