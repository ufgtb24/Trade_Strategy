# Skill v2 修复执行清单

> **创建日期**：2026-05-06
> **状态**：待执行
> **范围**：5 个修复（peer 化 + single_group 软化 + 删 changelog + 改写"不要做" + LLM-only meta）
> **明确不做**：dim-expert-template 抽取、结构化图像 snapshot、cheap tier、spawn_skip_hints、chart_class multi-pass、方案 C 复合替代

## 背景

`analyze-stock-charts` skill v2 跑完 smoke test（run `2026-05-06_112923_0bea3`）后暴露 2 个核心问题（修复 1+2）。期间审视 prompt 时又发现 3 个 prompt 工程层面的问题（修复 3+4+5）。经过 4 轮 agent team 辩论 + 多份研究文档（见末尾参考），决定只修复这 5 项，跳过其他价值不足的提议。

---

## 修复 1：phase-recognizer 从 gatekeeper 拉回 peer

### 问题陈述

phase-recognizer 当前同时承担两种角色：
- **dim-expert**：负责 structure_phase group 的视角分析（合理）
- **gatekeeper**：通过 `go/no-go` 决议决定整个 skill 是否继续运行（不合理）

`go=false` 触发条件：
1. ≥ 5 张图 `phase != range`
2. ≥ 5 张图 `difficulty ≥ 0.7`
3. 全部图 `in_low_position = false`

任一条件触发 → skip T3/T4/T5/T6 → skill 简化产出 `output_kind: skip_run`。

### 这违反 v2 设计原则

v2 核心原则："视角是友好提示，不是工作边界"。phase-recognizer 用 `phase != range` 一刀切等于"phase 视角是工作边界"——给 phase-recognizer 一个其他 dim-expert 没有的"超然地位"。

### 真实 bug：V 反转 batch 会被误拒

假想场景：5 张全 V 反转图（左半下跌主导，右半 V 启动）：

```
overviewer:
  dominant_class = v_reversal
  homogeneity = pass

phase-recognizer:
  按"突破前主导形态"判定
  5 张全 phase = falling
  触发 ≥5 张 phase != range → go = false
  → skill 拒绝分析 V 反转 batch ❌
```

但 v_reversal 是合法的 chart_class，user 可能就是想研究 V 反转规律。

### 修复方案

**完全删除 phase-recognizer 的 go/no-go 决策权**。

具体改动：

```yaml
# phase-recognizer prompt §5 schema 修改
# 旧：
agent_id: phase-recognizer
go: true                  # ← 删除
go_reason: "..."          # ← 删除
chart_phases: ...

# 新：
agent_id: phase-recognizer
chart_phases: ...         # phase 字段保留作信息（不阻塞）
```

**早停权限上移到 skill 入口**。在 spawn dim-expert 之前判定：

```python
# skill 入口在 T1 (overviewer) 完成后判定
batch_data = read(run_dir/"findings.md ## 1.gestalt")
median_difficulty = median([c.difficulty for c in batch_data.chart_phases])

if median_difficulty >= 0.7:
    output_kind = "skip_run"
    skip_reason = "median difficulty too high (信息不足)"
elif batch_data.batch_homogeneity.homogeneity_decision == "reject":
    output_kind = "skip_run"
    skip_reason = "class 混杂度过高"
else:
    继续 spawn T2/T3/T4/T5（全部 blockedBy=T1，并行）
```

**task DAG 简化**：

```
旧:
T1 → T2 → (T3 ∥ T4 ∥ T5) → T6 → T7

新:
T1 → (T2 ∥ T3 ∥ T4 ∥ T5) → T6 → T7
```

phase-recognizer (T2) 与其他 dim-expert 平级，4 个 dim-expert 同时启动。

### 实施步骤

