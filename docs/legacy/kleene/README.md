# Kleene 区间绑定算法 —— 归档

> **归档时间**:2026-06-15
> **归档前最后位置**:`path2/dag/`(`KleeneSpec` / `kleene_bind` / `_kleene_indeg_ok` / `W.first/last/count/any/distinct/reduce`)
> **不再被任何活跃代码引用**

## 为何归档

- B4 迁移后所有 `path2_apps/` 业务全部用 nested event(`BurstEvent.members` 内嵌完整 BOEvent)表达"段聚类",`path2_apps/bottom_burst/` 零现役 Kleene 业务消费者。
- tom 第一性原理裁定:Kleene 跟 nested event 在表达力上互不真子集——
  - **Kleene 强**:段长度/聚合判据可依赖外层已绑 role 字段(求解期可见 `assign`/`ctx.bound`)
  - **nested event 强**:同时共存的多个段(`all_ends` 前缀族)、任意非线性聚类规则
- path2 找买点业务中,"段聚类判据依赖外层 role 字段" 场景**不存在**(burst 聚 bo 只看 bo 内部间距和数量,与上游 trend/platform 字段无关),故 Kleene 求解期能力无业务消费者。
- 留在 `path2/dag/` 会污染 DAG 引擎核心:`endpoint()` 三态、`frontier_cut_signature` 双端点签名、`Solution.assign` union 类型、`_reify._flat` tuple 兼容、`diagnose._greedy_segment` 段诊断等 14 个文件适配点。

## 算法核心

**求解期区间绑定**(`kleene_bind`):

- 段首落外层窗口 `[lo, hi]`
- 成员对段首 `span_from_first` 跨度约束
- 整段过 cardinality 下界(`min_count`)+ `node.where` + `aggregate_where`(可跨 role 读 `ctx.bound`)
- yield `(seq_tuple, 段尾原始流下标)`

**外层边绑定**(`endpoint_for_edges`):

- Kleene 节点作为外层边端点时,选段首(`first`)还是段尾(`last`)由 `KleeneSpec.endpoint_for_edges` 决定

**入边校验**(`_kleene_indeg_ok`):

- 段首作为下游绑定时,所有入边 satisfies 校验

**前沿割签名**(归档前在 `_signature.py`):

- Kleene 段双端点都入 frontier_cut_signature(段首 + 段尾)

## 何时考虑复活

触发条件:出现"段长度/聚合判据依赖外层 role 字段"的业务场景,例如:

- "burst 段长度 N 必须 ≥ outer_trend.duration / k"(段长依赖前置 trend)
- "burst 内 vol_ratio 阈值由前置 platform 的 ATR 决定"(段聚合判据跨 role)

**届时优先考虑在 nested event 框架上扩展**(让 detector 接受"求解期延迟物化"接口),而非直接复活当前形态的 `KleeneSpec`:

- 当前 `KleeneSpec` 跟 `path2/dag/` 紧耦合(求解器循环、签名、reify、诊断各处),复活成本不低于重写
- nested event 框架本身具备"detector 跨 role 物化"扩展空间(detector 在 detect 时已可读 ctx)

## 前端归档说明

`node.kleene` boolean 标志(前端 topology 面板)+ `ClauseWitness.aggregate` 标志(前端 detail 侧栏 aggregate_where 来源指示)同步归档:

- 前端 topology 面板归档后不再差异化 Kleene 与 ONCE 节点
- 前端 detail 侧栏归档后不再差异化 "aggregate" 与 "once" 条件来源

## 归档代码文件

- `kleene_spec.py`:`KleeneSpec` dataclass
- `kleene_bind.py`:`kleene_bind` + `_kleene_shape_ok` 算法
- `_kleene_indeg_check.py`:`_kleene_indeg_ok`
- `kleene_dfs_branch.py`:原 `_any_dfs:411-430` 的 Kleene 分支(独立函数形态)
- `kleene_where_predicates.py`:`W.first / W.last / W.count / W.any / W.distinct / W.reduce` 6 个 seq 谓词工厂

**约束**:归档代码只 `from path2.core import Event`,不可 `from path2.dag import ...`(避免形成幽灵依赖)。
