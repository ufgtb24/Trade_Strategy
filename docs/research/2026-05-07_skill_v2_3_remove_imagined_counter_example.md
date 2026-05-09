# analyze-stock-charts skill — counter_example 与 chart_eight_self_check 的删除论证（v2.3 backlog）

> **状态**：未实施，等下次重构时纳入 v2.3
> **触发**：2026-05-07 user 在 v2.2 run 后审视 advocate §5.B 5 项校验，质疑其中 3 项的实际价值
> **结论**：advocate §5.B 缩为 2 项；删除 `counter_example` / `counter_search_path` / `counterexample_search_protocol` 三个字段
> **影响**：纯精简，不破坏防御链；v2.3 schema_version 升级

---

## 1. 背景

skill v2.2 中，dim-expert 每条 finding 必填以下字段：
- `counter_example`：用一句话描述"触发 trigger 但实际不发生上涨"的样本形态
- `counter_search_path`：把假说翻译成可代码化的反例搜索 query

advocate §5.B 写库前 5 项强制校验中，3 项与上述字段挂钩：
- 第 3 项 `counter_example_quality`：counter_example 必须具体非空
- 第 4 项 `counter_search_path_executability`：search path 必须可代码化
- 第 5 项 `chart_eight_self_check`：finding 必须能回答"为何图 8 类型样本（无预兆型）找不到该信号但仍上涨"

本文档记录对这 3 项的批判 + 删除提案。

---

## 2. 论证 1 — counter_example 是想象的产物，价值近零

### 2.1 三个潜在 bias

1. **想象偏差**：LLM 在只看 5 张已涨图的情况下"想"反例，往往是"应该想到的反例"（教科书案例），而不是真实历史里最常见的反例
2. **同源 bias**：trigger + counter_example 出自同一个思维过程——LLM 脑中的 trigger 模型本身被 5 张图塑造，构造的反例落在它的认知盲区**之外**
3. **概率盲区**：LLM 没有"基础发生率"概念。`counter_example: 高放量但阴线吞没` — 这种形态在所有"高放量样本"中占多大比例？它不知道。如果 95% 的高放量都伴随阴线吞没，那"高放量"本身就不是有效信号

### 2.2 三件事逐项核对

| skill 设计中 counter_example 的预期作用 | 实际效果 | 评判 |
|---|---|---|
| 可证伪性检查（强迫思考反例 → 过滤伪命题）| LLM 总能编出反例描述，校验通过率 ≈ 100%，过滤效果近零 | ❌ 空转 |
| search path 生成（为下游 mining 铺路）| 把 dim-expert 任务从"看图总结共性"扩展到"为下游搜索铺路"——任务蔓延，违背 skill 应专注本职的原则 | ❌ 任务蔓延 |
| 反例验证（影响状态机降级）| LLM 想出反例 ≠ 反例真存在 ≠ 反例多到能否定规律——伪装成验证 | ❌ 已确认无效 |

### 2.3 用户原话

> "可证伪性检查依旧是靠想象，并且总能把一个形态后面想象出一个下跌"
>
> "skill 的职责很简单，就是总结图像共有规律。我不想扩大它的职责范围，最优的选择是让它把有限的算力都集中在总结图像共有规律上，而不是去想象一个形态后面可能会发生什么"

---

## 3. 论证 2 — chart_eight_self_check 误把非必要性当 bug

### 3.1 "图 8" 的定义

不是本次 batch 第 8 张图，而是 skill 设计中的**抽象类型**指代"无预兆型上涨样本"（价格无任何蓄势特征突然爆发的图）。

### 3.2 校验的两个通过条件

| 通过条件 | 措辞 | 问题 |
|---|---|---|
| 答案 A | "承认 trigger 不是充分条件" | 应该是"承认非**必要**条件"——但这是规律的默认状态，不需要承认 |
| 答案 B | "限定 applicable_domain" | applicable_domain 应是"我能预测的图集合"——把它跟"图 8 没命中"挂钩等于循环定义 |

