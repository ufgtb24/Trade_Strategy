# 研究背景与团队协议（class_id 彻底清除 · 第二轮设计研究）

读 `原始问题.md` 后读本文。本文事实均由 lead 于 2026-08-14 在 instance-id-refactor 分支实测核对，带 file:line；**允许被证伪**，证伪时给出你自己的 file:line。

## 1. 对话脉络（为什么有这次研究）

1. 用户发现 web UI 入口A（brush 时段查询 gate 失败样例）显示 Python 类名（`ThrowbackEventV1`），认为应显示 `node_id`（`tb`），与前端其余部分一致，且"前端不应看到代码层数据结构"。
2. lead 调查确认：这是 instance-id 重构（Task 4）的语义偏移——`class_id` 的值从"event 子类声明的 tag（bo/burst/tb 风格）"迁成了 `event_cls.__name__`。重构前（best_ever_v1 分支）class_id 值就是 node_id 风格。
3. 用户确认设计意图："整个 repo 应该不再有 class_id 这个概念"，并拍板"把 class_id 彻底清掉统一到 node_id"。
4. lead 提出方案 A（§3）。用户未直接批准，而是要求**第二轮思考**：方案 A 是否最佳？有没有更好方案？第一性原理评估代价是否值得（不考虑开发成本）？多维度评估（扩展/维护/新 detector 上手成本）？→ 即本次 agent team 研究任务。

## 2. 已核实的代码事实

### class_id 三源头（repo 内全部 class_id 收敛于此）

| 源头 | 位置 | 现值 | 说明 |
|---|---|---|---|
| `NodeSpec.class_id` | `path2/dag/spec.py:21` | `event_cls.__name__` | 注释自认"class_id 体系已消灭，字段名保留供 web 消费"。NodeSpec **已有** `node_id` 字段（spec.py:18）→ class_id 是冗余别名 |
| `GateFailure.class_id` | `path2/dag/gate_failure.py:65` | `event_cls.__name__` | gate 失败样例的 event 类名；atoms 各构造点传 `class_id=XXX.__name__`（如 `path2/atoms/throwback_v1.py:126`） |
| `debug_break` class_id 参数 + debug class 门 | `path2/debug_ctx.py:79-81` | `event_cls.__name__` | debug 断点四门（`_DEBUG_MODE ∧ bar∈range ∧ anchor_kind ∧ class_id`）中的第四门 |

grep 规模：后端 18 文件 68 处、前端 4 文件 8 处，全部消费链源自上述三处。

### 身份体系现状（instance-id 重构后）

- `Event.node_id / instance_idx / instance_id` 由引擎物化注入（`path2/core.py:59-68`），**detector 阶段全为 None**（core.py:68 注释明说）。
- `instance_id = {node_id}_{start}[_{end}]}#{instance_idx}`，点事件塌缩，塌缩规则内联于 `path2/dag/engine.py:35-40`（annotate_stream）。
- 旧身份字段体系（event 行的 event_id/class_id/source_tag）已消灭：`path2_web/serialize.py:8` 明列 class_id 为已消灭的旧体系；事件行序列化只带 instance_id/node_id/instance_idx（serialize.py:45-52）。

### gate failure 链路（方案 A 的主战场）

- gate failure 在 detector 内部 `on_gate(GateFailure(...))` 构造（`path2/atoms/throwback_v1.py:105-134`，on_gate 是 helper 参数，非 detect 签名——`BarwiseDetector.detect(self, df)` 无 on_gate，`path2/stdlib/templates.py:29`）。
- **gate 失败 = 该 attempt 不产出 event**（短路失败），所以 gate failure 不关联任何已物化 event——想从 event 反查 node_id 无门。
- 收集机制：`path2_web/gate_collector.py:38-45` `attach_and_collect(spec)` 遍历 `spec.nodes`，把 `node.detector.on_gate = collector.add`（此刻**遍历方知道 node.node_id**）；跑完 detach（on_gate=None）。worker（scan/eval）跑 analyze 前挂。
- web 消费：`path2_web/diagnose.py:174-224` `_derive_time_response`：`all_classes = sorted({n.event_cls.__name__ ...})`（line 203，下拉锚），过滤 `gf.class_id == query.event_class`（line 215）。
- 前端消费：`path2_web_ui/src/components/FailedAttemptsCard.vue`（attempt 行显示 `a.class_id` + select filter）；`DetailSidebar.vue:36` debug 卡片 `debugTarget.className`。

### debug 链路

- `path2/debug_ctx.py`：四门合取，class 门在 79-81（`required_cid != class_id → return` 不 pause）。
- 全库 ~28 个 `debug_break(` 埋点（atoms 各文件），埋点处传 `class_id=XXX.__name__`。
- **fork 子代理已论证 class 门冗余**（2026-08-14，未独立复核，欢迎证伪）：①tb 版本区分（V0/V1/V3）在单 dag_spec 内是空需求（一个 pattern 只挂一个 tb detector 版本）；②容器 vs 段已被 anchor_kind 区分——数据铁证：容器埋点 anchor_kind 恒为 gate/entry，段埋点恒为 end/confirm。故 (bar range, anchor_kind) 已唯一命中目标锚点，class 门纯冗余。
- 背景：instance-id 重构 commit d64083be 曾把前端 triggerEventDebug 的 eventClass 参数从 `event.class_id` 误改为 `event.node_id`，导致 class 门恒 false、右键 debug 三锚全不命中（另一 session 定位的现存 bug）。用户**否决**了"前端传回类名"的最小修复路线（那会巩固 class_id），要求彻底解决。

