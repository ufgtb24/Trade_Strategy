# chart_class 决议交互设计 (analyze-stock-charts skill)

> **Spec type**: design
> **Status**: 待 user 审核
> **Date**: 2026-05-07
> **Scope**: skill v2.1 → v2.2 — chart_class 决议节点重构
> **Estimate**: 3.5-4 hr 工程量（仅 markdown 编辑，无代码）

---

## 1. 背景

### 1.1 当前设计

analyze-stock-charts skill v2.1 中，chart_class 同义判断由 synthesizer 在 T7 §5.1 自动执行：

1. 完全同名命中 → 直接复用
2. alias 命中 → 复用主 class，把 dominant 加入 aliases 列表
3. LLM 语义判定命中已有 class → 加入该 class 的 aliases
4. LLM 判定 NONE → 写入 `## proposed classes`，patterns 暂存 `_pending/<batch_id>/` 等 user **事后**决议

### 1.2 问题

1. **alias 概念冗余**：保留 alias 仅为性能 cache（避免重复 LLM 判断），但牺牲了"主名命名一致性"。
2. **`_pending/<batch_id>/` 推迟决议**：LLM 自动判定为新 class 时，patterns 暂存等用户事后决议，导致主目录碎片化、user 心智负担高。
3. **dim-expert baseline 时机错位**：dim-expert 的输入依赖 `patterns/<chart_class>/*.md` 历史 baseline。当前 LLM 自动决议在 T7 才完成，dim-expert (T2-T5) 跑时仍用 dominant_class，可能找不到正确历史，丢失"避免重复发现 + counterexample 反例验证"的能力。
4. **user 没有命名修正权**：LLM 给的 chart_class 名可能瑕疵（冗长 / 拼写不一致 / 不符合命名规范），user 没机会在 spawn dim-expert 之前修正。

### 1.3 目标

把 chart_class 同义判断 / 新建 / 合并的决策权前移到 **T1 后、T2-T5 spawn 前**，由 user 显式决议（lead 协调 + LLM 推荐辅助），消除 alias / proposed classes / _pending 三个冗余概念。

---

## 2. 架构总览

### 2.1 工作流变化

```
[skill 入口 pre-check] → [TeamCreate + spawn overviewer]
   ↓
T1: overviewer → 产出 dominant_class + first_impression
   ↓ TaskUpdate completed
   ↓
T1.5: lead 决议节点（新增）
   ├─ 读 _meta/chart_classes.md (active classes)
   ├─ 读 findings.md ## 1.gestalt (overviewer 输出)
   ├─ 调 LLM 求合并候选 (sim ≥ 0.5)
   ├─ 三种分支：
   │   ├─ A 同名命中 → text 通知 "类已存在，将合并"
   │   ├─ B 有候选 → AskUserQuestion 弹选项（新建 / 合并入 X）
   │   └─ C 无候选 → text 通知 "未找到合并候选，将新建"
   ├─ 持久化决议（写 _meta/chart_classes.md + findings.md ## 1.5.class_decision）
   └─ 计算 final_chart_class
   ↓
T2-T5: 4 个 dim-expert spawn 时注入 final_chart_class（取代旧的 dominant_class）
   ↓
T6: advocate
   ↓
T7: synthesizer 直接写 patterns/<final_chart_class>/，不再做 §5.1 chart_class 同义判断
   ↓
[shutdown + 用户摘要]
```

### 2.2 关键设计决策

| 决策 | 取值 | 理由 |
|---|---|---|
| 决议时机 | T1 后早问（A 模式）| dim-expert baseline 依赖 chart_class 必须在其 spawn 前确定 |
| 候选呈现 | 中等（含 LLM 推荐 + rationale + 差异说明）| 决策摩擦最低、质量最高 |
| 候选数量 | 1 个（最相似且 sim ≥ 0.5） | 避免决策疲劳 |
| 触发者 | skill 入口（lead）| AskUserQuestion 工具仅 lead 可用；overviewer 不应承担库索引职责 |
| 无候选处理 | 直接新建 + 通知（不弹选）| 与同名直接合并对称，最少打扰 |
| 命名修正 | 单段式默认可编辑 | user 可纠正 LLM 瑕疵但不强制二段 prompt |
| alias 概念 | 整体消除 | 性能 cache 价值随库扩大递减；user 决议替代 |
| `_pending/` 目录 | 整体消除 | user 决议先于 spawn，无需 staging |
| `## proposed classes` 段 | 整体消除 | 决议同步落地 |

---

