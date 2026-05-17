# Path 2 开发路线图 / 状态(上下文持久化)

> 用途:跨 session / 压缩上下文后,快速恢复"总目标 / 已完成 / 剩余拆分 / 在途位置"。
> 指针式——不复述内容,详情见所指文档。
> 最后更新:2026-05-17(#3 stdlib PatternDetector 已完成并合入)

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

## 2. 剩余工作 + 拆分(每条几份 spec/plan)

| # | 工作 | 来源 | cycle 拆分 |
|---|---|---|---|
| ~~1~~ | ✅ **已完成**:dogfood 两级形态端到端验证,报告 + 集成测试已合入;bool-as-idx 已拍板=显式拒绝 | 见 §1 | 已收口 |
| **2** | **spec v0.2 正式修订**:§9 并入 v0.1 正文 + 补 `run()` 推荐驱动文档(bool-as-idx 子项**已由 #1 闭环,移出本项**)| spec §9 / design §3.3 | 纯文档,无独立 plan(单独小改)|
| ~~3~~ | ✅ **已完成**:`Chain`/`Dag`/`Kof`/`Neg` + `PatternMatch` 合入(@ 047b4e5);核心经 agent team 重设计为 LEF-DFS,156 测试全过 | 见 §1 | 已收口 |
| **4** | **stdlib:常用 Event 类 / Detector 模板**(BarEvent/Peak/BO/VolSpike;Barwise/FSM/Windowed/Threshold)| spec §7.2 / qa.md B | 1 份 spec + 1 份 plan(完整 cycle);优先级由 #1 痛感定 |
| 5 | **DSL 层**(压缩简单连锁)| spec §7.2 / qa.md C | 可选;需求倒逼才启;1 份 spec + 1 份 plan |
| 6 | tutorial/api_reference 补 `run()` 推荐驱动说明 | design §3.3 | 小文档项,可并入 #2 |
| 7 | Path 2 自有下游流水线 | spec §0.2 | 远期,框架被 #1 证明前不碰 |

**排序逻辑**:#1/#3 已过并合入;**下一步主线默认做 #4**(stdlib 常用 Event/Detector 模板,优先级由 dogfood 报告 §5 浮动);#5 默认不做;#2/#6 便宜可捆绑;#7 远期。
**工作模式**:#4/#5 各走完整 superpowers 管线(brainstorming→writing-plans→subagent-driven-development,独立 worktree),勿跳 brainstorm。重大算法/设计缺口经审查暴露时:轻量→tom 裁定,重大→agent team(#3 LEF-DFS 即此先例,见 `path2_algo_core_redesign.md`)。

## 3. 当前在途位置

**#1、#3 均已收口并合入,各自 post-merge 收尾(update-ai-context)已做,worktree/branch 已清理。无在途任务。** 下一步入口见 §4。

## 4. 接下来做什么

1. **(主线)** 启动 **#4 stdlib 常用 Event 类 / Detector 模板**(BarEvent/Peak/BO/VolSpike;Barwise/FSM/Windowed/Threshold):重新进入 `superpowers:brainstorming`。输入材料:dogfood 报告 `docs/research/path2_dogfood_report.md` §5(框架贴合度痛点,定 #4 优先级);spec §7.2;qa.md Q1 备忘 B;#3 已落地的 `path2/stdlib/` + 算法权威 `path2_algo_core_redesign.md`(#4 模板须与 LEF-DFS PatternDetector 协作)。走完整 brainstorm→spec→plan→subagent-driven,独立 worktree。
2. **(可捆绑)** #2 spec v0.2 修订(§9 并入正文 + `run()` 驱动文档),纯文档小改;#6 tutorial/api_reference 补 `run()` 说明可并入。注:#3 实测的 spec 关键回写(`earlier`/`later` 是声明期端点标签非 event_id;§2.3 假"天然不重复"删除→#seq 无条件共享)应一并并入 #2,见 `path2_algo_core_redesign.md` §8/§11.6。
