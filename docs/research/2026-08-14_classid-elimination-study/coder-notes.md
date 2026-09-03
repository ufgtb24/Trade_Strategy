# coder 笔记 · 代码事实复核 + 消费点收敛表 + authoring 成本（2026-08-14）

全部结论带 file:line，实测于 instance-id-refactor 分支。

## 1. context.md 断言复核

### 1.1 三源头收敛性 —— 部分证伪（源头定位纠偏，收敛性本身成立）

- **证伪**：`NodeSpec` **没有** class_id 字段（`path2/dag/nodes.py:30-47` 字段全集 = node_id/detector/event_cls/produced_by/children/where/consumes_stream/render_grid，python 实测 `NodeSpec.__dataclass_fields__` 确认）。`path2/dag/spec.py:21` 的 class_id 属于 **`TopoNode`**（拓扑面板投影数据类，spec.py:15-24），context.md 把它误记为 NodeSpec。
- 修正后三源头 = `TopoNode.class_id`（spec.py:21，to_topology 于 spec.py:246 填 `n.event_cls.__name__`）/ `GateFailure.class_id`（gate_failure.py:65）/ `debug_break` class_id 参数 + class 门（debug_ctx.py:40, 79-81）。
- **无第四源头 ✓**：Event 基类（core.py:29-76）字段全集无 class_id/event_id/source_tag（旧身份体系确已消灭）。
- 规模复核：后端非测试 **70 处/20 文件**（context 说 68，计数口径差异，量级吻合）；前端纯 class_id **5 处/3 文件**（context 说 8；含 className/eventClass/eventClass 关联链路则 28 处/6 文件）。

### 1.2 新发现：TopoNode.class_id 是纯死字段

`serialize_pattern`（serialize.py:249-260）节点输出仅 node_id/where_rules/render_grid/materialize_keys/produced_by/child_slot/parent_refs——**不含 class_id**；前端 types.ts/api.ts 无 topology class_id 消费。→ 删 TopoNode.class_id 零 web 连带。

### 1.3 GateFailure 构造点全集（src 内 13 处）

- `path2/atoms/breakout.py`：144, 172（BurstEvent）/ 329, 386, 412, 429, 454, 473, 491（BOEvent）— 9 处
- tb 四版各 1 处（helper 内）：throwback_v1.py:121、throwback_v0.py:117、throwback.py:102、throwback_v3.py:70

### 1.4 「gate 失败不关联已物化 event」—— 表述以偏概全（结论不变）

- Phase1 三条短路（phase1_break/rise_before_confirm/no_confirm_timeout）确实不产 event（throwback_v1.py:177-219 各分支 `return None`）。
- **但 phase2_break / phase2_weak 产事件且同时 emit gate**（throwback_v1.py:253-270：emit 后 `return i-1,"break"` → evaluate 返回 result → detector 产事件；类 docstring 379 行自认"事件仍产, phase2_break gate"）。
- 不影响方案 A 前提：GateFailure 本身不携带 event 引用，「从 GateFailure 反查 node_id 无门」成立，wrapper 注入 node_id 仍是唯一通路。

### 1.5 共享 detector 酶实例断言 ✓（注：应为"零实例"）

全部 6 个 dag_spec 逐一核对：bb_v0/bb_v1/bb_v3/bo_only/bottom_burst/try_conplex_where 均 `NodeSpec("bo", BODetector(**params.bo_kwargs()), ...)` 形态——build 时每 node 新构造独立实例，无一例共享同一实例给两个 node。

### 1.6 debug 埋点全集 = 30 处（context 说 ~28），全在 throwback 系

throwback.py 9 / throwback_v0.py 6 / throwback_v1.py 7 / throwback_v3.py 8。**BODetector/BurstDetector 零 debug_break 埋点**。
anchor_kind 分布：end×18 / gate×4 / entry×4 / confirm×4。

### 1.7 d64083be 前端 bug 链路 ✓

view.ts:817 `className: event.node_id`、:825 第 7 参传 `event.node_id` → api.py:296-301 写 `DEBUG_EVENT_CLASS` → debug_ctx.py:79-80 与 `__name__` 比较 → 恒 false → 右键三锚全不命中。

