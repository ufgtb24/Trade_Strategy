# Spec: 交错标注重构(消除 anchor 的 span_id 尾巴)

> **状态:绑定实现契约(binding authority)。** plan(`docs/superpowers/plans/2026-08-13-interleaved-annotate-span-id-elimination.md`)从本 spec 论证;分析/权衡/来由见 research doc(`docs/research/2026-08-13_interleaved-annotate-span-id-elimination.md`)。三者冲突时,以本 spec 为准。

本 spec 是 instance_id 重构(已完成,分支 `instance-id-refactor`)在 anchor 机制上的收尾契约:消除该重构 Ruling H 留下的 `span_id` 尾巴,使 anchor 统一到 instance_id,并删除 `span_id` 函数。

---

## §1 `anchor_bo_id` 字段语义

- **取值** = 源 bo 的 `instance_id`(如 `bo_19#0`),由 throwback detector 在 **detect 阶段**写入,读 `last_bo.instance_id`。
- **恒非 None**(生产路径):交错标注(§3)保证 detect 期源 bo 已标注。
- **无 span 回退**:删除现行的 `if last_bo.instance_id is not None else span_id(...)` fallback 分支。
- **同窗口多 bo**:每个 throwback 实例的 `anchor_bo_id` 各带自己的源 instance_id(语义不变,只是值从 span 换成 instance_id)。

## §2 `_anchor_ok` 比较规则

`path2/dag/edges.py::DependencyEdge._anchor_ok`:

- **src 身份** = `src_ep.instance_id`(不再算 `span_id(type(src_ep).__name__, span)`)。
- **dst 值** = `getattr(e_dst, self.anchor_field)`。
- **集合语义**:`dst_v` 为 `tuple/list/set/frozenset` ⇒ `src_v in dst_v`;标量 ⇒ `dst_v == src_v`。
- `anchor_field is None` ⇒ 恒 `True`。
- `src_ep` 经 `endpoint()` 投影到 child(`last_bo` 等)后,其 `instance_id` 在 solve 期恒非 None。
- **消歧保证**:两个同 span、不同 `instance_idx` 的上游实例,`_anchor_ok` 必须能区分(交叉组合返回 False)——这是本重构的核心正确性条款。

## §3 `run_streams` 标注顺序(交错标注)

`path2/dag/engine.py::run_streams`:

- 标注**逐流进行、内嵌于 detector 拓扑循环**:每条 `streams[nid]` 填充后**立即标注该流**,再进入下一个 node 的 detect。任何 node 的 detector detect 时,其 `consumes_stream` 链上的上游已带 `instance_id`。
- **桶计数器跨迭代持久**:key = `(node_id, start_idx, end_idx)`,跨 node 不串扰(键含 node_id)。
- **前提**:consumes_stream 数据流图为无环 DAG ⇒ 拓扑序存在 ⇒ 上游必先于下游标注。path2 `detector_topo_order` 已预设无环。
- **隐含假设**:对象经 `members`/`child_slots()` 共享引用(非拷贝)——标注沿对象图传播(已验证 `breakout.py` `members=tuple(seg)` 为引用)。若未来 detector 拷贝上游事件,本契约失效,需回退到「标注后回填」方案。
- `_check_children_declarations` 仍在循环**之后**运行(需全部流),行为不变。

## §4 instance_id 编号不变式

交错标注产出的 `instance_id` 必须与重构前批量标注**逐字一致**(由既有 multi-instance 测试 + 新增回归测试钉死):

