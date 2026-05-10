# Loop + Reviewer 自迭代思考骨架（设计文档）

## 目标

为"主会话自迭代思考 + 隔离 reviewer 守门"这一工作模式建立最小可运行的骨架。通过 ralph-loop 让主会话在同一个 Claude Code session 里反复推进同一个思考任务；通过每轮派发的 `Agent` subagent 提供与主会话**完全隔离**的批判视角；以 reviewer 的判定作为 ralph-loop 的退出条件。

定位：通用基础设施的最小骨架（C 方案——不是裸 prompt，也不是 slash command）。先用真实任务跑通两到三次，再决定是否包装。

设计要点的根本驱动：

- **上下文隔离**：reviewer 不应被主会话的"沉没成本偏见"或自我说服污染。文件是主会话与 reviewer 的唯一沟通界面。
- **跨任务复用**：reviewer 评判维度是通用的（"什么叫合理解决方案"），任务特殊性只存在于 `question.md`。
- **唯一解约束**：最终目标是得到**有且只有一个**各方面合理的解决方案，不是一份候选对比清单。

## 整体环路

```
ralph-loop 启动 (--completion-promise "APPROVED" --max-iterations 15)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  主会话单轮（同一 Claude Code session，每轮重新执行）          │
│                                                              │
│  1. 读 question.md          (用户原始问题与约束，跨轮不变)     │
│  2. 读 design.md            (自己上轮的产出，首轮可空)         │
│  3. 读 reviews/<latest>     (上轮 reviewer 的判词，首轮无)     │
│  4. 思考 → 覆盖式改写 design.md                                │
│  5. Agent 工具派发隔离 reviewer (subagent_type: tom)           │
│       - reviewer 读 question/design/全部 reviews              │
│       - reviewer 写 review_<N>.md                            │
│  6. 主会话读 review_<N>.md 末尾的 VERDICT 行                   │
│       APPROVED          → 输出 <promise>APPROVED</promise>    │
│       OBJECTIONS_REMAIN → 不输出 promise，正常结束本轮         │
│                                                              │
│  Stop hook 检查 promise，未匹配则喂回相同 prompt → 下一轮      │
└──────────────────────────────────────────────────────────────┘
```

两层信号刻意分开：reviewer 的 `VERDICT: APPROVED` 是**评判语义**；主会话输出的 `<promise>APPROVED</promise>` 是 **ralph-loop 退出协议**。前者只决定后者，不直接触发退出。

## 文件布局

```
docs/tmp/loop/<task-slug>/
├── prompt.md              # 主会话每轮的 ralph-loop body（跨任务复用）
├── reviewer_prompt.md     # reviewer subagent 的指令模板（跨任务复用）
├── question.md            # 用户原始问题，任务特殊化（每个任务一份）
├── reference.png          # 可选：图像或其他附件
├── design.md              # 主会话当前立场（覆盖式更新）
├── reviews/               # 累积式追加，每轮新增一份
│   ├── review_001.md
│   ├── review_002.md
│   └── ...
└── notes.md               # 可选：主会话 scratch（reviewer 不读）
```

关键决策：

- **按任务隔离子目录**：第二个任务建立新 task-slug 子目录，互不干扰。
- **`docs/tmp/` 而非 `.claude/`**：CLAUDE.md 限定 `.claude/docs/` 仅放系统/模块意图；过程性产物归 `docs/tmp/`。
- **不进 git**：在 `.gitignore` 加 `docs/tmp/loop/`。最终设计应由主会话 loop 结束后另行写入 `docs/research/` 才进 git。
- **`design.md` 单文件覆盖**：reviewer 评判的是当前立场，不是历史立场；想看 diff 用 git 或自行 backup。
- **`reviews/` 累积**：reviewer 跨轮"记忆"全部源于此目录。文件名 `review_<NNN>.md`（三位零填充以便排序），N 由 reviewer 数现有文件数 + 1 得到。

## `prompt.md` 骨架

主会话每轮看到的 ralph-loop body，分四段：