| Step | 改动 | 文件 | 估时 |
|---|---|---|---|
| 1 | 删除 phase-recognizer prompt §5 中 `go` / `go_reason` 字段 | `prompts/phase-recognizer.md` | 10 min |
| 2 | 删除 §5.1 中所有 go=false 触发规则段落 | `prompts/phase-recognizer.md` | 5 min |
| 3 | 删除 §7 完成信号中"go=false 时通知 lead 跳过下游"分支 | `prompts/phase-recognizer.md` | 5 min |
| 4 | 修改 SKILL.md §5.2 task DAG 表，T2/T3/T4/T5 全部 blockedBy=T1 | `SKILL.md` | 10 min |
| 5 | 在 SKILL.md §3 / §5 加入"skill 入口在 T1 后判定 skip_run"逻辑 | `SKILL.md` | 30 min |
| 6 | 修改 synthesizer prompt §2 必读资源，删除"读 phase-recognizer 的 go 字段"引用 | `prompts/synthesizer.md` | 10 min |
| 7 | mixed tier 中 phase-recognizer 同步降到 sonnet（peer 化后无 opus 算力溢价必要）| `SKILL.md` 模型表 | 5 min |

总估时：**约 1 小时纯改动**，加测试约 **半天**。

### 风险与回滚

| 风险 | 影响 | mitigation |
|---|---|---|
| skill 入口缺乏细粒度 phase 判断（phase-recognizer 有的 base_duration / vol_squeeze 等数据）做 skip 决策 | 早停时机可能偏迟 | overviewer 的 difficulty + homogeneity 已经够用；phase-recognizer 的细节字段在 v2 已转为辅助信息 |
| 4 dim-expert 并行启动后 race condition（如同时读 findings.md）| 运行时错误 | 各 dim-expert 写不同 yaml 段（## E1/E2/E3/E4），物理隔离不冲突 |
| 旧版 finding（v1.4）中含 phase-recognizer go 字段的 yaml 被误读 | 新 synthesizer 解析失败 | synthesizer 的 yaml 解析容错跳过未知字段 |

**回滚**：git revert 单 commit 即可（所有改动在 `prompts/phase-recognizer.md` + `SKILL.md` + `prompts/synthesizer.md` 三处）。

---

## 修复 2：single_group_combo rule 软化

### 问题陈述

skill v1.4 引入硬约束：

> 每条入库规律的 `perspectives_used` 必须**跨 ≥ 2 个独立 merge_group**，否则 reject。

smoke test 中 12 条候选规律，**7 条因 single_group_combo 被 reject**（占失败首因）。

### 这条规则的设计困境

- **完全保留（硬约束）**：太苛刻。逐条审视，7 条 reject 中只有 ~1 条是真伪多视角（如 e1-01 [A,D,E] 同函数源），其余 ~3 条真有价值（trigger 锚点独立但 group 同），~3 条与 cross_group rule 无关（其他 filter 已能拦）。**精度仅 ~1/7**，不到合格硬约束应有的 80%。
- **完全取消（裸软化）**：会让 e1-01 这种真伪多视角进库。
- **方案 C（5 组件复合替代）**：在 LLM-only 环境中其"确定性算法"实际仍是 LLM 跟结构化规则——多了一个 `_meta/depends_on_families.md` 维护表 + synthesizer cross-group 合成层 + decoupling_check + `_single_dim/` 旁路。**复杂度过高**，工程量 ~3 天，多个新组件需测试。

User 判断："**硬性判定太苛刻，软性判定太复杂**"——需要 middle ground。

### 修复方案：仅做 confidence 分层（最简）

**唯一改动**：cross_group_diversity 从硬约束降级为**纯 confidence cap**。

- single-group finding：**允许入库**，但 `confidence` 上限为 `medium`（永远不能 high）
- cross-group finding：可达 `confidence: high` 进入 mining

