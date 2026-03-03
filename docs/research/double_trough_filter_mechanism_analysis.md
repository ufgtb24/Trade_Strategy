# 双底检测器过滤机制分析报告

## 1. 执行摘要

本报告分析了 `DoubleTroughDetector.detect()` 方法中的过滤机制，重点研究两个用户反馈的问题：

1. **Trough 位置占用问题**：当一个 trough 被 `min_tr2_depth` 过滤后，后续更明显的 trough 无法与同一个 TR1 配对
2. **TR1 索引占用问题**：某些过滤条件会将 TR1 标记为"已处理"，阻止后续配对尝试

**核心发现**：问题的根源在于"**结构紧邻约束**"的设计意图与当前实现之间的语义冲突。该约束强制 TR2 必须是 TR1 后的第一个 trough，但在某些过滤场景下，这种严格约束会导致有效信号被遗漏。

---

## 2. 代码逻辑详细分析

### 2.1 检测流程概览

```
1. 检测所有形状确认的 trough (troughs_low)
2. 按索引排序 troughs
3. 遍历每个 trough 作为潜在 TR2:
   a. 计算该时刻的 126 日最低点作为 TR1
   b. 检查 TR1 是否已处理 → 跳过
   c. 检查结构紧邻约束 → 跳过
   d. 检查 TR1 窗口约束 → 跳过
   e. 检查 max_gap_days → 标记 TR1 + 跳过
   f. 检查 TR2 > TR1 → 标记 TR1 + 跳过
   g. 检查 first_bounce_height → 标记 TR1 + 跳过
   h. 检查 min_tr2_depth → 仅跳过（不标记 TR1）
   i. 检查 min_recovery_pct → 仅跳过
   j. 生成信号 + 标记 TR1
```

### 2.2 过滤条件分类

根据过滤后是否执行 `processed_tr1_indices.add(tr1_idx)`，将条件分为两类：

#### 类型 A：消耗 TR1 的过滤（标记为已处理）

| 行号 | 条件 | 语义 | 是否合理 |
|------|------|------|----------|
| 267-269 | `gap_days > max_gap_days` | TR1 和 TR2 间隔过大 | **合理** - 超时意味着这个 TR1 已经"过期"，后续 trough 只会更远 |
| 274-276 | `tr2_price <= tr1_price` | TR2 没有高于 TR1 | **待议** - 见下文分析 |
| 283-285 | `not is_valid_bounce` | 反弹不够高 | **合理** - 反弹高度是 TR1 的固有属性，后续 trough 不会改变它 |
| 303 | 成功生成信号 | 正常消耗 | **合理** |

#### 类型 B：不消耗 TR1 的过滤（仅跳过当前 trough）

| 行号 | 条件 | 语义 | 是否合理 |
|------|------|------|----------|
| 245-246 | `tr1_idx in processed_tr1_indices` | TR1 已处理 | **合理** - 避免重复 |
| 255-259 | 结构紧邻约束不满足 | 不是 TR1 后第一个 trough | **问题根源** |
| 262-263 | `tr1_idx >= trough.window_start` | TR1 在 TR2 检测窗口内 | **合理** - 技术性约束 |
| 289-290 | `not is_valid_depth` | TR2 深度不够 | **有问题** - 见下文 |
| 299-300 | `recovery_pct < min_recovery_pct` | 恢复不够 | **有问题** - 见下文 |

---

## 3. 问题根源分析

### 3.1 问题 1：结构紧邻约束的阻断作用

**代码位置**：第 248-259 行

```python
# 检查结构紧邻约束：当前 trough 必须是 TR1 之后的第一个 trough
first_trough_after_tr1 = None
for t in troughs:
    if t.index > tr1_idx:
        first_trough_after_tr1 = t
        break

if (
    first_trough_after_tr1 is None
    or first_trough_after_tr1.index != trough.index
):
    continue
```

**问题描述**：
这个约束要求 TR2 必须是 TR1 之后的**第一个** trough。当这个第一个 trough 被任何后续条件（如 `min_tr2_depth`）过滤掉时，由于 `continue` 语句，算法会跳到下一个 trough。但下一个 trough 不再是"TR1 后的第一个 trough"，因此也会被这个约束过滤。

**结果**：一旦 TR1 后的第一个 trough 被过滤，这个 TR1 永远无法形成双底信号。