## 2. 消费点收敛表（方案 A 后各语义点落点）

| # | 语义 | 位置 | 方案 A 落点 |
|---|---|---|---|
| 1 | 定义·拓扑 | spec.py:21（TopoNode.class_id）+ :246 填值 | 删字段+删填值（web 零消费，纯死字段） |
| 2 | 定义·gate | gate_failure.py:65 | 删 → `node_id: str = ''`（带默认值兼容 13 构造点） |
| 3 | 定义·debug | debug_ctx.py:34,40,46,53,79-80 | 删参数 + 删 class 门（四门→三门） |
| 4 | 埋点传值·debug | atoms 30 处 `class_id=XXX.__name__` | 删实参 |
| 5 | 构造传值·gate | atoms 13 处 `class_id=XXX.__name__` | 删实参（wrapper 由 gate_collector 注入） |
| 6 | 注入·gate | gate_collector.py:37-45 attach_and_collect（遍历方已知 node.node_id） | 改 per-node wrapper：`dataclasses.replace(gf, node_id=node.node_id)` |
| 7 | 查询过滤·gate | diagnose.py:203（all_classes=__name__ 全集）/ :215（gf.class_id==query.event_class）/ api.py:296-301（env 写入） | all_classes → spec node_id 全集；过滤改 gf.node_id；api 参数语义改 node |
| 8 | 显示·前端 | FailedAttemptsCard.vue:79（a.class_id）+ types.ts:169 | 显示 node_id |
| 9 | 过滤·前端 | FailedAttemptsCard.vue:13,20 + api.ts:71-82（eventClass 参数） | 改 node_id 语义 |
| 10 | debug 卡显示 | DetailSidebar.vue:36（debugTarget.className，值已是 node_id） | 只改字段名 |
| 11 | debug 请求 | view.ts:825（已传 node_id） | **零改，bug 自愈** |
| 12 | 注释/docstring | spec.py:19 / nodes.py:55 / serialize.py:8 / bb 各 __init__+dag_spec（旧 tag tb_v1 等）/ v3.py:55-57 / diagnose.py:178-179 | 文案更新（非功能） |
| 13 | stale 消费 | scripts/gate_burst_2x2.py:94（`e.class_id=="burst"` 当前必 AttributeError）/ scripts/path2/path2_diag_env.py:25 / try_conplex_where/dag_spec.py:50 docstring | 修或删（本已坏/stale） |
| 14 | 测试 | 24 文件 107 处（重灾区见 §5） | 重写断言 |
| 15 | skill 文档 | authoring-path2-detector SKILL.md:114-117,165-169 + reference.md:97-99,150-181（描述 __init_subclass__/span_id 旧体系，已 stale）；diagnose-event/detectors/<class_id>.md×2 | 同步重写（否则 skill 指导 AI 写出带 class_id 的新代码） |

## 3. 关键新事实：前端已完成 node_id 化，后端 class 门是唯一残留环节

- `anchorsOf` 键 = node_id（view.ts:113-122，键只有 `tb`/`_default`）。
- `DEBUG_ENABLED_CLASSES = Object.keys(anchorsOf)`（view.ts:127）——值是 node_id；后端 serialize.py:267-278 `debug_enabled_classes` 值也已是 node_id。
- **tbAnchorProfile（view.ts:41-50）已靠 child_refs 结构信号区分 容器/段/V1 三档变体**——「版本信息丢失」张力点的前端解已存在且不依赖类名。
- → 方案 A 的 debug 部分 = 把后端对齐到前端已完成的世界（修断层，非新设计）。d64083be 实质是前端 node_id 化迁移没配后端的半拉子。

## 4. debug 定位唯一性实证（④，独立复核 fork 论证）

运行形态：`/diagnose` 单 pattern_id 单请求（api.py:285-305），DEBUG_* 三 env request 级写入 finally pop。同请求内只有一个 spec 一个 pattern。