不引入：
- ❌ decoupling_check（方案 C 提议的，需要 LLM 跟结构化规则，复杂度高）
- ❌ synthesizer cross-group 合成层（额外 LLM 调用 + 剪枝逻辑）
- ❌ `_single_dim/` 旁路目录结构
- ❌ `_meta/depends_on_families.md` 物理量族映射表
- ❌ Option β 的跨 batch 自动 promote

### 接受的 trade-off

承认：少量 e1-01 类真伪多视角会以 `confidence: medium` 进入主库。

mitigation（**全部依赖 v2 既有机制，无需新增**）：
1. **mining 不取 medium**：`mining_mode: ready_for_mining` 仅在 confidence=high 时为 true（既有逻辑）。e1-01 永远进不了 mining，对下游因子化无污染
2. **user 视为辅助资源**：medium 规律是 user 探索 / 跨 batch 联立的素材，不是终产物
3. **库膨胀控制**：02 §C.9 已有"单 chart_class > 12 触发合并提议"机制
4. **advocate 仍可 block_promotion**：advocate 5 项校验中如果发现某条 single-group 是明显伪多视角（如 e1-01 同函数源），仍可标 challenged_status=blocked，进 `_retired/`。这是**手动兜底**而非自动检查

### 实施步骤

| Step | 改动 | 文件 | 估时 |
|---|---|---|---|
| 1 | 修改 synthesizer prompt §4 校验清单：`cross_group_diversity=false` 不再 reject，改为 `confidence_cap: medium` | `prompts/synthesizer.md` | 30 min |
| 2 | 修改 02_memory_system.md §C.7 状态机：single-group hypothesis 可入库，但晋级路径上限 partially-validated（不能 validated）| `references/02_memory_system.md` | 30 min |
| 3 | 修改 03_team_architecture.md §5.2 group 多样性约束段：从"硬约束"改为"confidence 软分层"| `references/03_team_architecture.md` | 30 min |
| 4 | 修改 4 dim-expert prompts §6 防偏差 #1：从"≥ 2 视角且跨 ≥ 2 group 必填"改为"≥ 2 视角必填；跨 group 推荐但非必须，single-group finding confidence 上限 medium"| 4 个 prompts/*.md | 1 hour |
| 5 | 修改 advocate prompt 的 5 项校验 #1：从"perspectives_used 跨 ≥ 2 group"改为"perspectives_used ≥ 2"（删除跨 group 部分）| `prompts/devils-advocate.md` | 15 min |
| 6 | schema_version 升级到 2.1.0，加注释说明本次软化 | `_meta/schema_version.md` | 10 min |

总估时：**约 3 小时纯改动**，加测试约 **半天**。

### 实施后的预期效果（用 smoke test 数据推演）

按本次修复后的规则跑同样 smoke test：

| rule_id | 旧规则下 | 新规则下 |
|---|---|---|
| e1-01 [A,D,E] | reject | confidence=medium 入库（虽然真伪多视角，但 advocate 可手动 block）|
| e1-02 [A,D] | reject (3 主因之一是 single_group)| 仍 reject（per_batch_coverage=0.50 + advocate strong + chart8_failed 三道独立 filter 拦）|
| e1-03 [A,E,I] | reject | 仍 reject（clarity_threshold I 缺数据 + coverage 存疑）|
| e2-01 [B,F] | reject | confidence=medium 入库（trigger 逻辑独立，真有价值）|
| e3-01 [C,H] | reject | confidence=medium 入库（vol drought to burst 真信号）|
| e3-02 [C,H] | reject (single_group) | 仍 reject（per_batch_coverage=0.25 单图证据）|
| e3-03 [C,H,D] | reject | confidence=medium 入库（philosopher 理想 α 案例，跨时段独立）|
| e4-01 [G,C] | accept | accept (cross_group → confidence 可 high，与现状一致) |
| e4-02 [G,B] | reject (clarity)| 仍 reject（advocate block_promotion + clarity_threshold）|
| e4-03 [G,A] | accept | accept (cross_group → confidence 可 high) |