**设计意图推测**：
1. **防止信号稀释**：避免同一个 TR1 与多个后续 trough 形成多个信号
2. **保持形态紧凑性**：经典双底形态中，两个底部应该相对紧凑
3. **简化逻辑**：避免复杂的"最优匹配"算法

### 3.2 问题 2：TR1 标记时机不当

**问题描述**：
某些过滤条件在执行 `continue` 之前会先标记 TR1 为已处理，但有些过滤条件没有这样做。这导致了不一致的行为：

- `min_tr2_depth` 过滤（第 289-290 行）：**不标记** TR1
- `tr2_price <= tr1_price` 过滤（第 274-276 行）：**标记** TR1

**矛盾点**：
如果 `min_tr2_depth` 不标记 TR1 是为了让后续 trough 有机会与同一 TR1 配对，那么结构紧邻约束会阻止这种配对。这两个设计意图相互矛盾。

### 3.3 场景还原

用户描述的场景：

```
时间线：  TR1 -------- Trough_A -------- Trough_B -------→
                        (浅)              (深)
                    被 min_tr2_depth      期望成为
                        过滤              新的 TR2
```

**当前代码行为**：
1. 遍历到 Trough_A，计算出 TR1
2. 结构紧邻约束通过（Trough_A 是 TR1 后第一个 trough）
3. `min_tr2_depth` 过滤：Trough_A 深度不够，`continue`（不标记 TR1）
4. 遍历到 Trough_B，计算出**同一个** TR1
5. TR1 未被标记，继续
6. **结构紧邻约束失败**：Trough_B 不是 TR1 后第一个 trough
7. `continue`，Trough_B 被跳过
8. TR1 永远无法形成信号

---

## 4. 过滤条件语义分析

### 4.1 TR1 固有属性 vs TR2 相关属性

| 过滤条件 | 属性类型 | 说明 |
|----------|----------|------|
| `max_gap_days` | **TR2 相关**（时间递增） | 后续 trough 只会更远，无需重试 |
| `tr2_price <= tr1_price` | **TR2 相关**（可变） | 后续 trough 可能更高 |
| `first_bounce_height` | **TR1+区间固有** | 取决于 TR1 后到当前 trough 的最高点 |
| `min_tr2_depth` | **TR2 相关**（可变） | 后续 trough 深度可能不同 |
| `min_recovery_pct` | **TR2 相关**（可变） | 后续 trough 恢复程度可能不同 |

### 4.2 关键洞察

1. **`first_bounce_height` 的特殊性**：
   - 表面上看，`bounce_high` 是 [TR1, TR2] 区间的最高点
   - 但如果后续 trough 距离更远，这个区间会扩大，`bounce_high` 只增不减
   - 因此，如果当前 trough 满足反弹要求，后续 trough 也必然满足
   - 如果当前 trough 不满足，后续 trough **可能**满足（因为区间扩大）

2. **`tr2_price <= tr1_price` 的复杂性**：
   - 当前代码标记 TR1，假设"TR2 不能更低"是结构性失败
   - 但后续 trough 的价格可能更高，不应过早放弃 TR1

3. **`min_tr2_depth` 的意图**：
   - 过滤浅回调，保留明显的第二个底
   - 不标记 TR1 是正确的设计（后续可能有更深的 trough）
   - 但结构紧邻约束阻止了这种重试

---

## 5. 改进方向分析

### 5.1 方案 A：放宽结构紧邻约束

**思路**：允许在特定条件下跳过一个 trough，尝试后续 trough

**实现方式**：
```python
# 不再要求"第一个"，而是找到"第一个通过所有过滤的"trough
# 但需要控制跳过的数量，避免形态过于松散
```

**优点**：
- 解决用户描述的问题
- 保持大部分原有逻辑

**缺点**：
- 可能产生形态不紧凑的信号
- 需要引入"最大跳过数"等新参数

**风险**：
- 同一个 TR1 可能与不同 trough 形成多个候选，需要选择策略

### 5.2 方案 B：引入"有条件的 TR1 释放"

**思路**：某些过滤条件失败时，释放 TR1 供下一个 trough 重试

