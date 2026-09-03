# skeptic 笔记 · Q1（方案 A 是否最佳）红队攻击记录

全部 file:line 于 2026-08-14 在 instance-id-refactor 分支实测核对。

## 0. 结论先行

**方案 A 骨架全部成立（wrapper 注入、删 class 门、删冗余字段均正确），但不是最佳——应修订为 A'（三处补强）**：
A' = A + ①共享产-gate detector 从"接受模糊"改为"校验拒绝"；②连带清单补齐（debug_enabled_classes 改名/删、5 处 docstring 残留）；③把"顺手修复现存双 bug"写进验收。

攻击中推翻 lead/context.md 的三处事实（均不撼动方案方向，反而让它更简单）。

## 1. 攻击项 1：共享 detector 模糊性

**攻击成立，但解法不是换 wrapper 变体，而是消灭该状态。**

- 机制：`attach_and_collect` 逐 node 赋 `node.detector.on_gate = wrapper`（gate_collector.py:41-44），共享 detector 时后写覆盖前写 → 全部 gf 归最后一个 node。方案 A 自认"模糊"。
- 定性：**这不是显示降级，是数据错误**——gf 被错标 node 后，诊断 UI 把 bo 的失败归到 tb 名下，用户据此调参会错方向。"唤醒时才炸"的潜伏 bug。
- wrapper 变体穷举（广播 replace 多份 → 下游重复计数；链式回调 → detector 单槽不支持；置 node_id='' → 引入"未知 node"语义、过滤行为要特判）——全都引入新复杂度，不如消灭状态本身。
- **A' 补强 ①**：PatternSpec 校验加窄禁令——`hasattr(detector, 'on_gate')` 的 detector 实例被 ≥2 个 node 引用时 raise ValueError。依据：
  - on_gate 是类属性静态声明（breakout.py:124/238、throwback_v1.py:398 等 `on_gate = None`），hasattr 判定"产 gate 能力"准确；
  - 产 gate 的三 atom（BO/Burst/TB 系）detector 全部无状态全量 detect，共享零收益；
  - 当前 6 个生产 spec（bo_only/bb_v0/bb_v1/bb_v3/bottom_burst/try_conplex_where）逐一核对：每个 NodeSpec 各自新建 detector 实例，零共享实例；
  - 窄禁令不碰合法共享（如 down/side 共享 TrendDetector——Trend 无 on_gate，trend.py:41）。
  - 备选：只在 attach_and_collect 里 raise（保护面窄于 spec 校验，且报错时机晚）。推荐 spec 校验。

## 2. 攻击项 2：debug 删 class 门的定位唯一性（实证复核）

**复核通过，(bar, anchor_kind) 在单 pattern 内无歧义；但 fork 论证②的数据表述有误（结论侥幸成立）。**

埋点实测 **30 处**（非 ~28），全部在 throwback 家族 4 文件：
- throwback.py 9 处：Event{gate:304, entry:312} + Segment{end×6: 173/182/191/199/205/243, confirm:238}
- throwback_v1.py 7 处：**全部 EventV1**{gate:120, confirm:210, end×4: 259/269/273/279, entry:316}
- throwback_v0.py 6 处：**全部 EventV0**{gate:116, confirm:204, end×3+1: 246/250/256, entry:292}
- throwback_v3.py 8 处：EventV3{gate:69, entry:302} + SegmentV3{end×5: 135/155/163/171/216, confirm:205}

**fork 论证②错误处**：所谓"容器埋点恒 gate/entry、段埋点恒 end/confirm"的"数据铁证"对 v1/v0 不成立——v1/v0 无段层，end/confirm 埋点挂的是容器类（如 v1:259 `anchor_kind='end', class_id=ThrowbackEventV1`）。

**结论仍成立的真正理由**（替换 fork 的论证）：
1. bo/burst/trend/platform/distribution 零 debug_break 埋点（has_debug_hooks 全 False，breakout.py:122/235 等）→ 埋点全集 = tb 家族；
2. 单 pattern 只挂一个 tb detector 版本（6 spec 逐一核对）→ (bar, anchor_kind) 唯一命中一个 detector 文件；
3. 同 detector 内同 (bar, anchor_kind) 的多出口埋点（v1 的 259/269/273 同为 (i-1,'end')）class 门本就无法区分（同类名），真区分器是 pydevd stop_at_frame 的行号——删 class 门零损失。