30 埋点按 (anchor_kind × 类) 矩阵：
- 容器埋点（ThrowbackEvent/V3）：anchor_kind ∈ {gate, entry}（throwback.py:304,312 / v3.py:69,302）
- 段埋点（ThrowbackSegment/V3）：∈ {end, confirm}（throwback.py:173-243 / v3.py:135-216）
- V0/V1 单类：四 kind 都有，但单 pattern 内埋点只来自一个文件
- 单 pattern 内带埋点的 detector 恰好 ≤1 个（bo/burst 零埋点，tb 每 pattern 只挂一版）

结论：
1. **容器 vs 段互斥由 anchor_kind 完全承担**（30 埋点逐点核对，无交集）——fork 论证数据成立。
2. 同文件同 anchor_kind 多埋点（v1 end×4、旧版段 end×5+timeout）在同一 (attempt, bar) 互斥（各出口分支 return 互斥）；跨 kind 的 bar 巧合（confirm bar == end bar）被 anchor_kind 门区分。
3. 跨 attempt 同锚同 bar 双 fire：当前参数下窗口不重叠（burst 间隔 ≥ first_drought=20 > max_start_gap+max_window=12）；即使发生，两次 fire 同类同锚，class 门同样零区分力。
4. 跨 pattern 撞车（V1 entry vs V3 entry 同 bar）：单请求单 pattern 不共存；并发请求 env race 是既有问题（api.py:340 注释自认），与 class 门无关。
5. **裁定：删 class 门后 (bar, anchor_kind) 在全部 30 埋点、真实运行形态下定位唯一，无新增歧义。**（前端 profile 细分已把"想 debug 哪一档"翻译成 anchor_kind，不需要类名参与。）

## 5. 方案 A 实施面清单（⑤）

**后端 src（10 文件）**：spec.py / gate_failure.py / debug_ctx.py / gate_collector.py（wrapper）/ diagnose.py / api.py / serialize.py（注释）/ atoms: breakout.py（9 处 GateFailure）+ throwback.py/v0/v1/v3（埋点+构造）/ scripts: gate_burst_2x2.py + path2_diag_env.py（stale 修复）。
**前端（5 文件）**：types.ts / FailedAttemptsCard.vue / DetailSidebar.vue / api.ts / view.ts（debug 卡字段名）。
**测试**：class_id 相关 24 文件 107 处；重灾区 test_debug_ctx.py(42)、test_throwback_v3_debug_anchor_kinds(17)、test_diagnose_time(10)、test_diagnose_class_env(event_class 21)、test_tb_on_gate(4)、test_bo_on_gate(4)，其余 17 文件散点 1-3 处。
**dag_spec 层**：零代码改动（NodeSpec 无 class_id 字段可传；6 个 dag_spec 的 class_id 出现全是 docstring 旧 tag 文案）。
**skill 文档**：authoring-path2-detector（SKILL.md 对拍节 + reference.md §3 契约，后者整体 stale 须重写）、diagnose-event/detectors/ 两份 md 按类名组织 → 改 node_id。

## 6. authoring 成本对比（③，以 throwback_v1.py 为样本）

### 现状：新增一个带 debug+gate 埋点的 detector，class_id 相关必写项
1. event 类定义：class_id 零代码（Task 4 后值=__name__ 自动派生）——已零成本。
2. debug 埋点 ×N：每处 `debug_break(..., class_id=ThrowbackEventX.__name__)`（v1 7 处 / v3 8 处）——纯重复样板，值恒等。
3. gate helper：`GateFailure(class_id=ThrowbackEventX.__name__, ...)`（v1.py:126）——**版本复制 helper 时必须手改类名**（v3.py:55-57 注释自认"逐字复制,唯一改动:class_id 值"= 真实出错面；skill 踩坑清单 SKILL.md:165-166 明载"漏改→无声失败"）。
4. 前端 anchorsOf 条目：已按 node_id（与 class_id 无关）。
5. skill 对拍：(class_id, anchor_kind) 二维矩阵对拍（SKILL.md:114-117）。
6. diagnose-event/detectors/<class_id>.md 诊断契约文档。

### 方案 A 后
- 2 → 每埋点少一个参数；3 → helper 少一个手工同步点（"复制漏改类名"整类错误物理消失）；5 → 对拍降为 anchor_kind 一维；6 → 文档按 node_id 组织。
- 新增必写项：**零**（wrapper 集中在 gate_collector 一处，detector 作者无感；GateFailure.node_id 带默认值）。
- **净变化：authoring 步骤单调减少，出错面删去一整类（类名漂移静默失败，现存 3 处历史痕迹：skill 踩坑、v3 复制注释、d64083be bug）。**