## 3. T1.5 决议节点内部流程

### 3.1 步骤 1：读取上游产出

- 读 `{run_dir}/findings.md ## 1.gestalt` → 取 `dominant_chart_class` + `first_impression` 摘要
- 读 `{library_root}/_meta/chart_classes.md ## active classes` → 取已有 class 列表（class_name + 描述 + patterns_count）

### 3.2 步骤 2：分支判定

```
if dominant_class in [c.name for c in active_classes]:
    → 分支 A: 同名命中
elif active_classes 为空:
    → 分支 C: 无候选（库初期）
else:
    调 LLM 求合并候选（步骤 3）
    if 候选列表为空（最相似的 sim < 0.5）:
        → 分支 C: 无候选
    else:
        → 分支 B: LLM 推荐合并候选
```

### 3.3 步骤 3：LLM 候选检索（仅分支 B）

LLM prompt 形如：

```
Batch dominant_class: <name>
Batch first_impression 摘要: <每图 1 行 gestalt>
Active classes:
  - <name>: <description> (patterns_count: N)
  - ...

判断 dominant_class 与每个 active class 的语义相似度，输出最相似的 1 个候选（sim ≥ 0.5 才输出）：
{
  "candidate": "<class_name or null>",
  "sim_score": 0.78,
  "rationale": "两者都...",
  "key_difference": "差异在..."
}
```

只返回 1 个候选（最相似的），不返回 top-K。如果最相似的 sim < 0.5 → 返回 null → 分支 C。

### 3.4 步骤 4：交互呈现（仅分支 B）

通过 `AskUserQuestion` 呈现：

```
Batch dominant_class: long_consolidation_breakout
LLM 推荐合并入：long_base_breakout (sim=0.78)
理由：两者都强调"宽幅区间内的低波动横盘 + 突破"
差异：long_base 强调时间长度（≥40 日）；本批未明确时间约束
推荐：合并（差异属子变种）

请选择：
[ ] 1. 新建 long_consolidation_breakout（默认名可编辑）
[ ] 2. 合并入 long_base_breakout
```

- 选 1 → user 可选地修改 class 名（默认采用 LLM 给的 dominant_class；user 在回复中可附带 "rename: <new_name>" 指示 lead 改名）
- 选 2 → 直接采纳

**实施备注（rename 承载形式）**：lead 在 AskUserQuestion 中明确提示用户"如要改名，请在回复中追加 `rename: <new_name>`"。lead 解析回复时识别该字段。具体 AskUserQuestion 调用形式（multipleChoice + freeform 文本附注 / 或其他承载方式）由实施者决定，但用户体验上必须保持单段 prompt——禁止"先选项 + 再追问改名"的 2 段式。

### 3.5 步骤 5：分支 A / C 的提示

不调 AskUserQuestion，直接 text 通知：

- **分支 A**："✓ chart_class `<name>` 已存在，本 batch 将合并入此 class"，self-execute → final_chart_class = dominant_class
- **分支 C**："✓ 未找到 sim≥0.5 的合并候选，将新建 chart_class `<name>`"，self-execute → final_chart_class = dominant_class

### 3.6 步骤 6：持久化决议

更新 `_meta/chart_classes.md`：

- **新建分支** (B-new / C)：在 `## active classes` 段追加新行（class_name / description="<由 lead 用 first_impression 概括>" / first_seen=<runId> / patterns_count=0 / last_updated）
- **合并/同名分支** (B-merge / A)：仅更新该 class 的 `last_updated`（patterns_count 等 T7 写库后再 +N）

写 `{run_dir}/findings.md ## 1.5.class_decision`（决议日志，详见 §4）。

---

## 4. 决议日志 schema

T1.5 完成后，lead 在 findings.md 追加：

```markdown
## 1.5.class_decision

batch_dominant_class: long_consolidation_breakout
final_chart_class: long_base_breakout
decision_branch: B-merge       # A-existing / B-merge / B-new / C-no-candidate
user_decided_at: 2026-05-07T14:23:11+08:00

llm_candidate:                  # 仅 branch B 时填，否则省略
  candidate: long_base_breakout
  sim_score: 0.78
  rationale: "两者都强调宽幅区间内的低波动横盘 + 突破"
  key_difference: "long_base 强调时间长度（≥40 日）；本批未明确"
  recommendation: merge

user_choice: merge_into          # new / merge_into
user_renamed: false              # branch B-new 选了新建且改名时为 true
user_renamed_to: ""              # 改名后的 class 名
notification_only: false         # branch A / C 时为 true（user 未真正决议）
```