### 3.3 循环定义证明

例：trigger = `long-base + vol_squeeze`，图 8 没 long-base。
- chart_eight_self_check 的"修复"：要求 finding 写 `applicable_domain: "仅 long-base 样本"`
- 但这是把 trigger 重写成 applicable_domain，没增加任何信息
- 对 finding 的实际预测力**没有任何贡献**

### 3.4 核心错误

**chart_eight_self_check 把"规律的非必要性"误判为缺陷**。

但 skill 的本职定位就是找**充分非必要条件**：
- 满足 trigger → 大概率涨（充分性）
- 不满足 trigger → 也可能涨（**非必要性是预期，不是问题**）

→ "图 8 不满足 trigger 但仍涨" 是规律定位的预期现象。把这当作要 finding "回答" 的反驳，逻辑上错位。

### 3.5 用户原话

> "skill 找的本来就是充分非必要条件。股票上涨的条件非常多，如果一个股票上涨却没有满足特定规律，这很正常。你不能指望所有上涨的股票都符合一个规律"

---

## 4. 删除清单

### 4.1 删除的 schema 字段

| 字段 | 出现位置 |
|---|---|
| `counter_example` | 4 dim-expert prompt §5（finding yaml block）+ 02 §B.1 patterns schema + 01 §5.4 |
| `counter_search_path` | 同上 |
| `counterexample_search_protocol` | 02 §B.1 patterns frontmatter |

### 4.2 删除的校验条款

| 条款 | 位置 |
|---|---|
| advocate §5.B 第 3 项 `counter_example_quality` | prompts/devils-advocate.md |
| advocate §5.B 第 4 项 `counter_search_path_executability` | prompts/devils-advocate.md |
| advocate §5.B 第 5 项 `chart_eight_self_check` | prompts/devils-advocate.md |
| synthesizer §4 第 8 项 "图 8 类型反例自检" | prompts/synthesizer.md |

### 4.3 advocate §5.B 缩为 2 项

| # | 校验 | 类型 |
|---|---|---|
| 1 | **perspectives_diversity**（≥ 2 视角）| 结构约束，不依赖想象 |
| 2 | **clarity_threshold**（formalization.pseudocode 非空 + 可量化锚点）| 机械可验证 |

### 4.4 synthesizer §4 12 项校验缩为 11 项

删除第 8 项后顺延（或维持编号 + 标 deleted）。

---

## 5. 防御链完整性核对（删除后）

防幸存者偏差链由以下机制承担。所有保留机制基于**真实观察**或**真实数据触发**，不依赖 LLM 想象：

| 防御机制 | 测的是什么 | 是否保留 | 受影响？|
|---|---|---|---|
| `figure_exceptions`（本 batch 内反例图）| 真实图像观察 | ✅ | 否 |
| `per_batch_coverage < 0.4 → confidence=low` | 真实计数 | ✅ | 否 |
| `cross_image_observation` 必须 cite outlier | 强制看反例图 | ✅ | 否 |
| `unexplained_charts` 诚实失败兜底 | 允许"无规律" | ✅ | 否 |
| advocate §5 Phase 1 `refutes_for_findings`（反方质疑）| LLM 提反例假说 | ✅ | 否（未删除职责 A）|
| advocate §5 Phase 2 全规律巡检（02 §C.10）| 历史规律的反例 | ✅ | 否 |
| advocate §5 Phase 7 `library_doubt_proposals` | 历史规律降级建议 | ✅ | 否 |
| **状态机零容忍降级**（counterexamples ≥ 1 → disputed）| 跨 batch 真实反例触发 | ✅ | 否 |
| **双层 evidence**（distinct_batches ≥ 3 才 validated）| 跨 batch 稳定性 | ✅ | 否 |
| **user gatekeeper**（validated 不自动晋级）| 人审最终防线 | ✅ | 否 |

