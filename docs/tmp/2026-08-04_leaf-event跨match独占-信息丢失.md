# leaf event 跨 match 独占导致多 match 落空 & 信息丢失

> path2 dag 引擎 leaf 去重机制（`emitted_leaves`）的讨论记录。
> 核心结论：扫描结果里「同一个 leaf event 配不同上游」的多个合法 match **只会可见一个**，根因是引擎把 leaf event 跨 match 独占，**与 anchor_field 无关**。这是设计缺陷（信息丢失），非 bug。

## 场景

**通用**：pattern 为 `node_A -> node_B`（无 anchor_field）。node_B 是 leaf（无出边）。设 event_B_0 同时落在 event_A_0 与 event_A_1 的可行窗口内，故两个 match 几何/时序都合法：

- match0 = {node_A: event_A_0, node_B: event_B_0}
- match1 = {node_A: event_A_1, node_B: event_B_0}

**特例（bottom_burst）**：`burst.last_bo -> tb`，burst_A（末 bo=bo_A）与 burst_B（末 bo=bo_B）时序上都先于同一段企稳 tb_C。tb 是 leaf。

两例问的是同一件事：**这两个 match 是否都出现在扫描结果里？**

## 答案：不会都可见，只有一个

## 真正根因：leaf event 跨 match 独占（emitted_leaves）

引擎在 `_dfs` 回溯枚举所有合法绑定的同时，对 **leaf 节点**做了一道跨 match 独占：

1. **leaf 定义**（`path2/dag/_solve.py:60-62`）：没有正向出边的节点。node_B / tb 都是 leaf。
2. **emit 即占坑**（`_solve.py:180-184`）：每次物化出一个完整 match，就把该 match 里所有 leaf 节点的候选下标（stream_idx）记进 `emitted_leaves`。
3. **占坑即排除**（`_solve.py:229-235`）：后续枚举到 leaf 节点这层时，候选会过滤掉所有已记过的下标。

于是 event_B_0 一旦被先 emit 的 match 用掉，就进 `emitted_leaves["node_B"]`，另一个 match 在 node_B 选候选时 B_0 被直接过滤。**先到先得**——谁先取决于非 leaf 端（node_A）的候选排序（按 `(start_idx, end_idx)`，`_solve.py:223`）：A_0 排前则 match0 可见，A_1 排前则 match1 可见。剩哪个 match 是数据顺序的副产物，不是语义选择。

> 注意：emitted_leaves 按 **stream_idx**（候选在池里的下标）去重，不是按 span 或 event_id。它是引擎层的通用机制，对**所有 leaf** 生效，与 detector 内部的去重、与 anchor_field 都无关。

## 一个有解释力的不对称

leaf 独占这条规则，能解释一个看似矛盾的现象：

| 场景 | 结果 | 原因 |
|---|---|---|
| 一个 A 配**多个不同** B（B_0、B_1） | 多个 match 都可见 | B 是不同 leaf event、下标不同，互不冲突 |
| **多个** A 配**同一个** B（B_0） | 只有一个 match 可见 | 同一个 leaf event 被独占 |

dag_spec 的 docstring 说「一个 bo 可产 0..N 个 tb，dag 引擎对 tb 多候选枚举多 match」——那是左行（一个 burst 配多个 tb）。反过来「多个 burst 配同一个 tb」是右行，被 leaf 独占挡住。**不对称的根源就是 leaf 独占。**

## anchor_field 的真实角色：不改变 match 数量

对照 bottom_burst：**即便完全去掉 anchor_field，tb_C 仍然只会出一个 match**——因为 tb 是 leaf，emitted_leaves 早已把它独占。anchor_field（`path2/dag/edges.py:91-97` 的 `_anchor_ok`，在物化复核 `_solve.py:245` 调用）只是额外加了一道身份复核（让 tb 在身份上锚定一个具体 bo），它**不改变 match 的数量**，只改变「哪个 burst 配得上」的判定维度。

> 即：anchor_field 在 match 数量上是多余的；真正的拦截者是 emitted_leaves。

## detector 层（tb 特有）：独立的第二层

tb detector 自己还有一道去重（`path2/atoms/throwback.py:258-264`，docstring :201「同 span 多 bo 保留首个」）：tb 的 `event_id` 只编码 span（`throwback.py:253`），同 span 多 bo 触发的 tb 在进引擎候选池**之前**就被压成一个 event。

这是 **detector 层**的选择，与引擎层 emitted_leaves 是两码事：