**实现方式**：
```python
# 对于 min_tr2_depth 过滤失败的情况
if not is_valid_depth:
    # 不标记 TR1，且标记"当前 trough 不是有效 TR2"
    # 下次循环时，跳过结构紧邻约束
    skipped_first_trough_for_tr1[tr1_idx] = trough.index
    continue

# 在结构紧邻约束检查时
if tr1_idx in skipped_first_trough_for_tr1:
    # 允许使用非第一个 trough
    pass
```

**优点**：
- 精确控制哪些条件可以触发重试
- 保持结构紧邻约束对其他场景的作用

**缺点**：
- 增加代码复杂度
- 需要维护额外状态

### 5.3 方案 C：移除结构紧邻约束，改用"最优匹配"

**思路**：对每个 TR1，找到所有满足条件的 TR2 候选，选择最优的

**实现方式**：
```python
# 收集所有 TR1 -> TR2 候选对
candidates = []
for trough in troughs:
    tr1_idx, tr1_price, tr1_date = self._find_126d_low(df, trough.index)
    if passes_all_filters(tr1_idx, trough):
        candidates.append((tr1_idx, trough, score))

# 按 TR1 分组，每组选最优 TR2
for tr1_idx, group in groupby(candidates, key=lambda x: x[0]):
    best_tr2 = max(group, key=lambda x: x[2])  # 按评分选择
    signals.append(create_signal(tr1_idx, best_tr2))
```

**优点**：
- 最灵活，不会遗漏有效信号
- 可以定义明确的"最优"标准

**缺点**：
- 完全重写检测逻辑
- "最优"标准需要仔细定义

### 5.4 方案 D：分离"形态识别"和"信号过滤"

**思路**：
1. 第一阶段：宽松识别所有潜在双底形态
2. 第二阶段：应用过滤参数，筛选最终信号

**实现方式**：
```python
def detect(self):
    # 阶段 1：识别所有潜在双底
    potential_signals = self._identify_all_double_troughs()

    # 阶段 2：应用过滤
    filtered_signals = self._apply_filters(potential_signals)

    # 阶段 3：去重（每个 TR1 只保留一个信号）
    final_signals = self._deduplicate(filtered_signals)

    return final_signals
```

**优点**：
- 逻辑清晰，易于调试
- 过滤参数调整不影响形态识别
- 可以方便地看到"被过滤的信号"用于调试

**缺点**：
- 需要较大重构
- 可能增加计算量

---

## 6. 推荐方案

### 6.1 短期改进（方案 B 变体）

**目标**：最小改动解决用户问题

**具体实现**：

```python
def detect(self, df, symbol, end_index=None):
    signals = []
    # ...现有初始化代码...

    # 新增：记录因 TR2 属性（非 TR1 固有属性）过滤失败的 trough
    # 这些 trough 不应阻止后续 trough 与同一 TR1 配对
    tr2_filtered_troughs = set()

    for trough in troughs:
        tr1_idx, tr1_price, tr1_date = self._find_126d_low(df, trough.index)

        if tr1_idx in processed_tr1_indices:
            continue

        # 修改后的结构紧邻约束
        first_valid_trough_after_tr1 = None
        for t in troughs:
            if t.index > tr1_idx and t.index not in tr2_filtered_troughs:
                first_valid_trough_after_tr1 = t
                break

        if first_valid_trough_after_tr1 is None or first_valid_trough_after_tr1.index != trough.index:
            continue

        # ...其他约束检查...

        # min_tr2_depth 检查
        is_valid_depth, depth_pct = self._validate_tr2_depth(bounce_high, tr2_price)
        if not is_valid_depth:
            tr2_filtered_troughs.add(trough.index)  # 标记此 trough 被 TR2 属性过滤
            continue

        # min_recovery_pct 检查
        if self.min_recovery_pct > 0:
            recovery_pct = (tr2_price - tr1_price) / tr1_price * 100
            if recovery_pct < self.min_recovery_pct:
                tr2_filtered_troughs.add(trough.index)
                continue

        # ...生成信号...
```

**关键改动**：
1. 新增 `tr2_filtered_troughs` 集合
2. 当 `min_tr2_depth` 或 `min_recovery_pct` 过滤失败时，将 trough 加入此集合
3. 修改结构紧邻约束，跳过已被 TR2 属性过滤的 trough

### 6.2 中期改进（方案 D）

如果短期方案引入新问题或逻辑变得复杂，建议重构为两阶段检测。

---

## 7. 关于 TR1 标记时机的建议