1. **角色**：你正在 self-iterative 思考用户提出的问题；reviewer subagent 会以全新隔离上下文质询你。
2. **每轮固定流程**（procedural checklist）：读 question.md → 读 design.md → 读 reviews/ → 改写 design.md → 用 `Agent` 工具（`subagent_type: tom`）派发 reviewer，prompt 是 `reviewer_prompt.md` 内容 + 任务目录绝对路径 → 读新生成的 `reviews/review_<N>.md`。
3. **退出协议**：grep 最新 review 的 VERDICT 行；`APPROVED` → 输出 `<promise>APPROVED</promise>`（外层标签必不可少）；`OBJECTIONS_REMAIN` 或 grep 不到 → 不输出 promise，正常结束本轮。
4. **诚信约束**：绝不为脱离 loop 而伪造 verdict 或编造 reviewer 没说过的批准；max-iterations 即将耗尽也不例外。

首轮特殊处理：`prompt.md` 必须显式说明"如果 design.md 不存在或为空，这是首轮，基于 question.md 产出第一版完整设计"。

## `reviewer_prompt.md` 骨架（含通用八维评判）

五段：

1. **角色锁死**：你是 devil's advocate critic。**绝不提出你自己的替代设计**；想说"应该这样做"时，转写成"主会话没有论证为什么不这样做"。所有产出都是质询，不是方案。
2. **每轮工作流**：读 question.md（评判基准）→ 读 design.md → 读 reviews/ 全部历史（跨轮记忆）→ 必要时用 Read/Bash/Grep 验证 design 对代码现状的描述。
3. **批判维度结构**：对题性、覆盖度、歧义、跨轮一致性、事实核查。
4. **review 文件强制结构**：
   ```
   # Review N
   ## 上轮异议的回应核查
   ## 本轮新增异议
   ## 事实核查
   ## 八维评判
   - 唯一性: ✓/✗ — 理由
   - 对题性: ✓/✗
   - 充分比较: ✓/✗
   - 无挥手: ✓/✗
   - 跨轮一致性: ✓/✗
   - 可落地: ✓/✗
   - 第一性/奥卡姆: ✓/✗
   - 守界: ✓/✗
   ## 最终判定
   VERDICT: APPROVED   ← 八条全 ✓ 才能批准
   ```
5. **通用八维评判（APPROVED 的高门槛）**：
   1. **唯一性 / 决断性** — 有且只有一条选定路径，不允许"看情况而定"。
   2. **对题性** — design 显式回应了 question.md 中陈述的所有约束（reviewer 自己抽取）。
   3. **充分比较**（条件性） — 问题暗示多候选时，被淘汰候选必须有显式反对论证；纯调查类问题要求推理链可追溯。
   4. **无挥手 / 无歧义** — 每一步具体到知道在主张什么；"通过某种机制"视为未完成。
   5. **跨轮一致性** — 上轮异议要么被实质回应，要么 design 显式承认无法回应并解释为何不影响推荐。换措辞重复立场不算回应。
   6. **可落地 / 可证伪** — 主张能还原为可检验的下一步或对照现实的判断。
   7. **第一性 / 奥卡姆** — 每个组件都由问题本身要求，无为想象未来需求的复杂度。
   8. **守界** — 不漂移到 question.md 之外的问题，不发明 question.md 没有的约束。

   **任意一条 ✗ → `OBJECTIONS_REMAIN`**。"你的工作不是让主会话开心，是守门。"

## 首次任务：`question.md` 内容骨架

跨任务复用骨架，每个任务自己填写。六段：

1. **现象 / 问题描述** —— 任务的核心。如有图，附 reference.png 路径。
2. **现状的限制** —— 简短点出，不替主会话给诊断（让它读代码自己确认）。
3. **关键性质 / 难点** —— 这个任务里"为什么不容易"的具体性质。
4. **候选方向** —— 用户的初始想法作为锚点，**显式允许提第 N 种**：如果你认为这些都不是最优，必须显式说明为什么这些都不够。
5. **非目标** —— 防越界。本骨架的默认非目标包括"不写代码 / 不修改现有代码 / 不做完整工程实现规划"。
6. **参考资源路径** —— 共享给主会话和 reviewer："去这些地方挖"清单。

