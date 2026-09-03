# Marker 与实例绑定设计(全链路实例级交互)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:brainstorming → superpowers:writing-plans → superpowers:subagent-driven-development to implement this spec task-by-task.

**本 spec 中所有项目内路径均相对 repo root。**

## 背景与动机

实例流实施(2026-08-12,9 commits)完成后的遗留:引擎/契约层已实例化,但**前端的交互与判定链路仍停在身份级**:

1. **点击链路丢实例**:`handleChartClick`(components/KlineChart.ts:75)把 marker 点击解析成 `event_id` 传给 `focusEvent(eventId)`——marker 数据里的 `event_key` 复合键在入口丢弃。APCX 场景下点击 `tb_v1_293` 的任一实例 marker,进入 store 的都是身份 `tb_v1_293`。
2. **归属判定按身份展开**:`focusEvent`(stores/view.ts:677)的归属判定 `matchedIdsOf([m], events, edges).has(instanceKeyOf(ev))`——`matchedIdsOf` 按 match.children 身份引用展开为**该身份全部实例**,于是实例分属场景(每个实例各属一个 match)被误判为「多归属」→ 弹出 pendingDisambig 待选择。
3. **tier 判定半实例化**:matched 已实例级,但 qualified 是事件级(`qualifiedIdsOf` 集合元素为 event_id,因后端 diagnose attr 行无 instance_key)。
4. **tooltip clause 事件级**:`resolveTooltipData`(render/visible.ts:190)按 `event_id` 在 attr 行里 find 取第一条,悬停多实例时显示的是第一条实例的判定,无法展示所悬停实例自己的判定值。

实例拆分的语义(消费不同上游实例 → 同身份多实例)决定了**每个实例的归属在实例层是确定的**——「场景 A(实例分属)不需要待选择」,pendingDisambig 只应留给「同一实例被 ≥2 个 match 引用」的真共享场景。本设计让交互与判定全链路落到实例级,兑现该语义。

## 目标

- marker 点击绑定实例:点击任一实例 marker → 按实例归属判定(0/1/≥2 三分支),实例分属直选、真共享才待选择
- tier 三档(matched/qualified/detected)全部实例级判定
- tooltip 展示所悬停实例自身的属性与 clause 判定
- 焦点/高亮实例级:点 #0 亮 #0,#1 不同时亮
- 不兼容旧 scan 文件(契约 breaking change,无降级路径)

## 非目标

- 不动引擎(path2/dag)、不动 eval_runner 的 upstream_key 拼项(读内存对象,不受序列化形态影响,第一闸对拍零影响)
- 不动 match 的 predicate_trace(本就实例级:match 绑定具体实例组合)
- 不迁移/兼容历史 scan 文件
- 不做「身份级显示」的替代路径

## 契约层改动(后端)

### 1. serialize.py — match node_index 对象化

现状:match 序列化输出 `node_index: {nid: event_id}`(字符串,身份级)、`children: [event_id]`(身份级)、`leaf: {event_id, idx}`(Task 4 已实例级)。

改后:

```json
"node_index": {
  "burst": {"event_id": "burst_282_289", "idx": 0},
  "tb":    {"event_id": "tb_v1_293", "idx": 0}
}
```

- `idx` 与事件行 instance_key、leaf.idx **同一编号函数**(`_InstanceIndexer`,组内按流序从 0 起),三处同源、禁止各自编号
- node_index 恒单值对象(无 kleene 分支——kleene 语法与机制已废弃归档 docs/legacy/kleene/,引擎 _reify.py:2 docstring 确认 node_index = node_id -> 单 Event)
- `children` 保持身份级字符串列表——仅作显示投影(拓扑/侧栏「match 含哪些事件」),实例化权威数据是 node_index
- `leaf` 保持现状 `{event_id, idx}`(形态与 node_index 对象统一)

### 2. diagnose.py — attr 行加 instance_key

现状:`_attr_row`(diagnose.py:23-29)输出 event_id/start_idx/end_idx/clauses,无实例标识。

改后:

```json
{"event_id": "tb_v1_293", "instance_key": "#1", "start_idx": 293, "end_idx": 293, "clauses": {...}}
```

- 编号必须与 serialize_analysis 的事件行**同源一致**——diagnose 序列化入口需要拿到与事件行同一份 `_InstanceIndexer`(或等价编号),不能自行另编号。这是后端唯一需要穿透的接线点:serialize_diagnostics 的调用链需要能访问到事件全集/索引器(与 serialize_analysis 同一来源)
- attr 行本就是逐实例判定(node 的每个候选事件各自判定 where,多实例各判各的),补上实例标识后 clause 的 measured/threshold 即该实例的真实判定值

### 3. 兼容声明

**不兼容旧 scan 文件**(本实施之前的文件):node_index 值为字符串、attr 行无 instance_key。前端按新契约解析,不提供降级路径;不迁移历史文件。

## 前端改动

### 1. types.ts

```ts
export interface NodeRef { event_id: string; idx: number }
// MatchDict:
node_index: Record<string, NodeRef>
// AttrRow:
instance_key: string        // 必填(新契约)
```

`leaf` 已有 `{event_id, idx}` 形态(与 NodeRef 同构,可复用类型)。

### 2. render/visible.ts