### 7.1 当前问题

`tr2_price <= tr1_price`（第 274-276 行）会标记 TR1，但这可能过于激进：

- 场景：TR1 后第一个 trough 价格 <= TR1，但第二个 trough 价格 > TR1
- 当前行为：TR1 被标记，第二个 trough 无法与其配对
- 期望行为：第二个 trough 应该有机会尝试

### 7.2 建议

将 `tr2_price <= tr1_price` 的处理方式与 `min_tr2_depth` 统一：

```python
# 当前代码
if tr2_price <= tr1_price:
    processed_tr1_indices.add(tr1_idx)  # 问题：过早消耗 TR1
    continue

# 建议修改
if tr2_price <= tr1_price:
    tr2_filtered_troughs.add(trough.index)  # 改为：标记 trough，而非 TR1
    continue
```

**理由**：
- TR2 价格是 trough 的属性，不是 TR1 的固有属性
- 后续 trough 可能价格更高，应给予机会

---

## 8. 结论

### 8.1 问题本质

用户发现的问题本质是**过滤机制的粒度不当**：

1. 结构紧邻约束是"**TR1 级别**"的约束（一旦失败，放弃当前 TR1）
2. `min_tr2_depth` 是"**TR2 级别**"的过滤（应该只影响当前 trough）
3. 当前代码没有区分这两类，导致 TR2 级别的过滤触发了 TR1 级别的放弃

### 8.2 核心建议

1. **区分 TR1 固有属性和 TR2 可变属性**
2. **TR2 可变属性过滤失败时，只标记 trough，不影响 TR1**
3. **修改结构紧邻约束，跳过被 TR2 属性过滤的 trough**

### 8.3 需要权衡的问题

1. **形态紧凑性 vs 信号覆盖率**：放宽约束可能产生更松散的双底形态
2. **实现复杂度 vs 行为精确性**：更精细的控制需要更复杂的代码
3. **向后兼容性**：修改可能影响历史信号的复现

---

## 附录 A：相关代码行号索引

| 行号 | 功能 |
|------|------|
| 237 | `processed_tr1_indices = set()` |
| 244-246 | TR1 已处理检查 |
| 248-259 | 结构紧邻约束 |
| 261-263 | TR1 窗口约束 |
| 265-269 | max_gap_days 约束 |
| 271-276 | TR2 > TR1 约束 |
| 281-285 | first_bounce_height 约束 |
| 287-290 | min_tr2_depth 约束 |
| 292-300 | min_recovery_pct 约束 |
| 302-303 | 成功生成信号，标记 TR1 |

## 附录 B：测试用例建议

实现修改后，应测试以下场景：

1. **基本双底**：TR1 + 第一个 trough 形成有效双底
2. **深度过滤重试**：第一个 trough 深度不够，第二个 trough 深度足够
3. **价格过滤重试**：第一个 trough <= TR1，第二个 trough > TR1
4. **多次过滤**：连续多个 trough 被过滤，最后一个有效
5. **超时放弃**：所有候选 trough 都超过 max_gap_days
6. **反弹不足**：TR1 反弹不够，应该放弃（不重试）

---

## 附录 C：TR1 消耗机制的本质与统一分析

> 本附录回应用户的追问：
> "结构紧邻约束和标记TR1本质上都是 TR2 对 TR1 的消耗，对吗？如果是这样，那么岂不是很冗余，有没有办法只采用一个？"

### C.1 问题重述

用户提出的核心直觉是：两种机制（`processed_tr1_indices` 显式标记 vs 结构紧邻约束隐式限制）看起来都在做"消耗 TR1"这件事，是否存在冗余？

### C.2 两种机制的本质分析

#### C.2.1 机制定义

**机制 1：`processed_tr1_indices` 显式标记**
```python
processed_tr1_indices = set()
# ...
if tr1_idx in processed_tr1_indices:
    continue  # 跳过已消耗的 TR1
# ...
processed_tr1_indices.add(tr1_idx)  # 显式消耗 TR1
```

**机制 2：结构紧邻约束（隐式消耗）**
```python
first_trough_after_tr1 = None
for t in troughs:
    if t.index > tr1_idx:
        first_trough_after_tr1 = t
        break

if first_trough_after_tr1.index != trough.index:
    continue  # 当前 trough 不是 TR1 后的第一个
```