**结论**：删除的 3 项校验 + 3 个字段全部基于"想象的反例"。保留的所有防御机制基于真实观察、跨 batch 累积、或 user 审查。**删除后防御链完全不受影响**。

---

## 6. 何时实施

不立即实施。归入 v2.3 backlog，等下次合适窗口再统一重构（避免连续多次微调）。

实施时一并考虑：
- schema_version 升级到 2.3
- 已入库的 v2.2 patterns（10 条）的 counter_example / counter_search_path / counterexample_search_protocol 字段：选择 ① 一并清除 ② 标记 deprecated 不再读取 ③ 保留供历史审计
- explain 文档（docs/explain/analyze_stock_charts_logic_analysis.md）需同步更新

---

## 7. 论证 3 — 状态机反例降级机制是死代码 / 逻辑错误

后续讨论（同日 user 审视防御机制时）发现状态机本身也有问题。

### 7.1 两条降级路径核对

synthesizer §6 状态机硬规则：

| 降级触发 | 字段定义 | 触发可能性 | 与"充分非必要"定位是否一致 |
|---|---|---|---|
| `counterexamples ≥ 1 → disputed` | 触发了 trigger 但**不上涨**的样本（"满足条件却反例"）| **永远 0%**——user 永远提供上涨图，"触发但不涨"的样本根本不在 user 输入中 | n/a（触发不了） |
| `should_have_matched_but_failed ≥ 3 → refuted` | 应被规律捕捉但 trigger 没触发，且后续未涨；实际语义 = "漏掉的应匹配的上涨样本"| 完全可能（dim-expert / advocate 标 SHOULD_FAIL）| ❌ **与"充分非必要"直接冲突**（user 已确认 skill 找的是充分非必要条件，漏掉上涨样本是预期不是缺陷）|

### 7.2 用户原话

> "如果是前者（满足规律却不上涨），那么'1 条反例即触发降级'和 per_batch_coverage 的原则是矛盾的。
> 如果是后者（不满足规律却上涨），那么应该永远不可能发现，因为用户永远提供上涨的股票。"

(注：user 第一句的"前者矛盾"实际指向 dead code 问题——`counterexamples` 在 skill 范畴内不可达；第二句指向 `should_have_matched_but_failed` 的逻辑错误)

### 7.3 与 chart_eight_self_check 同源

`should_have_matched_but_failed ≥ 3 → refuted` 与已被否决的 `chart_eight_self_check` 是**同一个设计错误**：

> 把"规律的非必要性"误判为缺陷。

skill 找的是充分非必要条件——"漏掉一些上涨样本"是预期，不是缺陷。所以两个机制都基于错误前提。

### 7.4 v2.3 backlog 追加项

| 删除项 | 位置 |
|---|---|
| `counterexamples ≥ 1 → disputed` 状态机规则 | synthesizer §6 + 02 §C.7 |
| `should_have_matched_but_failed ≥ 3 → refuted` 状态机规则 | synthesizer §6 + 02 §C.7 |
| `evidence.counterexamples[]` 字段 | 02 §B.1 patterns frontmatter |
| `evidence.should_have_matched_but_failed[]` 字段 | 02 §B.1 patterns frontmatter |
| advocate §5 Phase 2 全规律巡检中的 COUNTER / SHOULD_FAIL 标签 | prompts/devils-advocate.md |
| `library_doubt_proposals` 中"counterexamples 计数 / supports > 0.40 触发降级"的逻辑 | prompts/devils-advocate.md §5 Phase 7 |

### 7.5 状态机简化为单向晋级

删除两条降级路径后，状态机退化为：

```
hypothesis → partially-validated → validated（user gatekeeper）
```

无 disputed / refuted 两个旁路态。`_retired/` 目录仍保留供 user 主动归档（例：跨 batch review 时 user 决定某规律不适合）。

### 7.6 防御链替代