**入库率从 17% (2/12) 提升到 ~50% (6/12)**。其中 4 条新增的全是 confidence=medium，不进 mining，但成为 user 探索素材。

### 风险与回滚

| 风险 | 影响 | mitigation |
|---|---|---|
| e1-01 类真伪多视角进库（confidence=medium）| 库 medium 池有低质量条目 | mining 不取 medium，对因子化无污染；advocate 可手动 block 明显伪多视角 |
| 跨 batch 同 finding 用不同 perspectives 命名（一次 [A,D]，一次 [A,B]），库变得难 dedup | 库膨胀 | 02 §F.3 dim_sim 跨 batch 同义判断保留；library bloat control（02 §C.9）仍有效 |
| user 看到大量 medium 规律困惑 | UX | confidence 分层让 user 一眼区分 high vs medium；patterns/ 目录默认按 confidence 排序 |

**回滚**：git revert 一个 commit。所有改动在 prompts + references 层的 markdown，无代码改动。

### 与之前讨论方案的关系

| 方案 | 状态 | 备注 |
|---|---|---|
| 当前硬约束 | 被本次修复替换 | 太苛刻，精度仅 1/7 |
| Option β（跨 batch 自动 promote）| **不采纳** | 否定单 batch 分析价值；伪多视角跨 3 batch 还是伪多视角 |
| 方案 C（5 组件复合替代）| **不采纳** | 复杂度过高；其"确定性算法"在 LLM-only 环境中实际仍是 LLM 跟结构化规则，hidden assumption 多 |
| **本方案（纯 confidence cap）** | 采纳 | 工程量最小（~3 小时），接受少量 medium-cap 伪多视角进库的代价 |

---

## 修复 3：删除 prompt 中的开发过程叙述

### 问题陈述

5 个 dim-expert prompts 在第 1 段后含有"v2 重要变更"/"v1.4 双结构职责"/"v2 新增职责"等 changelog 段，描述这次升级改了什么。这些内容是**开发文档**而不是 **agent prompt**——agent 不需要知道历史，只需要知道当前怎么做。

具体位置（`grep -nE` 全表）：

| 文件 | 行号 | 类型 |
|---|---|---|
| `prompts/phase-recognizer.md` | :7 | `**v2 重要变更**：` |
| `prompts/resistance-cartographer.md` | :7 | `**v2 重要变更**：` |
| `prompts/volume-pulse-scout.md` | :7 | `**v2 重要变更**：` |
| `prompts/launch-validator.md` | :7 | `**v2 重要变更**：` |
| `prompts/launch-validator.md` | :17 | `**v2 视角拓展（实验性）**：` + 引用外部 dimension_review_2026-05-04 报告 |
| `prompts/devils-advocate.md` | :7 | `**v1.4 双结构职责**：` |
| `prompts/synthesizer.md` | :7 | `**v2 新增职责**：` |
| `prompts/synthesizer.md` | :13 | `**v2 删除职责**：` |
| `prompts/synthesizer.md` | :131 | `**v2 不再输出**：` |

约 9 处。

### 修复方案

按 changelog 性质分两类处理：

**类型 1：纯历史叙述**（如"v2 删除职责"/"v2 不再输出"）→ **直接删除**

这类内容描述 agent **不再做**什么。删除后 agent 只看到当前应该做什么，不会被历史负担干扰。

**类型 2：现状被包装成历史**（如"v2 重要变更：视角不是工作边界"）→ **改写为正向当前状态**

例：

```markdown
# 旧
**v2 重要变更**：
1. **视角不是工作边界**：你的专长方向是 checklist 提示，不是限制
2. **开放观察优先**：先问"为什么上涨"...

# 新（融入 §1 你是谁）
你的专长方向（pricing_terrain）是 checklist 提示，不是工作边界——
人人可发现任何视角的现象。先问"为什么这只股票上涨"，
再用 9 视角 checklist 防遗漏。
```