## 7. 方案 A 机械核心可行性预验

- GateFailure 是 frozen dataclass（`GateFailure.__dataclass_params__.frozen == True` 实测）；frozen 上 `dataclasses.replace(gf, node_id=...)` 是 Python 文档化支持。
- 「删 class_id、加 `node_id: str = ''`」与 gate_failure.py:71-72 现成先例完全同构——code_location 就是带默认值追加的（注释自认"追加字段,带默认值 → 既有 kwargs 构造点全兼容"），同一手法。
- 附带实证：`ThrowbackEventV1(...).class_id` → AttributeError（core Event 无此字段），坐实 scripts/gate_burst_2x2.py:94 当前必崩（stale）。
- 抽查 baseline：test_gate_failure.py + test_debug_ctx.py = 31 passed。

## 8. skeptic 替代方案验证（⑥）+ arch 补充问题回答

### skeptic 5 项代码事实复核（全部确认/精确化）

1. **TopoNode.class_id 零读者 ✓ 完全确认**：全库唯一写点 spec.py:246（`TopoNode(n.node_id, n.event_cls.__name__, ...)` 位置传参）；`grep '\.class_id\|class_id=' path2/dag/` 零读引用；serialize_pattern 不输出；前端无字段。纯死字段，方案 A 源头1 = 零成本纯删。
2. **共享禁令校验可行性**：a) hasattr(n.detector,'on_gate') 判定准确 ✓——protocol 静态声明即"产 gate"标记（breakout.py:124/238、throwback_v1.py:398 等声明 `on_gate = None` 类属性；trend.py/platform.py/distribution.py 无声明 → hasattr False，trend.py:41 是 has_debug_hooks=False）。b) **我裁定放 attach_and_collect（哨兵）优于 PatternSpec（禁令）**：NodeSpec docstring（nodes.py:38-39）明文把共享当合法用法（"一身多角用不同 node_id,如 down/side 同 TrendSegmentDetector"），gate_collector.py:11-12 注释亦明言共享幂等是有意设计——spec 层 raise 推翻文档载明的合法用法；归属模糊只在收集 gate failure 时成立，attach 侧哨兵精确打击且可逆。c) 6 spec 零共享 ✓（bottom_burst/bo_only 完整核对：bo/burst/tb detector 均 `**params.*_kwargs()` 各自新建；bo_only 单 node）。
3. **30 埋点全 throwback 家族 ✓**：`grep -rln debug_break path2/atoms/` 仅 4 文件；has_debug_hooks=True 恰好 = 4 个 throwback detector（throwback.py:280 / v0:363 / v1:395 / v3:262），trend/breakout×2/distribution/platform 全 False（breakout.py:122/235 等）。
4. **双 bug 链 ✓ 成立并精确化**：view.ts:825 传 event.node_id → api.ts:82 拼 event_class → api.py 写 DEBUG_EVENT_CLASS='tb' → bug1 debug_ctx.py:79-80 与 __name__ 比较恒 false（不 pause）；bug2 diagnose.py:215 `_class_ok` 恒 false → 该请求 failed_attempts 恒空。补充：**bug2 只影响右键 debug 那次请求**——入口 A（triggerTimeQuery, view.ts:774-777）恒不传 event_class，显示正常（这正是用户从入口 A 看到类名的路径）。方案 A 后两条链同时自愈，应进 e2e 验收。
5. **13 生产构造点全 kwargs ✓**；tests 构造也全 kwargs（`grep 'GateFailure([0-9"('\''(]'` 全库零命中，test_gate_failure_code_location.py:18 为 `GateFailure(**base)`）。"删 kwarg + node_id 默认值"零位置参数风险。

### skeptic 替代方案裁决的代码面裁定（同意 B/C/D 弃，给更硬理由）

