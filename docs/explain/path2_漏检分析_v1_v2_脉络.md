# path2 漏检分析方法 · v1 → v2 脉络

> 陪你的两份 report 一起看:
> - v1: `docs/research/2026-07-05_path2-miss-detection-analysis/final_report.md`
> - v2: `docs/research/2026-07-05_path2-miss-detection-v2-break-limits/final_report.md`
>
> 这份文档不重复 report 里的细节(断点位置、LOC 数、Sprint 拆分),只讲**脉络**:两次分析各回答了哪个层级的问题、v2 相对 v1 前进了什么、现在需要你判断的核心分歧点在哪。

---

## 1. 面对的问题一句话

你在 web UI 按 bo pattern 排序、选 active=bottom_burst,看到一支大涨股没有 bottom_burst marker。你想快速知道:**为什么这支股漏了?**

问题不在"漏检本身",在**当前系统告诉不了你原因**——UI 只显示已检出的 event,不显示"这个 role 差一点通过、卡在哪里";detector 内部 gate 全静默;solver 每一次剪枝也是静默 return False。所以你只能靠断点/打印/凭直觉猜。

两次分析都在回答同一个问题:**怎么让"漏检根因"变成可见的信息**。差别是——v1 假设不能改代码,v2 允许改。

---

## 2. v1 做了什么

v1 是被绑住手做的。约束 = 不改 detector、不改 solver、不改 UI。

在这个约束下,v1 干了两件事:

**第一件**:把漏检可能的失败点摊开,分成 4 层——

- **L1** · role 属性 clause(比如 `first_drought` / `distinct_pk` 单节点 where 条件不过)
- **L2** · role 之间的 pair 关系(比如 tb 找不到能对上 burst 的伙伴)
- **L3** · detector 自己内部的 gate(比如 BurstDetector 里 chain 断链、BODetector 里 peak 判据不过)
- **L4** · solver 深度 DFS 组合失败(pair 满足性 fail、strict_clear fail、NegationEdge 违禁)

每层 v1 都盘点了"现在能看到什么、看不到什么":L1 是唯一一层 UI 现在有覆盖(候选表 + tooltip);L2 数据在后端 JSON 里但前端从没渲染;L3 和 L4 完全静默,只能靠断点。

**第二件**:给了一份从便宜到贵的操作手册——

先在 UI 里花 30 秒扫 marker,能定就定;不能定 → 打开 DetailSidebar 看角色漏斗(1-2 分钟);还不能定 → 写个十几行的 driver 脚本单独跑这只股,配 PyCharm **无条件**断点(5-10 分钟);想更省事 → 装 mcp-pdb 让 Claude 自动跑 pdb。

v1 的价值 = **今天就能用**。不动一行代码,给了一套 tier 化的诊断路径,含具体断点位置清单。

v1 的边界 = 手册再详细也是**绕过**限制,不是**消除**限制。用户视角是"点股一眼看根因",driver + pdb 永远兑不出这个体验。

---

## 3. v2 松绑后想清了什么

允许改代码之后,思路从"绕过静默"变成"让引擎主动结构化说话"。但真正难的不是改哪几行,而是——**先把问题的分类想清楚**。v2 有两个关键洞察是 v1 里没浮出来的。

### 洞察一 · 你的 P1/P2 二分方向基本站得住

原稿 team critique 曾主张扩为六分(P0/P1/P2a/P2b/P3/P4),核心是把 `path2/dag/engine.py:83-89` 的 `isolated_consumed` 后处理过滤单列为 P3。但你 2026-07-06 review 后裁定——**这是设计上的正确过滤,不是漏检根因**:若某个 role 是孤立无边且被其他机制消费,它本来就不该以独立 match 形式存在。critique 把"设计正确过滤的场景"和"漏检根因分类"混为一谈,类别错了。

修正后:去掉 P3,剩下 P0/P1/P2a/P2b/P4,其中 P0(输入异常)和 P4(wiring 错误)是排除项,主线回到你的 P1/P2 二分:

- **P1** · detector 内 gate(为何没检测到 event)
- **P2** · pair / 组合级失败(role 为何没构成 pattern);细分 P2a(pair 满足性)/ P2b(solver DFS 剪枝)

真正的补充在洞察二——UI 覆盖度断言不完全成立,得先修硬伤,才能让 P1/P2 二分"唯一未解"的叙事真正成立。