**外部研究文档引用**（`launch-validator §17` 的 `dimension_review_2026-05-04`）→ **删除引用，保留实质内容**

agent 不应该读外部 dev 文档。把"如发现 BO 序列拓扑现象"这一实质指引保留，但去掉"见 dimension_review_2026-05-04 报告 §2.1"引用。

### 实施步骤

| Step | 改动 | 文件 | 估时 |
|---|---|---|---|
| 1 | 删除 5 dim-expert + advocate + synthesizer 各文件的 changelog 段；保留信息融入相邻段 | 7 prompts | 1 hour |

### 风险

| 风险 | mitigation |
|---|---|
| 删除 changelog 后未来 reviewer 不知"为什么这么设计" | 设计 rationale 已存档在 `docs/research/skill_redesign_principles_2026-05-04.md`，git log 也有记录 |
| 改写"现状被包装成历史"段时丢失精髓 | 改写后用 git diff 人工 review 一次确保信息完整 |

---

## 修复 4：改写"不要做"段为正向描述

### 问题陈述

6 个 prompts 全部含 `## 9. 不要做的事` 段（部分还有 `**你不做**：` 短段）。这类内容增加 LLM 认知负担：

- 模型需要查询"X 是什么"才能知道"不要做 X"
- 大部分情况下模型本来就不会做 X（如"不要建议 FactorInfo 字段"——模型不知 FactorInfo 是什么）
- 个别情况是真实 bias 防御（如"不要把右侧大涨作为 tag"反穿越偏差）

简单删除会丢失第三类的价值。需要按场景分类处理。

### 修复方案（B 方案：正向改写）

**类型 1：其他 dim-expert 的分工**（如"不要分析量价"——这是 volume-pulse-scout 的事）→ **直接删除**

理由：分工已在 §1 你是谁 和 §3 必读资源 / merge_group 字段说明清楚，不需重复 negative form。

**类型 2：真实 LLM bias 防御**（如"不要把右侧大涨作为 tag"——VLM 真实倾向）→ **融入相关字段说明**

例：

```markdown
# 旧（在 §9 不要做的事）
- 不要把右侧大涨作为 tag（避免穿越偏差）

# 新（融入 §5 字段说明）
first_impression 字段：限于"启动前的形态"
（窗口截掉右侧已涨段后的形态描述）
```

**类型 3：命名空间隔离**（如"不读 factor_registry.py"）→ **改写为正向资源声明**

例：

```markdown
# 旧
- 不读 factor_registry.py

# 新（融入 §3 必读资源）
**必读资源不含** `factor_registry.py`。formalization 用通用伪代码即可
（如 `amplitude / atr_ratio / percentile`），不引用具体因子名。
```

**类型 4：禁令型**（如"不要修改 patterns/* 或 chart_classes.md"——synthesizer 是唯一写入者，其他 agent 应只读）→ **融入 §4 写权限段**

§4 已经说明各 agent 的写权限范围，不需要在 §9 重复"不能写 X"。

### 范围

6 prompts × 1 个 `## 9 不要做的事` 段（约 4-8 条 each）+ 4 prompts 中的 `**你不做**：` 短段 = 共约 30-40 条 negative items 需分类处理。

### 实施步骤

| Step | 改动 | 文件 | 估时 |
|---|---|---|---|
| 1 | 对每条 negative item 按类型 1/2/3/4 分类 | 6 prompts | 30 min |
| 2 | 类型 1（分工）直接删除 | 6 prompts | 15 min |
| 3 | 类型 2（bias 防御）融入相关字段说明 | 6 prompts | 45 min |
| 4 | 类型 3（命名空间）改写为资源段 | 6 prompts | 15 min |
| 5 | 类型 4（禁令）确认 §4 已覆盖即删 | 6 prompts | 15 min |
| 6 | 删除 `## 9` 整段（如该段已空）| 6 prompts | 5 min |

总估时：**约 2 hours**。

### 风险

