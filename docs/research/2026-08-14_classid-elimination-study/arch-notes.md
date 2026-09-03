# arch 研究笔记（Q2 第一性原理价值评估 + Q3 架构面）

所有 file:line 均为 instance-id-refactor 分支 2026-08-14 实测。

## 0. 对 context.md 的两处证伪/修正

1. **§2 "NodeSpec.class_id (spec.py:21)" 不成立**。实际：
   - `NodeSpec`（`path2/dag/nodes.py:44-51`）**没有 class_id 字段**；
   - class_id 在 `TopoNode`（`path2/dag/spec.py:24`）上，值 = `n.event_cls.__name__`（spec.py:246）；
   - **TopoNode.class_id 全库零读者**：`serialize_pattern`（serialize.py:249-259）只读 node_id/child_slot/parent_refs，不读 class_id；前端 `TopoNode` 类型（types.ts:8-15）无此字段。→ 它是纯僵尸字段，删除零功能代价、零连带改动。方案 A 第 1 条比 lead 预想更干净——不存在"web 消费改用 node_id"，web 早就只用 node_id。
2. **埋点数实测 30 处**（context 说 ~28）：throwback.py 9 + v0 6 + v1 7 + v3 8。

## 1. Q2 第一性原理框架：身份字段各自承载什么

一个事件表达框架里，一条记录（event / gate failure）的身份要回答三个正交问题：

| 问题 | 承载者 | 层次 |
|---|---|---|
| 唯一性：这条记录是哪一条 | `instance_id`（node_id+时空坐标+桶序） | 物化层 |
| 结构位置：它在走势叙事中扮演什么角色 | `node_id` | **声明层**（app 作者赋予语义） |
| 实现类型：字段结构由什么定义 | `event_cls`（Python 类） | 实现层 |

`class_id = event_cls.__name__` 的字符串形式携带两样东西：
- (a) **类型名**：实现细节。运行时判别用 isinstance/字段反射即可，**不需要字符串形式**；显示给人看时即泄漏代码层（用户原始不满）。
- (b) **版本**（V0/V1/V3 后缀）：是 detector 作者**命名纪律的副产物，不是框架机制**——作者忘写后缀信息即丢。它碰巧能用 ≠ 它是身份体系的一部分。

### 版本信息的正确归属（张力点①的正面回答）

**版本不是事件的属性，是声明的属性**。同一个 `ThrowbackEventV1` 类被哪个 pattern 挂、以什么参数挂，是 pattern 声明的选择；事件实例本身无"版本"。证据链：

1. **pattern_id 已编码版本**：bb_v0/bb_v1/bb_v3 的命名本身就是 tb 版本声明（bb_v1 的 "v1" = ThrowbackEventV1 的 v1）。版本表达位已存在。
2. **node_id 是自由命名空间，版本可入名**：bb_v3 的 `tb_seg_v3`（bb_v3/dag_spec.py:55）就是先例。需要版本区分时作者命名 `tb_v1`/`tb_v3` 即可——表达力 node_id ≥ 类名，且是声明层可控的。
3. **类名携带版本是脆弱巧合**：改名 `ThrowbackEventV1 → LegacyThrowback` 版本信息即蒸发；node_id 是契约字段，稳定性义务天然归它。
4. **所有实际消费场景都在 pattern 上下文内**：
   - scan：gate_failures 挂 AnalysisResult，per-symbol **per-pattern 分桶**（scan.py:96-124），从不跨 pattern 混桶；
   - scope=time：all_classes 从**单 pattern** spec 取（diagnose.py:203）；
   - debug：handler recompute **单 pattern**（api.py:295 `registry.get(pattern_id)` → 331 单 spec analyze），跨版本 class 门区分物理不可达。
   → "这个失败样例来自哪个版本的 detector"在一切真实场景里已被 pattern 上下文回答；类名是第三重冗余编码。

①现在的 class_id 在传达版本吗？——是，但只在"类名碰巧带版本后缀 + 消费者恰好读得懂 Python 命名"双重巧合下，且与 pattern_id 冗余。②清除后丢失什么？——脱离 pattern 上下文的裸记录（如导出 CSV 脱 UI 单看一行）不自明版本；弱损失，可由 payload 带 pattern_id 列补偿。③pattern 上下文能否完全替代？——当前全部消费场景（scan/诊断/debug/跨 pattern 对比，均分桶）内能。