#### C.2.2 核心洞察：两者确实是同一回事

**命题**：在当前代码逻辑下，结构紧邻约束等价于"TR1 只能被其后的第一个 trough 消耗"。

**证明**：

假设有 TR1_A，以及其后的 trough 序列 [T1, T2, T3...]

1. **当 T1 遍历时**：
   - `first_trough_after_tr1` = T1 ✓
   - T1 通过结构紧邻约束
   - 如果 T1 通过所有过滤 → TR1_A 被标记消耗 → 后续 T2, T3 无法使用 TR1_A
   - 如果 T1 未通过某些过滤 → 分两种情况：
     - 过滤标记了 TR1 → TR1_A 被消耗 → 后续无法使用
     - 过滤未标记 TR1 → TR1_A 未消耗，但...

2. **当 T2 遍历时**（假设 TR1_A 未被标记）：
   - 计算得到 TR1_A（假设 126 日最低点仍是 TR1_A）
   - `first_trough_after_tr1` = T1
   - T2 != T1 → **结构紧邻约束失败** → 跳过

**结论**：即使 TR1_A 未被显式标记，结构紧邻约束也会阻止 T2 与 TR1_A 配对。

这意味着：**结构紧邻约束隐式地实现了"TR1 被其后第一个 trough 消耗"的语义，无论该 trough 是否通过所有过滤**。

### C.3 冗余性分析

#### C.3.1 两种机制的功能重叠

| 场景 | 结构紧邻约束作用 | processed_tr1_indices 作用 |
|------|------------------|---------------------------|
| T1 通过所有过滤，生成信号 | T2 无法通过（T1 != T2）| TR1 被标记，T2 检查时跳过 |
| T1 未通过过滤，TR1 被标记 | T2 无法通过（T1 != T2）| TR1 被标记，T2 检查时跳过 |
| T1 未通过过滤，TR1 未标记 | T2 无法通过（T1 != T2）| 无作用（未标记）|

**关键观察**：
- 前两种场景中，两种机制**同时起作用**，形成双重保险
- 第三种场景中，**只有结构紧邻约束起作用**

#### C.3.2 为什么存在冗余？

推测原因：
1. **历史演进**：可能先有 `processed_tr1_indices`，后加结构紧邻约束
2. **防御性编程**：双重保险，但增加了理解难度
3. **语义不同**：设计者可能认为两者表达不同意图（但实际效果重叠）

### C.4 只保留一种机制的可行性分析

#### C.4.1 方案 A：只保留 `processed_tr1_indices`

**做法**：移除结构紧邻约束，完全依赖显式标记

**问题**：
- 需要在**所有**过滤分支添加 `processed_tr1_indices.add(tr1_idx)`
- 如果某个分支忘记标记，会导致 TR1 被多个 trough 重复使用
- 代码维护负担重，容易出错

**结论**：不推荐

#### C.4.2 方案 B：只保留结构紧邻约束（推荐）

**做法**：移除分散的 `processed_tr1_indices.add()` 调用，将标记统一到结构紧邻约束之后

**分析**：

结构紧邻约束的语义是：**对于任意 TR1，只有其后的第一个 trough 有资格成为 TR2**。

这个语义**天然地**保证了：
- TR1 最多只能与一个 trough 配对
- 不需要在每个过滤分支单独标记

**关于性能优化**：

`processed_tr1_indices` 还用于**提前跳过**已知无效的 TR1，避免重复计算。这是一个有价值的优化，但可以简化其使用方式。

### C.5 推荐的统一方案

#### C.5.1 核心原则

**TR1 的消耗由结构紧邻约束单独控制，`processed_tr1_indices` 仅作为缓存/优化存在。**

#### C.5.2 统一后的代码结构

