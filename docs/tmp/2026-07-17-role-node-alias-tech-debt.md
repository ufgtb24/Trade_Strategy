# path2 里 role 一词的两种混用 · 别名清理 tech debt

**日期**: 2026-07-17
**决定人**: 用户
**当前决议**: 不做,记录为 tech debt · 未来任意时机可清理

---

## 为什么会有这份便签

path2 项目里 "role" 这个词承载了**两种不同**的意思,长期在 code / docstring / 变量名 / 讨论口头里混用。刚落地的 anchor_kind refactor(commit 22b90a5)消除了其中一种(v3 debug 层面的),另一种(topology 层面的别名)残留。写下来免得未来读者再踩坑。

### 两种 role 各是什么

**(A) topology role** — pattern DAG 里"一个 detector 挂在这里"的位置。

- 权威字段名 = `path2/dag/spec.py::NodeSpec.node_id`(全局唯一,`_validate_node_ids` 强制)
- 历史别名 = "role" / "role_id",随手用
- 事实关系:**role = node,同一个东西**
- code 里代表性证据:`path2/dag/result.py:68` 注释直接写 `role_events: Dict[str, str]    # role_id(node_id) → event_id` —— 明说 `role_id` 就是 `node_id`

一 detector class 可挂多个 node,每个 node 有独立 `node_id`。"这个 detector 在 pattern 里扮演什么角色"就是 node 在 pattern DAG 里的位置。

**(B) v3 debug_break kwarg 里曾经叫 `role` 但实际是 anchor kind** — 已在 2026-07-17 的 anchor_kind refactor(commit 22b90a5)消除。这里已经改完,不再是 tech debt。

**本便签只讨论 (A)。** 别把两个 role 混在一起。

---

## 现状(残留别名清单)

数据结构的核心字段名已经统一是 `node_id`。混淆源在于**别名残留**散落在多处 identifier / 变量名 / docstring:

- `path2/dag/result.py::PatternMatch.role_index` — 类型注释明说是 `node_id → 单 Event`
- `path2/dag/result.py::PatternMatchAlt.role_events` — 类型注释明说是 `role_id(node_id) → event_id`
- `path2/dag/diagnose.py::RoleDiagnostic` 类名
- `path2/dag/diagnose.py` 里 `roles` 字典变量名(key 用 node_id · 变量名叫 roles)
- `path2_apps/**/dag_spec.py` docstring 里 "节点" 和 "role" 两个词随手混用(例:`bottom_breakout_burst/dag_spec.py:5` "节点: bo(孤立 role,无边)")
- 可能的前后端 web JSON 序列化契约里也有 `role_events` / `role_index` 字段名(未查证 · 若做时要 grep 前端 store / component 有无对应字段)

---

## 不做的理由(当前 · 2026-07-17)

- role 别名不阻塞功能,现状 code 已 90% 用 node
- 数据结构核心字段名(`NodeSpec.node_id`)已经是权威,不需要动
- 波及**前后端序列化契约**(如果 web JSON 也用 `role_events`),前端 store/component 潜在 role 词也要一起 grep 同步
- scope 中等(不是纯 rename · 涉及类名 / 字段名 / 契约),现在没有强触发点
- 与 anchor_kind refactor(小 scope · 干净)独立,不合并做

---

## 什么时候值得重启

任意时机可做。以下之一触发就是好时机:

- **触发 A**:又一次讨论 / 文档里看到 role 和 node 被混用、导致误解(说明混淆真在造成成本)
- **触发 B**:实施新功能时被 `role_events` / `role_index` 这类字段名迷惑,需要澄清才能继续(阻塞点)
- **触发 C**:前后端序列化契约反正要动(比如加新字段),顺手把 role 别名一起改
- **触发 D**:某个空档时间做 code hygiene sweep

---

## 清理清单(方向 A · 参考实施 scope)

一次 commit 完成,分组做。

### Python 层(数据结构别名清理)

- `path2/dag/result.py::PatternMatch.role_index` → `node_event_index`(名副其实:每个 node 对应的 Event)
- `path2/dag/result.py::PatternMatchAlt.role_events` → `node_events`
- `path2/dag/diagnose.py::RoleDiagnostic` 类 → `NodeDiagnostic`
- `path2/dag/diagnose.py` 里 `roles` 字典变量 → `node_diags`

### Docstring 层

`path2_apps/**/dag_spec.py` docstring 里所有非 topology-role-语义的 "role" 字样统一改 "node"。例:`bottom_breakout_burst/dag_spec.py:5` "节点: bo(孤立 role,无边)" → "节点: bo(孤立 node,无边)"

### 序列化契约层(如涉及)

先 grep 前后端:

```bash
grep -rn "role_events\|role_index" path2_web/ path2_web_ui/
```

若有相应字段,前后端同步改;若前端已用 `node_events`(仅后端叫 role),则 backend 单侧改即可。

### 不改的

- `NodeSpec.node_id` 字段本身 — 已是权威字段名,不动
- `NodeSpec` 类名 — 不动

---

## 不该动的 role 词(避免误改)

清理时逐处判断,以下 role 词是 topology role 语义的**合法**用法,不该被误认为"别名残留"改掉:

- **已由 anchor_kind refactor 处理**:`debug_break` kwarg / `DEBUG_ROLE` env / URL query `role`(commit 22b90a5 已改为 `anchor_kind` / `DEBUG_ANCHOR_KIND`,不再是 tech debt)

- **`path2_web/api.py` 里的 topology role 参数**:
  - `src_role` / `dst_role`(scope=roles topology-edge 诊断 query · 语义就是 topology role 边端点)
  - `end_role` / `end_roles`(eval_meta 概念 · 也是 topology role)

- **`path2_web_ui/src/api.ts::getRolesDiagnose(srcRole, dstRole)` · `scope=roles`**(前端端点,与 backend 对应)

- **`path2_web_ui/src/stores/view.ts` 里**:
  - `roleVisible` / `roleColors` / `Selected.kind:'role'` / `roleOfEventByBand`
  - 这些是 topology role 层面的用法 · 语义正确
  - **但如果做清理,建议单独评估是否要动 UI** —— 前端 store 语义清晰、别名清理波及 UI 层可能不划算;或分批做:先动 backend 再评估前端

---

## 与 anchor_kind refactor 的边界

anchor_kind refactor(commit 22b90a5)动的是 v3 debug 里被**错借用**为 role 的 anchor kind 值(gate / trough / end / entry 5 元 enum),把它 rename 为 `anchor_kind`。那次 refactor 后,path2 项目里 role 一词只剩下 topology 层面的用法(node 别名 + 语义正确的边端点 / eval_meta 概念)。

**本 tech debt 处理的是剩下的"node 别名"部分**,不涉及 anchor kind、也不涉及语义正确的 topology role 用法。

清理时逐处判断:如果这个 role 词在 code 里的实际语义是"某个 node",就该改;如果它的语义是"边的一个端点"或"eval_meta 里的位置声明"这类 topology role 用法,就不该改。

---

_便签 · 无时限 · 未来任意时机可做,或永远不做(如果不再有触发点)_