注意：原计划中第 5 段"接受标准"已被 reviewer 的通用八维评判替代，question.md 中**不再特殊化评判标准**。

## 失效模式与安全网

- **硬上限**：`--max-iterations 15`。15 轮未 APPROVED → 人工介入。
- **首轮空文件**：prompt.md 显式处理，避免主会话困惑。
- **reviewer 异常**：（a）未产出文件 → 视为 OBJECTIONS_REMAIN，notes.md 记录，下轮重试；（b）VERDICT 行缺失 → 视为 OBJECTIONS_REMAIN。**默认守严不守松**。
- **死循环异议**：**不做特殊检测**。max-iterations 兜底；真卡死则编辑 question.md 或 cancel-ralph。
- **人工介入**：编辑 question.md 加约束 / `/ralph-loop:cancel-ralph` 中止 / 手写 review 强制通过（不推荐）。
- **Token 成本**：reviewer 每轮 5–15k，主会话 10–20k，15 轮上限下整个 loop 数百 k tokens。

## 启动与中止

启动：

```bash
/ralph-loop:ralph-loop "<prompt.md 的内容>" \
  --completion-promise "APPROVED" \
  --max-iterations 15
```

中止：`/ralph-loop:cancel-ralph`

终态产出：loop 自然退出后，最终 design.md 和 reviews/ 留在任务目录。如需沉淀为正式研究产出，主会话另行写入 `docs/research/`。

## 未来改进点

骨架刻意省略以下功能。当真实使用中暴露需求时，再按需扩展：

1. **多视角 reviewer panel**（来自 Q3 选项 C） — 每轮并发派发 2–3 个不同视角的 reviewer（领域批评者 / 架构批评者 / 第一性原理批评者），全部 ✓ 才 APPROVED。当前单 reviewer 角度可能太窄。
2. **reviewer 提反方案**（来自 Q3 选项 B） — 当前禁止 reviewer 提替代设计，避免污染主会话作者身份。如果发现"主会话钻牛角尖时 reviewer 无法把它拉出来"是真问题，可以 opt-in 这一功能。
3. **包装为 slash command**（来自 Q1 选项 A） — 目前是文件骨架，每次启动手工调 ralph-loop。跑过几个真实任务、骨架定型后，可以包装为 `/think-loop "<question>"`。
4. **死循环异议检测** — 当前不做。如果 max-iterations 频繁触发且原因都是"reviewer 死守一点"，可加"同一异议连续 N 轮不动 → 升级"机制。需要语义比对，复杂度高。
5. **并发 reviewer** — 当前单 reviewer 串行。如果 token 预算允许、且单 reviewer 角度被证不够，可以并发。
6. **design.md 历史快照** — 当前依赖 git。如果不想每轮 commit、又想看历史 diff，可以加自动 `design.md.iter_<N>.bak`。
7. **结构化人工 override** — 当前手写 review 强制通过被列为"不推荐"。可以提供合法路径：`reviews/manual_override_<N>.md` 必须包含 rationale 字段。
8. **跨任务 review pattern 提取** — 多任务跑过后，"reviewer 经常在 X 维度卡住"是有价值的信号，可以提炼成 meta-doc 反哺新任务的 design.md 起手式。
9. **reviewer subagent type 切换** — 当前固定 `tom`（深度技术）。非技术性思考任务可能更适合 `general-purpose` 或自定义 subagent。
10. **基于上轮 verdict 调整下轮 prompt** — 当前 ralph-loop body 跨轮固定。Stop hook 可以注入 systemMessage 高亮"上轮 reviewer 重点关注 X"。需要修改 hook，侵入性高。
11. **reviewer 信任度衰减检测** — fresh subagent 在结构上不会软化，但若多任务跑下来发现某些维度长期被"轻易批准"，是 prompt 设计问题，不是机制问题。

## 与现有约定的对齐

- 文件位置遵循 CLAUDE.md：过程性产物 `docs/tmp/`，最终研究产出 `docs/research/`，不碰 `.claude/docs/`。
- 命名遵循 BreakoutStrategy 工程的中文注释 + 英文标识符约定。
- 骨架本身**不实现任何交易策略代码**，是元工具基础设施。