- **B（detector 显式传 nid）弃 ✓**：detector 是可复用对象，node_id 在 spec/引擎层（engine.annotate_stream 物化期才注入 event，core.py:59-68）——detect() 签名拿不到 node_id，要么改协议签名要么构造注入（13 处构造 + 协议面），且违背 detect 走势-无关分层。wrapper 1 处集中最优。
- **C（spec tag 字段）弃 ✓**：NodeSpec 已有 node_id，任何新 tag = 冗余还魂（且正是用户否决过的反向路线）。
- **D（code_location/gate_name 定位）弃 ✓**：code_location 是文件路径级、gate_name 是判据名——debug 定位分组键语义错位（用户心智 = 图上哪个锚点）。

### arch 三个 authoring 成本问题回答

- **a) 新写 detector 的 class_id 负担**：以 v1 形态为模板 = **8 处**（7 debug_break + 1 GateFailure helper）；v3 形态 = 9 处（8+1）；旧版 = 10 处。全 atoms 43 处（throwback.py 10 / v0 7 / v1 8 / v3 9 / breakout 9）。方案 A 后 = **0 处**。
- **b) 老 scan 文件兼容成本 = 零，问题不存在**：GateFailure 不落盘——serialize.py 零输出 failed_attempts/gate_failures；scan.py:117 只把 collector.snapshot() 塞进内存 result；前端收到的 failed_attempts 全部来自 /diagnose 实时响应。无持久化面即无老文件兼容。前端容错 vs 后端 backfill 之争不成立。
- **c) wrapper 对新 detector 作者零感知 ✓**：detector 内部 `on_gate(GateFailure(...))` 调用零改（GateFailure.node_id 带默认值不传即 ''，wrapper replace 注入）；attach/detach 机制不动，作者甚至不知道 wrapper 存在。

### arch 共享哨兵补丁成本裁定

值得做，增量极小：wrapper 本体是方案 A 必写（gate_collector.py:37-45 改 per-node wrapper ~3 行）；哨兵增量 = seen dict（by id(det)）+ 二次赋值分支 ~4 行 + 1 个测试。收益 = 把方案 A 已自认的"共享场景归属模糊"从静默错误值变成显式哨兵值（如 `node_id=''` 或 `'shared'`），且不杀 NodeSpec 文档载明的合法共享用法。放 attach_and_collect 而非 PatternSpec 校验（理由见 §8 skeptic 第 2 项 b）。

### 附带新发现（stale 文案）

bottom_burst/dag_spec.py:60 注释仍写 "tb.anchor_bo_id == last_bo.event_id"——现为 instance_id 形态（Task 4 后），属方案 A 清理时应顺手更正的 docstring（与 try_conplex_where/dag_spec.py:50 同类）。

## 9. skeptic 第二轮跟进的亲验（2026-08-14）

1. **hasattr 判据五处类级声明亲验 ✓**：throwback.py:282 / v0:366 / v1:398 / v3:265 / breakout.py:124+238 全部 `on_gate = None` 类级声明；trend/platform/distribution 零声明。attach 前 `hasattr(detector,'on_gate')` 判定准确。skeptic 对 arch 的纠偏亦亲验成立：Detector Protocol 的 on_gate 声明在 `if TYPE_CHECKING:` 守卫内（core.py:144-145），运行时不可见（注释自陈原因 = runtime_checkable isinstance 回归风险）——protocol 声明与 atom 类级声明是两层，arch 混淆了。
2. **澄清**：我从末主张"保留 class_id 字段加默认值"变体——此前消息"GateFailure.class_id 有默认值方案下 13 处构造零改也行"表述歧义，所指默认值是**新字段 node_id**（方案 A 原文形态），与 skeptic"删字段"裁定一致。
3. **throwback.py:299-307 真·on_gate 包装先例亲验 ✓**：旧版 detector detect 层对 self.on_gate 包一层 _on_gate（补 debug_break 后调 _real）——collector 侧 per-node wrapper 与之同构且链式兼容（attach 后链 = detect 内层 wrapper → collector wrapper → collector.add）。这比 gate_failure.py code_location 默认值先例更贴切（真·on_gate 链上再包一层）。方案 A 机械面两重先例齐备。

## 10. 共享处置机制裁定轨迹（哨兵 → 撤回，终裁定 attach 期 raise）

我的裁定轨迹完整记录（防失真）：