**残余风险（诚实披露）**：同 pattern 并存两个不同版本 tb detector（如 tb + tb_v1 做 A/B 对照）时，(bar, end) 会命中两处、连 pause 两次。当前零实例；pause 行号（throwback.py vs throwback_v1.py）自证版本，属可接受降级非功能破坏。

**附带发现（方案 A 的隐藏红利）**：删 class 门顺手修复现存双 bug——view.ts:825 把 `event.node_id`（'tb'）当 eventClass 传 → api.py:292-293 `DEBUG_EVENT_CLASS='tb'` ≠ 埋点值 `'ThrowbackEventV1'` → ①debug_ctx.py:79-81 class 门恒 false（右键 debug 三锚全不 pause）；②diagnose.py:215 `_class_ok` 用 'tb' 过滤 `gf.class_id`（值 'ThrowbackEventV1'）→ 右键请求的 failed_attempts 恒空。方案 A 的 node 过滤同时修两者。**建议写进验收**：右键 debug 端到端 e2e（pause 恢复 + failed_attempts 非空）。

## 3. 攻击项 3：信息丢失（"哪个版本 detector"）

**评估：无实质丢失场景。**

1. gf 不持久化：scan 文件无 gf 字段（serialize_per_pattern_result，serialize.py:288+）；eval 路径收集但自认无消费者（eval_runner.py:72）→ 不存在"归档后回看"场景。
2. gf 只活在实时诊断（入口A），请求恒带 pattern_id → 版本由 pattern_id 承载（bb_v1/bb_v3 的 pattern 名即版本）。
3. **行内已有承载位**：gf.code_location（`throwback_v1.py:126` 风格，__post_init__ 自动抓，gate_failure.py:76-111）含 detector 源文件名+行号，已序列化进前端契约（types.ts:176）。版本信息一直在 payload 里，只是 UI 没显示；要显示是前端加一行的事。
4. 未来单 pattern 并存多版本时：node_id 是自由字符串，author 命名 `tb_v1`/`tb_v3` 即表达版本（NodeSpec 无命名约束，nodes.py:44），架构零改。版本表达不是丢失，是 apps 选择了不带版本的命名。

## 4. 攻击项 4：web 契约变更面复核

lead 清单基本齐，**遗漏三处（均轻）+ context.md 两处事实修正**：

- **遗漏 1：`debug_enabled_classes`**（serialize.py:267-284、api.py:245 老文件 backfill、types.ts:23）——字段名是 class 概念残留，值已全是 node_id（注释自认"沿袭旧名"），**前端零实际消费**（仅类型声明）→ 应改名 `debug_enabled_nodes` 或直接删（老 scan 文件 backfill 一并处理）。
- **遗漏 2：apps docstring 5 处过时描述**：bb_v0/bb_v1/bb_v3 各自 `__init__.py` + `dag_spec.py:5` 写 `class_id=tb_v1` 等（旧 tag 值）；try_conplex_where/dag_spec.py:50 称基类字段含 class_id（Event 基类已无此字段，core.py:68-73）。
- **遗漏 3**：gate_collector.py:10-12 注释"同一 detector 可能被多 node 共享…幂等"需随 A' 补强①同步改写。
- **context.md 事实错误 1**：源头 1 是 **TopoNode.class_id**（spec.py:21，to_topology 投影产物，spec.py:246 赋值），不是 NodeSpec.class_id——NodeSpec（nodes.py:44-51）根本没有该字段。
- **context.md 事实错误 2（重要，让方案 A 更简单）**：TopoNode.class_id **全 repo 零读者**——serialize_pattern 不读它（serialize.py:249-259 的 node dict 无 class_id）、前端 TopoNode 类型无此字段（types.ts:8-16）、dag 引擎/求解层零引用（grep `.class_id` 于 path2/dag 无结果）。其注释"字段名保留供 web 消费"是错的。→ 删除它是纯死字段清理，**无任何 web 消费需迁移**（lead 预估的"web 消费改用 node_id"一项实际不存在）。
- 附带：GateFailure 生产构造点实测 **13 处**（throwback 家族 4 + breakout 9），gate_failure.py:73 注释称 10 处——删 kwarg 改动面基数修正。debug_break 埋点 30 处（见 §2）。