```python
def detect(self, df, symbol, end_index=None):
    signals = []
    # ...

    # 已消耗的 TR1（由结构紧邻约束自动消耗）
    consumed_tr1 = set()

    for trough in troughs:
        tr1_idx, tr1_price, tr1_date = self._find_126d_low(df, trough.index)

        # 快速跳过已消耗的 TR1（性能优化）
        if tr1_idx in consumed_tr1:
            continue

        # 核心约束：结构紧邻
        first_trough = next((t for t in troughs if t.index > tr1_idx), None)
        if first_trough is None or first_trough.index != trough.index:
            continue

        # ★ 关键：到达这里，TR1 就被消耗了，无论后续过滤结果如何
        consumed_tr1.add(tr1_idx)

        # === 以下是纯过滤逻辑，只决定是否生成信号，不影响 TR1 消耗 ===

        # TR1 窗口约束
        if tr1_idx >= trough.window_start:
            continue

        # 时间约束
        if trough.index - tr1_idx > self.max_gap_days:
            continue

        # 价格约束：TR2 > TR1
        tr2_price = self._get_tr2_price(df, trough.index)
        if tr2_price <= tr1_price:
            continue

        # 反弹约束
        bounce_high = df["close"].iloc[tr1_idx:trough.index + 1].max()
        if not self._validate_tr1_bounce(bounce_high, tr1_price)[0]:
            continue

        # 深度约束
        if not self._validate_tr2_depth(bounce_high, tr2_price)[0]:
            continue

        # 恢复约束
        if self.min_recovery_pct > 0:
            recovery_pct = (tr2_price - tr1_price) / tr1_price * 100
            if recovery_pct < self.min_recovery_pct:
                continue

        # 生成信号
        signals.append(...)

    return signals
```

#### C.5.3 关键变化总结

| 原代码 | 统一后 |
|--------|--------|
| `processed_tr1_indices` 在多处标记 | `consumed_tr1` 在单一位置标记（结构紧邻约束之后）|
| 部分过滤标记 TR1，部分不标记 | 所有过滤都不标记 TR1（已由结构紧邻约束隐式消耗）|
| 语义模糊：何时标记 TR1？ | 语义清晰：通过结构紧邻约束 = TR1 被消耗 |

### C.6 回应用户问题

#### Q1: 结构紧邻约束和标记 TR1 本质上都是 TR2 对 TR1 的消耗，对吗？

**A: 是的，本质相同。**

更精确地说：
- 结构紧邻约束实现了**隐式消耗**：TR1 只能被其后第一个 trough 使用
- `processed_tr1_indices` 实现了**显式消耗**：标记 TR1 不可再用

在当前代码中，这两者**功能重叠**，形成双重保险。

#### Q2: 有没有办法只采用一个？

**A: 可以，推荐只保留结构紧邻约束。**

具体做法：
1. 将 `processed_tr1_indices` 重命名为 `consumed_tr1`，语义改为"缓存"
2. 在结构紧邻约束通过后**立即标记** `consumed_tr1.add(tr1_idx)`
3. **移除**所有过滤分支中的单独标记逻辑

这样：
- 代码更简洁
- 语义更清晰
- 消除了"这个过滤应不应该标记 TR1"的困惑

### C.7 补充说明：关于"宽松匹配"

如果用户确实希望"第一个 trough 被过滤后，允许尝试第二个"，那需要**移除结构紧邻约束**，改用本报告主体部分的方案 B（有条件的 TR1 释放）或方案 C（最优匹配）。

但这会带来形态松散的风险，需要引入新的约束（如"最多跳过 N 个 trough"）来控制。

当前推荐的统一方案保留了**严格紧邻语义**，这符合双底形态的经典定义：两个底应该紧凑相连

---

## 附录 D：用户反驳分析与最终方案修订

> 本附录回应用户对附录 C 结论的反驳：
> "我认为应该保留 TR1 标记，而不是结构紧邻约束，原因是：某些类型的被过滤掉的 TR2 不该消耗 TR1，比如说凹陷很浅的，可以说根本没有形成底。而另一些被过滤掉的 TR2 应该消耗 TR1，比如说 not is_valid_bounce。因此，如果采用结构紧邻约束，则会一概而论，而采用 TR1 标记，才能灵活地分情况处理。"

### D.1 用户观点验证

**结论：用户观点正确。**

用户的核心洞察是：**不同的过滤失败有不同的语义含义**，需要区别对待。这与附录 C 中"只保留结构紧邻约束"的建议相冲突。

### D.2 过滤条件的语义分类

#### D.2.1 分类依据

过滤条件可分为两类：

| 类型 | 定义 | 特点 | 处理方式 |
|------|------|------|----------|
| **TR1 固有/结构属性** | 过滤结果由 TR1 或 [TR1, 当前trough] 区间决定，后续 trough **无法改变** | 失败意味着此 TR1 无法形成有效双底 | **应消耗 TR1** |
| **TR2 局部属性** | 过滤结果仅取决于当前 trough 的固有属性，不同 trough **结果不同** | 失败仅意味着当前 trough 不合格 | **不应消耗 TR1** |