- `matchedIds` 初始集改从 node_index 对象化数据取**精确实例**:`{event_id, idx}` → `instanceKeyOf` 复合键。不再「children 身份引用展开全部实例」——match 引用谁就是谁。APCX 下 match A 只贡献 `{tb_v1_293#0, burst_282_289#0}`,match B 只贡献 `{tb_v1_293#1, burst_282_290#0}`
- 递归展开(child_refs / anchor 反查)保持身份级(展开该身份全部实例)——这些引用只承载身份,视觉上同身份兄弟一起进集,与现状一致
- `qualifiedIdsOf` 升级实例级:集合元素从 event_id 变为复合键(`event_id + instance_key`),数据源 = attr 行的 (event_id, instance_key)
- `eventTierOf`:matched 实例级(现状)+ qualified 实例级(新)——两档都按复合键判定
- `resolveTooltipData`:attr 行查找从 `node.attr.find(r => r.event_id === eventId)` 升级为按复合键 `instanceKeyOf(r) === instanceKey`;identity 组装同样按实例取(悬停实例的属性,如 anchor_bo_id)

### 3. stores/view.ts

- `focusEvent` 签名升级:`focusEvent(eventId, idx?)`——**双入口分级语义**(idx 由调用方携带与否区分入口粒度):
  - **实例级入口(marker 点击,带 idx)**:实例复合键在几个 match 的 node_index 中精确出现:
    - 0 个 → 只聚焦事件(不设 match)
    - 1 个 → 直选该 match(不再弹待选择)
    - ≥2 个 → pendingDisambig(真正共享实例的场景)
  - **身份级入口(侧栏 trace 行 / 候选表行点击,不带 idx)**:收集该身份下全部实例的归属——
    - 全部实例归属同一 match(或单实例身份)→ 直选该 match
    - 实例分属不同 match / 存在共享 → pendingDisambig(身份级入口无法确定用户意图,歧义真实存在)
    - 无任何归属 → 只聚焦事件
- 焦点选中实例级:`selectedEventKey`(复合键)取代事件级 selectedEventId 的**判定作用**——点 #0 只亮 #0,#1 不同时亮(chart.ts 的 group 判定按 event_key 复合键匹配,现状已具备字段,统一到实例级语义);`selectedEventId` 字段本身保留(仍被 shift 选择、详情卡等事件级状态消费,不在本次改造范围)
- 删除身份级降级路径(focusEvent 的 children 身份展开判定分支)

### 4. components/KlineChart.ts + KlineChart.vue + DetailSidebar.vue

- `handleChartClick`:marker 点击把 `data.event_key`(marker 数据已有复合键字段)解析成 `(event_id, idx)` 传给 focusEvent——实例信息不再在入口丢弃
- `resolveTooltipData` 签名升级:`resolveTooltipData(eventId, idx, ...)`——唯一调用点 KlineChart.vue:457(tooltip 从 marker 悬停触发,按 event_key 定位实例,展示该实例属性与 clause 判定)
- `DetailSidebar.vue` 两处调用点(`selectNodeEvent` :357 / `selectCandidateRow` :362)保持身份级入口:不带 idx 调 focusEvent,走身份级判定语义(见 view.ts 节)
- `ChartClickPayload.data` 类型补 `event_key?: string`

## 数据流

```
点击 marker(data.event_key) → handleChartClick → focusEvent(event_id, idx)   [实例级入口]
  → 实例复合键 → 各 match node_index 精确引用计数
     0 → 只聚焦   1 → 直选 match   ≥2 → pendingDisambig(候选 brackets)
点击侧栏 trace 行 / 候选表行 → focusEvent(event_id)                          [身份级入口]
  → 身份下全部实例的归属并集 → 一致则直选 / 分属或共享则 pendingDisambig
→ 焦点高亮按 selectedEventKey(实例级)

悬停 marker(event_key) → resolveTooltipData(event_id, idx)
  → attr 行按复合键取该实例 clause + 事件属性平铺(该实例)
```

## 测试

### 后端

- serialize 测试:node_index 对象化的 idx 与事件行 instance_key / leaf.idx 同源一致(APCX 双实例场景:tb_v1_293 #0/#1 各就其位)
- diagnose 测试:attr 行 instance_key 与 serialize_analysis 同一编号函数(同源)

### 前端(vitest)

- visible:matchedIds 精确初始集(双 match 各贡献自己的实例,不互相污染)、qualifiedIdsOf 实例级(同身份两实例一个 qualified 一个不 qualified 可区分)、eventTierOf 三档实例级
- view:focusEvent 实例归属三分支(0/1/≥2)、实例分属直选不再触发 pendingDisambig、真共享(同一 {event_id, idx} 被两 match 引用)仍弹待选择、身份级入口(不带 idx)在实例分属时弹待选择、单实例身份直选
- chart:点击传 event_key 解析、tooltip clause 按复合键取实例

### 验收场景(真实数据)

加载 `outputs/path2_web/scans/20260813T005540.json`(APCX 双实例):

1. 点 `tb_v1_293` #0 marker → 直选 match A(不再弹待选择);点 #1 → 直选 match B
2. 悬停 #1 → tooltip 显示 `anchor_bo_id: bo_290` + #1 的 clause 判定
3. 用单测 fixture 构造「同一 {event_id, idx} 被两 match 引用」→ 待选择正常弹出

## 全局约束

- 全中文注释/UI;入口脚本不使用 argparse
- 测试先 RED 后 GREEN;不得直接修改既有断言以适配实现(先复核推演)
- 后端契约改动同步前端类型,同 commit 完成,保持每 commit 绿
- 实施基线:instance-flow 分支(本 spec 在其实施后继续)