**次要留项**:v2 里 `AnalysisResult.dropped_matches` 字段**保留**,但作用从"漏检归因数据源"改为"UI 呈现辅助"——用户视觉上会看到有 marker 但无 match(设计过滤后残留的 marker),此时 tooltip 或候选级查询响应的 caveat 里一句"这些 marker 属于被消费的 role,当前 pattern 未触发"消除困惑。这是 UX 呈现约定,不是分类。

### 洞察二 · "UI 已覆盖 qualified 归因"是伪断言

你判断"event 为何没 qualified"UI tooltip 已经覆盖,不用再管。team 实际读了 DetailSidebar 相关代码后回答:**这断言只在 L1 一元标量 where 层成立**,有 4 处硬伤:

- **A**:`RoleDiagnostics.rel`(上游侧关系诊断)后端 JSON 里躺着,前端**从没渲染**过。所以整个 L2"pair 通过 K/N"你现在根本看不到。
- **B**:diagnose 层调 `edge.satisfies` 却**没调** `_anchor_ok`——anchor_field 场景下,anchor 不匹的候选**会虚报 pair 通过**。UI 越看越自信,实际信息是错的。
- **C**:跨节点 clause(引用兄弟 role 属性)当前 spec 恰好不触发,一旦触发**会静默产错值**——没有报警。
- **D**:multi-value where(比如 `distinct_pk_min` 多分量)tooltip 显示扁平化。

意思是——**要真的让"UI 已覆盖"成立,得先把这 4 处硬伤补上**。这是 v2 方案的**前置**,不是"顺手做的加分项"。硬伤 A 尤其关键:整个 L2 rel 层现在对你完全不可见,你把它归入 P2 是合理的,但你想在 UI 里查却查不到。

### 洞察三 · 全局摘要没 actionable 价值,改成用户驱动的局部查询(2026-07-06 review 后重构)

v2 初稿曾把 UX 骨架定为"点股 → 一句全局摘要 banner",隐含前提是"知道最窄卡点就知道往哪调"。这个前提站不住——调 spec_dag 或 detector 需要具体 `(bar_idx, gate, measured/threshold)` 或 `(src_cand, dst_cand, edge, reason)`,全局摘要只告诉你"往哪层看"、不告诉你"看什么"。**2026-07-06 review 撤 Layer 1 banner**。

引擎侧做法不变——**让引擎在扫描完之后自然带出结构化数据**,这三条保留:

- 加 `path2/debug.py` 放 ContextVar,scan 前 set 当前 symbol。消灭"BurstDetector 无法按 symbol 设条件断点"槽点
- detector 加 `on_gate` hook,每次 gate pass/fail 结构化 emit。gate 不再静默,而是把 "BurstDetector 在 bar N chain 断链,gap=13 > gap_max=10" 直接输出成数据
- solver 加 `solve(trace=True)` + `SolveTrace` + `PruneRecord`,把 `_dfs` 里每一处 return False / continue 记录下来。生产扫描 `trace=False` 零开销;单股诊断路径开,memo 强制关

**变化在消费侧**——不再合成全局摘要,而是按用户查询分派:

- **时段查询**(K 线框选/zoom):`GET /diagnose?scope=time` → `gate_events[]`(bar 级)
- **Role-subset 查询**(拓扑点边):`GET /diagnose?scope=roles` → `pair_failures[]`(候选级)
- **候选级查询**(点 K 线 marker):`GET /diagnose?scope=candidate` → `rejection_chain[]`(单 candidate 的淘汰路径)

引擎侧的原子数据源(on_gate/SolveTrace/dropped_matches)本来就是逐 bar/逐 pair 记录,天然适配三种局部查询。撤的只是 UI 消费口径,数据源不动。

V1 D0"一键复制 driver 脚本"按钮**保留**,移到 K 线区右键菜单(banner 撤了,原来的落脚点没了)。

### 洞察四 · v2 不完全取代 v1

driver + pdb 这条路**永远保留**。原因是——detector 内部的超细节(某个 peak 的 relative_height 具体值是多少、由哪几根 bar 决定、参数敏感度怎样)UI 表达代价极高,而 driver 里 print 几行就出来。跨股对比、临时假设、参数扫描,driver 都是最经济的。