---

## 5. spawn prompt 注入

### 5.1 dim-expert (T2-T5)

lead spawn dim-expert 时注入 `final_chart_class`（替代当前的 dominant_chart_class）：

```
=== 本次 run 元信息（由 skill 入口注入）===
run_id        : ...
chart_paths   : ...
dominant_chart_class : long_consolidation_breakout    # overviewer 给的，仅供参考
final_chart_class    : long_base_breakout             # ← 用此值做后续工作（user 已决议）
class_decision_branch: B-merge
history_baseline     : <patterns/long_base_breakout/*.md frontmatter 摘要，由 synthesizer 注入>
counterexample_protocols: <历史 protocol 列表>
```

**dim-expert 行为变化**：

- 旧版：用 `dominant_chart_class` 找历史 baseline（可能找不到 = 库初期或新 class）
- 新版：用 `final_chart_class` 找历史 baseline——
  - 合并分支：拿到该已有 class 的全部历史规律 baseline + counterexample protocols
  - 新建分支：仍是空 baseline，但状态明确（不是"还没决议"的 ambiguous）

### 5.2 synthesizer (T7)

synthesizer 不再做 §5.1 chart_class 决议工作（已上移到 lead）：

- spawn prompt 注入 `final_chart_class` —— synthesizer 直接写 `patterns/<final_chart_class>/`
- 新建分支：synthesizer 第一次写入时 `_meta/chart_classes.md` 该 class 的 `patterns_count` 从 0 → N
- 合并分支：synthesizer 累加 `patterns_count` + 跑 dim_sim 与历史 patterns 聚类（MERGE / VARIANT / NEW 子判定不变，仅"是否新 class" 这层被 lead 取代）

---

## 6. chart_classes.md 新 schema

```markdown
# Chart Classes Registry

> 本 batch 视觉类别（chart_class）的活跃注册表。每个 chart_class 对应 `patterns/<class_name>/` 一个目录。
> 决议由 user 在每次 batch 的 T1.5 节点完成（lead 协调），synthesizer 写库时直接使用 final_chart_class。

## active classes

| class_name | description | first_seen_run | patterns_count | last_updated |
|---|---|---|---|---|
| long_base_breakout | 宽幅区间内的低波动横盘 ≥40 日后突破 | 2026-05-06_112923_0bea3 | 5 | 2026-05-07_142311 |
| ... | ... | ... | ... | ... |

## decision history

> 每次 T1.5 决议追加一行（含分支、最终结果、所属 run）。供审计与跨 run 追溯用。

| run_id | dominant_class | final_class | branch | user_choice |
|---|---|---|---|---|
| 2026-05-06_112923_0bea3 | long_consolidation_breakout | long_base_breakout | B-merge | merge_into |
| ... | ... | ... | ... | ... |
```

**移除的字段 / 段**：

- `aliases` 字段
- `## proposed classes` 段
- 任何 `_pending` 的引用

**新增段**：

- `## decision history` —— 跨 run 审计追溯 user 在每次 batch 做了什么决议

---

## 7. 错误处理矩阵

| 异常情况 | 处理 |
|---|---|
| user 不回复 AskUserQuestion（超时）| 不设硬超时——AskUserQuestion 本身阻塞 lead，user 可随时回复。lead 记录 "等待 user 决议中"。除非用户 abort 整个 skill，否则不强制走默认。|
| LLM 候选检索调用失败（模型 error / 超时）| 重试 1 次；仍失败 → 降级为分支 C（无候选直接新建），text 通知 user "LLM 候选检索失败，降级新建 `<name>`，可在事后手动改 chart_classes.md 改归类" |
| user 选了"新建 + 自定义名"，但自定义名与已有 active class 同名 | 拒绝该名 + 重新弹问 "名字 `<x>` 已存在，请改名或选合并到 `<x>`" |
| user 选了"新建 + 自定义名"，名含非法字符（空格 / 中文 / 特殊符）| 拒绝 + 重新弹问 "class_name 仅支持 `[a-z][a-z0-9_]*` 格式" |
| dim-expert 看到的 `final_chart_class` 在 chart_classes.md 中不存在（lead 写入失败 / 并发问题）| dim-expert SendMessage 给 lead 报错；lead 检查 chart_classes.md 完整性后修复或 abort |
| 决议后 lead 写 chart_classes.md 锁失败（02 §A.5 锁文件残留）| 等 30s 重试；仍失败则 abort 整个 run，runs/ 标 `status=incomplete` |
| user 在 T1.5 阶段选择 abort skill | lead 调用 TeamDelete，runs/ 标 `status=user_aborted_at_t1_5`，不写 chart_classes.md |
| 库为空（首次 run）| 跳过 LLM 候选检索（active classes 列表为空），直接走分支 C 通知"将新建 `<name>`" |