- detector 层：把「同 span 多 bo」压成「一个 tb event」（tb 池里只有一个下标）。
- 引擎层：把「一个 leaf event」跨 match 独占（只进一个 match）。

两层叠加，才让 bottom_burst 里「多个 burst 配同一段企稳」彻底只剩一个 match。

## 三层身份（分清别混）

| 层面 | 区分键 | 本场景 |
|---|---|---|
| leaf event 身份 | `event_id`（tb 还 = span） | 同 span = 同一个 event →「一个」|
| match 身份 | node→event 映射 | 上游槽填不同 event = 两个不同 match，哪怕 leaf 槽是同一个 →「两个」|
| match 物化 | leaf 独占（emitted_leaves） | 同一个 leaf event 只能进先到的 match →「剩一个」|

match 身份层面「两个 match」成立，但物化层面引擎只放行一个。

## 问题定性：设计缺陷（B 类），非 bug

机制内部自洽——leaf 独占是 solve docstring（`_solve.py:272`）明写的「按 leaf event 跨 prefix 去重」的设计意图：把 leaf（通常是 end_node / 买点）当「结果单元」，认为同一个买点不该因不同 prefix 重复计数。但这个去重把「一个买点被多个上游确认」的多对一关系，强制压成「买点唯一、只算第一个上游」，丢掉了多确认信号。语义选择丢信息 = 设计缺陷。

## 修复方向（两层，且耦合）

要实现「两个 match 都可见」，分两层，且对 tb 场景两层都得动：

1. **引擎层（通用，必改）**：放宽 `emitted_leaves`，允许 leaf event 跨 match 复用。
   - 单独这一步就能解决通用 `node_A -> node_B` 场景（无 anchor 时 match0、match1 都可见）。
   - 代价：同一个 leaf event 会出现在多个 match 里，需重新定义「结果去重」语义——把这种「重复」重新认定为「多确认信号」而非冗余。

2. **tb 专属（detector + 边层）**：anchor 单值 → 集合。
   - `ThrowbackEvent.anchor_bo_id: str` → `anchor_bo_ids: tuple[str, ...]`；detector 按 span 合并时**收集所有触发 bo** 而非丢弃（`throwback.py:258-264`）。
   - `_anchor_ok`（`edges.py:91-97`）单值相等 → 集合包含；`spec.py:112-135` 校验适配。
   - **但这层单独不够**：tb_C 仍是 leaf，若不放宽 emitted_leaves，第二个 match 还是被独占挡掉。

> 结论：tb 场景要「两个 match 都可见 + tb_C 自带多 anchor 元信息」，**引擎层 + tb 层两层都要改**，只改其一都不够。这比「一个 span 一个 tb」的几何诉求更深——几何去重在 detector 层已满足，真正的信息丢失在引擎层的 leaf 独占。

### 牵涉代码位置

| 文件 | 位置 | 改动 |
|---|---|---|
| `path2/dag/_solve.py` | emit 入集（:180-184）、leaf 过滤（:229-235） | 放宽 leaf 独占（引擎层，通用） |
| `path2/atoms/throwback.py` | 字段（:186）、去重（:258-264）、产出（:252-257） | anchor 单值→集合；去重改合并收集 |
| `path2/dag/edges.py` | `_anchor_ok`（:91-97） | 单值相等 → 集合包含 |
| `path2/dag/spec.py` | `_validate_anchor`（:112-135） | 校验适配集合字段 |
| 前端 / 序列化 | tb 渲染、tooltip | 暴露 `anchor_bo_ids` 计数 |

## 一处保留意见（待实验）

「一个 leaf event 被多个上游确认 → 置信度更高」方向合理，但有效性不能先验打包票，取决于上游是否独立：

- bottom_burst 里若 bo_A、bo_B 是同一波动的两个相近标记（一次突破的两次确认），指向同段企稳几乎 trivially true，不增信。
- 只有两次**独立突破尝试**各自失败后回踩到同段企稳，「被多次测试」才真正增信。

引擎现在不区分独立与冗余，raw 的「被几个上游共享」计数可能混噪声。修复后可能还需一道独立性过滤（如要求两个上游 end_idx 间隔超阈值）。需真实数据实验定。

> 但这不影响主结论：信息丢失是确定事实，该不该丢独立于「丢掉的信息有多值钱」。

## 相关 memory

- `project_tb_buypoint_modeling.md` — tb 买点方案 C 实施背景
- `project_path2_duplicate_event_id.md` — event 身份 / 去重键历史