所以 v2 的定位是——**日常"点股看根因"的 90% 场景交给 UI,剩下 10% 交给 driver 兜底**。不是 v2 淘汰 v1,是 v2 把 v1 顶到"最后一公里"的位置。

---

## 4. 从整体上看你在赢什么

回到出发点:两次分析各解决了哪个层的问题——

- **v1** = **告诉你今天能做什么**。一份可以拿了就用的手册,不改代码。
- **v2** = **告诉你改一次代码之后能做什么**。把静默的引擎变成会说话的引擎,让"框选时段 / 点边 / 点 marker"都能得到具体 bar/pair/candidate 级答案(不再是"点股看全局摘要")。

v2 引擎侧改动全部在 400 LOC 以内(Sprint 1 + Stage 0/1),Sprint 1 完成时覆盖率从 v1 的 L1 40% 跳到 L1+L2 约 75%。Sprint 2/3 再补引擎剩余(gate hook、full solver trace、workflow 批量),周级预算,总覆盖率约 95%。剩下 5% 就是 detector 内部超细节留给 driver。

---

## 5. 现在需要你判断的三件事

其他细节都可以由 spec / plan 阶段吸收。真正需要你现在拍板、影响方案骨架的只有三个:

**~~O1 · 是否接受 P3 独立成一类?~~**(2026-07-06 已撤回)

裁定:isolated_consumed 是设计正确过滤,不是漏检根因,P3 分类下架。`dropped_matches` 字段保留,作用改为 UI 呈现辅助(消除"有 marker 无 match"的视觉困惑)。

**O2 · Sprint 1 是否把前端消费层硬伤 A/B/C/D 全修?**(2026-07-06 更新:硬伤定位从 DetailSidebar 组件升级到前端消费层)

推荐:全修**在 shared 层**(tooltip + DetailSidebar 一并),因为两者共享 `RoleDiagnostics.attr` 数据源。硬伤 A 让 rel 数据两侧都看不到、硬伤 B 让 rel 徽标虚报,Sprint 1 不修就是骗你。C 只是加一个 tripwire (~5 LOC),D 是 fmt() 抽到 `shared/formatters.ts` 加 Array 分支(~25 LOC),都不大。若想 Sprint 1 极简,C 可拖到 Sprint 2,A/B/D 不动摇。

**O3 · V1 那颗 driver 按钮**——放哪?

推荐:保留,**放 K 线区右键菜单**(2026-07-06 更新:banner 已撤,原展开区没了)。detector 内部超细节 UI 表达代价高,driver 是永远的兜底底线。三方一致意见。

其他弱依赖(workflow 是否 cron / atom 落地顺序 / debug 是否单独出包)团队已经给了推荐,可以进入 spec 后再定。

---

## 6. 附录 · 两份 report 定位

| 文档 | 一句话定位 | 适用场景 |
|---|---|---|
| **v1 · final_report.md** | 不改代码前提下的 tier 化操作手册 | 今天就要诊断某一具体股(如 DGNX 2025-08-01),或者你不打算做引擎改动,只想用现有工具兜住 |
| **v1 · survey_path2_diagnostics / survey_debug_tools / survey_web_ui_extension** | v1 三方各自的调研原稿 | 想看 v1 结论的一手证据 / 反驳细节 |
| **v2 · final_report.md** | 打破限制后的完整方案(五分类主线 + 引擎结构化 + 三种局部查询 + Sprint 路线;P3 已撤回,banner/三层渐进披露已撤) | 你决定要做引擎/UI 改动、想看整体架构和路线图 |
| **v2 · critique.md** | 独立 critique 二分完备性 + UI 覆盖度 | 想看 UI 覆盖度硬伤论证;分类学部分已被 2026-07-06 review 部分推翻(P3 撤回) |
| **v2 · engine_instrument.md** | 引擎侧数据源打破限制的详细设计 | 进入 spec 阶段写 Stage 0/1/2/3/4 时的技术参考 |
| **v2 · ux_integrator.md** | 前端三层 + 后端投影 + workflow 的详细设计 | 写前端 spec 时的技术参考 |

先看这份文档拉齐脉络,再按需去 v1/v2 report 里取细节。真要开工时,v2 final_report 的 §3(架构)+ §5(Sprint 路线)+ §6(开放问题)是最短起点。
