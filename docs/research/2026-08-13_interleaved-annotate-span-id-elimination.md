# 交错标注重构:消除 anchor 的 span_id 尾巴

> 2026-08-13 讨论结论。**状态:设计方向定稿,未实施。**
> 这是 instance_id 重构(已完成并推送,分支 `instance-id-refactor`)的后续收尾设计——
> 解决该重构在 anchor 机制上留下的 span_id 尾巴,让整个计算收敛到「只有 instance_id 一种身份串」。

## 背景:instance_id 重构留下了什么

instance_id 重构把事件标识统一成了 `instance_id = span_id(node_id, start, end) + "#" + instance_idx`,消灭了 event_id/class_id/source_tag 体系。但在 **anchor 机制**上留下了一处尾巴——`anchor_bo_id` 仍用 `span_id` 而非 `instance_id`:

- `throwback*.py`(4 处):`anchor_bo_id = last_bo.instance_id if not None else span_id(type(bo).__name__, span)`
- `edges.py::_anchor_ok`:比 `span_id(type(src).__name__, span)` 与 `anchor_bo_id`

这是 instance_id 重构时的 **Ruling H**(权宜裁决):anchor 比较用 span 语义。本文档提出消除该权宜的正解。

## 问题:span 语义在同 span 上游多实例时失效

### 缺陷机制

`anchor_bo_id` 存的是源 bo 的 **span 坐标**(`BOEvent_19`),不含实例序号。当两个上游实例 A1、A2 **span 相同**(instance_idx > 0):

- A1 = `A_s_e#0`、A2 = `A_s_e#1`,但两者的 `anchor_bo_id` 都 = `span_id(类名, s, e)` → **完全相等**。
- 下游 B1(产自 A1)、B2(产自 A2)的 anchor 也都指向那个共享 span → 相等。
- `_anchor_ok` 对四种组合(A1-B1、A1-B2、A2-B1、A2-B2)**全部放行**。
- 边的另一道约束 `satisfies`(gap/containment)也救不了:A1、A2 span 相同 ⇒ gap(A1,B2) == gap(A2,B2),后者本就合法 ⇒ 交叉对(A1-B2)同样通过。

**后果**:求解器把 2 个真实绑定扩成 4 个,match_id 因 B 的 instance_id 不同不会被去重 ⇒ **match 数虚增、含语义错误的交叉绑定**。

### 根因:时序卡死

`anchor_bo_id` 在 **detect 阶段**写入,而 `instance_id` 要到 `annotate_instances`(**全部 detect 完成后**)才注入。detect 那一刻源 bo 的 `instance_id` 恒为 None,detector 拿不到,只能写几何坐标(span)。这不是漏写,是「写 anchor 时 instance_id 还不存在」的硬约束。

### 当前为何休眠

这个交叉绑定要出问题,前提是**同 span 多实例出现在一条被消费的上游 node 上**。当前 app:

- 唯一同 span 多实例的是 **tb**(APCX 的 `tb_293#0/#1`)——但 tb 是叶子(end_node),**不喂任何下游边**,同 span 的两个 tb 没有"下游 B 去绑错它们"。
- 真正当上游的 bo / burst,在当前数据下 span 唯一,不产生 A1/A2 同 span。

所以缺陷**休眠**。Ruling H 的赌注是「源 span 唯一 ⇒ span 语义充分」——本文档的正解正是让这个赌注不再需要。

## 正解:交错标注(interleaved annotate)

### 核心改动

当前 `run_streams`(`engine.py`)的流水线:

```
for nid in detector_topo_order:   # 全部 detect
    run detector → streams[nid]
_check_children_declarations
annotate_instances(streams, spec)   # 全部 detect 完后统一标注
```

重构为**逐 node 交错**:

```
for nid in detector_topo_order:
    run detector → streams[nid]
    annotate 这一条流              # detect 完立刻标注
_check_children_declarations       # 仍放最后(需全部流)
```

### 为什么成立:无环有向图(DAG)

交错标注要成立,唯一要求是:**detect 一个 node 时,它(直接或间接)依赖的上游都已标注完**。这等价于「consumes_stream 数据流图存在拓扑序」⇔ **无环(DAG)**。

- path2 的 `consumes_stream` 天然满足:`detector_topo_order` 就是在算拓扑序,它**预设无环**(有环排不出序)。
- 不要求是树/单链/单上游——只要无环:多下游共享一上游(fan-out)、跨多跳间接取(tb 经 `burst.members[-1]` 取 bo)都成立。
- **隐含假设**:对象共享引用(下游经 `members`/`child_slots` 拿到的是上游已标注的同一个对象,不是副本)。已验证 `breakout.py:206` `members=tuple(seg)` 是引用、非拷贝。若未来某 detector 偷偷 copy 上游事件,交错标注传不进去,需回退到回填方案。

### 收益:anchor 升级为 instance_id