1. **第一轮（§8）**：主张 attach_and_collect 哨兵（~4 行 seen dict），反对 PatternSpec 禁令。理由三条：docstring 载明共享合法 / gate_collector 注释幂等设计意图 / 归属模糊只在收集时成立。arch 第二轮曾转向支持哨兵（其论据 = 运行时真值 > 声明性近似）。
2. **skeptic 再挑战三条反驳，逐条核验后全部成立，干净认错**：
   - ①论域滑动：nodes.py:26-28 docstring 载明的共享例子是 TrendSegmentDetector（无 on_gate），窄禁令不禁它——从"无 gate 共享合法"推不出"产 gate 共享也合法"。
   - ②循环论证：gate_collector.py:10-12 注释是现状幂等描述非归属语义承诺，且方案 A wrapper 本身破坏该前提（每 node 不同 wrapper 后写覆盖前写），用将被改写的注释反对加检测不成立。
   - ③哨兵显示层语义未定义：node_id 哨兵行在前端下拉（FailedAttemptsCard 按 node 过滤）无归属——我只盘了后端 ~4 行、没盘显示层。
3. **终裁定：attach 期 raise**（撤回哨兵）。决定性新论据：gf.node_id 在共享产 gate 场景**结构上无真值**（on_gate 是实例属性，同一实例的 detect 不知道被哪个 node 的求解调用；gate_collector.py:41-44 亲验 attach 挂 on_gate 不看任何 flag、无条件赋值）→ 哨兵值无下游消费价值（无法归因过滤、用户无行动选项）→ 不可消费的标记信息量 = 一条报错，但报错更早终止 + 带修复指引。
4. **attach raise vs spec 窄禁令（skeptic 第一优先）**：维持 arch"真值>近似"方向——spec 期判据只能 hasattr 声明近似，flag 遗忘漏判面机制真实（flag 遗忘 detector 在 attach 无条件赋值下照样归属错误，禁令失明）；skeptic 引的 _validate_render_grid 先例（spec.py:209-228，行号核实）性质不同构：event_cls 构造必需（遗忘=build 即崩，nodes.py:70-72 自动兜住）、is_point 本是几何声明；"产 gate"是行为事实。spec 禁令报错早的优势由 skill reference §4 一句提示补齐（skeptic 自提闭环）。
5. **收口建议（已发 leader）**：attach 期 raise（主，~4 行 id(det) 二次检测+修复指引文案）+ skill 文档一句（辅）。当前立场：coder=raise、skeptic=接受 raise（首选 spec 禁令）、arch=哨兵（已收修正论证，其真值标准兼容 raise）。分歧实施细节级，不撼 A' 主干。

### 附：skeptic 第三选项（attach 侧延迟 raise）四点验证（2026-08-14 终轮，全部实证）

1. **单槽覆盖语义 ✓**：gate_collector.py:41-44 逐 node 赋 `node.detector.on_gate`（实例属性单槽），共享 detector 首挂 _wrap、次挂 _boom 覆盖 → 最终 self.on_gate==_boom，该 detector **所有** gf（无论哪个 node 的 detect 调用）都炸，不静默归首 node。id() 在 attach→detach 窗口内对象恒存活（spec.nodes 持引用）故稳定；第三 node 重复挂 _boom 幂等。
2. **零误杀 ✓（实证）**：trend.py 零 on_gate 调用（grep=0）→ down/side 合法共享从不 emit → _boom 永不被调、行为零差异。且纯 id 判据（无 hasattr 过滤）下"声明了 on_gate 但从不 emit"的边缘 detector 也不会被误杀——"不 emit 不炸"天然零误杀。
3. **raise 冒泡面三路径全部天然接住，零专门异常类型、零额外行数**：engine.py 零 try/except（grep=0）→ raise 从 on_gate 回调无损冒到 analyze 调用方；scan.py:136-137 `except Exception → return (symbol, None, None, msg)` per-symbol error（进程池不裸崩、其余 symbol 继续）；eval_runner.py:117-118 同 per-symbol error；api /diagnose 只 except ValueError→400（:338），RuntimeError 走 FastAPI 默认 500 + traceback 进日志（单人 debug 工具可接受；想改 400 加两行 except，非必需）。三路径均 finally detach/pop（scan.py:114-116 / eval_runner.py:79-80 / api.py:343-346），on_gate/env 零跨 symbol/request 泄漏。
4. **eval 不该豁免 ✓**：eval_runner.py:71-76 attach + finally detach，:72 注释自认无 gf 消费者但保持同挂收模式；豁免=另写无 wrapper 分支=防护面开洞+多代码，不豁免=零代码+全路径统一暴露。零存量共享实例=零现实成本。