### provenance 已被更强机制覆盖（且已在前端显示）

若真正想问的是"这条记录由哪段实现产出"（调试）：`GateFailure.code_location`（gate_failure.py:74，file:line 自动抓 caller）比类名精确一个量级；pydevd pause 直接落在源码行（debug_ctx.py:85-86），也不需要类名字符串。

**补强（2026-08-14 实测）**：code_location 已进前端契约并直接渲染（types.ts:176；FailedAttemptsCard.vue:98 `v-if="a.code_location"` 恒显示）——每条 attempt 行上 `throwback_v1.py:120` vs `throwback_v3.py:69` 一眼可辨。即"这个失败来自哪个版本 detector"的信息，**版本指纹已以更强形式（精确到文件行）常驻 UI**，class_id 不是它唯一的甚至不是它最好的载体。

### 漏洞自审：同 pattern 内换 detector 版本

"pattern_id 编码版本"依赖命名纪律——若 bb_v1 内部把 V1 换成 V3 而 pattern_id 不变，老/新 scan 文件的 tb 将不可区分。评估为弱残余风险：(a) 团队实践是版本变化开新 pattern（bb_v0/v1/v3 三目录并存即证据）；(b) code_location 仍在 scan 文件里区分版本（文件名即指纹）；(c) 跨版本 gate failure 语义本身不可比（gate_name/threshold 随版本变），"对比不同版本判据的失败样例"这个需求自身语义可疑。

另核实：gate failure 的全部消费面 = web scope=time + debug；eval/regress/healthcheck 路径只读 res.matches（eval_runner.py:72-74 注释明说，collector 挂收仅为保持模式一致）。

### 显示标识 vs 身份字段分层（张力点相关）

"只改 view 层显示 node_id、后端契约保留 class_id"技术上可行，但不是等价方案：
- 双轴并存 → 每个新消费点都要选轴 + 维护轴间映射（diagnose.py:199-203 的 all_classes 反射对齐就是纯胶水代码）；
- **轴错位是已发生的 bug 模式**：view.ts:817 前端把 node_id 塞进 className 参数，后端 class 门拿它与 `__name__` 比较 → 恒 false，debug 三锚全不命中（d64083be，现存 bug）。这正是双轴体系的直接产物；
- 类名留在契约（API 响应/scan 文件）= 泄漏留在、类名冻结进持久化产物。
→ 单轴化是治本。用户"repo 不再有 class_id 概念"的直觉在架构上成立。

## 2. Q2 结论：值得（无保留条件；一处实现级修补建议）

代价逐项盘点（不虚报不隐瞒）：

| 代价项 | 评估 |
|---|---|
| 版本信息表达位 | **无实际损失**（pattern_id 已编码 + node_id 可控命名先例 + 消费全在 pattern 上下文内）。前瞻弱损失：裸记录导出脱上下文不自明版本 |
| 共享 detector 的 gate failure node 归属 | class_id 在共享场景**同样失效**（同 detector → 同 event_cls → 同 class_id，无法区分 node）——现状本就是无归属。方案 A wrapper 把"无归属"变"错误归属到最后 node"是 wrapper 缺陷非方向错误。**最终处置 = lead 终裁 attach-raise（类级 on_gate 声明判据 ∧ 同对象 ≥2 node → raise），裁定四轮轨迹见 §2.1** |
| 老 scan 文件兼容 | **零成本，问题不存在**（coder 证实）：GateFailure 不落盘——serialize.py 零输出 failed_attempts，前端收到的全部来自 /diagnose 实时响应；无持久化面即无兼容问题 |
| debug 定位唯一性（30 埋点实测） | 结论成立但 fork 论证②数据有误（skeptic 纠正，见 §2.2）：v0/v1 无段层、end/confirm 埋点挂容器类，"容器恒 gate/entry、段恒 end/confirm"只对 throwback.py/v3.py 成立。真理由 = **粒度对齐论证**：bo/burst/trend 零 debug_break 埋点 + 单 pattern 单 tb 版本 → (bar, anchor_kind) 唯一命中一个 detector；而同 detector 内同 (bar,anchor_kind) 的多出口埋点 class 门本就区分不了（同类名），区分靠 pause 落点行号。即 class 门的区分度上限 = detector 粒度，单 pattern 下 (bar,anchor_kind) 恰好达到同一粒度 → class 门零增量。跨版本：debug 物理单 pattern，不可达；且 class 门当前已死（d64083be），删除是修 bug 非丢功能 |
| 事件行类型信息 | 三轴身份重构已清（serialize.py:8-9），本次零增量损失 |