| 风险 | mitigation |
|---|---|
| 类型 2 改写时遗漏真实 bias 防御 | 改写前对每条做"模型真实会犯吗"评估；不确定的保留正向版宁可冗余 |
| §9 删除后 prompt 失去"防偏差"段 | 防偏差信息已分散到各字段说明（§5）和 §6 防偏差硬约束段；§6 保留 |
| 不同 dim-expert 的 §9 删除程度不一致 | 用一份分类清单跨 prompt 统一应用 |

---

## 修复 5：锁定 LLM-only 设计原则（meta-rule）

### 问题陈述

之前 single_group_rule 修复的方案 C 提出"`decoupling_check`确定性算法"。但 skill 在 LLM-only 环境运行——synthesizer 没有 Bash/Python 执行权，所谓"确定性算法"实际是 LLM 跟一段结构化规则。这种 hidden assumption 让方案设计偏离实际能力，需要在文档层面**显式锁定**约束。

### 修复方案

不改 prompt，而是在 SKILL.md 加 meta-rule 段。

**位置**：SKILL.md 新增 `## 0.2 设计约束` 段（紧跟 `## 0 Meta-team 不写代码原则`）。

**内容**：

```markdown
## 0.2 设计约束（LLM-only）

所有 skill 行为必须 LLM 可完成。具体约束：

- **不引入** Python/Bash 脚本作为 skill 运行时依赖
- **不引入** 需要外部数据查询（如股票 API / 数据库）的功能——skill 只看 user 提供的 K 线图
- 所有"算法"实质是 LLM 跟结构化规则（yaml 字段比较、set 相等判定、字面匹配等），不是真函数调用

## 判定层级（任何新 fix 提议都按此分类）

| 层级 | 描述 | 允许？ |
|---|---|---|
| L1 | LLM 自由判断（如"这两条规律是否同源？"）| ✅ 允许，但低可靠度 |
| L2 | LLM 跟结构化规则（如"set A == set B？"）| ✅ 允许，主要工作模式 |
| L3 | 真 Python 函数（如 `numpy.corr(x, y)`）| ❌ 禁止 |

任何新 fix 提议如包含 L3 行为，必须在 design 阶段被 reject 或降级到 L2。
```

### 审计结果

当前 skill 已符合此原则：

- synthesizer 的所有"check"是 LLM 跟 yaml 字段规则（L2）
- dim_sim 的 Jaccard fallback 实际是 LLM 算 token 重合（L2，不是真 set 算法）
- 无任何 Bash/Python 调用

**无需重构**，仅添加 meta-rule 文档。

### 对未来 fix 的影响

明确禁止 L3：

- 方案 C 的 `decoupling_check` 如未来要做，必须是 prompt 里给 synthesizer 的结构化规则（L2）
- 跨 batch 同义判断不能用真正的相似度算法（如 cosine sim）—— 必须 LLM 跟 Jaccard 字面或语义判断
- 任何"自动 trigger 检测"不能用 numpy/pandas——必须让 dim-expert 用 LLM 视觉判断

### 实施步骤

| Step | 改动 | 文件 | 估时 |
|---|---|---|---|
| 1 | SKILL.md 加 §0.2 段 | `SKILL.md` | 20 min |
| 2 | references/02_memory_system.md 加注释（指向 SKILL.md §0.2）| `references/02_memory_system.md` | 5 min |
| 3 | references/03_team_architecture.md 同上 | `references/03_team_architecture.md` | 5 min |

总估时：**约 30 min**。

### 风险

| 风险 | mitigation |
|---|---|
| 未来开发者忽视 meta-rule 提议 L3 行为 | §0.2 在 SKILL.md 显眼位置（紧跟 §0），新 fix design 阶段会被看到 |
| L2 与 L3 边界模糊（如 "LLM 跟 numpy 调用拼接"是哪一档？）| 实践中只要不真正 spawn Python 进程就是 L2；prompt 里写 numpy 风格伪代码也是 L2 |