**★ 对 leader final_report §4 收口形态的一处实施修正建议**：§4 判据写的是「hasattr(detector,'on_gate') ∧ id 共享 → attach 期 raise」——**hasattr 过滤应去掉、raise 应延迟（挂 _boom 而非 attach 期立即 raise）**。理由：hasattr 过滤对"flag 遗忘（detector 写了 emit 但没写类级 on_gate 声明）+ 共享"场景漏挂 _boom（hasattr False → 不进共享检测 → 挂普通 _wrap → 真 emit 时归属错误**静默**）——恰好重新引入 arch"递归缺陷"论要消灭的声明性近似漏判面；而纯 id + 延迟 raise 三行全覆盖（共享+emit→炸，无论 flag；共享+不 emit→零误杀；不共享→正常），零作者配合、零 flag 依赖，skeptic 伪码即最终形态。

**★ 论据诚实修正（终轮亲验，2026-08-14）**：我上一轮"hasattr 过滤有漏判面（flag 遗忘+共享→静默错误归属）"的论据**按现有 atoms 代码形态不成立**——亲验：全部产 gate detector 在生产路径裸读 `self.on_gate`（breakout.py:141 `if self.on_gate is not None:`、throwback 系经 `on_gate=self.on_gate` 透传），无类级声明 + 未 attach 时读即 AttributeError（python 实测复现）→"写了 emit 但忘写类级声明"的 detector **在生产路径第一次 detect 就崩，物理不可能活到 attach/共享场景**。arch 的"类级声明是功能必需不可遗忘"（skeptic 证伪其第三轮论据后的结论）正确，我的漏判面论据作废。skeptic 终轮场景（"未来自定义 detector 忘写声明但 emit 且被共享"）需该作者还用 `getattr(self,'on_gate',None)` 防御式读法才可能存活——理论边缘，纯 id 延迟 raise 连它也覆盖。**终裁形态（纯 id + 延迟 raise）不受影响**，其独立优势：判据更简（零判据维度）、零误杀由"不 emit 不炸"天然保证（vs hasattr 需依赖声明正确性）、覆盖防御式读法边缘。已回报 lead/arch/skeptic 防记录失真。

### 实施细节建议（arch 移交：报错文案 + 测试覆盖）

- _boom 文案建议：`RuntimeError(f"detector {type(node.detector).__name__} 被 ≥2 node 共享且产出 gate failure，node 归属无法表达——产 gate failure 的 detector 须一 node 一实例(拆为独立实例或去掉共享)")`。
- 测试覆盖建议（2 个，放 tests/path2_web/test_gate_collector.py 或新建）：①共享产 gate detector + 真 emit gf → RuntimeError 且消息含修法关键词；②合法共享 TrendDetector（无 on_gate 声明）→ 正常跑完零行为差异。回归锚：attach→detach 后 on_gate 复位 None 不泄漏。

### 附：fork 论证②表述修正的核验（skeptic 指出，属实）

「容器埋点恒 gate/entry、段埋点恒 end/confirm」只覆盖 v3/旧版双类形态（16 埋点：throwback.py 容器 304/312+段 7 处 / v3.py 容器 69/302+段 6 处）；v1/v0（13 埋点）是**单类多 anchor_kind** 形态（ThrowbackEventV1 独占 gate/confirm/end/entry 四 kind）。我的 §4 矩阵行号本身正确（所列容器行号确为容器类埋点），但"容器/段互斥"不普适。定位唯一性结论不变，真理由 = class 门区分度上限本是 detector 粒度（同 detector 内多出口埋点同类名，class 门本就区分不了），(bar, anchor_kind) 恰达同一粒度 + 互斥分支语义。