- `instance_idx` = 桶 `(node_id, start, end)` 内流序,从 0 起(流序 = detector yield 顺序)。
- 嵌套 child 继承父容器 `node_id`,共用同一桶计数器。
- `instance_id = f"{node_id}_{start_idx}[_{end_idx}]}#{instance_idx}"`:点事件(`start==end`)塌缩为 `{node_id}_{start}`;区间为 `{node_id}_{start}_{end}`。
- instance_id 契约本身(格式、#idx 后缀、唯一性)**不变**。

## §5 `span_id` 删除

- **前置条件**:§1–§3 落地后,`span_id` 真实调用点仅剩 `annotate` 内造 instance_id 前缀一处。
- **动作**:将该处塌缩规则**内联**(点/区间三元),删除 `path2/core.py::span_id` 函数 + `path2/stdlib/_ids.py` 与 `path2/stdlib/__init__.py` 的 re-export;清全部 docstring 残留。
- **规则存活、函数消失**:塌缩编码以 inline 形式服务于 instance_id;`span_id` 这个旧 event_id 生成器函数从计算中消失。`instance_id` 仍带 span 坐标,信息不丢。
- 删除后 `grep -rn "span_id" path2/ --include=*.py` 必须零命中。

## §6 前端契约(两个 anchor 消费方)

§1 落地后,后端 `anchor_bo_id` 恒为 instance_id 形态。前端有**两个** anchor 消费方都建在「span 反查(parseSpanId)桥接」上,均切 instance_id 直连:

1. `path2_web_ui/src/stores/view.ts::findBoBar`(debug 菜单 anchor→bar):坍缩为**纯精确匹配** `events.find(x => x.instance_id === anchor)`,删 span 反查路径。
2. `path2_web_ui/src/render/visible.ts::matchedIds` 的 `resolveAnchor`(K 线高亮集 anchor 展开):坍缩为 `if (byId.has(v)) enqueue(v)`,删 parseSpanId span 反查分支。

- 两者切直连后 `parseSpanId` 零消费方,删 `src/shared/span.ts`。
- 一批测试(`anchorsOf`/`triggerEventDebug`/`anchor-kind-mapping`/`KlineChart-debug-menu`/`render.visible`/`kline-click`)建立在 span 形态 anchor 契约上,同步改 instance_id 形态(fixture 补匹配 bo 事件);直测 parseSpanId 的用例删除。
- 前端单一 instance_id 命名空间,无 span 反查桥接。

## §7 不在范围内 / 决策前提

- **instance_id 稳定性**:仅承诺单次物化内;不做跨运行/跨窗口应用场景。
- **共享 detector 多 node**(休眠特性):交错标注下首现 node 标注、其余 first-writer-wins 跳过,行为不变。
- **wire 字段名同步重命名**(`src_event_id`/`dst_event_id`/`GateFailure.class_id`/`TopoNode.class_id` 等 ~15 处):值已迁移到 instance_id/`__name__`,字段名保留——**纯命名债,不在本重构范围**(需后端+前端同步改名,独立 task)。
- **anchor_src_field 字段**:`edges.py` 保留(已退役、零消费),本重构不动。

## §8 验收基准

- **后端**:全绿除 pre-existing baseline 6(`test_throwback_debug_anchor_kinds` 4 + `bb_v1`/`bb_v3` `p2.yaml` 2)。
- **前端**:vitest 全绿除 baseline 4(`sidebar-result-list`)+ `vue-tsc` 0 errors + `vite build` success。
- **回归测试**:新增「同 span 上游多实例消歧」测试(`_anchor_ok` 单元级 + solve 端到端)必须绿,且在重构前代码上必须红(证明缝隙被闭合)。
- **编号不变**:专门的 interleave 编号 invariant 测试(plan Task 1 Step 3a,characterization)+ 既有 multi-instance / 标注测试全绿(交错标注未改编号)。
- **验收 fixture**:新后端重算 `outputs/path2_web/scans/apcx-instance-id-acceptance.json`(plan Task 4),`anchor_bo_id` 全 instance_id 形态(`grep BOEvent_` 零命中);`instance-id-acceptance.spec.ts` 在新 fixture 上 PASS。
- `span_id` 残留 grep 零命中(后端)+ `parseSpanId` 残留 grep 零命中(前端)。