#### D.2.2 具体分析

**`not is_valid_bounce` 应该消耗 TR1**

虽然从纯技术角度，后续 trough 区间可能反弹更大。但从业务语义考虑：

1. 双底形态强调**结构紧凑性**
2. 如果 TR1 后第一个 trough 都没有足够反弹，说明这个 TR1 形成的结构不完整
3. 后续出现的大反弹应视为新结构，而非延续原 TR1

**`min_tr2_depth` 不够不应该消耗 TR1**

用户的表述非常精准：

> "凹陷很浅的，可以说根本没有形成底"

分析：

1. TR2 深度是 trough **自身**的局部属性
2. 浅凹陷（如 T1）只是"噪音"，不是有意义的 trough
3. 后续 trough（如 T2）可能有完全不同的深度
4. 只有深度足够的 trough 才值得作为双底的第二个底

```
        高点(bounce_high)
       ↗    ↘
TR1  ↗        ↘  T1(浅,噪音)
(底)            ↘
                  ↘  T2(深,有意义)
```

### D.3 结构紧邻约束的根本问题

结构紧邻约束（第 248-259 行）的问题在于：**它无差别地将"TR1 后第一个 trough"视为唯一候选**。

| 场景 | 结构紧邻约束行为 | 问题 |
|------|------------------|------|
| T1 被 `min_tr2_depth` 过滤 | T2 无法与 TR1 配对 | T1 只是噪音，不应阻止 T2 |
| T1 被 `is_valid_bounce` 过滤 | T2 无法与 TR1 配对 | 这里应该消耗 TR1，符合预期 |

**核心矛盾**：结构紧邻约束"一概而论"，无法区分过滤原因。

### D.4 修订后的统一方案

#### D.4.1 核心变更

1. **移除结构紧邻约束**（删除第 248-259 行）
2. **完全依赖 TR1 标记机制**，根据过滤条件的语义精确控制是否消耗

#### D.4.2 过滤条件消耗规则

| 过滤条件 | 消耗 TR1 | 语义分类 | 理由 |
|----------|----------|----------|------|
| `max_gap_days` | **是** | 时间单调递增 | 后续 trough 只会更远，无改善可能 |
| `tr2_price <= tr1_price` | **是** | TR1 被取代 | TR2 成为新的 126 日最低点，原 TR1 自然被消耗 |
| `not is_valid_bounce` | **是** | 结构完整性 | 保持双底形态紧凑性（业务决策） |
| `min_tr2_depth` | **否** | TR2 局部属性 | 浅凹陷只是噪音，后续可能有深凹陷 |
| `min_recovery_pct` | **否** | TR2 局部属性 | 后续 trough 恢复程度可能不同 |
| 成功生成信号 | **是** | 正常消耗 | 避免重复信号 |

#### D.4.3 代码结构

```python
def detect(self, df, symbol, end_index=None):
    signals = []
    # ...
    processed_tr1_indices = set()

    for trough in troughs:
        tr1_idx, tr1_price, tr1_date = self._find_126d_low(df, trough.index)

        # 快速跳过已消耗的 TR1
        if tr1_idx in processed_tr1_indices:
            continue

        # ★ 移除了结构紧邻约束 ★

        # TR1 窗口约束（技术性）
        if tr1_idx >= trough.window_start:
            continue

        # 时间约束 → 消耗 TR1（后续只会更远）
        gap_days = trough.index - tr1_idx
        if gap_days > self.max_gap_days:
            processed_tr1_indices.add(tr1_idx)
            continue

        tr2_price = self._get_tr2_price(df, trough.index)

        # 价格约束 → 消耗 TR1（TR2 成为新的最低点，取代原 TR1）
        if tr2_price <= tr1_price:
            processed_tr1_indices.add(tr1_idx)
            continue

        bounce_high = df["close"].iloc[tr1_idx : trough.index + 1].max()

        # 反弹约束 → 消耗 TR1（业务决策：保持结构紧凑）
        is_valid_bounce, bounce_pct = self._validate_tr1_bounce(bounce_high, tr1_price)
        if not is_valid_bounce:
            processed_tr1_indices.add(tr1_idx)
            continue

        # 深度约束 → 不消耗 TR1（TR2 局部属性）
        is_valid_depth, depth_pct = self._validate_tr2_depth(bounce_high, tr2_price)
        if not is_valid_depth:
            continue  # 当前行为正确

        # 恢复约束 → 不消耗 TR1（TR2 局部属性）
        if self.min_recovery_pct > 0:
            recovery_pct = (tr2_price - tr1_price) / tr1_price * 100
            if recovery_pct < self.min_recovery_pct:
                continue  # 当前行为正确

        # 成功 → 消耗 TR1
        processed_tr1_indices.add(tr1_idx)
        # 生成信号...
```

