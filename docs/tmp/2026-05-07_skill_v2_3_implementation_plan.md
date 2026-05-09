# Skill v2.3 — Remove Imagined Counter Mechanisms (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 analyze-stock-charts skill 的"想象的反例"机制（counter_example / chart_eight_self_check / 状态机降级）和冗余字段（figure_exceptions / per_batch_coverage）全部移除；状态机简化为单向晋级；schema 缩到只剩"基于真实观察"的字段。

**Architecture:** 改动横跨 7 prompts + 4 references + SKILL.md + docs/explain + 已有 v2.2 库（10 patterns）。按文件分组任务，每 task 限定单一文件，避免 cross-file 冲突。最后单 commit。

**Tech Stack:** 纯 markdown / yaml frontmatter 编辑（无代码无 TDD）。

**Decision record (spec):** `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md`

**Commit strategy:** 全部改动整合为单 commit `refactor(skill): v2.2 → v2.3 remove imagined counter mechanisms`。

---

## Prerequisites

执行 plan 前确认：

1. **当前在 dev 分支**：`git status` 显示 `On branch dev`
2. **v2.2 commit 已落地**：`git log --oneline | head -5` 应含 `2af8630 refactor(skill): move analyze-stock-charts working dir to experiments/`
3. **decision record 可读**：执行 task 时 implementer 必须先 Read `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md`，特别是 §10 v2.3 backlog 总览表
4. **执行模式**：subagent-driven（每 task dispatch tom implementer + spec-review subagent）；用 `tom` agent type + `model: sonnet`

## File Structure

| 文件 | 改动类型 | 主要内容 |
|---|---|---|
| `.claude/skills/analyze-stock-charts/SKILL.md` | Modify | §5.1 元信息约束 + §5.3 流程映射 + §7 质量门槛去除 counter_example / counter_search_path 引用 |
| `prompts/overviewer.md` | 不改 | overviewer 不涉及 counter_* / 状态机字段 |
| `prompts/phase-recognizer.md` | Modify | §3 / §5 / §6 删 counter_example / counter_search_path / figure_exceptions / per_batch_coverage / 反例搜索清单 / single-image bias 防御措辞 |
| `prompts/resistance-cartographer.md` | Modify | 同上 |
| `prompts/volume-pulse-scout.md` | Modify | 同上 |
| `prompts/launch-validator.md` | Modify | 同上 |
| `prompts/devils-advocate.md` | Modify | §3 / §5 删 counterexample_search_protocol / counter_example / chart_eight 引用；§5.B 5 项校验缩为 2 项；§5 Phase 7 library_doubt 移除 |
| `prompts/synthesizer.md` | Modify | §1 状态机描述 / §4 12 项校验缩为 11 项 / §6 状态机表删降级行 / §11 防偏差硬约束精简 / §13 不要做的事精简 |
| `references/01_analysis_dimensions.md` | Modify | §5.4 finding schema 删 counter_example / counter_search_path / figure_exceptions / per_batch_coverage；§3.5 删图 8 反例描述；§5.1 unexplained_charts 描述保留 |
| `references/02_memory_system.md` | Modify | §B.1 patterns schema 删 counterexamples / should_have_matched_but_failed / counterexample_search_protocol / figure_exceptions / per_batch_coverage 字段；§C.7 状态机表删 disputed / refuted；§F 防偏差硬约束精简 |
| `references/03_team_architecture.md` | Modify | §4.4 advocate 5 项校验缩为 2 项；§5.2 防偏差机制清单移除"想象反例"相关项；§5.3 图 8 反例段重写 |
| `references/00_README.md` | Modify | 顶部状态机说明 / 词典更新（删图 8 / 零容忍 / SHF 等条目）|
| `docs/explain/analyze_stock_charts_logic_analysis.md` | Modify | §4.5 advocate 描述、§4.7 状态机图、§7 设计权衡（v2.3 新增 §7.6 解释删除决议） |
| `experiments/analyze_stock_charts/stock_pattern_library/patterns/long_flat_base_breakout/*.md` × 10 | Modify | 删除 evidence.counterexamples / should_have_matched_but_failed / figure_exceptions / per_batch_coverage / counterexample_search_protocol 字段（forward-only 清理）|
| `experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md` | Modify | 2.2 → 2.3 + 升级历史新行 |

---

## Task 1: SKILL.md 精简

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md`（约 line 470-476, 590-593, 703）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet) 实施：

读 spec `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md` §10 backlog 表。修改 `/home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md`：

**A. §5.1 spawn 元信息 constraints 列表（约 line 466-476）** — 删除两行：

旧：
```
  - perspectives_used 必须 ≥ 2
  - **perspectives_used 必须跨 ≥ 2 个独立 merge_group**（v1.4 group 多样性硬约束 — 同 group 内组合 confidence ≤ medium，由 synthesizer 校验）
  - counter_example 必须非空
  - counter_search_path 必须非空（01 §5.4 强制字段）
  - applicable_domain 字段必须存在（可空表示全域）
  - 允许 honest failure（output_kind: no_new_pattern / skip_run / chart_unexplained / library_doubt）
  - 你的 merge_group: <由 lead 注入 — 见 §5.1 表>，dim-expert 在 finding 中可填 `cross_group_dependency: <其他 group>` 表明需联立
  - agent 间通信使用 7 字段轻量摘要传递 pattern 引用（03 §3.5 / 02 §G.5）
                （id / one_liner / n_supports / n_counterexamples / n_should_have_failed / sample_refs / confidence_score / last_updated_at）
```

新（删 counter_example / counter_search_path 两行 + 改 7 字段摘要的 n_counterexamples / n_should_have_failed → 移除）：
```
  - perspectives_used 必须 ≥ 2
  - **perspectives_used 必须跨 ≥ 2 个独立 merge_group**（v1.4 group 多样性硬约束 — 同 group 内组合 confidence ≤ medium，由 synthesizer 校验）
  - applicable_domain 字段必须存在（可空表示全域）
  - 允许 honest failure（output_kind: no_new_pattern / skip_run / chart_unexplained / library_doubt）
  - 你的 merge_group: <由 lead 注入 — 见 §5.1 表>，dim-expert 在 finding 中可填 `cross_group_dependency: <其他 group>` 表明需联立
  - agent 间通信使用 7 字段轻量摘要传递 pattern 引用（03 §3.5 / 02 §G.5）
                （id / one_liner / n_supports / sample_refs / confidence_score / distinct_batches / last_updated_at）
```

**B. §5.3 流程映射（约 line 590-593）** — 4 行 dim-expert 校验列由"counter_example 非空"改为"figure_supports 非空"：

旧：
```
| S4 | phase-recognizer | `runs/<runId>/findings.md ## E1`（structure_phase 维度发现） | counter_example 非空 |
| S5a | resistance-cartographer | `## E2` yaml findings | counter_example 非空 |
| S5b | volume-pulse-scout | `## E3` yaml findings | counter_example 非空 |
| S5c | launch-validator | `## E4` yaml findings | counter_example 非空 |
```

新：
```
| S4 | phase-recognizer | `runs/<runId>/findings.md ## E1`（structure_phase 维度发现） | figure_supports 非空 |
| S5a | resistance-cartographer | `## E2` yaml findings | figure_supports 非空 |
| S5b | volume-pulse-scout | `## E3` yaml findings | figure_supports 非空 |
| S5c | launch-validator | `## E4` yaml findings | figure_supports 非空 |
```

**C. §7 质量门槛（约 line 700-705）** — 删除 counter_example / counterexample_search_protocol 引用：

旧：
```
- 每条新 hypothesis 都填写了 `counter_example` 和 `counterexample_search_protocol`（02 §B.1）
```

整行删除（保留下一行 perspectives_used.length ≥ 2 不变）。

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|chart_eight\|n_counterexamples\|n_should_have_failed" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md
```
Expected: 0 匹配。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent (model: sonnet)：

验证 SKILL.md 改动符合 v2.3 spec §10 backlog 表中 SKILL.md 相关项：
- §5.1 constraints 不再含 counter_example / counter_search_path
- §5.3 dim-expert 校验列改为 figure_supports 非空
- §7 质量门槛不再含 counter_example / counterexample_search_protocol
- 7 字段摘要改为不含 n_counterexamples / n_should_have_failed
- grep 全清
- 其他章节 untouched