交错后 tb detect 时源 bo 已标注,`last_bo.instance_id` 是真实值(`bo_19#0`),detector 现有的 `if not None else span_id(...)` **自动走 instance_id 分支**——detect 代码几乎不用改。`_anchor_ok` 改比 `src.instance_id` 与 `anchor_bo_id`。

- A1(`A_s_e#0`)、A2(`A_s_e#1`)同 span ⇒ B1.anchor=`A_s_e#0`、B2.anchor=`A_s_e#1`(不再相等)。
- `_anchor_ok(A1, B2)`:`A_s_e#0` != `A_s_e#1` ✗ **交叉绑定被挡死**。缺陷闭合。

### 编号不变

instance_idx 的桶 key 是 `(node_id, span)`,逐 node 标注时计数器跨 node 不串扰(键含 node_id),结果与批量标注**逐字一致**。instance_id 契约不动。

## 连锁收益:span_id 彻底可删

交错标注清空了 span_id 的 5 个 anchor 调用点,使其只剩 **1 处**:`annotate_instances` 里造 instance_id 前缀(`engine.py:39`)。此时把那条「点塌缩 / 区间」规则**内联**进 annotate(两行三元),即可删 `span_id` 函数 + `stdlib` 两处 re-export。

**计算里从此只有 instance_id 一种身份串**:anchor 用它、match_id 的 node_bits 用它、序列化用它、前端解析它,统一。

### 与早前「删 span_id」提议的关系

实施 instance_id 重构时,曾有一个跨会话提议「删 core.span_id + 内联进 annotate + 删 stdlib re-export」。该提议**方向正确但时机错**:当时 anchor 还用 span_id,直接删会 NameError 崩掉 5 处锚点(被核实否掉)。**交错标注是让该提议变正确的前提**:先交错标注 → anchor 切 instance_id → span_id 只剩 1 处 → 内联删除。两步合起来是自洽收尾。

### 分清:规则存活,函数消失

span_id 不是纯垃圾——它封装的「`kind_start` / `kind_start_end` 塌缩」是 instance_id 前缀的编码规则。这条**规则会留下**(以 inline 形式服务于 instance_id),消失的是**名叫 span_id 的函数**(旧 event_id 生成器的遗物)。instance_id 仍带 span 坐标(`bo_19#0` 的 `19`),信息没丢。

## 前端红利

anchor 变 instance_id 后,前端 `findBoBar` 的双路径(精确 instance_id + `parseSpanId` span 反查)坍缩成**纯精确匹配**——commit `9dcde36` 为补 anchor 死路径加的 `src/shared/span.ts` 的 span 反查分支变死代码,可一并清。整个链路从「两个命名空间(instance_id + span_id)靠反查桥接」收敛成「单一 instance_id 命名空间」。

## 改动清单

后端:
1. `path2/dag/engine.py` `run_streams`:把 `annotate_instances` 从循环外挪进循环内,改成逐流标注(bucket 计数器跨迭代保留)。
2. `path2/dag/edges.py` `_anchor_ok`:比 `src_ep.instance_id` 与 `getattr(dst, anchor_field)`,不再算 span_id。
3. `path2/atoms/throwback.py` / `throwback_v0.py` / `throwback_v1.py` / `throwback_v3.py`:`anchor_bo_id = last_bo.instance_id`(回退分支走不到,可留防御或删)。
4. `path2/core.py`:删 `span_id` 函数 + docstring;`annotate_instances` 内联塌缩规则。
5. `path2/stdlib/_ids.py` + `path2/stdlib/__init__.py`:删 span_id re-export。

前端:
6. `path2_web_ui/src/stores/view.ts` `findBoBar`:坍缩为纯 `instance_id === anchor` 精确匹配。
7. `path2_web_ui/src/shared/span.ts`:确认 `parseSpanId` 无其他消费者后删(或保留作 instance_id 解析工具)。
8. 相关 spec fixture:anchor_bo_id 改 instance_id 形态。

## 诚实评估

- **值得做**:这是让 instance_id 重构真正闭环的收尾——消除 span_id 旧时代尾巴、闭合同 span 上游多实例的交叉绑定隐患、统一身份命名空间。
- **不紧急**:缺陷当前休眠(同 span 多实例只在叶子 tb)。可等真有 app 触发(非叶子同 span 多实例)再做,但届时设计已清楚,无需临时方案。
- **范围**:多文件(engine/edges/4 throwback/删 span_id/前端 findBoBar+span.ts),但每步无设计分叉,适合一个聚焦 task。
- **必须补的回归测试**:「A1/A2 同 span 喂下游 B」场景——当前无此测试(因场景休眠),重构后须新增以钉死交叉绑定被挡。

## 决策前提(记录在案)

- 沿用 instance_id 重构的既有前提:不做跨窗口应用场景(instance_id 稳定性只承诺单次物化内);诊断用最新参数文件。
- 共享 detector 多 node(休眠):交错标注下首现 node 标注、其余 first-writer-wins 跳过,行为不变。