降级机制移除后，防御幸存者偏差完全靠：
- **跨 batch 累积要求**（distinct_batches_supported ≥ 3 才晋级 validated）
- **user gatekeeper**（validated 不自动，user 周期性 review）
- **figure_exceptions / per_batch_coverage**（本 batch 内观察反例，影响 confidence）

这些机制都基于真实观察 + user 决策，**不依赖**"反例触发"假设。

---

## 8. 论证 4 — 防御机制 framing 修正

同日 user 审视 figure_exceptions / per_batch_coverage / cross_image_observation 时，揭出 skill 文档（和早期解释）对这些机制的 framing 有误。

### 8.1 figure_exceptions 不是"必须非空"

错误 framing：figure_exceptions 为空 = 伪规律。
正确 framing：**honest declaration**——本 batch 内有不符合的图就必须列入；如果 5/5 全符合，留空合法。

→ 修正各 dim-expert prompt §6 防偏差硬约束的相关措辞。

### 8.2 per_batch_coverage 与 figure_exceptions 不矛盾

| 字段 | 真实语义 |
|---|---|
| per_batch_coverage | 本 batch 内规律的覆盖率，**越高越好**（< 0.4 → confidence low） |
| figure_exceptions | 本 batch 内**不符合规律的图列表**，**可以为空** |

两者一致：高 coverage → exceptions 少（或空）。矛盾感只在错误 framing 下出现。

→ 修正 cross_image_observation 强制要求"必须 cite outlier"的措辞——应改为"如有 outlier 必须 cite，全部一致也合法"。

### 8.3 per_batch_coverage 与 cross_image_observation 部分冗余

| 字段 | 表达层级 |
|---|---|
| cross_image_observation | 质性叙述（含图号引用），强迫 LLM 显式做跨图对比 |
| per_batch_coverage | 量化总结 = `len(figure_supports) / chart_count` |

per_batch_coverage 完全可由 synthesizer 自动从 figure_supports 计算，dim-expert 不必单独填。

→ v2.3 可考虑：dim-expert 不再单独填 per_batch_coverage，由 synthesizer 校验时自动算。

### 8.4 用户原话

> "为什么全部支持就是伪规律？只能说这种情况下可能规律的约束力很弱，但是不能说是违规率吧。"
> "per_batch_coverage 和 figure_exceptions 是不是互相矛盾的？前者希望每张图都命中规律，后者希望不要全部命中。"
> "cross_image_observation 和 per_batch_coverage 是不是重复冗余了？还是说前者是引导 LLM 做出跨图的观察，后者是对前者观察结果的计数？"

### 8.5 figure_exceptions 也是冗余字段（user 后续追问）

user 进一步指出：figure_exceptions 也能由 cross_image_observation 推导得到。核对后发现 figure_exceptions 比 per_batch_coverage **冗余度更高**——有**两条独立推导路径**：

| 路径 | 推导方式 | 难度 |
|---|---|---|
| A | 从 cross_image_observation 叙述抽取（LLM 解析"图 X 不符合"等措辞）| LLM 解析 |
| B | 从 figure_supports + unexplained_charts 取集合补：`exceptions = all_chart_ids - supports - unexplained` | 机械计算 |

→ figure_exceptions 的独立信息量比 per_batch_coverage 还少（per_batch_coverage 只有 1 条机械路径，figure_exceptions 有 2 条）。

### 8.6 schema 最终精简形态

| 字段 | 是否保留 | 推导关系 |
|---|---|---|
| `figure_supports` | ✅ 主字段 | dim-expert 主动判定 |
| `unexplained_charts` | ✅ 主字段 | 诚实兜底 |
| `cross_image_observation` | ✅ 主字段 | 必填叙述，含 outlier 形态细节 |
| `figure_exceptions` | ❌ 删除 | 由 `all_chart_ids - supports - unexplained` 集合补推得；叙述细节已在 cross_image_observation |
| `per_batch_coverage` | ❌ 删除 | 由 `len(supports) / chart_count` 算出 |