收益：单一身份轴全链路；契约稳定化（类名不再冻结进 scan 文件/UI）；轴错位 bug 类根除；前端不见实现细节（用户原始诉求）。

### 2.1 共享 detector 处置：裁定轨迹（哨兵 → 禁令 → 哨兵 → lead 终裁 attach-raise）

四轮记录（保留轨迹供复核；最终以 lead 终裁收口）：

**第一轮（arch 初案）**：wrapper 检测共享 → node_id 哨兵。
**第二轮（skeptic 禁令，arch 曾接受）**：PatternSpec 校验禁止"产 gate detector 被 ≥2 node 引用"。理由 = fail-fast at declaration + 该状态零收益应消灭。
**第三轮（coder 反驳 + arch 再推演）**：转回 attach 哨兵（node_id=''）。当时的核心论据 = "禁令判据只能是声明性近似（产 gate 与否无法从类结构推断），哨兵判据是运行时真值；防作者犯错的机制自身依赖作者配合是递归缺陷"。
**第四轮（skeptic 再挑战，arch 的判据论据被证伪）**：skeptic 实测 + arch 独立复核确认——**5 个产 gate detector 全部有类级 `on_gate = None` 静态声明**（breakout.py:124/:238、throwback.py:282、throwback_v0.py:366、throwback_v1.py:398、throwback_v3.py:265，注释自认"protocol 静态声明"），且是功能必需（`self.on_gate` 读取点 breakout.py:141/164、throwback.py:300、v0:395、v1:442、v3:315 全依赖实例属性存在，不写即 AttributeError）→ 声明不可遗忘、hasattr 判据在 attach 前即准确 → 第三轮"递归缺陷"论据坍塌。**arch 事实错误记录**：第三轮我断言"on_gate 是 attach 时才赋的实例属性、平时类上不存在"——错误根源是从 core.py:141-142 的 Protocol TYPE_CHECKING 守卫推断 atom 实现而未 grep atoms；core 的 Protocol 声明与 atom 各自的类级声明是两回事。
**Lead 终裁（final_report §4，arch 接受）**：**attach_and_collect 内 raise**——判据 = 类级 on_gate 声明（hasattr，已存在零新增）∧ 同一 detector 对象被 ≥2 node 引用 → raise。此混合形态吸收双方仍成立的最强论据：从禁令方取"消灭状态而非容忍"（raise 而非 node_id='' 降级，不引入新契约边缘值）；从哨兵方取"检测点与唯一发作点重合 + 判据自动精确 + 不动 spec 层语义"（lead 理由 2/3）。arch 对终裁无异议——第四轮输入后 spec 禁令与 attach-raise 的判据有效性已完全相同（同一 hasattr 反射），剩余差异（报错时机 spec 构造期 vs attach 期）为纯实施细节，两者皆正确。
**事实修正（供 final_report §4 理由 1 微调，不推翻裁定）**：lead 理由 1 括号"类级 flag 需 3-4 个 detector 类加声明"与代码不符——类级声明已存在 5 处、无需新增；此修正反而强化"零声明成本"。"flag 与 emit 行为漂移"风险只剩假阳性方向（声明了不 emit 又被共享 → 误拦，报错教育作者，安全方向）。

### 2.1.1 第五轮：主体收口后的判据微调（coder 撤回哨兵 + skeptic 延迟 raise）

**coder 撤回静默哨兵、改 attach raise**（与 lead 终裁一致），并给出独立决定性论据（arch 认为是本分歧最好的单条论证，采纳进案）：**gf.node_id 在"共享产 gate"场景结构上无真值**——on_gate 是实例属性，同一实例的 detect 不知道自己被哪个 node 调用（attach 无条件赋值，gate_collector.py:41-44）；既然无真值，哨兵值无任何下游消费价值（前端下拉无法归因过滤、用户无行动选项），**一个不可消费的标记，其信息量 = 一条报错，而报错更早终止 + 带修复指引**。静默哨兵由此三方全体弃守。