如不符合，返回具体行号 + 问题。

---

## Task 2: 4 个 dim-expert prompts 批量精简

**Files:**
- Modify: `prompts/phase-recognizer.md`
- Modify: `prompts/resistance-cartographer.md`
- Modify: `prompts/volume-pulse-scout.md`
- Modify: `prompts/launch-validator.md`

每个 prompt 应用相同的 5 类改动：

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md` §10 backlog 表 + §8（framing 修正）。对 4 个 dim-expert prompt 应用以下 5 类改动：

### 改动 A: §3 必读资源表 — 删除"反例搜索清单"行

每个 prompt §3 表中含一行：
```
| 反例搜索清单 | 自己 dim 的 patterns 的 `counterexample_search_protocol` | 必须显式回应 |
```
**整行删除**。

### 改动 B: §5 schema yaml 示例 — 删除 4 个字段

每个 prompt §5 schema 示例的 finding yaml block 中含：
```yaml
    figure_exceptions: [图 2, 图 4]               # 该 batch 内反例的图
    per_batch_coverage: 0.6                     # 3/5
```
和：
```yaml
    counter_example: "..."
    counter_search_path: "..."
```

**删除这 4 个字段对应的所有行**（每个 prompt 可能含 1-2 个 finding 示例，全部清除）。

### 改动 C: §5 schema yaml 示例 — historical_protocol_responses 段重写

每个 prompt §5 schema 末尾含：
```yaml
# 历史规律的反例搜索回应（如本批有触发的 protocol）
historical_protocol_responses:
  - pattern_id: R-xxxx
    response: "...建议升 should_have_matched_but_failed"
```

**整段删除**（包括前面的注释行）。

### 改动 D: §5.1（或 §5 写入约束） — 删除强制字段说明

phase-recognizer / resistance-cartographer / volume-pulse-scout / launch-validator 都含类似段落：

旧：
```
- `findings[].counter_example`: 必填非空（01 §5.4）
- `findings[].counter_search_path`: 必填非空（02 §B.1）
```
**整段删除**。

### 改动 E: §6 防偏差硬约束 — 删除 / 修正多条

每个 prompt §6 防偏差硬约束含若干条目：

旧（几乎一致）：
```
2. **counter_example 必填非空**：禁止 "无"、"未知"、空字符串
3. **single-image bias 防御**：若某条 finding 只在 1-2 张图上观察到 → confidence 强制 low（per_batch_coverage ≤ 0.4 自动 low）
4. **cross-image 强制**：你的 findings 必须在 `cross_image_observation` 段引用具体图号（"图 1, 3, 5 都显示..."）+ 标注 outlier 图（"图 4 不符合"）
5. **K cutoff 软建议**：
   - per_batch_coverage ≥ 3/5 → 主推规律（confidence 可 medium / high）
   - per_batch_coverage 1-2/5 → 弱信号或反例 hypothesis（confidence 强制 low；放入 `unexplained_charts` 或 `findings` with low confidence）
```

新：
- 第 2 条 `counter_example 必填非空` → **整条删除**，后续编号不顺移（保留原 1, 3, 4, 5... 编号防止其他文档引用错乱）
- 第 3 条 single-image bias 措辞改为：
```
3. **single-image bias 防御**：若某条 finding 的 figure_supports 仅含 1-2 张图（图数 / chart_count ≤ 0.4）→ confidence 强制 low（synthesizer 校验时自动按 figure_supports 计算覆盖率）
```
- 第 4 条 cross-image 强制 改为：
```
4. **cross-image 强制**：你的 findings 必须在 `cross_image_observation` 段引用具体图号（"图 1, 3, 5 都显示..."）；如本 batch 有 outlier 图，必须 cite 并说明形态差异；全部图一致也合法（不强制必须有 outlier）
```
- 第 5 条 K cutoff 改为：
```
5. **K cutoff 软建议**：
   - figure_supports 数量 ≥ 3/5 → 主推规律（confidence 可 medium / high）
   - figure_supports 数量 1-2/5 → 弱信号或反例 hypothesis（confidence 强制 low；放入 `unexplained_charts` 或 `findings` with low confidence）
```

注意原编号有 6/7/8 等（每个 prompt 略不同），保持其余条目不动。

完成后 grep 验证：
```bash
for f in phase-recognizer resistance-cartographer volume-pulse-scout launch-validator; do
  echo "=== $f.md ==="
  grep -c "counter_example\|counter_search_path\|counterexample_search_protocol\|figure_exceptions\|per_batch_coverage\|should_have_matched_but_failed" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/$f.md
done
```
Expected: 全部 0。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent (model: sonnet)：

对 4 个 dim-expert prompt 验证：
- §3 无"反例搜索清单"行
- §5 schema 示例无 counter_example / counter_search_path / figure_exceptions / per_batch_coverage 字段
- §5 schema 末尾无 historical_protocol_responses 段
- §5.1 字段说明列表无 counter_example / counter_search_path
- §6 第 2 条已删；第 3-5 条已按 v2.3 framing 修正
- 4 个 prompt 改动一致性高（不应有结构性差异）
- grep 全清

返回具体不一致项（如有）。

---

## Task 3: prompts/devils-advocate.md 重写

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/prompts/devils-advocate.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec §10 backlog（advocate 相关条目）+ §7（状态机降级删除）。修改 prompts/devils-advocate.md：

### 改动 A: §3 必读资源表 — 删除两行

旧：
```
| 反例搜索协议清单 | 全部 patterns 的 `counterexample_search_protocol` | 02 §F.4 未来契约：你必须显式回应这些清单 |
```
**整行删除**。

### 改动 B: §5 Phase 1 refutes_for_findings yaml 示例 — 简化

§5 Phase 1 example 中含：
```yaml
    proposed_counter_search: "查找 long-base + long-drought 但 ma_pos > 0 (高于均线) 的样本"
```
**整行删除**。

### 改动 C: §5 Phase 3 historical_protocol_responses 段 — 整段删除

§5 schema 中含：
```markdown
# === Phase 3: 对历史规律的反例搜索协议回应 ===
historical_protocol_responses:
  - pattern_id: R-0001
    protocol_quoted: "..."
    response: "..."
  - pattern_id: R-0019
    protocol_quoted: "..."
    response: "..."
```
**整段删除**（包括 Phase 编号后续顺移，原 Phase 4 → Phase 3，Phase 5 → Phase 4 等，调整 schema 中的编号）。

### 改动 D: §5 Phase 7 library_doubt_proposals 段 — 整段删除

§5 schema 中含：
```markdown
# === Phase 7: 触发 library_doubt（02 §F.3）===
library_doubt_proposals:
  - pattern_id: R-0019
    reason: "..."
    evidence: [...]
```
**整段删除**。

注：删 Phase 3 + Phase 7 后，原 Phase 1 / 2 / 4 / 5 / 6 重编号为 1 / 2 / 3 / 4 / 5（schema 内 + §6 防偏差描述中如有引用 phase 编号需同步）。

### 改动 E: §5.B 5 项校验缩为 2 项

§5.B advocate_block_validations yaml 中含 5 个 check_id：
1. perspectives_diversity ✅ 保留
2. clarity_threshold ✅ 保留
3. counter_example_quality ❌ 删除整 check_id 块
4. counter_search_path_executability ❌ 删除
5. chart_eight_self_check ❌ 删除

**删除 check_id 3, 4, 5 三块（含其内的 passed / challenged_status / reason 字段）**。

### 改动 F: §5.B "5 项校验语义" 段缩为 2 项

旧：
```
**5 项校验语义**：
1. **perspectives_diversity**：...
2. **clarity_threshold**：...
3. **counter_example_quality**：...
4. **counter_search_path_executability**：...
5. **chart_eight_self_check**：...
```

新：
```
**2 项校验语义**：
1. **perspectives_diversity**：perspectives_used ≥ 2（跨 group 推荐但非必须 — synthesizer 会按 cross_group_diversity 字段决定 confidence 上限：cross_group=true 时可达 validated；cross_group=false 时 confidence_cap=medium）
2. **clarity_threshold**：finding.formalization.pseudocode 非空 + 含 ≥ 1 个可量化锚点（时间窗 / 阈值 / 比较对象 / 触发顺序）；不达标 → 否决（写入 unexplained_charts[].clarity_failure_reason）
```

### 改动 G: §6 防偏差硬约束第 3 条 — 删除"图 8 反例的常驻提醒"

旧第 3 条：
```
3. **图 8 反例的常驻提醒**：每条 finding 都自检"图 8 类型上是否找不到该规律但仍可能上涨"——若是，建议 applicable_domain 限定
```
**整条删除**，后续编号不调整（保留 1 / 2 / 4 / 5 / 6 / 7 防止跨文档引用错乱）。

### 改动 H: §1 职责 A 描述精简

§1 含：
```
- **职责 A：反方质疑（refute_notes）**
  - 对每条**新候选规律**提"反例搜索路径"，写入 `should_have_matched_but_failed` 候选项
  - 对每条**历史规律**基于本批 9 图给出 SUPPORT / COUNTER / SHOULD_FAIL / IRRELEVANT / NO_DATA 判断（02 §C.10 全规律巡检）