前端消费点复核（与 lead 清单对齐无新增遗漏）：types.ts:169/176/181-184、api.ts:71-82、view.ts:240/773-774/817、DetailSidebar.vue:36/386-387、FailedAttemptsCard.vue:6-79、KlineChart.vue:624。后端：diagnose.py:178/200/203/215、api.py:276/292-293/321/342-346、serialize.py、atoms 13 构造点 + 30 埋点。

## 5. 替代方案构造与裁决

### B：detector 显式传 nid（on_gate 签名带 nid / detector 持有 node 引用）——弃
node_id 是 spec/引擎层概念，detector 阶段不可知（core.py:68；BarwiseDetector.detect(df) 无 node 上下文，templates.py:29）。要 detector 知道 nid 只能：①NodeSpec.__post_init__ 反向注入 detector → atoms 依赖 node 概念，破坏"走势无关 atoms"分层脊梁（nodes.py docstring 明言）；或 ②attach 时 setattr + 13 处构造点改读 → 改动面 13 处 vs wrapper 1 处，且共享场景同样错。"显式优于隐式"的批评不成立：wrapper 是挂载方闭包携带挂载上下文的标准回调模式（等价 functools.partial），不是隐式 magic。

### C：spec 层声明非类名 tag 字段——弃（但向用户披露此空间曾被考虑）
tag 与 node_id 在一 node 一 detector 下恒一一映射，纯冗余概念；本质是 class_id 换名还魂，与用户"彻底清除"意图相反。版本对照的真需求由 node_id 自由命名承载（§3.4）。若未来出现"同 pattern 多版本并存"，届时 node_id 命名即是声明式标签，无需新字段。

### D：GateFailure 不加 node_id，靠已有 code_location/gate_name 定位——弃
入口A 下拉的用户心智是"哪个角色（node）的尝试失败"，不是"哪个源文件/哪个 gate"。gate_name 粒度错位（bo 一个 node 有 7 个 gate_name）；code_location 是实现细节且本质是类名替身（throwback_v1.py ≈ ThrowbackEventV1），绕回类型分组。node_id 是唯一语义正确的分组键。

### 裁决：A'（= A + 三补强）最优
A 的三个核心动作（wrapper 注入 node_id、删 debug class 门、删 TopoNode.class_id）全部经受住攻击；A 唯一实质缺陷是"接受共享模糊"（§1），A' 用窄禁令校验消灭之。A 相对 B/C/D 的优势：atoms 保持走势无关、改动面最小（1 处 attach vs 13 处构造点）、分组键语义正确。

## 6. 队队交叉复核后的吸收与修正（2026-08-14 第二轮）

**coder 纠偏采纳（对 context.md §2 的事实修正，不影响方案 A 前提）：**
- context.md "gate 失败 = 该 attempt 不产出 event（短路失败）"**以偏概全**：phase1 三短路确实不产 event，但 phase2_break/weak **产事件且同时 emit gate**（throwback_v1.py:253-270，docstring :379 自认）。正确表述：GateFailure 不持有 event 引用（无论是否与 event 同产），node 归属无法从 event 反查 → wrapper 注入仍是唯一解，且 phase2 场景 gf 与 event 同 node、wrapper 归属依然正确。
- coder 独立复核全部通过且补强：定位唯一性成立（同 (attempt,bar) 出口分支互斥；跨 attempt 窗口重叠当前参数下不发生——burst 间隔≥20 > max_start_gap+max_window=12；tbAnchorProfile 前端 view.ts:41-50 已按 child_refs 区分容器/段/V1 三档变体，后端 class 门是链路上唯一残留 __name__ 环节）。
- coder 提出"class_id 保留字段加默认值 → 13 处构造零改"的最小改动变体：**裁定不采**——保留字段违背用户"彻底清除"明令；13 处删 kwarg 是机械改动，不构成负担。删。

**arch 认输并背书 A'（禁令优于其哨兵方案）**；其 fork 论证②表述错误已双方确认（真理由 = class 门区分度上限是 detector 粒度，单 pattern 下 (bar,anchor_kind) 恰达同一粒度 → class 门零增量）。

