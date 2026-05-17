# Path 2 开发路线图 / 状态(上下文持久化)

> 用途:跨 session / 压缩上下文后,快速恢复"总目标 / 已完成 / 剩余拆分 / 在途位置"。
> 指针式——不复述内容,详情见所指文档。
> 最后更新:2026-05-17(#4 stdlib BarwiseDetector + span_id 已完成并合入 @ 4c5fda9;第 2 周期 stdlib 主体齐,无主线在途)

## 0. 总目标

Path 2 = **独立的多级事件表达框架**(独立业务,与突破选股/mining/因子框架无关,自带未来流水线)。
当前阶段:**按周期逐步建出框架**(协议层 → stdlib → 可选 DSL → 自有流水线)。
权威定义见 `docs/research/path2_spec.md`;教学见 `path2_tutorial.md` / `path2_api_reference.md`;尖锐问答见 `path2_qa.md`。

## 1. 已完成

**协议层(第 1 周期)—— 已实现、已验证、已合入 `complex_framing`**:

- 代码:`path2/`(`config`/`core`/`operators`/`pattern`/`runner`),50 pytest 全过
- 流程:brainstorm → spec → plan → subagent-driven(9 任务,每个两阶段 review)→ holistic review APPROVED → 合入(worktree 已清理)
- 文档:
  - design:`docs/superpowers/specs/2026-05-16-path2-protocol-layer-design.md`
  - plan:`docs/superpowers/plans/2026-05-16-path2-protocol-layer.md`
  - spec v0.2 反馈:`path2_spec.md` §9(偏差①②、3 补强卫语、bool-as-idx 边界)
  - AI 上下文:`.claude/docs/modules/path2.md` + `system_outline.md` 模块表
- 过程中关键发现:spec 偏差①(frozen 由 Python `@dataclass` 装饰期原生强制,自检为死代码,已删)——已落 design §2.4 + spec §9

**#1 dogfood 验证(第 1 周期收尾)—— 已实现、已验证、已合入 `complex_framing`(@ 25b082d)**:

- 形态:两级自包含 `VolSpike`(L1)→`VolCluster`(L2),仅吃 `volume`,零领域逻辑
- 代码:`tests/path2/dogfood_detectors.py`(脚手架,**不进 `path2/` 包**)+ `tests/path2/test_dogfood_integration.py`(真实数据 pin 死)+ `tests/path2/fixtures/aapl_vol_slice.csv`(committed,CSV 替代 pkl)+ `scripts/path2_dogfood_chart.py`;63 pytest 全过
- bool-as-idx:**已决议=显式拒绝**(`Event.__post_init__` `type() is bool`),回归测试在 `test_event.py`;spec §9.3 已闭环 → **#2 不再含此项**
- 文档:design `docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md`;plan `docs/superpowers/plans/2026-05-16-path2-dogfood-validation.md`;验证报告 `docs/research/path2_dogfood_report.md`(§5 框架贴合度痛点 = 喂 #3/#4 的核心交付)
- 流程:brainstorm→spec→plan→subagent-driven(7 任务,各两阶段 review)→ holistic APPROVED → FF 合入 → worktree/branch 已清理
- post-merge 收尾已做:`update-ai-context` 已刷新 `.claude/docs/modules/path2.md`(bool 现记为"已显式拒绝";已知局限去掉该条);`system_outline.md` 无需改(path2 仍仅协议层)

**#3 stdlib PatternDetector(第 2 周期)—— 已实现、已验证、已合入 `complex_framing`(@ 047b4e5,FF)**:

- 代码:`path2/stdlib/`(`_ids`/`pattern_match`/`_labels`/`_graph`/`_advance`/`detectors`/`__init__`)= `Chain`/`Dag`/`Kof`/`Neg` + 统一 `PatternMatch`,经 `path2/__init__` 出口;156 pytest 全过;协议层/spec **零改动**
- 流程:brainstorm→spec→plan→subagent-driven(11 任务,各两阶段 review)→ holistic review READY-TO-MERGE → FF 合入 → worktree/branch 已清理
- **过程关键事件**:两阶段 review 查出原 plan"单调双指针 O(ΣN) 永不回退"核心有 **5 根缺陷**(C1 源-only 回溯不完整 / C2 多源只回溯首源 / C3 单 run event_id 重复 / C4 不健全 start_idx 单调假设 / I1 `.index` 值相等错位)→ **agent team 对抗式重设计为 LEF-DFS**;Kof / Neg 各经 **tom 二次裁定**补语义缺口(Kof = LEF-DFS 结构姊妹/诚实指数;Neg = forbid 成员资格谓词,修单方向假设)
- 文档:design `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`(含 redesign 回写横幅);plan `docs/superpowers/plans/2026-05-16-path2-stdlib-pattern-detectors.md`(Task 5/8/9 OVERRIDE);**算法权威 `docs/research/path2_algo_core_redesign.md`**(LEF-DFS §1-9 / Kof §10 / Neg §11)
- post-merge 收尾已做:`update-ai-context` 已刷新 `.claude/docs/modules/path2.md`(协议层 → 协议层+stdlib);`system_outline.md` 无需改(path2 非 BreakoutStrategy 模块,不在其 scope)

**#4 stdlib 常用 Detector 模板 + id 便利(第 2 周期续)—— 已实现、已验证、已合入 `complex_framing`(@ 4c5fda9,FF)**:

- 代码:**净交付仅 2 公开符号**——`path2.BarwiseDetector`(`path2/stdlib/templates.py`,abc.ABC,逐 bar 单点扫描模板,用户子类只实现 `emit(df,i)->Optional[Event]`;`detect` 拥有 `range(len(df))` 主循环+None 过滤;零跨事件校验/零领域假设/无 warmup)+ `path2.span_id`(`_ids.py` 新增,单点 `start==end` 塌缩 `kind_i` 否则 `kind_s_e`)。**不沉淀任何 Event 类**;`default_event_id`(#3 内部桩)一字节未改且不公开。协议层 + #3 全部文件 **零 diff**;169 pytest 全过(基线 156 + #4 新增 13)
- 流程:brainstorm(每问派 tom)→spec→plan→subagent-driven(6 任务,各两阶段 review,Task4/5 各一轮 review-fix)→ holistic review **READY-TO-MERGE** → FF 合入 → worktree/branch 已清理
- **过程关键事件**:① brainstorming YAGNI 狠砍——`BarEvent/Peak/BO/VolSpike/MACrossOver` 全砍(无 dogfood 证据 / Peak·BO 命名违反独立业务约束 / 用户 L1 总带私有领域字段不可预沉淀)、`Threshold/FSM/Windowed` 全砍(零证据)。② D1「`default_event_id=span_id` 别名」方案被 pinned 测试 `test_ids.py:9` 硬证伪 → 改两函数并存(语义刻意不同)。③ **plan 期对 `Kof` 代码级核查证伪 brainstorming 裁定「痛点2 归 Kof」**——`Kof` 是 k-of-n 边松弛(成员数恒=label 数),本质无法表达滑动「窗口内 ≥N」;红线(#4 不造 `WindowedDetector`/任何贪心计数 detector)**不变但理由改为「无足够复用证据进 stdlib,使用方自管,待 #5/#7」**(反更稳,不依赖被证伪的覆盖声明);§7.4 据此拆 A(核心充分:重写等价+无循环判据)/ B(降级:诚实 pin `Chain` 真实产出 `[(60,61,2),(61,67,2),(264,265,2),(265,267,2)]`,不复刻旧贪心)
- 文档:design `docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`(**含写回横幅:Kof 不覆盖滑动计数 + §7.4 拆 A/B + 痛点2 红线理由修正,为权威**);plan `docs/superpowers/plans/2026-05-17-path2-4-stdlib-templates.md`
- post-merge 收尾已做:`update-ai-context` 已刷新 `.claude/docs/modules/path2.md`(协议层+stdlib → 加 stdlib 便利层 BarwiseDetector/span_id);`system_outline.md` 无需改(同 #3 理由)

## 2. 剩余工作 + 拆分(每条几份 spec/plan)

| # | 工作 | 来源 | cycle 拆分 |
|---|---|---|---|
| ~~1~~ | ✅ **已完成**:dogfood 两级形态端到端验证,报告 + 集成测试已合入;bool-as-idx 已拍板=显式拒绝 | 见 §1 | 已收口 |
| ~~2~~ | ✅ **已完成**:spec v0.2 正式修订——§9 并入正文(§1.1.2 frozen/§1.2.5 run()/§1.3 max_gap+earlier_later 标签/§5.1 补强卫语+bool),§9 转变更摘要;`earlier`/`later`=声明期端点标签写回已落地 | 见 §1 | 已收口 |
| ~~3~~ | ✅ **已完成**:`Chain`/`Dag`/`Kof`/`Neg` + `PatternMatch` 合入(@ 047b4e5);核心经 agent team 重设计为 LEF-DFS,156 测试全过 | 见 §1 | 已收口 |
| ~~4~~ | ✅ **已完成**:净交付 `BarwiseDetector` + `span_id`(@ 4c5fda9);YAGNI 砍掉全部候选 Event 类 + Threshold/FSM/Windowed;Kof 不覆盖滑动计数(红线理由修正);169 测试全过 | 见 §1 | 已收口 |
| 5 | **DSL 层**(压缩简单连锁)| spec §7.2 / qa.md C | 可选;需求倒逼才启;1 份 spec + 1 份 plan |
| ~~6~~ | ✅ **已完成**:tutorial §10 Step5 + §10.5、api_reference §0.2/§1.3/§1.4 补 `run()` 推荐驱动 + 改正 stdlib 已就绪/LEF-DFS(随 #2 一并) | design §3.3 | 已收口 |
| 7 | Path 2 自有下游流水线 | spec §0.2 | 远期,框架被 #1 证明前不碰 |

**排序逻辑**:#1/#3/#4 已过并合入,#2/#6 文档已收口;#5(DSL 层)**默认不做**,需求倒逼才启;#7 远期(框架被证明前不碰)。**当前无主线在途任务**。
**工作模式**:#5 若启走完整 superpowers 管线(brainstorming→writing-plans→subagent-driven-development,独立 worktree),勿跳 brainstorm。重大算法/设计缺口经审查暴露时:轻量→tom 裁定,重大→agent team(#3 LEF-DFS 即此先例,见 `path2_algo_core_redesign.md`)。#4 先例:brainstorming 裁定可被 plan/实现期代码级核查证伪(Kof 痛点2),写回 spec 横幅为权威。

## 3. 当前在途位置

**#1、#3、#4 均已收口并合入(post-merge update-ai-context 均已做,worktree/branch 已清理);#2/#6 文档修订已完成(spec/tutorial/api_reference,未提交)。无在途任务。** #4 之后第 2 周期 stdlib 主体(PatternDetector + BarwiseDetector/span_id 便利层)已齐。下一步入口见 §4。

## 4. 接下来做什么

**无主线在途任务。** 剩余可选项:
- **#5 DSL 层**(压缩简单连锁,spec §7.2 / qa.md C):**默认不做**,仅当真实使用出现高频简单连锁样板、需求倒逼时才启;启则走完整 brainstorm→spec→plan→subagent-driven + 独立 worktree(brainstorming 每问派 tom,见 memory `feedback_path2_delegate_tom`)。
- **#7 Path 2 自有下游流水线**(spec §0.2):远期,框架被充分证明前不碰。
跨 session 恢复仍先读本文件;#4 设计/实现细节权威见 `docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`(含写回横幅)。