**skeptic 第三选项（延迟 raise）**：判据 = attach 期 seen dict（id 重复记录，不 raise）+ **首条共享 gf 实际到达时 raise**（带修法报错）。与 lead 终裁（attach 期 hasattr ∧ id 重复即 raise）的差异收敛为两点：①判据是否需要 hasattr 前置——延迟版零反射依赖（任何写法含防御式均覆盖）、零假阳性（"声明不 emit 又共享"的合法无害配置不被误拦，且误拦时报错对 author 不可操作——author 自己都不知道哪个 detector 产 gate）；②raise 时机——attach 期（更早，未跑 detector）vs 首条 gf（发作点字面重合，报错时手里有 gf 上下文，bo/tb gate failure 高频、几乎必然立即触发）。

**arch 裁定（终，随 lead 终裁升级更新）**：lead 在 skeptic 终轮行权后将 A' 第 4 条终裁升级为**挂雷式延迟 raise**（seen dict by id(det) 判共享 → 共享时覆盖挂 _boom wrapper → 该 detector 首条 gf 真到达时 raise，报错带修法），取代此前的 hasattr 立即 raise 形态。arch 接受并受托独立验证，结果**通过、无机制问题**：

1. **冒泡完整性（arch 独立 grep 实证）**：engine.py 零 try/except（raise 从 on_gate 回调无损冒泡至 analyze 调用方）；scan.py:136-137 与 eval_runner.py:117-118 均 `except Exception → per-symbol error` 4-tuple（error 路径 per_pattern/rows 为 None，不写部分结果、不裸崩进程池）；api /diagnose 走 FastAPI 默认 500。detach finally 清除由 coder 亲验，arch 抽查一致。
2. **机制推演八项**（arch 自查）：单槽覆盖语义正确（_boom 覆盖后共享 detector 的 gf 全炸、不静默归首 node）；零误挂（_boom 仅 id 重复时挂）；零误杀（Trend 等合法共享不 emit gf，雷永不动）；无跨调用状态（每次 build_pattern 新 spec 新 seen dict）；detach 幂等；无声明顺序敏感；raise 时点无半收集副作用（error 4-tuple 整票丢弃）。
3. **架构定性**：挂雷式 = "raise 行为（skeptic）× seen-dict 判据（coder）× 运行时真值标准（arch 第三轮论据的完全体）"三方最强论据的融合形态，且消除了 hasattr 形态残余的漏判面（未来 detector 忘写类级声明但 emit gf 且共享 → hasattr 过滤漏判 → 静默错误归属；挂雷式正确炸）。arch 此前"维持 hasattr 版"的建议基于时序交错的旧终稿文本，对挂雷式无异议且验证通过。

### 2.2 补充事实（skeptic + coder 提供）

- **gf 不持久化**：scan 结果文件无 gf 字段、eval 路径自认无消费者（eval_runner.py:72-74）→ gate failure 的"归档回看/导出脱上下文"场景**物理不存在**，§1 中"弱损失：导出 CSV 脱 UI"一条连场景都没有，撤销。
- B/C/D 替代方案裁决与 arch 框架自洽：B（detector 显式传 nid）= 层次倒置（node_id 是声明层槽位、detector 是走势无关实现层组件，core.py:68 物化注入方向不可反转）；C（spec 第三标签）= "与 node_id 一一映射纯冗余、class_id 换名还魂"，与张力点④表态一致；D（code_location/gate_name 做分组键）= 语义错位——身份分层应各司其职：**node_id=归因分组键、code_location=实现指纹、gate_name=判据名**，provenance 载体不 usurp 归因键。

## 3. Q3 架构面：四层概念账

| 层 | 变化 |
|---|---|
| dag spec 声明层 | −1 概念（TopoNode.class_id 死字段清除；NodeSpec 本来就没有） |
| detector 实现层 | −1 概念：GateFailure 构造与 debug_break 签名不再收 class_id；30 埋点 × 样板消除；作者不再需要"我的类名要传给框架"这个反直觉知识点 |
| web 契约层 | 轴统一：event_class→node_id；all_classes→all_nodes（diagnose.py:199-203 的 `__name__` 反射对齐胶水消失，直接取 spec node_id，更浅） |
| debug 机制层 | 四门→三门；debug_enabled_classes 值**早已是 node_id**（serialize.py:267-278，types.ts:22 注释自认），门删除后前后端轴一致 |

