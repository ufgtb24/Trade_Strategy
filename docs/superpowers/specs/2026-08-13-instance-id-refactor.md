# 事件标识重构 spec:instance_id 取代 event_id(全量)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:brainstorming → superpowers:writing-plans → superpowers:subagent-driven-development to implement this spec task-by-task.
> 设计定稿来源:docs/research/2026-08-13_instance-id-design.md(本 spec 是其可实施化,冲突时以本 spec 为准——研究文档是设计讨论,本 spec 是实施契约)。

**本 spec 中所有项目内路径均相对 repo root。**

## 目标

消灭 event_id(class+span 混合身份键)与 class_id 字符串体系,事件标识统一为 **instance_id = (node_id, span, 流序)** 的编码——node 维度做声明锚、span+流序做物化坐标。随之消灭:source_tag 体系、instance_key 外挂编号、NodeRef 对象、身份展开/身份并集/身份聚合、`#` 拼接解析、class_id 注册表与序列化 class 字段。类型以 **Python 类**表达(event_cls / isinstance / `__name__`),不进契约。

不兼容旧 scan 文件;不提供降级路径;不迁移历史文件。

## 核心契约(唯一出处,禁止各处重复实现)

### 1. 事件标识

事件对象(Event 子类)携带三个标识字段,全部由**物化标注**(见 §2)注入:

| 字段 | 类型 | 语义 |
|---|---|---|
| `node_id` | `str \| None` | 物化来源 node(dag 内唯一);detector 构造阶段为 None,物化后恒非 None |
| `instance_idx` | `int` | 桶 (node_id, start_idx, end_idx) 内按流序从 0 起的序号 |
| `instance_id` | `str \| None` | 组合键 = `span_id(node_id, start, end) + "#" + str(instance_idx)`,恒输出(单实例也是 `#0`);detector 构造阶段为 None |

- `span_id`(path2/core.py)保留,语义不变(单点塌缩 `kind_start`、区间 `kind_start_end`),kind 取 node_id。
- **Event 类删除 `event_id` 字段**(含 `__post_init__` 的自动推导与「显式传值逃生舱」)。
- 事件行序列化字段:`instance_id`、`node_id`、`instance_idx` + 属性平铺。**删除** `event_id`、`source_tag`、`instance_key`、`class_id`。
- **class_id 字符串体系一并消灭**(见 §1a)。

### 1a. class_id 字符串消灭(类型以 Python 类表达)

- `path2/core.py`:`_CLASS_ID_REGISTRY` 删除;`__init_subclass__` 的「必须声明非空 class_id / 冲突检查」删除;Event 子类不再要求 `class_id` ClassVar。
- **保留**(Python 类属性,类型系统的真实部分,非字符串镜像):
  - `Event.is_point` ClassVar——几何承诺,`render_grid='price'` 校验与前端 marker 形态用。
  - detector 的 `event_cls`——C3 children 类型核对用 isinstance。
  - `type(e).__name__`——诊断/错误消息/gate_failure/debug_ctx 的「这是什么类」显示。
- 序列化契约不出现任何 class 字符串字段;事件行无 `class_id`。
- `summarize` 按 `node_id` 统计(`{node_id: count} ∪ {"matches": n}`)。
- 样式(event_styles / 前端 colors.ts / topology)配置键改 `node_id`;同 class 多 node 共享样式由 app 配置层显式各配一份。
- C3 类型核对错误消息用 `type(c).__name__`。

### 2. 物化标注(引擎唯一出处)

`run_streams`(path2/dag/engine.py)出口新增 `annotate_instances(streams, spec)`:

1. 遍历每条流 `(node_id, events)`,维护桶计数 `{(node_id, start, end): n}`;对每个事件按流序 `object.__setattr__` 注入 `node_id`/`instance_idx`/`instance_id`(已标注对象跳过——共享 detector 多 node 边界:首现 node 获胜)。
2. 递归补标:遍历已标注事件,其 `child_slots()` 成员若未标注(如 tb.segments 内部构造的子事件),按**父事件的 node_id** + 自身 span 用同一桶计数标注。

**编号前置的后果**:serialize 层不再编号——`path2_web/serialize.py` 的 `_InstanceIndexer` 删除;diagnose 与 analyze 共用 run_streams,标注同源自动成立,无需对拍保证。

### 3. 引用协议(全实例化)

- `match.node_index`: `{nid: instance_id 字符串}`(值从 `{event_id, idx}` 对象**退化为字符串**;NodeRef 消灭)。
- `match.children`: `[instance_id]` 字符串列表。
- 事件行 `child_refs`: `{slot: [instance_id]}`(值实例化)。
- 侧栏/候选表/详情卡等一切「按身份聚合」的 UI 语义改为**实例列表**。
- 前端 `event_key`、复合键拼接、`lastIndexOf('#')` 解析等概念消失:instance_id 本身就是完整键。前端若需 idx/前缀,直接从 instance_id 解析(`#` 与 `_` 分隔规则见 span_id,此解析仅允许存在于一处共享工具函数,禁止散布)。

### 4. match 标识