### D.5 附录 C 结论的修订

附录 C 推荐"只保留结构紧邻约束"，理由是：
- 结构紧邻约束自动消耗 TR1，无需在每个分支单独标记
- 代码更简洁

**修订**：用户反驳有效。结构紧邻约束的"自动消耗"特性恰恰是问题所在——它无法区分过滤原因。正确的方案是：

1. **移除结构紧邻约束**
2. **保留 TR1 标记机制**
3. **根据语义精确控制每个过滤条件是否消耗 TR1**

### D.6 关于 `tr2_price <= tr1_price` 的补充分析（已修订）

> **修订说明**：用户指出原分析有误。`tr2_price <= tr1_price` **应该**消耗 TR1。

当前代码行为（保持不变）：

```python
if tr2_price <= tr1_price:
    processed_tr1_indices.add(tr1_idx)
    continue
```

**正确理由**：

当 TR2 价格 <= TR1 价格时：
1. TR2 本身成为了新的 126 日最低点
2. 后续 trough 会以 TR2 作为新的 TR1 来计算
3. 原来的 TR1 被**取代**，自然应该消耗

这与 `min_tr2_depth` **不同**：
- `min_tr2_depth`：TR2 深度不够只是"形态不够明显"，TR1 仍然是最低点
- `tr2_price <= tr1_price`：TR2 成为新的最低点，TR1 的角色被取代

### D.7 最终结论

| 机制 | 附录 C 推荐 | 附录 D 修订 |
|------|-------------|-------------|
| 结构紧邻约束 | 保留（作为唯一机制） | **移除** |
| TR1 标记机制 | 简化（仅作为缓存） | **保留并精确控制** |

**最终方案**：移除结构紧邻约束，完全依赖 TR1 标记机制，根据过滤条件的语义分类决定是否消耗 TR1。

---

## 附录 E：实现变更清单

基于附录 D 的分析，以下是具体的代码变更：

### E.1 删除结构紧邻约束

**位置**：第 248-259 行

**动作**：删除以下代码

```python
# 检查结构紧邻约束：当前 trough 必须是 TR1 之后的第一个 trough
first_trough_after_tr1 = None
for t in troughs:
    if t.index > tr1_idx:
        first_trough_after_tr1 = t
        break

if (
    first_trough_after_tr1 is None
    or first_trough_after_tr1.index != trough.index
):
    continue
```

### E.2 保持不变的部分

以下行为保持不变：

1. `max_gap_days` 过滤 → 消耗 TR1 ✓
2. `tr2_price <= tr1_price` 过滤 → 消耗 TR1 ✓（TR2 取代 TR1 成为新最低点）
3. `not is_valid_bounce` 过滤 → 消耗 TR1 ✓
4. `min_tr2_depth` 过滤 → 不消耗 TR1 ✓
5. `min_recovery_pct` 过滤 → 不消耗 TR1 ✓
6. 成功生成信号 → 消耗 TR1 ✓

### E.4 测试用例建议

实现变更后，应测试以下场景：

1. **基本双底**：TR1 + 第一个 trough 形成有效双底 → 行为不变
2. **深度过滤重试**：T1 深度不够，T2 深度足够 → T2 应与 TR1 配对
3. **价格过滤重试**：T1 <= TR1，T2 > TR1 → T2 应与 TR1 配对
4. **反弹不足放弃**：T1 反弹不够 → 消耗 TR1，T2 不应配对
5. **时间超限放弃**：T1 超过 max_gap_days → 消耗 TR1
6. **多次过滤**：连续多个 trough 因局部属性被过滤 → 最后一个有效应成功
