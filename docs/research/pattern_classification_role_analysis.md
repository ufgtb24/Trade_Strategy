# 模式分类在信号-评分融合中的角色分析报告

**日期**: 2026-02-10
**分析师**: pattern-analyst (Technical Researcher)

---

## Executive Summary

信号系统的 `sequence_label` 和评分报告的 5 种模式分类，表面看似同源，实则描述的是**不同层级的市场行为**。sequence_label 刻画的是"发生了什么事件序列"（事实描述），bonus-based 分类刻画的是"这个突破的内在属性构成"（质量解构）。两者是**互补关系**，不可互相替代。

**核心结论**：模式分类应在**评分系统内部**实现（方案 a），基于 bonus 分解。sequence_label 作为独立的事件描述保留在信号系统中。两者在最终消费层（Simple Pool / 回测）并行使用。

---

## 一、序列标签 vs 模式分类：语义映射分析

### 1.1 两套体系的信息源对比

| 维度 | sequence_label (信号系统) | 模式分类 (评分系统) |
|------|--------------------------|-------------------|
| 输入数据 | 信号类型 + 时间序列 + pk_num/tr_num | 11 个 bonus 的 level/value |
| 粒度 | 事件级（每个信号是一个事件） | 属性级（每个 bonus 是一个属性维度） |
| 视角 | **时间序列视角** — 什么信号按什么顺序出现 | **截面属性视角** — 单次突破的多维质量属性 |
| 信息量 | 信号类型(B/D/V/Y) + 强度(pk_num/tr_num) | 年龄、测试次数、高度、成交量、动量、连续性等 |
| 适用场景 | 描述"市场事件叙事" | 描述"阻力突破的内在性质" |

### 1.2 映射关系表

| 信号序列模式 | 对应的评分模式 | 映射程度 | 详细说明 |
|---|---|---|---|
| `D → B` 或 `D(N) → B` | 部分对应 A 势能突破 | **弱** | D 信号表示双底确认，B 信号表示随后突破。但评分系统的 A 模式由 pk_momentum（凹陷深度）主导，D 信号检测的是 trough 级别的底部，两者刻画的是不同尺度的"回撤后反弹"。D→B 更接近"底部确认后突破"，而非"V型反弹突破近期peak"。 |
| `B(3)` 或 `B(N)` 单独出现，N>=2 | 对应 B 历史阻力突破 | **中** | pk_num 表示穿越了几层阻力，与 age_bonus + tests_bonus 有相关性。但 pk_num 只计数被穿越的 peak 数量，不区分这些 peak 的年龄和空间分布。pk_num=3 可能是穿越 3 个近期 peak（非模式 B），也可能是穿越包含远期 peak 的 3 层阻力（是模式 B）。 |
| `V → B` 或 `Y → B` | 部分对应 C 放量爆发突破 | **中偏弱** | V/Y 信号检测的是绝对的放量/大阳线事件，而模式 C 是 volume_bonus + gap_vol/idr_vol 主导的突破**属性**。关键区别：V/Y 是独立事件（可能不在突破日），而 gap_vol/idr_vol 是突破日当天的行为属性。如果 V 信号在突破日之前 2 周出现，sequence_label 为 `V → B`，但突破日本身可能并无放量，不构成模式 C。 |
| `B → B` 或 `B → B → B` | 部分对应 E 趋势延续突破 | **中** | 连续 B 信号确实对应 streak_bonus 场景。但 streak_bonus 在评分系统中由 `recent_breakout_count` 计算（来自 breakout detector 内部的连续突破计数），而 sequence_label 的多个 B 来自聚合器的 lookback 窗口内多个独立突破事件。两者口径不完全一致：评分的 streak 要求短期内"连续"，而信号系统的 B→B 只要求在 lookback 窗口内存在。 |
| `D(N) → B(M)` 复合序列 | 混合模式 A+B 或 B+D | **弱** | 复杂序列涉及多个信号的组合，但无法从中推断出 pk_momentum, age, height 等评分属性的具体值。 |
| 无 D 信号的纯 `B` 系列 | 难以区分 A/B/D/E | **极弱** | 单个 `B` 或 `B(1)` 在信号系统中无法区分是势能突破、历史阻力突破还是密集测试突破——这些区别完全依赖于评分系统的 bonus 属性分解。 |