**arch 的实施级 flag（hasattr 判据不精确）被实测部分证伪：**
- 5 个产 gate atom 全部有**类级** `on_gate = None` 静态声明（breakout.py:124 Burst、:238 BO、throwback.py:282、throwback_v0.py:366、throwback_v1.py:398、throwback_v3.py:265）；trend/platform/distribution 零声明（grep 无匹配）→ attach 前 `hasattr(detector, 'on_gate')` 判定即准确。arch 担心的"平时类上不存在此属性"不成立于现有 atom。
- core.py:135-142 的 TYPE_CHECKING 守卫是 Detector **Protocol** 的 isinstance 行为问题，与 atom 类自己的类级声明无关。
- 判据的真实真空区（arch flag 的合理内核）：**自定义 detector 作者若不写类级声明**（只靠 attach 赋实例属性）→ spec 校验期漏判。闭环方案：authoring-path2-detector skill 的 on_gate 接线指南（reference.md §4）已存在，实施 A' 时加一句"类级 `on_gate = None` 声明是 spec 校验识别 gate 能力的依据"。当前零此类实例。判据细节交 coder 落实，方向不变。
- 备选判据（attach 期 id() 重复即 raise）被否：会误杀合法共享（down/side 共享 TrendDetector，nodes.py:26-28 明文支持的一身多角）——TrendDetector 无 on_gate，attach 是无条件赋值，attach 期判据无法区分"有 gate 能力"与"无"。

**新发现先例（支持 wrapper 模式）**：主线 ThrowbackDetector 内部已有 on_gate 再包装先例（throwback.py:300-306，`_real = self.on_gate; def _on_gate(gf): ...` 补 gate debug 钩子）——collector 侧 wrapper 与之同构，且链式兼容（collector wrapper 挂 self.on_gate 后会被内层再包一次，gf 流向不变）。

**对 arch 挑战的回应（张力点④划线精确化）：**
- arch"独立于 node_id 的新标签 = 复活 class_id"立场**过宽**：按此标准 gate_name 也是独立标签，但无人认为它是 class_id 还魂。正确定性：class_id 的定义特征不是"独立"，而是**承担事件类型的身份/分组/归属职能**。修正后划线："任何承担类型-身份轴职能（作为分组/过滤/归属键）的新标签 = 复活 class_id"；gate_name 是判据名（描述失败原因），不参与身份分组，故合法。
- "裸记录脱离 pattern 上下文"场景评估：当前无权重——gf 生命周期 = 单请求内（api.py request 级 env + finally pop），不持久化（scan 文件无 gf 字段）。未来若持久化为独立数据集，正确解是给数据集加 pattern_id 列（数据集设计），而非行内塞版本。不构成保留 class_id 的理由。

## 7. 对 Q1 的最终裁定

**方案 A 不是最佳；A'（A 的修订版）是。** A' 与 A 的差异全部是收紧而非重设计：共享禁令（~10 行校验）、清单补齐（1 个死契约字段 + 5 处 docstring + 1 处注释）、验收补右键 debug e2e。无新增机制、无新增概念——符合奥卡姆。

**A' 最终形态（吸收队友复核后）：**
1. TopoNode.class_id 删字段（零读者实证，纯死字段，无 web 迁移）。
2. GateFailure：删 class_id、加 `node_id: str = ''`；wrapper 注入（gate_collector.attach_and_collect 一处改，先例 throwback.py:300）；13 生产 + 6 测试构造点删 kwarg（全部 kwargs 形态实证）。
3. debug：删 class 门（debug_ctx.py 四门→三门）+ 30 埋点删 class_id kwarg + api/前端删 event_class 通道；验收补右键 debug e2e（顺带修复 d64083be 双 bug：class 门恒 false + failed_attempts 过滤清空）。
4. 共享产-gate detector：PatternSpec 校验窄禁令（hasattr(detector,'on_gate') 判据，attach 前准确；skill 指南闭环类级声明规范）。
5. 清单补齐：debug_enabled_classes 改名/删、apps 5 处 docstring、gate_collector 注释。

## 8. 第三轮：coder 全项确认 + 禁令放置层的残余分歧（2026-08-14）