---

## 8. 影响面 + 文档变更范围

### 8.1 需要修改的文件

**SKILL.md**：

- §3.2 `chart_class + batch 协议` → 删除"同义性校验"逻辑（user 自决）
- §5.1 model 表 → 不变
- §5.2 任务依赖图 → 在 T1 与 T2-T5 间插入 T1.5 lead 决议节点描述（注：T1.5 是 lead 内部步骤，**不**写入 TaskCreate）
- §5.x 新增 "T1.5 chart_class 决议" 一节，描述 lead 的 6 步内部流程

**prompts/overviewer.md**：

- §1 角色描述补一句"你的 dominant_chart_class 输出会先经过 lead+user 决议后才注入下游 dim-expert"
- §6 写完后通知协议：去掉"同质性校验"部分（lead 接管），保留 outlier 比例警告

**prompts/synthesizer.md**：

- §5.1 chart_class 同义判断 → 整段删除
- §5.2 writing 流程 case 2 (新 class proposed) → 整段删除（无 _pending 概念了）
- §4 校验清单 12 项的第 9 项 "chart_class 一致性" → 改为 "finding 的 chart_class 必须等于 spawn prompt 注入的 final_chart_class"
- §3 输入资源 → `chart_classes.md` 改读"决议后的 active classes"

**prompts/dim-expert × 4**（phase-recognizer / resistance-cartographer / volume-pulse-scout / launch-validator）：

- §3 输入资源表中 `dominant_chart_class` → `final_chart_class`
- 增加一句："final_chart_class 由 lead 在 T1.5 完成 user 决议后注入；如果是合并入既有 class，你能拿到该 class 的历史 baseline + counterexample protocols"

**references/02_memory_system.md**：

- §A.5 chart_classes.md schema 章节 → 整段重写（删 aliases / proposed classes / _pending；新增 decision history）
- §C / §D 提及 _pending 的部分 → 全部删除
- §E STEP 流程 → 在 STEP 1 加描述 "lead 在 T1.5 已完成 chart_class 决议，synthesizer 直接用 final_chart_class"

**references/03_team_architecture.md**：

- §3 工作流图 → 在 T1 → T2 之间加 T1.5 节点描述
- §4 角色权限矩阵 → lead 新增"chart_class 决议"权限；synthesizer 从"chart_class 决议"权限中删除

### 8.2 工作量估算

| 文件 | 工作量 |
|---|---|
| SKILL.md | 30 min |
| 7 prompts | 1.5 hr |
| 02 memory_system.md | 1 hr |
| 03 team_architecture.md | 30 min |
| **总计** | **3.5-4 hr** |

### 8.3 不在本设计范围

- 现有 `_pending/2026-05-06_112923_0bea3/` 数据迁移决议（user 手动处理）
- `docs/explain/analyze_stock_charts_logic_analysis.md` 用户文档更新（事后单独 commit）

---

## 9. 与 v2.1 commits 的关系

```
本 spec → 实施 commit → v2.2
                 ↓
* refactor(skill): v2.1 → v2.2 chart_class user-decision flow ← 本设计实施
* fix(skill): align dim-expert §2 (model + blockedBy)
* refactor(skill): v2 → v2.1 cleanup (5 fixes integrated)
```

实施成单 commit。建议 subagent-driven 模式：6-8 个 task（每个文件 1 task + audit + commit），每 task implementer + spec review。

---

## 10. 验收标准

实施完成时：

- [ ] SKILL.md §5.x 含完整 T1.5 决议流程描述
- [ ] synthesizer.md §5 中无 alias / proposed classes / _pending 引用
- [ ] 4 个 dim-expert prompt 的输入表用 `final_chart_class`，不再用 `dominant_chart_class`
- [ ] 02 memory_system.md §A.5 chart_classes.md schema 已重写为新版（含 decision history）
- [ ] 03 team_architecture.md 工作流图含 T1.5 节点
- [ ] grep `_pending\|aliases\|proposed classes` 在 SKILL.md / prompts / references 下无剩余引用
- [ ] grep `dominant_chart_class` 在 prompts 中仅 overviewer 输出端 + dim-expert 注释提及（不再用于 spawn 注入）