```

新（移除 should_have_matched_but_failed + 简化巡检标签集）：
```
- **职责 A：反方质疑（refute_notes）**
  - 对每条**新候选规律**提反例的形态描述（写入 refutes_for_findings 段）
  - 对每条**历史规律**基于本批 9 图给出 SUPPORT / IRRELEVANT / NO_DATA 判断（02 §C.10 全规律巡检；v2.3 移除 COUNTER / SHOULD_FAIL 标签——前者在本 skill 范畴不可达，后者与"充分非必要"前提冲突）
```

### 改动 I: §5 Phase 2 crosscheck_advocate_view yaml — 移除非法标签

§5 Phase 2 含：
```yaml
crosscheck_advocate_view:
  - chart_id: C-xxx-1
    pattern_id: R-0007
    dim_expert_label: SUPPORT
    advocate_label: SHOULD_FAIL        # 你的修正
    reason: "..."
```

新：
```yaml
crosscheck_advocate_view:
  - chart_id: C-xxx-1
    pattern_id: R-0007
    dim_expert_label: SUPPORT          # SUPPORT | IRRELEVANT | NO_DATA
    advocate_label: IRRELEVANT         # 仅可使用 SUPPORT / IRRELEVANT / NO_DATA
    reason: "..."
```

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|chart_eight\|图 8\|should_have_matched_but_failed\|library_doubt\|SHOULD_FAIL\|^[ ]*COUNTER" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/devils-advocate.md
```
Expected: 0 匹配（除 advocate_label 注释中"COUNTER"作为 v2.2 残留说明不允许，但本 task 已用 IRRELEVANT 替换不应再有 COUNTER 字样）。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent (model: sonnet)：

验证 devils-advocate.md：
- §3 无 counterexample_search_protocol 行
- §5 Phase 1 yaml 无 proposed_counter_search 字段
- §5 Phase 3 historical_protocol_responses 整段已删
- §5 Phase 7 library_doubt_proposals 整段已删
- Phase 编号已重整为 1-5（如 implementer 选择重编号）或保留原编号但相关段已空
- §5.B 仅含 2 个 check_id（perspectives_diversity / clarity_threshold）
- §5.B 校验语义段为 2 项
- §6 第 3 条"图 8 反例常驻提醒"已删
- §1 职责 A 描述含"v2.3 移除 COUNTER / SHOULD_FAIL"说明
- grep 全清

返回具体不一致项。

---

## Task 4: prompts/synthesizer.md 重写（最复杂）

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec §10 backlog（synthesizer 相关 + 状态机简化）。修改 prompts/synthesizer.md：

### 改动 A: §1 职责描述

旧：
```
- **5 态状态机**：`hypothesis → partially-validated → validated`，旁路 `disputed` / `refuted`（终态移入 `_retired/` **物理保留**，不删除）
```

新：
```
- **3 态状态机**（v2.3 简化）：`hypothesis → partially-validated → validated`（单向晋级，无 disputed / refuted 旁路）；`_retired/` 仅供 user 主动归档（不再由状态机自动移入）
```

### 改动 B: §4 12 项校验缩为 9 项

§4 列表项中删除：
- 第 4 项 `counter_example 非空`
- 第 5 项 `counter_search_path 非空`
- 第 6 项 `figure-level evidence 完整`（提及 figure_exceptions / per_batch_coverage 三字段）→ 改为 `figure_supports 非空`
- 第 7 项 `per_batch_coverage 与 confidence 一致` → 改为 `figure_supports 数量与 confidence 一致：< 0.4 × chart_count → confidence 强制 low`
- 第 8 项 `图 8 类型反例自检`

最终 §4 含 9 项（原 1, 2, 3, 6改, 7改, 9, 10, 11, 12 重编号为 1-9）。原编号到新编号映射：

```
1 → 1 (perspectives_used.length ≥ 2)
2 → 2 (跨 group 多样性)
3 → 3 (清晰度门槛)
4 (counter_example) → 删
5 (counter_search_path) → 删
6 → 4，改为 "figure_supports 非空"
7 → 5，改为 "figure_supports 数量与 confidence 一致"
8 (图 8 反例自检) → 删
9 → 6 (chart_class 一致性)
10 → 7 (同 chart_class 内 dim_sim)
11 → 8 (双层 evidence 累积)
12 → 9 (不引用 codebase 因子名)
```

### 改动 C: §6 状态机表

旧：
```
| 当前状态 | 晋级目标 | 条件 |
|---|---|---|
| hypothesis | partially-validated | distinct_batches_supported ≥ 2 AND total_figure_supports ≥ 4 AND counterexamples = 0 |
| partially-validated | validated | distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9 AND counterexamples = 0 AND should_have_matched_but_failed = 0 AND `confidence_cap` 字段未设（含 `confidence_cap: medium` 时此行不适用，停留在 partially-validated）|
| 任意 | disputed | counterexamples ≥ 1（强反例触发零容忍降级）|
| 任意 | refuted | should_have_matched_but_failed ≥ 3 |
```

新：
```
| 当前状态 | 晋级目标 | 条件 |
|---|---|---|
| hypothesis | partially-validated | distinct_batches_supported ≥ 2 AND total_figure_supports ≥ 4 |
| partially-validated | validated | distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9 AND `confidence_cap` 字段未设（含 `confidence_cap: medium` 时此行不适用，停留在 partially-validated）|

> v2.3：移除 `disputed` / `refuted` 旁路状态。前者基于 `counterexamples ≥ 1`（在本 skill LLM-only / 仅看上涨图的设定下永远不可达）；后者基于 `should_have_matched_but_failed`（与"充分非必要"前提冲突）。状态机简化为单向晋级。
```

### 改动 D: §8 写权限表 — 修改 `_retired/` 行