coder 正式确认 §1-5 全部代码事实（TopoNode 零读者 / hasattr 判定准确 / 30 埋点分布 / 双 bug 链 / 13+测试构造点全 kwargs），并精确化：**bug2（diagnose.py:215 恒过滤空）只影响右键 debug 那次请求**——入口 A triggerTimeQuery 恒不传 event_class（view.ts:774-777）显示正常，恰好解释用户现象（入口 A 能看到类名、右键 debug 失效）。另发现 bottom_burst/dag_spec.py:60 注释 stale 文案（event_id）顺手更正，并入清单。

**残余分歧（唯一，不撼动 A' 主干）——共享防护的放置层**：coder 裁定 attach_and_collect 哨兵（seen dict by id(det)，二次赋值置哨兵 ~4 行），反对 PatternSpec 禁令。我方反驳（已发 coder）：
1. 其"spec 层 raise 推翻文档载明的合法用法"是论域滑动——NodeSpec docstring（nodes.py:26-28）载明的共享例子是 TrendSegmentDetector，而 Trend 无 on_gate，窄禁令下完全合法；从"无 gate detector 共享合法"推不出"产 gate detector 共享合法"。
2. gate_collector.py:10-12 注释（"共享幂等"）是现状描述非设计承诺，且方案 A 的 wrapper 本身已破坏该幂等性、注释已在待改清单——用将改之物论证不可改，循环论证。
3. 哨兵显示层语义未定义（下拉过滤时哨兵行算哪个选项？），矛盾被延迟到显示层而非解决；arch 在同一点上已认输。
4. 补充先例：PatternSpec._validate_render_grid（spec.py:209-228）已读 n.detector.event_cls/is_point——spec 校验读 detector 声明属性有直接先例，非新耦合类别。

**我方优先序：spec 窄禁令 > attach 期 raise > 哨兵**（前两者均为消灭/立即暴露错误，仅报错时机与保护面之差；哨兵最次）。已声明：attach 期 raise 可接受（实施层自由度），哨兵不签字——除非补上显示层语义定义且证明更简单。标注为开放实施细节，交 leader 拍板。

## 9. 第四轮：声明期禁令认输 + 延迟 raise 第三选项（2026-08-14，最终轮）

**arch 终稿撤回禁令支持（"检测有效性 > 检测时机"+ 递归缺陷论），coder/arch/lead 三方一度收口静默哨兵**（final_report v1 §4）。我方最终回应：

1. **事实纠正（arch 终稿论据 1 的前提）**："产 gate 无法从类结构推断、类上零反射痕迹"不成立于存量——5 个产 gate atom 全部有类级 `on_gate = None`（throwback.py:282 / v0:366 / v1:398 / v3:265 / breakout.py:124+238，coder 两轮亲验）；trend 零声明（grep 确认）。存量零遗忘零误报。
2. **认输其时间维度论证**：未来自定义 detector 的类级声明依赖 authoring skill 指南，可遗忘——"防作者犯错的机制依赖作者配合 = 递归缺陷"成立；且 arch 论据 2 反向削弱声明期禁令的"提前告知"价值（author 读源码才知道谁产 gate）。**放弃声明期禁令作为首选。**
3. **第三选项：attach 侧延迟 raise**——判据沿用 coder 哨兵的 seen dict by id(det)（零作者配合、运行时真值），wrapper 行为从"静默置哨兵值"改为"raise RuntimeError（带修法：产 gate detector 须一 node 一实例）"。共享时 _boom 覆盖首 node 的 _wrap（单槽后写胜）→ 该 detector 全部 gf 都 raise（归属不明就该全炸，不能静默归首 node）。性质：零作者配合 × 零误杀（Trend 合法共享从不 emit gf 永不触发）× 首条共享 gf 即炸（≈ 该 spec 第一次真实扫描，bo/tb gf 高频必触发）× 错误信息直达 author。~8 行，链式兼容先例 throwback.py:299-307。已请 coder 验证四点（单槽覆盖语义 / 零误杀 / raise 冒泡面 scan-eval-api 三路径 / eval 路径豁免与否）。
4. **对静默哨兵的两点保留（最终立场）**：a) 显示层语义未定义（下拉过滤时哨兵行算哪个选项？全选项显示=重复计数，单列一类=新 UI 概念，与概念收敛方向相反）——coder 两轮未答；b) 静默降级在单人开发流可能永不被察觉（每扫描成百上千条 gf，一行 node_id='' 淹没其中）。
5. **最终优先序：attach 延迟 raise > spec 声明期禁令 > attach 静默哨兵**。若团队最终裁静默哨兵，接受程序结果、保留本条异议；若接受延迟 raise，final_report §4 实施形态应写"attach 侧运行时防护（raise 优先）"。