---

## 总实施顺序

5 个修复改的文件高度重叠（都在 prompts/ + SKILL.md + references/）。建议**整合实施**，每个文件改完一次性应用所有相关修复，最终单 commit ("skill v2 → v2.1 cleanup")。

```
Phase 1（半天 + 1 hour）：phase-recognizer peer 化 + 同文件做修复 3+4
  - 改 prompts/phase-recognizer.md（peer + 删 v2 changelog + 改 §9 不要做）
  - 改 SKILL.md task DAG + skip 判定 + 加 §0.2 LLM-only meta-rule
  - 改 prompts/synthesizer.md 引用（+ 删该文件的 v2 changelog）
  - 跑一次 smoke test 验证 (sonnet tier ~$2-5)

Phase 2（半天 + 2 hours）：single_group cap + 同文件做修复 3+4
  - 改 prompts/synthesizer.md 校验（+ 删剩余 v2 changelog 段）
  - 改 4 dim-expert prompts §6（+ 删 v2 changelog + 改 §9 不要做）
  - 改 prompts/devils-advocate.md 校验（+ 删 v1.4 双结构 changelog + 改 §9）
  - 改 prompts/overviewer.md（仅修复 4，无 changelog）
  - 改 references/02 + 03（+ 加 LLM-only meta 引用）
  - 升 schema_version 到 2.1.0
  - 跑一次 smoke test 验证

总工程量：1.5 天（修复 1+2 1 天 + 修复 3+4+5 共 3.5 hours 整合在同 commit）
```

---

## 验证标准

完成后跑两次 smoke test 验证：

### 验证 1：原 5 张 long_base_breakout batch（已有 run）

预期：
- ✅ 入库规律数从 2 → ~6（新增 e1-01 / e2-01 / e3-01 / e3-03 进 medium）
- ✅ 4 dim-expert 并行启动（不再串行等 phase-recognizer）
- ✅ output_kind = `validated_added`
- ✅ written.md 中无 `cross_group_diversity` 作为 reject 原因

### 验证 2：3-7 张 V 反转图 batch（旧版会被误拒）

> Note：本验证需要 user 提供 V 反转形态的 K 线图（v_reversal class）。如暂无，可跳过此验证；Phase 1 smoke test 中观察 task DAG 并行也能确认 peer 化生效。

预期：
- ✅ skill 不拒绝（旧版会 phase-recognizer go=false 拒绝）
- ✅ 4 dim-expert 跑完 cross-image V 反转分析
- ✅ output_kind = `validated_added` 或 `no_new_pattern`（取决于实际能否找到规律）
- ✅ 无 skip_run 状态

---

## 参考文档（不再展开）

| 文档 | 角色 |
|---|---|
| `docs/research/dim_expert_design_review_2026-05-06.md` | 4 角色 review，提出方案 B（已弃用）|
| `docs/research/skill_v2_optimization_2026-05-06.md` | 5 动作优化方案（其他 4 个动作不采纳）|
| `docs/research/2026-05-06_single_group_rule_decision.md` | single_group_rule 方案 C（已弃用，本方案为简化版）|
| `docs/research/dim_expert_template_evaluation_2026-05-06.md` | 模板抽取评估（不采纳）|
| `docs/explain/analyze_stock_charts_logic_analysis.md` | skill 整体说明（实施后需更新 v2.1.0 版本号）|

---

## 实施后需更新

实施完成后顺手更新：

- [ ] `_meta/schema_version.md` 升 2.1.0
- [ ] `docs/explain/analyze_stock_charts_logic_analysis.md` 反映 v2.1.0 变化（约 §4.3 / §6 / §8.5 三处）
- [ ] `.claude/docs/modules/<相关>.md` 如有需要（运行 update-ai-context skill 决定）

完成后**本文档可删除**（属 docs/tmp/，一次性 plan）。
