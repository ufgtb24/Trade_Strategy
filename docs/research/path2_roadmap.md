# Path 2 开发路线图 / 状态(上下文持久化)

> 用途:跨 session / 压缩上下文后,快速恢复"总目标 / 已完成 / 剩余拆分 / 在途位置"。
> 指针式——不复述内容,详情见所指文档。
> 最后更新:2026-05-16(#1 dogfood 已完成并合入)

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

## 2. 剩余工作 + 拆分(每条几份 spec/plan)

| # | 工作 | 来源 | cycle 拆分 |
|---|---|---|---|
| ~~1~~ | ✅ **已完成**:dogfood 两级形态端到端验证,报告 + 集成测试已合入;bool-as-idx 已拍板=显式拒绝 | 见 §1 | 已收口 |
| **2** | **spec v0.2 正式修订**:§9 并入 v0.1 正文 + 补 `run()` 推荐驱动文档(bool-as-idx 子项**已由 #1 闭环,移出本项**)| spec §9 / design §3.3 | 纯文档,无独立 plan(单独小改)|
| **3** | **stdlib:消费 TemporalEdge 的标准 PatternDetector**(`Chain`/`Dag`/`Kof`/`Neg`,带最优实现)| spec §7.1 **已确定必做** | 1 份 spec + 1 份 plan(完整 cycle)|
| **4** | **stdlib:常用 Event 类 / Detector 模板**(BarEvent/Peak/BO/VolSpike;Barwise/FSM/Windowed/Threshold)| spec §7.2 / qa.md B | 1 份 spec + 1 份 plan(完整 cycle);优先级由 #1 痛感定 |
| 5 | **DSL 层**(压缩简单连锁)| spec §7.2 / qa.md C | 可选;需求倒逼才启;1 份 spec + 1 份 plan |
| 6 | tutorial/api_reference 补 `run()` 推荐驱动说明 | design §3.3 | 小文档项,可并入 #2 |
| 7 | Path 2 自有下游流水线 | spec §0.2 | 远期,框架被 #1 证明前不碰 |

**排序逻辑**:#1 经验闸门**已过**(报告 §5 已产出 #3/#4 的痛点输入);#3 是 §7 唯一"必须",**下一步默认做 #3**;#4 优先级由报告 §5 浮动;#5 默认不做;#2/#6 便宜可捆绑;#7 远期。
**工作模式**:#3/#4/#5 各走完整 superpowers 管线(brainstorming→writing-plans→subagent-driven-development,独立 worktree),勿跳 brainstorm。

## 3. 当前在途位置

**#1 已收口并合入,post-merge 收尾(update-ai-context)已做。无在途任务。** 下一步入口见 §4。

## 4. 接下来做什么

1. **(主线)** 启动 **#3 stdlib PatternDetector**(`Chain`/`Dag`/`Kof`/`Neg`):重新进入 `superpowers:brainstorming`。输入材料:验证报告 `docs/research/path2_dogfood_report.md` §5(尤其"L2 须自物化下层流 + 贪心样板""窗口锚定语义须命名默认""event_id 默认生成器");spec §7.1;qa.md Q1 备忘 B。走完整 brainstorm→spec→plan→subagent-driven,独立 worktree。
2. **(可捆绑)** #2 spec v0.2 修订(§9 并入正文 + `run()` 驱动文档),纯文档小改;#6 tutorial/api_reference 补 `run()` 说明可并入。