**分歧性质收口**：三方对"消灭产-gate-detector 共享状态"目标零分歧，分歧最终收敛为"检测到之后的一行行为选择：静默降级 vs raise"。

## 10. 终裁收口（2026-08-14，lead 两轮拍板，分歧全关闭）

**终裁轨迹（两轮反转，最终落定我方第三选项）**：
- lead 第一轮拍板形态 X：attach 期立即 raise，判据 `hasattr(detector,'on_gate') ∧ id 共享`。
- coder 四点验证我方伪码时发现 X 的漏判面：**"flag 遗忘（写了 emit 没写类级声明）+ 共享"时 hasattr=False → 不进共享检测 → 挂普通 wrapper → 真 emit 时归属错误静默**——恰好重新引入 arch"递归缺陷"论要消灭的声明性近似。我方纯 id + 延迟 raise 三行全覆盖该场景。
- **lead 终裁：采纳第三选项（attach 侧延迟 raise）为 A' 第 4 条最终形态**——判据从 hasattr（声明性近似）升级为 gf 真到达（运行时真值），消除最后的作者配合依赖；零误杀等价成立；检测点与错误发作点 100% 重合；三方最强论据融合（skeptic 的 raise 行为 × coder 的 seen-dict 判据 × arch 的运行时真值标准）。

**coder 四点验证全部成立**（coder-notes §10 附节）：①单槽覆盖 ✓（gate_collector.py:41-44 逐 node 实例属性赋值，_boom 后写覆盖 _wrap，该 detector 全部 gf 都炸；id() 在 attach→detach 窗口内稳定，spec.nodes 持引用；第三 node 重复挂 _boom 幂等）；②零误杀 ✓ 实证（trend 零 on_gate 调用，合法共享永不 emit；纯 id 判据连"声明了但从不 emit"的边缘也不误杀）；③冒泡面三路径天然接住零专门异常（engine.py 零 try/except 无损冒泡；scan.py:136-137 / eval_runner.py:117-118 `except Exception` per-symbol error 不裸崩进程池；api /diagnose RuntimeError 走默认 500 可接受；三路径 finally detach/pop 零泄漏）；④eval 不豁免 ✓（豁免=无 wrapper 分支开洞+多代码，不豁免=零代码全路径统一，零存量共享=零现实成本）。

**终轮质量记录**：
- coder 干净认错三条（论域滑动 / 循环论证 / 显示层语义真缺口）并撤哨兵，其独立新论据 **"gf.node_id 在共享产 gate 场景结构上无真值"**（on_gate 是实例属性，detector 的 detect 不知道被哪个 node 调用，wrapper 无论多聪明都拿不到归属）比我方"显示层语义未定义"更根本——上游无真值 ⟹ 下游任何降级都是无米之炊。此定式已采纳为哨兵淘汰的决定性论据；其验证期发现的 X 漏判面直接促成终裁反转。
- arch 确认我方 hasattr 证伪成立（其"递归缺陷"论据坍塌，根源 = 从 core.py:141-142 Protocol TYPE_CHECKING 推断 atom 实现而未 grep atoms），认错在案；接受张力点④职能划线修正；接受终裁。
- lead 把我方 spec 声明期校验记为可选增强（升级无机制障碍，_validate_render_grid 先例已记录）；我方"认输声明期禁令"的诚实声明与两点终局保留（显示层语义未定义 / 静默降级可能永不察觉）均已补记 final_report §4。

**skeptic 最终优先序落定（= 终裁形态）**：attach 侧延迟 raise（纯 id 判据 + _boom 延迟炸）> spec 声明期禁令（可选增强）> attach 期立即 raise（hasattr 过滤有漏判面）> 静默哨兵（淘汰）。无未决项，研究关闭。