新 detector 作者概念集：{node_id, event_cls, anchor_kind, **class_id(类名反射)**} → {node_id, event_cls, anchor_kind}。删掉的是最像魔法、最易传错的一个。

**coder 实证校准（2026-08-14，coder-notes.md）**：authoring 成本单调减少、零新增必写项——现状负担 = N 处 debug_break 样板 + helper 内 GateFailure class_id 手工同步点（v3.py:55-57 注释自认复制时唯一要改的就是 class_id 值）+ skill 二维对拍 (class_id, anchor_kind) + detectors/<class_id>.md 文档组织；方案 A 后全消失，wrapper 集中 gate_collector 一处对作者无感。出错面删一整类："类名漂移静默失败"有 3 处历史痕迹（skill 踩坑清单 / v3 复制注释 / d64083be 真 bug）。前端佐证 Q2 版本论证：anchorsOf 键=node_id、DEBUG_ENABLED_CLASSES 值=node_id、tbAnchorProfile 靠 child_refs（结构信息）区分容器/段/V1（view.ts:41-50, 113-127）——**前端区分版本/形态的机制已不依赖类名**，后端 class 门是唯一残留断层，方案 A 是修断层非新设计。

**Q3 新增维度（coder 发现，arch 上升为架构判断）：概念的文档半衰期**。class_id 概念还活在 authoring skill 层（authoring-path2-detector/reference.md:97-99 描述已消灭的旧体系、diagnose-event skill detectors/ 按类名组织文档）。架构含义：**一个概念真正的死亡边界 = 代码 + 契约 + skill 文档三层同步清除**——skill 是 AI authoring 的教学源，代码清了 skill 不清，新 detector 会被 skill 教着把 class_id 写回来（概念复活通道）。这把"彻底"的执行清单从 repo 代码扩展到 .claude/skills/**，是用户"整个 repo 不再有 class_id 概念"的应有之义，不改变方向判断、扩大清除范围。

方向定位：这是 2026-08-06 三轴身份方案（消灭事件行 event_id/class_id/source_tag）的**收尾**——那次清了主链路，这次清残留在 gate failure / debug 门 / spec 投影 / skill 文档里的尾巴，身份概念从"三轴"收敛为"node_id + instance_id 双轴，event_cls 退回 Python 类型系统不进字符串契约"。

前瞻（非现状，Q3 扩展维度）：若未来一个 pattern 需挂两个版本同类 detector 对比 → node_id 必然异名（tb_v1/tb_v3），区分度不降反升；若未来一 node 产多类型事件（当前 NodeSpec 强制一 node 一 event_cls）→ 那时才有新标签需求，YAGNI。

## 4. 张力点④表态："彻底"的边界（arch 初稿 + skeptic 精确化）

- "声明层非类名的事件类型标签"若指 = node_id 本身：不违反，这本来就是终态。
- 若指再造独立于 node_id 的第三标签字段：= 复活 class_id 换个名字，违反概念消灭精神。best_ever_v1 的"class_id 值为 node_id 风格"之所以被废弃，是因为它的使命（事件类型注册表反查）已消灭（nodes.py:55 注释）；Task 4 把值迁成 `__name__` 是字段无处安放后的语义漂移，不是设计。现在删除是纠正漂移。
- **划线判据精确化（skeptic 挑战 c，arch 接受）**：初稿"独立于 node_id 的新标签 = 复活 class_id"过宽——按此标准 gate_name 也是独立标签（gf 内、非 node 派生、语义标识），但它显然不是还魂。正确定性：class_id 的定义特征不是"独立"，而是**承担事件类型的身份/分组/归属职能**。修正后划线："任何承担类型-身份轴职能（作为分组/过滤/归属键）的新标签 = 复活 class_id"。实施意义：未来有人想加 NodeSpec.tag 之类字段，判据是"它是否成为第二身份轴"，不是"它是否是独立字符串"——gate_name（判据名）合法；spec tag 若用于 UI 分组 = 还魂。