### 其他关键事实

- **共享 detector 是休眠特性**：当前所有生产 dag_spec（bb_v0/v1/v3、bo_only、try_conplex_where）均一 node 一 detector 实例；共享 detector 多 node 复用机制存在但零实例（lead 未逐一核对全部 dag_spec，teammate 可复核）。
- baseline：后端 0 failed（945 passed/2 skipped，2026-08-14 实测）；前端 vitest 4 failed（sidebar-result-list，pre-existing）。注意历史 baseline 提法中的 `test_throwback_debug_anchor_kinds 4 failed` 已被后续 commit 修复转绿。
- `datasets/pkls/` 本机有数据（APCX 等，Task 4 曾真实重算过）。

## 3. 待审方案 A（lead 第一轮提案，本轮研究对象）

**三源头各击破：**

1. `NodeSpec.class_id`：**删字段**，web 消费改用 `node_id`。
2. `GateFailure`：**删 class_id，加 `node_id: str = ''`**（带默认值兼容构造点）。值来源 = **gate_collector per-node 包装**：`attach_and_collect` 改为给每个 node 挂 wrapper，wrapper 收到 GateFailure 后 `dataclasses.replace(gf, node_id=node.node_id)` 再进 collector。detector/atoms 内部 on_gate 调用零改（构造只删 `class_id=` 参数）。
3. `debug_break`：**删 class_id 参数 + debug_ctx 删 class 门**（四门→三门），~28 埋点删 `class_id=`；前端右键菜单不传 eventClass，只传 anchor_kind + bar。

**连带改动**：diagnose（all_classes 用 spec node_id、过滤用 gf.node_id）/ api（scope=time 的 event_class 参数→node 过滤）/ 前端 types·FailedAttemptsCard·DetailSidebar·view。

**已自认的代价**：共享 detector（休眠 edge case）下 gate failure 的 node 归属归到最后赋值的 node——模糊。

## 4. 本轮三个研究问题（用户原话分解）

- **Q1（skeptic 主责）**：方案 A 是否最佳？有没有更好的方案达到"彻底废弃 class_id 且不影响功能"？
- **Q2（arch 主责）**：第一性原理：废弃 class_id 所要承受的代价是否值得（**不考虑开发成本**——只算功能/架构/长期代价）？
- **Q3（coder 主责，arch 协同）**：多维度评估：易于扩展、易于维护、易于（skill/开发者）增加新 detector 等等。

值得显式摆上桌面的张力点（不许回避）：
- **版本信息丢失**：`ThrowbackEventV1` vs `V3` 携带"哪个版本的 detector"信息，`node_id='tb'` 不携带。bb_v0/v1/v3 三个 app 各用不同 tb 版本；scan/诊断/UI 场景下这个信息是否需要表达位？pattern 上下文能否完全替代？
- **共享 detector 唤醒时的正确性**：方案 A 的 wrapper 在共享场景 node 归属错误。休眠≠不存在，唤醒时这是 bug 还是可接受模糊？
- **debug 定位唯一性**：class 门删除后 (bar, anchor_kind) 是否在全部 28 埋点中无歧义？请实证数埋点。
- **"彻底"的边界**：用户要"整个 repo 不再有 class_id 概念"。dag spec 层声明一个**非类名**的事件类型标签（回归 best_ever_v1 的显式 tag 风格但与 Python 类解耦）算不算违反？这属于开放设计空间，欢迎论证。

## 5. 团队协议

- 成员：**arch**（第一性原理+价值评估）/ **skeptic**（红队：攻击方案A+找更好方案）/ **coder**（代码事实官：可行性+新 detector authoring 成本）。leader = 主会话。
- 协作：完成自己核心研究后，把关键结论 `SendMessage` 给另外两位（按 name）请其挑战/补充；收到队友消息认真回应；**coder 在收到 skeptic 的替代方案后验证其代码可行性**。最终结论 `SendMessage` 给 leader（to: 'main'）。
- 中间笔记（可选）：本文件夹 `<name>-notes.md`。最终 `final_report.md` 由 leader 综合撰写。

## 6. 红线（全员）

1. **不修改任何正式代码**——纯思考/分析/讨论。确需运行验证脚本，放 `docs/research/2026-08-14_classid-elimination-study/repro/`。
2. **论证纪律**：用户用第一性原理审，禁止动机性推理（先有结论再凑理由）；干净区分"弱论点"与"真论点"；不确定就标不确定 + 给验证办法；别拿理论上的跨场景泛化当论据压过当前单一 dag_spec 的事实（但"未来扩展性"本身是 Q3 评估维度，允许讨论，须标注是前瞻非现状）。
3. **实测 > 一切文档**：context.md 的事实允许被证伪，证伪给 file:line。