synthesizer 校验时机械计算 exceptions 和 coverage，dim-expert 不必单独填。

### 8.7 用户原话

> "和 per_batch_coverage 一样，figure_exceptions 也能由 cross_image_observation 推导得到，对么？"

---

## 9. 此文档的位置

- 路径：`docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md`
- 不是 spec（spec 应在 v2.3 实施前另写为 docs/tmp/<date>_v2_3_*_design.md）
- 是**决策记录**——记录四轮批判 + 结论 + 影响面，供未来重构时直接拿来用，不需要重新论证一遍

---

## 10. v2.3 backlog 总览（汇总各论证）

| 改动 | 来源论证 | 影响 |
|---|---|---|
| 删 `counter_example` / `counter_search_path` / `counterexample_search_protocol` 三字段 | 论证 1 | dim-expert / synthesizer / advocate prompt + schema |
| 删 advocate §5.B 第 3、4 项校验（counter_example_quality / counter_search_path_executability）| 论证 1 | prompts/devils-advocate.md |
| 删 advocate §5.B 第 5 项校验（chart_eight_self_check）| 论证 2 | prompts/devils-advocate.md |
| 删 synthesizer §4 第 8 项校验（图 8 反例自检）| 论证 2 | prompts/synthesizer.md |
| 删 `counterexamples ≥ 1 → disputed` 状态机规则 | 论证 3 | synthesizer §6 + 02 §C.7 |
| 删 `should_have_matched_but_failed ≥ 3 → refuted` 状态机规则 | 论证 3 | synthesizer §6 + 02 §C.7 |
| 删 `evidence.counterexamples[]` / `evidence.should_have_matched_but_failed[]` 字段 | 论证 3 | 02 §B.1 patterns frontmatter |
| 删 advocate §5 Phase 2 全规律巡检的 COUNTER / SHOULD_FAIL 标签（保留 SUPPORT / IRRELEVANT / NO_DATA）| 论证 3 | prompts/devils-advocate.md |
| 删 advocate §5 Phase 7 library_doubt_proposals | 论证 3 | prompts/devils-advocate.md |
| 修正 figure_exceptions framing（不是"必须非空"）| 论证 4 | 4 dim-expert prompt §6 — 同时此字段被 §8.5 论证为可删除 |
| 修正 cross_image_observation framing（"如有 outlier 必须 cite，全部一致也合法"）| 论证 4 | 4 dim-expert prompt §5 / §6 |
| **删 `figure_exceptions` 字段**（由集合补 `all - supports - unexplained` 推得，叙述细节在 cross_image_observation）| 论证 4 §8.5 | 4 dim-expert prompt schema + 02 §B.1 |
| **删 `per_batch_coverage` 字段**（由 `len(supports) / chart_count` 算出）| 论证 4 §8.5 | 4 dim-expert prompt schema + 02 §B.1 |

**advocate §5.B 5 项校验缩为 2 项**（perspectives_diversity + clarity_threshold）。

**synthesizer §4 12 项校验**：删第 8 项（图 8 反例）→ 11 项；进一步可删第 11 项（双层 evidence MERGE 累积，因状态机降级机制移除后该项简化）→ 但保留更稳健，待 v2.3 实施时一并审视。

**状态机简化为单向晋级**：`hypothesis → partially-validated → validated`，无 disputed / refuted 两个旁路态；`_retired/` 仅供 user 主动归档。

**防御链最终形态**（v2.3 后）：
- **真实观察层**：figure_exceptions / cross_image_observation / unexplained_charts（基于本 batch 图像）
- **跨 batch 累积**：distinct_batches_supported ≥ 3（结构性硬约束）
- **user gatekeeper**：validated 不自动晋级（人审）
- **删除**：所有依赖"想象反例"和"必要性误判"的机制