### 1.3 映射困难的根本原因

**信息不对称**：sequence_label 携带的信息维度与 5 种模式分类所需的信息维度**交集很小**。

- sequence_label **知道**但模式分类**不知道**的：
  - 信号间的时间顺序和间隔
  - D 信号的存在（底部确认）
  - V/Y 信号的存在（非突破日的市场强度事件）
  - 信号的 freshness 衰减

- 模式分类**需要**但 sequence_label **不携带**的：
  - peak 的 age（年龄，天数）
  - peak 的 relative_height（相对高度）
  - peak_volume_ratio（峰值放量）
  - breakout 的 pk_momentum（凹陷深度）
  - breakout 的 gap_up_pct, intraday_change_pct（突破日行为）
  - breakout 的 annual_volatility（波动率上下文）
  - breakout 的 recent_breakout_count（精确的连续突破计数）

这些缺失的信息正是评分系统的 11 个 bonus 所量化的内容。

---

## 二、三种实现方案的详细评估

### 方案 a: 在评分系统内部实现（基于 bonus 分解）

**实现位置**: `BreakoutStrategy/analysis/breakout_scorer.py`

**实现方式**: 在 `get_breakout_score_breakdown_bonus()` 末尾，利用已计算的 `List[BonusDetail]` 调用 `_classify_pattern(bonuses)` 方法，将分类结果写入 `ScoreBreakdown.pattern_label`。

**信息完整性: 最高**

该方案可以访问所有 11 个 bonus 的 raw_value、bonus 乘数和 level，这正是区分 5 种模式所需的全部信息。具体优势：

1. **模式 A（势能突破）**: 直接读取 `pk_momentum_bonus.level >= 1`
2. **模式 B（历史阻力）**: 直接读取 `age_bonus.level >= 2`（即 >= 63 天）
3. **模式 C（放量爆发）**: 直接读取 `volume_bonus.level + idr_vol_bonus.level + gap_vol_bonus.level`
4. **模式 D（密集测试）**: 直接读取 `test_bonus.level >= 2`（即 >= 3 次）
5. **模式 E（趋势延续）**: 直接读取 `streak_bonus.level >= 1`

**实现复杂度: 低（约 40-60 行）**

分类逻辑只是对已计算好的 bonus level 进行条件判断，不需要新增任何计算。评分报告中已给出的伪代码基本可以直接使用。

**与下游衔接: 最自然**

- `ScoreBreakdown` 已是评分系统的输出结构，添加 `pattern_label` 字段对下游透明
- Simple Pool 和回测引擎已经通过 `Breakout.quality_score` 和 `ScoreBreakdown` 消费评分输出，pattern_label 作为附加属性自然传递
- 回测分组统计只需按 `pattern_label` groupby

**局限性**:

- 模式分类只在"B 信号"（突破事件）发生时产生，对于 V/Y/D 信号没有模式标签
- 如果未来需要"事件序列级"的模式（如"底部确认后的势能突破"），需要跨信号类型的信息，评分系统单独无法完成

---

### 方案 b: 在信号系统内部实现（基于 sequence_label 扩展）

**实现位置**: `BreakoutStrategy/signals/composite.py` 的 `generate_sequence_label()` 扩展

**实现方式**: 将 `generate_sequence_label` 扩展为同时输出 `pattern_type`，基于信号类型组合和 pk_num/tr_num 进行模式推断。

**信息完整性: 严重不足**

如第一节分析所示，信号系统缺少区分 5 种模式的关键属性（age, height, pk_momentum, volume_ratio 等）。信号系统只有：
- 信号类型（B/D/V/Y）
- pk_num（穿越的 peak 数量）
- tr_num（双底确认数量）
- volume_ratio（breakout detector 传递的成交量比）