- `PatternMatch` 删除继承来的 `event_id`,新增自有字段 `match_id`(语义不变:唯一 match 键)。
- reify 构造:`match_id = f"{plan.pattern_id}@{start}-{end}#{node_bits}"`,`node_bits = "|".join(f"{nid}:{e.instance_id}" for nid, e in sorted(node_index.items()))`。
- analyze 的碰撞消歧(engine.py:135-153)改用 `match_id`,后缀规则不变。
- 序列化:`"match_id": m.match_id`;前端 `MatchDict.match_id`。

### 5. 前端新契约类型(types.ts)

```ts
export interface EventDict {
  instance_id: string            // 唯一实例键(node_span#idx)
  node_id: string                // 物化来源 node(band 分组键)
  instance_idx: number
  start_idx: number; end_idx: number; confirm_idx?: number
  child_refs?: Record<string, string[]>   // 全实例化引用
  // ...属性平铺(现状其余字段不变;无 class_id/source_tag/event_id)
}

export interface MatchDict {
  match_id: string
  start_idx: number; end_idx: number
  node_index: Record<string, string>      // nid -> instance_id 字符串
  children: string[]                       // instance_id 列表
  predicate_trace?: unknown                // 现状形态不变
}

export interface AttrRow {
  instance_id: string; node_id: string
  start_idx: number; end_idx: number
  clauses: Record<string, ClauseWitness>
}
```

- `Diagnostics`、`TopoNode` 等其余类型的 `source_tag`/`event_id` 字段按同规则迁移(node 分组用 `node_id`)。
- 前端焦点/选中状态:`selectedEventId`/`focusedEventId`/`focusedEventKey` 等事件级字段**统一为实例级单字段** `selectedInstanceId`/`focusedInstanceId`(shift 选择、详情卡、焦点、高亮全部实例级;无身份级入口残留)。
- `focusEvent` 单入口:`focusEvent(instanceId: string)`——所有调用点(marker 点击、侧栏实例行、候选表行)都持有 instance_id,身份级入口消灭。

### 6. 诊断

- attr 行:`{instance_id, node_id, start_idx, end_idx, clauses}`(键 instance_id 即完整实例;删除 event_id/instance_key)。
- rel 行:`src`/`dst` 事件引用改 instance_id;`example_failed_pairs` 元组元素改 instance_id。
- `serialize_diagnostics` 直接读事件标注字段,不再构造 indexer。

### 7. 引擎内部消费点迁移

- `_solve.py:285` 多实例判定 `len({e.event_id for e in s}) < len(s)` → 改为 `any(e.instance_idx > 0 for e in s)`。
- `result.py` AnalysisResult 校验「同身份完全重复对象」→ 改为 instance_id 唯一性断言(`len({id(e) for e in events}) == len(events)` 语义不变,判据从 `(event_id, a==b)` 换成 instance_id 重复)。
- `edges.py`/`diagnose.py`/`runner.py`/`spec.py` 等所有 `event_id` 字符串消费点按语义迁移(身份比较 → instance_id;身份聚合 → node_id 聚合)。
- `stdlib/_ids.py` 的复合 id 逃生舱(显式 event_id 构造)删除。
- `atoms/*`(trend/throwback*/breakout)删除 `source_tag` 参数与显式 event_id 传参;`assign_auto_source_tags` 删除。
- **class_id 消灭**(§1a):core.py 注册表/`__init_subclass__` 强制声明删除;`debug_ctx.py`/`gate_failure.py`/`spec.py`/`result.py`/`eval.py`/`engine.py` 等所有 class_id 字符串消费改 `__name__` 或 Python 类;`summarize` 按 node_id 统计;`_check_children_declarations` C3 错误消息用 `type(c).__name__`。

### 8. eval_runner

- `upstream_key` 惰性 `#idx` 拼项改读 `instance_id`(内存对象直接取)。

## 边界(设计文档已裁决,实现按此)

- **共享 detector 多 node**(单流多 node,当前休眠):标注时首现 node 获胜,不报错;记录注释。真出现时再议。
- **单 node 多流**:当前 app 单 node 单流;出现时组定义扩展,届时再议。
- **嵌套 child 无独立流**(如 tb.segments):递归补标继承父 node_id(§2.2)。
- **点事件 span**:span_id 单点塌缩(start==end),instance_id 无冗余坐标。

## 测试纪律

- 全量契约变更:既有测试的 fixture(手构事件)一律显式传 `node_id`/`instance_idx`/`instance_id`(或经便捷构造 helper);断言从 event_id 断言迁移为 instance_id 断言;Event 子类删除 `class_id` ClassVar 声明。
- RED→GREEN 每 task 强制;既有断言修改先复核推演(契约升级必然同步,禁止盲改语义)。
- 前端测试 fixture 同步:node_index 值从 NodeRef 对象改 instance_id 字符串;事件行补 node_id/instance_id。
- pre-existing 失败对照名单(实施前基线):后端 test_throwback_debug_anchor_kinds 4 + bb_v1/bb_v3 p2.yaml 2;前端 sidebar-result-list 4。