旧：
```
| `{library_root}/patterns/_retired/*.md` | S8（移动 disputed/refuted — **物理保留**） |
```

新：
```
| `{library_root}/patterns/_retired/*.md` | 仅 user 手动归档（synthesizer v2.3 不再自动移动） |
```

### 改动 E: §9 Stage 4.3 既有 pattern 状态机更新 — 删降级路径

§9 Stage 4.3 含：
```
  - 应用 §6 状态机晋级判定表：
      hypothesis → partially-validated:
        distinct_batches_supported ≥ 2 AND total_figure_supports ≥ 4 AND counterexamples == 0
      partially-validated → validated（user gatekeeper）:
        distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9 AND
        counterexamples == 0 AND should_have_matched_but_failed == 0
        → 不自动晋级，写入 _meta/proposals.md "## validation_ready" 段等 user 决议
      旁路：
        - counterexamples ≥ 1 → disputed（强反例零容忍降级）
        - should_have_matched_but_failed ≥ 3 → refuted

  - 设置 confidence.blocked_from_promotion 字段：
    若 counterexamples ≥ 1 或 should_have_matched_but_failed ≥ 1 → blocked_from_promotion = true
```

新：
```
  - 应用 §6 状态机晋级判定表：
      hypothesis → partially-validated:
        distinct_batches_supported ≥ 2 AND total_figure_supports ≥ 4
      partially-validated → validated（user gatekeeper）:
        distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9
        → 不自动晋级，写入 _meta/proposals.md "## validation_ready" 段等 user 决议

  - 旁路降级路径（disputed / refuted）已在 v2.3 移除
  - blocked_from_promotion 字段已废弃（v2.3 起不再写入；旧 patterns 中此字段被忽略）
```

### 改动 F: §9 Stage 6.2 advocate 5 项校验对接 — 改为 2 项

§9 Stage 6.2 含：
```
1. 每条新规律的 counterexample_search_protocol 字段非空？
2. 新规律 confidence.status 是否被强制为 hypothesis？
3. 全规律巡检矩阵是否完整（含你刚填补的 IRRELEVANT）？
4. 卡在 partially-validated 的规律，proposals.md 是否含"反例搜索任务"传给下次 run？
5. 即将晋级 validated 的规律，是否同时满足：
   n_supports ≥ 3 AND distinct_runs ≥ 3 AND n_counterexamples == 0 AND n_should_have_failed == 0？
```

新：
```
1. 新规律 confidence.status 是否被强制为 hypothesis？
2. 全规律巡检矩阵是否完整（含你刚填补的 IRRELEVANT；标签集仅 SUPPORT / IRRELEVANT / NO_DATA）？
3. 即将晋级 validated 的规律，是否同时满足：
   n_supports ≥ 3 AND distinct_runs ≥ 3？

任一项失败 → advocate 标 block-promotion → 你必须修正后再次提交校验。
```

### 改动 G: §9 Stage 6.3 三字段保留 — 整段删除

§9 含：
```
#### 6.3 反对意见的三字段保留

advocate 给的每条反对都含 `raised_at / raised_by / reason` 三字段。你写入主库 patterns/*.md 的 `evidence.counterexamples[]` 时**必须保留**这三字段，不能简化。
```

**整段删除**（counterexamples[] 字段已废弃）。

### 改动 H: §9 Stage 7 自检 12 项 → 9 项

按 §4 改动 B 同步精简（删原第 4, 5, 8 项；改第 6, 7 项措辞）。

### 改动 I: §9 Stage 8 STEP 3.c — 删除 disputed/refuted 物理保留

旧：
```
STEP 3.c: 移动 disputed/refuted 的规律到 patterns/_retired/（**物理保留**，不删除）
```

**整行删除**（v2.3 状态机不再产生 disputed/refuted）。

### 改动 J: §11 防偏差硬约束精简

§11 列表删除：
- 第 2 项 `零容忍反例` (counterexamples / should_have_matched_but_failed)
- 第 7 项 `物理保留` (disputed/refuted 移入 _retired/)
- 第 11 项 `三字段保留`

### 改动 K: §13 不要做的事 — 删除 disputed/refuted 相关条款

§13 删除：
```
- 不要删除任何 pattern 文件（disputed/refuted 移入 _retired/ 物理保留）
```
（v2.3 不再有 disputed/refuted 自动转换；保留"不要删除任何 pattern 文件"措辞改为：）

新：
```
- 不要删除任何 pattern 文件（如 user 主动 retire 也仅由 user 操作）
```

### 改动 L: §10 output_kind 决策表 — 删除 library_doubt

旧表中含：
```
| 某历史规律本批反例 > 支持 → advocate library_doubt | `library_doubt`（混合标） |
```
**整行删除**。`library_doubt` 状态已无来源。`output_kind` 合法集合从 5 缩为 4：`validated_added / no_new_pattern / skip_run / chart_unexplained`。

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|figure_exceptions\|per_batch_coverage\|should_have_matched_but_failed\|^.*counterexamples\|chart_eight\|disputed\|refuted\|library_doubt\|SHOULD_FAIL\|n_counterexamples\|n_should_have_failed" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/synthesizer.md
```
Expected: 仅在"v2.3 移除"说明性段落中允许出现（描述被删除的旧机制），其余位置 0 匹配。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent (model: sonnet)：

验证 synthesizer.md：
- §1 状态机描述为 3 态单向
- §4 12 项校验缩为 9 项，编号 1-9
- §6 状态机表无 disputed / refuted 行；hypothesis → partially-validated 条件无 counterexamples = 0；partially-validated → validated 条件无 counterexamples / should_have_matched_but_failed
- §6 末尾含 "v2.3 移除..." 说明段
- §8 写权限表 _retired/ 改为 user 手动
- §9 Stage 4.3 / 6.2 / 6.3 / 7 / 8 STEP 3.c 按 spec 改动
- §10 output_kind 表无 library_doubt
- §11 防偏差硬约束已精简（无第 2/7/11 旧项）
- §13 不要做的事已精简

返回具体不一致项。

---

## Task 5: references/01_analysis_dimensions.md 精简

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec §10 backlog（01 相关）。修改 01_analysis_dimensions.md：

### 改动 A: §3.5 诚实失败原则 — 删除"图 8"段

§3.5 描述含：
```
**为什么这条至关重要**：图 8（几乎无预兆型上涨）就是这条原则的典型适用对象。如果团队被迫在每张图上都"找到规律"，结果必然是过拟合的低质量伪规律。**承认无知比编造规律更有价值**。
```

新：
```
**为什么这条至关重要**：如果团队被迫在每张图上都"找到规律"，结果必然是过拟合的低质量伪规律。**承认无知比编造规律更有价值**——某张图所有视角都无信号是合法产出，强迫造规律不是。
```

### 改动 B: §5.1 / §5.4 finding schema yaml — 删除字段

§5.1 / §5.4 中 yaml 示例含：
```yaml
    counter_example: "..."
    counter_search_path: "..."
    figure_supports: [...]
    figure_exceptions: [图 2, 图 4]
    per_batch_coverage: 0.6
```

**删除 counter_example / counter_search_path / figure_exceptions / per_batch_coverage 4 个字段对应行**（保留 figure_supports）。

### 改动 C: §5.4 反例搜索强制规则 — 修订

§5.4 修订规则可能含图 8 / counter_example 引用，例如：
```
| Agent-1 状态识别师 | structure_phase | "查找触发了 phase=range + vol_squeeze 但后续 60 日未启动的样本"。重点反例：下跌中继的横盘（看似 range 实为 distribution）。9 图中**图 8** 类型（涨前几乎无明显蓄势特征）作为关键反例参照，提醒该 agent 不要把"任何长横盘"都当作蓄势 |
```

→ **整行（或整 4 行 agent 表）删除**或简化为不再涉及"图 8"或 counter 概念的说明。

如有 `**关键参照样本**：图 8...`段：
```
**关键参照样本**：图 8（几乎无预兆型上涨）作为整体团队的常驻反例。任何 agent 输出"我看到了显著早期信号"时，必须自检：**这条规律为什么在图 8 中也找不到，但图 8 仍然涨了？** 答案要么是规律确实非充分条件（接受），要么是规律对图 8 类型无效（应限定适用域）。
```
**整段删除**。

### 改动 D: §5.4 unexplained_charts schema — chart_id 示例改

§5.4 yaml 示例含 `<例如 "图 8">` 作为 chart_id 占位：
```yaml
unexplained_charts:
  - chart_id: <例如 "图 8">
```

新：
```yaml
unexplained_charts:
  - chart_id: <例如 "C-xxxxx-3">
```

### 改动 E: 主流程描述中"counter_example 必填" 引用

§5 / §6 / §7 等如有"counter_example 必填非空"等约束，**整行删除**。

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|figure_exceptions\|per_batch_coverage\|图 8\|图8" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md
```
Expected: 0 匹配。

- [ ] **Step 2: spec-review subagent 审核**

验证 01：
- §3.5 不再含"图 8"具体引用
- §5.1 / §5.4 finding yaml 不含 counter_example / counter_search_path / figure_exceptions / per_batch_coverage
- §5.4 关键参照样本（图 8）段已删
- unexplained_charts chart_id 示例不再用"图 8"
- grep 全清

返回具体不一致项。

---

## Task 6: references/02_memory_system.md 精简（最大）

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/02_memory_system.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec §10 backlog（02 相关）。修改 02_memory_system.md：

### 改动 A: §0 章节 1（最小要求字段）

§0 含：
```
1. 规律入库的最小要求字段中**强制包含 `counterexamples` 与 `should_have_matched_but_failed`**（可为空数组，但字段必须存在）。
```
**整条删除**。

### 改动 B: §0 章节 5（counterexample_search_protocol）

§0 含：
```
5. 每条规律必须附 `counterexample_search_protocol` 字段：明确"将来如何从失败 case 中验证它"。
```
**整条删除**。后续编号顺移。

### 改动 C: §A.1 目录树注释 — `_retired/` 描述

旧：
```
│   │   └── _retired/                   ← 被废弃 / refuted 的规律（不删，只移动）
```

新：
```
│   │   └── _retired/                   ← user 主动归档的规律（v2.3 起仅 user 手动操作）
```

### 改动 D: §B.1 patterns schema yaml 整段重写

§B.1 schema 中含字段：
```yaml
  counterexamples:
  should_have_matched_but_failed: []
  counterexample_search_protocol: |
  figure_exceptions: [...]
  per_batch_coverage: 0.6
  per_batch_observations:
    - run_id: ...
      supports: [...]
      exceptions: [...]
      coverage: 0.60
```

**删除字段**：
- `counterexamples` 整段
- `should_have_matched_but_failed` 整行
- `counterexample_search_protocol` 整段
- `figure_exceptions` 整行
- `per_batch_coverage` 整行
- `per_batch_observations.[].exceptions` 子字段
- `per_batch_observations.[].coverage` 子字段

保留：`figure_supports / total_figure_supports / distinct_batches_supported / per_batch_observations.[].run_id / per_batch_observations.[].supports`。

### 改动 E: §B.1 字段语义速查表

字段表中删除：
- `counterexample_search_protocol` 行
- `evidence.distinct_batches_with_full_coverage` 行（per_batch_coverage 已删）
- 状态枚举中 `disputed / refuted` 项 → 改为 `confidence.status enum: hypothesis / partially-validated / validated`

### 改动 F: §C.7 状态机表

§C.7 含状态降级表：
```
| `disputed` | `counterexamples ≥ 1`（强反例触发即降级，零容忍）|
| `refuted` | `should_have_matched_but_failed ≥ 3`（应触发未触发累积达阈值）|
```

**整两行删除**。状态机表只剩 hypothesis → partially-validated → validated 三态。

### 改动 G: §C.7 状态自动降级规则段

§C.7 含：
```
- `validated` 状态下 `n_counterexamples ≥ 1`（任何新反例）→ `disputed`
- `validated` 状态下 `n_should_have_failed ≥ 1` → `disputed`
- `disputed` 状态下 `refute_count > support_count` 持续 N_run 次 → 移入 `_retired/`（保留历史，不删除）
- 任何状态下 `supports == 0 AND counterexamples ≥ 1` → `refuted`（终态，移入 `_retired/`）
```

**整段删除**，替换为：
```
v2.3：状态机简化为单向晋级。`hypothesis → partially-validated → validated`，不再有自动降级路径。
- 移除 `disputed`：基于 `counterexamples ≥ 1`，但本 skill LLM-only 仅看上涨图，counterexamples 不可达
- 移除 `refuted`：基于 `should_have_matched_but_failed`，与"充分非必要"前提冲突
- `_retired/` 仅 user 主动归档（不再由状态机自动移入）
```

### 改动 H: §F 防偏差硬约束 — 精简

§F 各表 / 列表删除引用：
- `counterexample_search_protocol 必填` → 删
- `n_counterexamples ≥ 1 → 不允许 validated` → 删
- `n_should_have_failed ≥ 1 → 不允许 validated` → 删
- 任何提及 SHF / counterexamples 的硬约束 → 删

### 改动 I: §F.4（如有）反例搜索未来契约 — 整段删除

§F.4 描述"counterexample_search_protocol 字段是对未来 run 的硬性指令" — **整段删除**。

### 改动 J: §G（agent 间通信摘要 7 字段）

§G.5 七字段含：
```
n_counterexamples / n_should_have_failed
```

**删除这两个字段**，七字段减为 5 字段：`id / one_liner / n_supports / sample_refs / confidence_score / distinct_batches / last_updated_at`（与 SKILL.md Task 1 改动 A 同步）。

### 改动 K: §A.5 deprecated 标记

§B.1 中如有：
```yaml
counterexamples:                     # [legacy / deprecated for promotion logic]
should_have_matched_but_failed: []   # [legacy / deprecated for promotion logic] ...
```

**整段删除**（v2.3 不再保留 deprecated 字段，patterns 一并清理）。

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|figure_exceptions\|per_batch_coverage\|should_have_matched_but_failed\|n_counterexamples\|n_should_have_failed\|图 8\|图8\|disputed\|refuted\|SHF\|library_doubt" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/02_memory_system.md
```
Expected: 仅在 "v2.3 移除..." 说明性段中允许出现，其余 0 匹配。

- [ ] **Step 2: spec-review subagent 审核**

验证 02：
- §0 章节 1 / 5 已删
- §A.1 _retired/ 注释更新
- §B.1 schema 已删 5 个字段（counterexamples / should_have_matched_but_failed / counterexample_search_protocol / figure_exceptions / per_batch_coverage / observations 子字段）
- §B.1 字段表已同步精简
- §C.7 状态机仅 3 态，无自动降级规则
- §F 防偏差硬约束已精简
- §F.4 已删
- §G.5 七字段缩为 5 字段
- grep 全清（除 v2.3 说明段外）

返回具体不一致项。

---

## Task 7: references/03_team_architecture.md 精简

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/03_team_architecture.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

读 spec §10 backlog（03 相关）。修改 03_team_architecture.md：

### 改动 A: §1（执行总图）章节 6 "图 8 反例 = 压力测试"

§1 含 "6 | 图 8 反例 = 压力测试 | §5.3 ..."，**整行删除**或改为通用诚实失败说明。

### 改动 B: §2.4 / §3 overviewer 段（如含图 8 引用）

如含 "图 8 这种几乎无预兆 case" 等具体描述：
```
- **Overviewer**：01 假定每个 agent 自带视觉感知能力...这会让"图 8 这种几乎无预兆"的 case 被各专家分别"找出"伪规律。
```

新：
```
- **Overviewer**：01 假定每个 agent 自带视觉感知能力...这会让"几乎无预兆"型上涨样本被各专家分别"找出"伪规律。
```
（去掉具体的"图 8"引用）

### 改动 C: §4.4 advocate 5 项校验 → 2 项

§4.4 含 5 项校验描述，按 Task 3 改动 F 同步精简为 2 项（perspectives_diversity / clarity_threshold）。

### 改动 D: §5（防偏差机制清单）

§5 含：
```
| 每条新候选必含 `counter_example` 字段 | 01 §5.4 + 02 §B.1 | dim-expert spawn prompt 显式要求 |
| 每条新候选必有 `counterexample_search_protocol` | 02 §F.1 | synthesizer 自检步 |
| 每条新候选必有 `counter_search_path` 非空（可代码化反例查询） | 01 §5.4 修订 | synthesizer 校验：未填则降级为"待验证"不入库 |
| 图 8 常驻反例自检：每条规律必须回答"为何图 8 找不到该信号但仍上涨" | 01 §5.4 修订规则 4 | synthesizer 强制自检；若无法回答则强制限定 `applicable_domain` |
```

**整 4 行删除**。

### 改动 E: §5.3（图 8 压力测试 / 关键参照样本）

含：
```
**图 8 压力测试**：synthesizer 必须能识别"对图 8 全部专家都给 IRRELEVANT 或 NO_DATA" 而不是强行找规律。
```

**整段删除**或重写为通用诚实失败描述（不引用"图 8"）。

### 改动 F: §5（如有）"counter_example required"代码示例

```python
"counter_example required": True,
```
**整行删除**或改为 `"figure_supports required": True`。

### 改动 G: §3.5 / §5（防偏差三层防御 / 输入层 / 执行层等）

如含：
```
4. **三层防偏差**：输入层 overviewer 打 difficulty 标 + 执行层 dim-expert 必填 counter_example + 审计层 devils-advocate 全局反例搜索 + 状态机 distinct_runs 强制要求。
```

新：
```
4. **三层防偏差**（v2.3 修订）：输入层 overviewer 打 difficulty 标 + 执行层 dim-expert 主动声明 figure_supports + 审计层 devils-advocate 全局规律巡检 + 状态机 distinct_runs / cross_group_diversity 强制要求。
```

### 改动 H: §5（诚实兜底）

如含：
```
5. **诚实兜底**：team 必须支持 `no_new_pattern` / `skip_run` / `chart_unexplained` / `library_doubt` 四种"非积极"产出，图 8 这种无预兆 case 不被强行解释。
```

新：
```
5. **诚实兜底**：team 必须支持 `no_new_pattern` / `skip_run` / `chart_unexplained` 三种"非积极"产出（v2.3 移除 `library_doubt`），无预兆型上涨样本不被强行解释。
```

### 改动 I: §F.4（反例搜索未来契约段，如有）

```
每条入库的新规律必须填写 `counterexample_search_protocol`（02 §B.1），下次 run 在 S2 加载 patterns 时...
```

**整段删除**。

完成后 grep 验证：
```bash
grep -n "counter_example\|counter_search_path\|counterexample_search_protocol\|图 8\|图8\|library_doubt\|chart_eight" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/03_team_architecture.md
```
Expected: 0 匹配（v2.3 说明性引用例外）。

- [ ] **Step 2: spec-review subagent 审核**

验证 03：
- §1 章节 6 / §2.4 / §3 / §5.3 / §5 关于"图 8"具体引用已删
- §4.4 advocate 5 项 → 2 项
- §5 防偏差机制清单 4 行已删
- §5 三层防偏差 / 诚实兜底措辞已修正
- grep 全清

返回具体不一致项。

---

## Task 8: references/00_README.md 精简

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/00_README.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

修改 00_README.md：

### 改动 A: 顶部状态机说明段

含 v1.4 状态机描述：
```
- 防幸存者偏差硬约束（F.x）：counterexample_search_protocol 必填 / **双门槛升级**（v1.4：n_supports ≥ 3 AND distinct_runs ≥ 3）/ **零容忍反例**（v1.4：counterexamples 或 should_have_failed 任一 ≥ 1 阻止晋级 validated）/ should_have_matched_but_failed ≥ 3 触发降级
- 规律不能从 `hypothesis` 直接跳 `validated`，必须经过 `partially-validated`；v1.4 双门槛：升级 validated 需 `n_supports ≥ 3 AND distinct_runs ≥ 3`，且零容忍 counterexamples / should_have_failed
- v1.4 旁路状态：`disputed`（advocate block-promotion 触发）/ `refuted`（counterexamples ≥ 1 + supports == 0），均移入 `patterns/_retired/` 物理保留
```

新：
```
- 防幸存者偏差硬约束（v2.3）：cross_group_diversity 多样性 / 双门槛升级（n_supports ≥ 3 AND distinct_runs ≥ 3）/ figure_supports 主动声明
- 规律不能从 `hypothesis` 直接跳 `validated`，必须经过 `partially-validated`
- v2.3：移除 `disputed` / `refuted` 旁路状态（前者基于 counterexamples 在本 skill 不可达；后者基于 SHF 与"充分非必要"前提冲突）
- `_retired/` 仅供 user 主动归档（不由状态机自动移入）
```

### 改动 B: 词典段

词典中删除条目：
- `**SHF / should_have_matched_but_failed**`
- `**零容忍反例**`
- `**raised_at / raised_by / reason**`
- `**图 8 反例**`
- `**library_doubt**`（如有）

### 改动 C: 状态机层条目

如含：
```
4. **状态层**：distinct_runs 强制时间分散；should_have_matched_but_failed ≥ 3 触发降级
```

新：
```
4. **状态层**：distinct_runs ≥ 3 + total_supports ≥ 9 才晋级 validated（user gatekeeper）
```

完成后 grep 验证：
```bash
grep -n "should_have_matched_but_failed\|SHF\|图 8\|图8\|disputed\|refuted\|library_doubt\|counterexample_search_protocol" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/00_README.md
```
Expected: 0 匹配（v2.3 说明性引用例外）。

- [ ] **Step 2: spec-review subagent 审核**

验证 00 README 改动一致性。

---

## Task 9: docs/explain 同步更新

**Files:**
- Modify: `docs/explain/analyze_stock_charts_logic_analysis.md`

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

修改 docs/explain：

### 改动 A: 标题 / §3.3 表

标题 `v2.2` → `v2.3`。

§3.3 表格补 v2.3 列（或重写为 v2.x 演进表），含：
- 状态机简化（v2.3：3 态，无 disputed / refuted）
- counter_example / chart_eight 移除
- figure_exceptions / per_batch_coverage 移除（schema 精简）

### 改动 B: §4.5 advocate 描述

旧（约 line 137-147）：
```
- **职责 B**：写库前 5 项强制校验，任一失败 synthesizer 不得写库
  1. `perspectives_diversity`：perspectives_used ≥ 2（cross_group 字段记录但不 block）
  2. clarity 门槛
  3. counter_example 存在性
  4. 图 8 反例自检
  5. chart_class 一致性
```

新：
```
- **职责 B**：写库前 2 项强制校验（v2.3 精简，原 5 项中 3 项被论证为伪校验）
  1. `perspectives_diversity`：perspectives_used ≥ 2
  2. `clarity_threshold`：formalization.pseudocode 非空 + ≥ 1 可量化锚点
```

### 改动 C: §4.7 状态机

旧：
```
hypothesis → partially-validated → validated
                                 ↓
                      （confidence_cap=medium 时此跃迁不适用）
                                 ↓
                          停留在 partially-validated
（任意状态）→ disputed (counterexamples ≥ 1)
（任意状态）→ refuted (should_have_matched_but_failed ≥ 3) → 移入 _retired/（物理保留）
```

新：
```
hypothesis → partially-validated → validated（user gatekeeper）
                                 ↓
                      （confidence_cap=medium 时此跃迁不适用）
                                 ↓
                          停留在 partially-validated

v2.3：移除 disputed / refuted 旁路状态。_retired/ 仅 user 主动归档。
```

### 改动 D: §7 设计权衡 — 新增 §7.6

在 §7.5（LLM-only meta-rule）后追加 §7.6：

```markdown
### 7.6 为什么删除 counter_example 等"想象的反例"机制（v2.3）

v2.0/v2.1/v2.2 中，dim-expert finding 必填 counter_example（"想象 trigger 触发但不涨的样本形态"）+ counter_search_path（"如何去历史里找反例"）。advocate §5.B 5 项校验中 3 项（counter_example_quality / counter_search_path_executability / chart_eight_self_check）和状态机的 disputed / refuted 降级都依赖这套机制。

v2.3 整体移除，理由：
1. **想象的反例不能验证规律**：LLM 在只看 5 张已涨图的情况下"想"反例，等于自我审查（无独立信号）
2. **可证伪性检查空转**：LLM 总能编出反例描述，过滤效果近零
3. **chart_eight_self_check 误把非必要性当 bug**：skill 找的是充分非必要条件，"图 8 不满足 trigger 但仍涨"是预期，不是问题
4. **counterexamples ≥ 1 → disputed 是 dead code**：本 skill LLM-only / 仅看上涨图，"满足 trigger 不涨"的样本永远不在 user 输入中
5. **should_have_matched_but_failed ≥ 3 → refuted 与设计前提冲突**：漏掉上涨样本是"非必要"的预期表现，不是缺陷

防御链替代方案（基于真实观察 + 跨 batch 累积 + user gatekeeper）：
- figure_supports 主动声明 / cross_image_observation 跨图叙述（基于本 batch 真实图像）
- distinct_batches_supported ≥ 3（结构性硬约束）
- validated 由 user 周期性 review 决议（user gatekeeper）

详见 `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md`。
```

### 改动 E: §5 输出位置 — 字段精简

如 §5 chart_classes.md 描述含 figure_exceptions / counterexamples 等字段示例，删除。

### 改动 F: §9 已知边界

如有"medium-cap 池低质量...靠 advocate 手动 block_promotion + user retire 兜底"段，更新为 v2.3 表述（advocate block-promotion 移除后，仅依赖 confidence_cap + user retire）。

完成后 grep 验证：
```bash
grep -n "counter_example\|chart_eight\|disputed\|refuted\|图 8\|图8\|should_have_matched\|library_doubt" /home/yu/PycharmProjects/Trade_Strategy/docs/explain/analyze_stock_charts_logic_analysis.md
```
Expected: 仅在 §7.6 v2.3 解释段中允许出现（描述被删除的旧机制），其余 0 匹配。

- [ ] **Step 2: spec-review subagent 审核**

验证 explain doc：
- 标题 v2.2 → v2.3
- §3.3 表含 v2.3 列
- §4.5 advocate 5 项 → 2 项
- §4.7 状态机图无 disputed / refuted
- §7.6 新增解释段
- §9 已知边界已更新
- grep 全清（除 §7.6 解释段）

返回具体不一致项。

---

## Task 10: 现有 v2.2 patterns 数据清理（forward-only 一次性清除）

**Files:**
- Modify: `experiments/analyze_stock_charts/stock_pattern_library/patterns/<chart_class>/R-*__*.md`（数量按实际扫描结果而定，可能为 0 / 10 / 更多）

**前置探查**：

执行 task 前先扫描实际文件清单（不要假设数量）：

```bash
find /home/yu/PycharmProjects/Trade_Strategy/experiments/analyze_stock_charts/stock_pattern_library/patterns/ -name "R-*.md" -not -path "*/_retired/*" 2>/dev/null
```

如返回 0 文件 → **Task 10 跳过**（库为空，无需迁移），直接进 Task 11。

如返回 N 文件 → 对全部 N 文件应用统一清理（不分 chart_class 子目录）。

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

对前置探查列出的所有 pattern 文件应用统一清理。

读 spec §6（清理策略）— **采用选项 1：一并清除**（库为 experimental 状态，forward-only 比 deprecated 标记更干净）。

对每个 R-XXXX__*.md 的 frontmatter 删除以下字段：

```yaml
evidence:
  ...
  counterexamples: 0                              # ← 整行删除
  should_have_matched_but_failed: 0               # ← 整行删除
  figure_exceptions: [...]                        # ← 整行删除
  per_batch_coverage: ...                         # ← 整行删除
  per_batch_observations:
    - run_id: ...
      supports: [...]
      exceptions: [...]                           # ← 子字段删除
      coverage: ...                               # ← 子字段删除
counterexample_search_protocol: |                 # ← 整段删除（如存在）
  ...
confidence:
  ...
  blocked_from_promotion: false                   # ← 整行删除（v2.3 字段废弃）
```

保留：`evidence.distinct_batches_supported / evidence.total_figure_supports / evidence.figure_supports / evidence.per_batch_observations.[].run_id / evidence.per_batch_observations.[].supports`。

完成后 grep 验证：
```bash
grep -rn "counterexamples\|should_have_matched_but_failed\|figure_exceptions\|per_batch_coverage\|counterexample_search_protocol\|blocked_from_promotion" /home/yu/PycharmProjects/Trade_Strategy/experiments/analyze_stock_charts/stock_pattern_library/patterns/
```
Expected: 0 匹配（在所有 chart_class 子目录的 patterns 中）。

注：`description` 段内可能含 counterexample 一词（描述性英文，非字段名）— 这种情况下保留（不影响 schema）。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent (model: sonnet)：

验证 10 个 patterns：
- 每个文件 evidence 块无被删字段
- 每个文件无 counterexample_search_protocol 顶层字段
- 每个文件 confidence 块无 blocked_from_promotion
- 保留字段（distinct_batches_supported / total_figure_supports / figure_supports / per_batch_observations 的 run_id+supports）完整
- 各 description 段内容未被错误修改

返回具体不一致项。

---

## Task 11: schema_version 升级 + run_history.md 添加迁移记录

**Files:**
- Modify: `experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md`
- Modify: `experiments/analyze_stock_charts/stock_pattern_library/_meta/run_history.md`（追加迁移说明）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent (model: sonnet)：

### 改动 A: schema_version.md 升级

**前置探查**：先 Read 当前 schema_version.md 实际内容（不假设是 v2.2）：

```bash
cat /home/yu/PycharmProjects/Trade_Strategy/experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md
```

**操作**（基于读取后的实际内容）：

1. 把 `current:` 行改为 `current: 2.3`（无论原值是 2.2 / 2.1 / 其他）
2. 在 `## 升级历史` 表格末尾追加一行：
   ```
   | 2.3 | 2026-05-07 | remove imagined counter mechanisms — counter_example / chart_eight_self_check / counterexamples / should_have_matched_but_failed / figure_exceptions / per_batch_coverage 字段全部移除；状态机简化为单向晋级（无 disputed / refuted）；advocate §5.B 5 项校验缩为 2 项；synthesizer §4 12 项校验缩为 9 项；详见 docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md |
   ```

如果 schema_version.md **不存在**：跳过 schema_version 改动（库未 bootstrap，下次首次跑时会建）。

如果 `## 升级历史` 段**不存在**：在文件末尾追加该段 + v2.3 行。

注：不用精确 old/new 文本匹配，因 v2.2 文件内容可能已变。

### 改动 B: run_history.md 追加迁移说明

run_history.md 末尾追加一段：

```markdown

## v2.3 schema migration (2026-05-07)

- 现有 10 个 patterns（R-0001 至 R-0010）的 frontmatter 已按 v2.3 schema 清理
- 删除字段：`evidence.counterexamples` / `evidence.should_have_matched_but_failed` / `evidence.figure_exceptions` / `evidence.per_batch_coverage` / `evidence.per_batch_observations.[].exceptions` / `evidence.per_batch_observations.[].coverage` / `counterexample_search_protocol` / `confidence.blocked_from_promotion`
- 保留字段：`evidence.distinct_batches_supported` / `evidence.total_figure_supports` / `evidence.figure_supports` / `evidence.per_batch_observations.[].run_id` / `evidence.per_batch_observations.[].supports`
- 状态机：所有 patterns 维持 hypothesis 状态（无 disputed / refuted 转换）
- patterns_count 不变（10 条）
```

- [ ] **Step 2: spec-review subagent 审核**

验证 schema_version.md 显示 current: 2.3 + 升级历史含 v2.3 行；run_history.md 末尾含迁移说明段。

---

## Task 12: 全局一致性 audit

**Files:** 仅读

- [ ] **Step 1: 全局 grep audit**

Run:
```bash
cd /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo "=== 检查 1: counter_example / counter_search_path（应仅在 v2.3 说明段中残留）==="
grep -rn "counter_example\|counter_search_path" .

echo ""
echo "=== 检查 2: counterexample_search_protocol（应 0）==="
grep -rn "counterexample_search_protocol" .

echo ""
echo "=== 检查 3: figure_exceptions / per_batch_coverage（应 0）==="
grep -rn "figure_exceptions\|per_batch_coverage" .

echo ""
echo "=== 检查 4: counterexamples / should_have_matched_but_failed（应仅在 v2.3 说明段）==="
grep -rn "should_have_matched_but_failed" .
grep -rn "counterexamples" .

echo ""
echo "=== 检查 5: 图 8 / chart_eight（应仅在 v2.3 说明段）==="
grep -rn "图 8\|图8\|chart_eight" .

echo ""
echo "=== 检查 6: disputed / refuted 状态（应仅在 v2.3 说明段；保留 description 文本中的非状态用法）==="
grep -rn "^[ ]*disputed\|^[ ]*refuted\|status: disputed\|status: refuted\|→ disputed\|→ refuted" .

echo ""
echo "=== 检查 7: library_doubt（应 0 或仅在 v2.3 说明段）==="
grep -rn "library_doubt" .

echo ""
echo "=== 检查 8: figure_supports（应保留，多处出现）==="
grep -rln "figure_supports" .

echo ""
echo "=== 检查 9: docs/explain ==="
grep -n "v2.2\|counter_example\|figure_exceptions\|per_batch_coverage\|disputed\|refuted" /home/yu/PycharmProjects/Trade_Strategy/docs/explain/analyze_stock_charts_logic_analysis.md

echo ""
echo "=== 检查 10: patterns 库 ==="
grep -rn "counterexamples\|should_have_matched_but_failed\|figure_exceptions\|per_batch_coverage\|counterexample_search_protocol\|blocked_from_promotion" /home/yu/PycharmProjects/Trade_Strategy/experiments/analyze_stock_charts/stock_pattern_library/patterns/

echo ""
echo "=== 检查 11: schema_version ==="
cat /home/yu/PycharmProjects/Trade_Strategy/experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md
```

Expected:
- 检查 1-4: 0 匹配 OR 仅在 v2.3 说明性段（如 synthesizer §6 末尾、03 §5、explain §7.6）
- 检查 5: 0 匹配 OR 仅在 v2.3 说明性段
- 检查 6: 0 实质 status 引用
- 检查 7: 0 OR 仅说明
- 检查 8: figure_supports 仍在多个文件中（健康）
- 检查 9: docs/explain 无 v2.2 残留（除 §3.3 演进表外）
- 检查 10: patterns 库 0 匹配
- 检查 11: schema_version current: 2.3

- [ ] **Step 2: 全局一致性 review subagent**

dispatch tom subagent (model: sonnet)：

读 spec `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md` §10 backlog 表全文。
扫描以下 14 个文件，验证 v2.3 改动一致性：

- `.claude/skills/analyze-stock-charts/SKILL.md`
- `.claude/skills/analyze-stock-charts/prompts/{phase-recognizer,resistance-cartographer,volume-pulse-scout,launch-validator,devils-advocate,synthesizer}.md`
- `.claude/skills/analyze-stock-charts/references/{00_README,01_analysis_dimensions,02_memory_system,03_team_architecture}.md`
- `docs/explain/analyze_stock_charts_logic_analysis.md`
- `experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md`

跨文件一致性检查：
1. **状态机表述**：所有文件描述为 "3 态单向晋级（hypothesis → partially-validated → validated）"，无文件引用 disputed / refuted 作为活跃状态
2. **advocate §5.B**：所有文件描述为 "2 项校验"（perspectives_diversity / clarity_threshold），无文件引用旧 5 项
3. **synthesizer §4**：所有文件描述为 "9 项校验"（如有提及）
4. **figure_supports**：保留为基于真实观察的字段，不被错误删除
5. **schema_version**：current: 2.3
6. **v2.3 说明性段**：各文件中"v2.3 移除 X" 类描述措辞一致

返回不一致清单（含文件名 + 行号 + 问题）。如全一致，返回 "✅ all consistent"。

- [ ] **Step 3: 修复（如有）**

如 step 1 / step 2 返回不一致，dispatch implementer subagent 修复。fix 后回到 step 1 重跑。

直到 step 1 / step 2 都通过为止。

---

## Task 13: 单 commit

**Files:** 仅 git

- [ ] **Step 1: git status 检查**

Run: `git status --short`

Expected 路径范围（实际数量动态，可能因某 task 跳过而少几个文件）：
- `.claude/skills/analyze-stock-charts/SKILL.md`（Task 1 改）
- `.claude/skills/analyze-stock-charts/prompts/{phase-recognizer,resistance-cartographer,volume-pulse-scout,launch-validator,devils-advocate,synthesizer}.md`（Task 2-4 改）
- `.claude/skills/analyze-stock-charts/references/{00_README,01_analysis_dimensions,02_memory_system,03_team_architecture}.md`（Task 5-8 改）
- `docs/explain/analyze_stock_charts_logic_analysis.md`（Task 9 改）

非 git-tracked（experiments/ 在 .gitignore）：
- `experiments/analyze_stock_charts/stock_pattern_library/_meta/schema_version.md`（Task 11 改，本地有效）
- `experiments/analyze_stock_charts/stock_pattern_library/_meta/run_history.md`（Task 11 改，本地有效）
- `experiments/analyze_stock_charts/stock_pattern_library/patterns/<class>/R-*.md`（Task 10 改，本地有效）

如某文件因实际 grep 结果零匹配而未被 task implementer 修改 → git status 不出现该文件 → 接受（跳过的 task 等于"该文件已是 v2.3 状态"）。

Untracked（spec / plan docs）:
- `docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md`（要 commit）
- `docs/tmp/2026-05-07_skill_v2_3_implementation_plan.md`（不 commit，留作历史）

- [ ] **Step 2: git diff review**

Run:
```bash
git diff --stat .claude/skills/analyze-stock-charts/ docs/explain/
git diff .claude/skills/analyze-stock-charts/SKILL.md  # spot check
git diff .claude/skills/analyze-stock-charts/prompts/synthesizer.md  # 最大变化
```

人工 review 关键点：
- §状态机表 disputed / refuted 行已删
- §4 12 项 → 9 项编号正确
- §5.B 2 项 check_id 完整
- counter_example / counter_search_path 引用全清
- 图 8 引用全清
- v2.3 说明性段措辞统一

- [ ] **Step 3: commit**

注：使用 `git add <dirs>` 而非显式列文件 — 让 git 自己决定哪些文件实际有改动。

Run:
```bash
git add .claude/skills/analyze-stock-charts/ docs/explain/ docs/research/
git commit -m "$(cat <<'EOF'
refactor(skill): v2.2 → v2.3 remove imagined counter mechanisms

把"想象的反例"机制（counter_example / chart_eight_self_check）和状态机
零容忍降级（disputed / refuted）从 analyze-stock-charts skill 全部移除。

主要变化：
- 删除字段：counter_example / counter_search_path / counterexample_search_protocol /
  figure_exceptions / per_batch_coverage / evidence.counterexamples /
  evidence.should_have_matched_but_failed / confidence.blocked_from_promotion
- advocate §5.B 5 项校验缩为 2 项（perspectives_diversity / clarity_threshold）
- synthesizer §4 12 项校验缩为 9 项；删第 4/5（counter_*）/ 第 8（图 8 反例）项
- 状态机简化为 3 态单向晋级（无 disputed / refuted 旁路）
- output_kind 5 选 1 缩为 4 选 1（移除 library_doubt）
- _retired/ 仅 user 主动归档（不再由状态机自动移入）
- 修正 figure_exceptions framing（不强制非空，是 honest declaration）

防御链替代（基于真实观察 + 跨 batch 累积 + user gatekeeper）：
- figure_supports / cross_image_observation / unexplained_charts（真实图像）
- distinct_batches_supported ≥ 3（结构性硬约束）
- validated 由 user 周期性 review 决议

Schema 升级：v2.2 → v2.3。已有 10 个 v2.2 patterns 的 frontmatter
按 v2.3 schema 清理（forward-only 一次性清除，库为实验状态）。

设计决策：docs/research/2026-05-07_skill_v2_3_remove_imagined_counter_example.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

注：experiments/analyze_stock_charts/ 在 .gitignore 排除，patterns + _meta 改动**不会**进 commit（这是预期）。Schema migration 仅本地有效。

- [ ] **Step 4: git status 验证**

Run: `git status`
Expected：working tree clean (除 docs/tmp/ plan 文档 untracked + experiments/ ignored 外)

- [ ] **Step 5: git log 验证**

Run: `git log --oneline -5`
Expected：最近 1 行是 `refactor(skill): v2.2 → v2.3 remove imagined counter mechanisms`

---

## 完成判定

全 13 个 task 完成 + Task 12 audit 全绿 + Task 13 commit 成功 → plan 实施完成。

后续不在本 commit：
- 本 plan 文档（`docs/tmp/2026-05-07_skill_v2_3_implementation_plan.md`）可在事后清理
- 下次 user 用 v2.3 skill 跑 batch 时，skill 应按新 schema 工作（首次跑应验证整个流程通畅）

---

## 执行模式建议

按用户偏好 **subagent-driven 模式**：

每 task 流程：
1. dispatch implementer subagent (`tom`, `model: sonnet`)
2. dispatch spec-review subagent (`tom`, `model: sonnet`)
3. 不通过 → 回 step 1 修复；通过 → 进下一 task
4. Task 12 多一步 global consistency review

每 task 估时（含 implementer + review）：
- Task 1: 20 min（SKILL.md 小改）
- Task 2: 60 min（4 dim-expert 同模式批改，但每个文件多处改动）
- Task 3: 45 min（advocate 重写 §5/§5.B）
- Task 4: 75 min（synthesizer 改动最复杂）
- Task 5: 25 min（01 删图 8 引用）
- Task 6: 60 min（02 schema 重写最大）
- Task 7: 30 min（03 团队架构）
- Task 8: 15 min（00 README）
- Task 9: 30 min（docs/explain）
- Task 10: 20 min（10 patterns 字段清理）
- Task 11: 10 min（schema_version + run_history）
- Task 12: 25 min（audit + global review）
- Task 13: 10 min（commit）

**总计估时**：约 7 hr（中等规模重构，多文件协调）。

注：本次 v2.3 比 v2.2 复杂，原因：
1. 跨文件一致性多（14 文件）
2. 状态机改动牵涉多个引用点（synthesizer / 02 / 03 / explain）
3. patterns 数据迁移（10 个文件）
4. v2.3 说明性段措辞需在多文件保持一致