无法区分的场景（致命问题）：

| 场景 | 信号系统看到的 | 实际模式 | 问题 |
|------|---------------|---------|------|
| 穿越 1 个近期 peak | B(1) | A 势能突破 | 无 pk_momentum 信息 |
| 穿越 1 个远期 peak | B(1) | B 历史阻力 | 无 age 信息 |
| 穿越 1 个密集测试 peak | B(1) | D 密集测试 | 无 tests 信息（pk_num 只计穿越数） |
| 放量穿越 | B(1) + V | 可能 C | V 可能在不同日期 |

**实现复杂度: 中高（需要引入评分系统的属性信息）**

为了实现有效分类，需要将 breakout detector 的输出中加入 age、tests 等属性，或者在 composite.py 中重新引入 peak 分析逻辑。这将造成：
1. 信号系统与评分系统的职责边界模糊
2. 信息的重复计算（peak 属性在 scorer 和 signal 中各算一遍）
3. 模块间的耦合度显著增加

**与下游衔接: 可行但不自然**

`SignalStats.sequence_label` 已存在，可扩展为 `pattern_type` 字段。但问题是：
- sequence_label 是股票级的（聚合了所有信号），而模式分类是突破级的（每次突破可能是不同模式）
- 一个 lookback 窗口内可能有多次突破，它们可能属于不同模式
- Simple Pool 如果需要按模式过滤，需要从 `SignalStats` 而非 `ScoreBreakdown` 获取，增加数据流复杂度

---

### 方案 c: 作为独立的第三层消费两者输出

**实现位置**: 新建 `BreakoutStrategy/classification/` 模块

**实现方式**: 创建 `PatternClassifier` 类，接收 `ScoreBreakdown` 和 `SignalStats` 作为输入，综合两者信息进行分类。

**信息完整性: 理论最高**

可以同时利用：
- 评分系统的 11 个 bonus 分解（属性视角）
- 信号系统的 sequence_label（事件序列视角）
- 可实现"底部确认后的势能突破"等跨层模式

**实现复杂度: 最高（约 150-200 行 + 新模块结构）**

1. 新建模块目录和文件
2. 定义输入接口（需要同时获取 ScoreBreakdown 和 SignalStats）
3. 实现分类逻辑
4. 定义输出结构
5. 在调用方（Simple Pool / 回测引擎）中集成

**与下游衔接: 需要额外集成层**

- Simple Pool 需要在获取评分和信号之后，额外调用分类器
- 数据流：`Scanner → Signals` + `Detector → Scorer` → `Classifier` → `Pool`
- 增加了处理流水线的长度和复杂度
- 需要确保分类器在正确的时机被调用（评分和信号都就绪之后）

**关键问题: 是否需要跨层信息？**

当前 5 种模式的定义完全基于 bonus 属性（pk_momentum, age, tests, volume, streak），不需要信号序列信息。只有以下假设的"高阶模式"才需要跨层：
- "底部确认后的势能突破" = D信号 + A模式
- "放量确认后的历史阻力突破" = V信号 + B模式

但这些高阶模式目前尚未定义，也没有数据证明其价值。按照奥卡姆剃刀原则，不应为假设需求增加架构复杂度。

---

## 三、综合对比矩阵

| 评估维度 | 方案 a (评分内部) | 方案 b (信号内部) | 方案 c (独立第三层) |
|----------|:---:|:---:|:---:|
| 信息完整性 | **足够** (11个bonus) | **严重不足** | **理论最高** |
| 实现复杂度 | **~50行** | ~200行+耦合 | ~200行+新模块 |
| 与 Simple Pool 衔接 | **自然** (ScoreBreakdown扩展) | 可行但不自然 | 需额外集成 |
| 与回测引擎衔接 | **自然** (groupby pattern_label) | 可行 | 需额外集成 |
| 模块耦合度 | **零新增** | 高 (需引入评分属性) | 中 (新增消费关系) |
| 未来扩展性 | 中 (仅限突破属性) | 低 | **高** (可利用所有信息) |
| 符合奥卡姆剃刀 | **是** | 否 | 否 |
| 当前数据支撑 | **充分** | 不足 | 过度 |

---

## 四、sequence_label 能否替代 bonus-based 分类？

**明确结论：不能。**

理由摘要：

1. **信息维度不匹配**：sequence_label 缺少 age、height、pk_momentum、tests、volume_ratio 等区分 5 种模式的核心属性。一个 `B(1)` 可以是模式 A/B/C/D 中的任何一种。

2. **粒度不匹配**：sequence_label 是股票级别的（一个 lookback 窗口内所有信号的序列），模式分类是突破级别的（每次突破有独立的模式属性）。

3. **时间语义不同**：sequence_label 的"顺序"是信号间的时间关系（D先于B），模式分类的"属性"是单次突破的内在性质（这个peak有多老）。

### 两者的正确关系：互补

| 层级 | 工具 | 回答的问题 | 示例 |
|------|------|-----------|------|
| 事件叙事层 | sequence_label | 这个窗口内发生了什么事件序列？ | "先有双底确认，后有3层阻力突破，伴随放量" |
| 突破质量层 | pattern_label | 这次突破的质量属性构成是什么？ | "历史阻力突破 + 密集测试（B+D混合模式）" |
| 策略决策层 | 两者结合 | 应该如何操作？ | sequence_label 提供信心（多信号共振），pattern_label 提供策略（止损位、持仓周期） |

---

## 五、最终建议

### 推荐方案：方案 a（评分系统内部实现）

**理由**：

1. **信息充分**：5 种模式的定义完全基于 bonus 属性，评分系统内部拥有全部所需信息
2. **实现最简**：约 40-60 行代码，在已有的 `get_breakout_score_breakdown_bonus()` 尾部添加分类调用
3. **零耦合**：不引入新的模块间依赖
4. **符合架构原则**：模式分类是评分的"后处理"（评分先行，分类后行），逻辑上属于评分模块的职责延伸
5. **与 C+ 方案一致**：与之前评分分析报告推荐的 Phase 2 实现路径完全吻合

### sequence_label 的定位

sequence_label 应保持在信号系统中作为**事件叙事标签**，不承担模式分类职责：
- 在 UI 中作为辅助信息展示（帮助用户理解"发生了什么"）
- 在回测中作为附加分组维度（分析"什么事件组合"的表现）
- 在 Simple Pool 中作为排序的辅助参考（多信号共振 > 单信号）

### 渐进演化路径

```
当前 → Phase 2 (方案a) → 如需要 → Phase 5 (方案c)

Phase 2: 在 breakout_scorer.py 中添加 _classify_pattern()
         输出: ScoreBreakdown.pattern_label

Phase 3: 回测验证，按 pattern_label 分组统计 MFE/MAE

Phase 4: 如果回测证明某些 sequence_label + pattern_label 的组合
         有显著策略差异，再考虑建立方案 c 的独立分类层

Phase 5 (仅在数据驱动下): 建立 PatternClassifier，
         消费 ScoreBreakdown + SignalStats，
         产出更丰富的复合模式标签
```

### 实现注意事项

1. `_classify_pattern` 应返回 `str` 类型的标签，不返回评分调整值——模式分类不改变评分，只提供标签
2. 混合模式（A+B, B+D 等）应优先于单一模式判定
3. 分类结果写入 `ScoreBreakdown.pattern_label`，通过现有数据流自然传递到下游
4. 如果评分修复（Phase 1: 合并 gap_vol/idr_vol, 放宽 overshoot, 扩展 streak）先行，分类逻辑的阈值需要基于修复后的 bonus 配置

---

*报告由 pattern-analyst 生成*
*分析方法: 代码级逆向分析 + 信息论视角的映射评估 + 架构适配性评估*