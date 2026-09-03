# event_id 全面实例化重构 — 全量回归 + 真实数据验收报告

> 2026-08-13。重构收口(Task 11)。SDD ledger:`.superpowers/sdd/2026-08-13-instance-id-refactor/progress.md`;设计文档:`docs/research/2026-08-13_instance-id-design.md`。

## 一、契约变更摘要

本重构(11 个 task)把事件标识体系从「身份键 + NodeRef 双轨」收敛为**纯实例化单轨**,契约变更:

| 消灭的旧契约 | 取代物 | 说明 |
|---|---|---|
| `event_id`(身份键,如 `tb_v1_293`) | `instance_id`(如 `tb_293#0`) | = (node_id, span, 流序) 编码,全局唯一实例键 |
| `instance_key`(`#0`/`#1` 独立字段) | 并入 `instance_id` 尾部 `#idx` | 不再独立成字段 |
| `source_tag`(class 维度消歧/分层补丁) | 无(node 维度 + `node_id`) | 键用 node 后天然不撞,补丁退场 |
| `class_id` 字符串(契约层镜像) | Python 类(`event_cls.__name__` / isinstance) | 注册表、事件行 class 字段、按类聚合全删 |
| `match.event_id`(match 身份) | `match.match_id` | match 唯一键含 node_index 组合位 |
| `node_index` 值为 `{event_id, idx}` 对象 | `node_index` 值为 `instance_id` 字符串 | 引用即事实,零反推 |
| `focusEvent(event_id, idx)` 双参入口 | `focusEvent(instance_id)` 单入口 | 调用点全持完整实例键 |

引用协议(children / child_refs / anchor / match.node_index)一律走 `instance_id` 字符串。真共享语义(同 instance_id 被 ≥2 match 引用 → pendingDisambig)不变、更直白。

## 二、回归摘要

### 后端 `uv run pytest tests/ -q`

| | 基线(实施前,progress.md) | 收口(本 task) |
|---|---|---|
| failed | **6** | **6** |
| passed | 1112 | 1047 |
| skipped | 2 | 2 |

**6 项失败逐项对照(与基线完全吻合,无新增)**:

| # | 测试 | 类型 |
|---|---|---|
| 1-4 | `tests/path2/atoms/test_throwback_debug_anchor_kinds.py`(has_exactly_two_debug_break_calls / anchor_kind_distribution / class_id_distribution / joint_distribution) | pre-existing(基线 4 项) |
| 5 | `tests/path2_apps/bb_v1/test_bb_v1.py::test_p2_yaml_loadable_and_mirrors_params_yaml` | pre-existing(p2.yaml,基线 1 项) |
| 6 | `tests/path2_apps/bb_v3/test_bb_v3.py::test_p2_yaml_loadable_has_peak_age_min` | pre-existing(p2.yaml,基线 1 项) |

passed 从 1112 降到 1047(净 -65):重构删除了失效/重复测试(`test_event_id_unchanged.py` 整删、Task 7-10 前端旧 fixture 同步、部分旧断言测试被新契约测试取代),不是新增失败。**失败数严格等于基线 6、「无新增失败」判据达成。**

#### 本 task 的后端改动

- **Ruling J(4 项 path2_apps 契约漂移测试迁移)** —— 重构引入的非 pre-existing 失败,生产代码正确,只迁测试断言(class_id 断言 → Python 类):
  - `tests/path2_apps/bb_v0/test_bb_v0.py::test_pattern_id_and_topology`:`event_cls.class_id == "tb_v0"` → `event_cls is ThrowbackEventV0`
  - `tests/path2_apps/bb_v1/test_bb_v1.py::test_pattern_id_and_topology`:`→ ThrowbackEventV1`
  - `tests/path2_apps/bb_v3/test_bb_v3.py::test_pattern_id_and_topology`:`→ ThrowbackEventV3 / ThrowbackSegmentV3`
  - `tests/path2_apps/bottom_burst/test_dag_spec.py::test_nodes_present_and_typed`:`→ BOEvent / BurstEvent / ThrowbackEvent / ThrowbackSegment`
  - 迁移后 `tests/path2_apps/ -q` = **2 failed**(仅 bb_v1/bb_v3 p2.yaml pre-existing),78 passed。
- **Task 6 遗留 docstring 修正**(progress.md「Important(deferred)」):`path2_web/eval_runner.py::_upstream_key` docstring 原写「独立于事件身份」说反,现键含 `instance_id`——已修 docstring + 显式注释声明「单实例节点逐字不变」不变式被放弃(改读实例身份的固有结果、行为正确)。

### 前端三绿

| 项 | 基线 | 收口 |
|---|---|---|
| `npx vitest run` | 4 failed / 819 passed | **4 failed / 822 passed**(+3 新验收测试) |
| `npx vue-tsc --noEmit` | 0 errors | **0 errors** |
| `npx vite build` | ok | **✓ built**(仅 chunk-size warning,非错误) |

4 个 pre-existing 失败全部在 `tests/components.sidebar-result-list.spec.ts`(first_passage 显示格式 75.0% vs 75% + 3 个 global char forwarding),与基线逐项吻合、无新增。

## 三、真实数据验收(APCX · bb_v1)

### 数据来源

- **窗口参数**:取自旧 scan 元数据 `outputs/path2_web/scans/20260813T005540-instanced.json` 的 scan 节(start 2025-01-01 / end 2026-01-01 / win 2024-09-19..2026-03-08 / label_horizon 40),与 plan 硬编码值一致。
- **重算**:新后端(`PatternRegistry` + `_scan_ticker_multi`)对 `datasets/pkls/APCX.pkl` 单股重算 bb_v1,固化到**新文件** `outputs/path2_web/scans/apcx-instance-id-acceptance.json`(原历史文件不动;outputs/ 在 gitignore,按仓库先例 force-add)。
- **为什么重算**:旧 `20260813T005540-instanced.json` 是新契约前产物(事件行仍含 `event_id/source_tag/class_id/instance_key`,node_index 值为 `{event_id, idx}` 对象),与新契约不兼容,不可直接当验收 fixture。

### 实例形态(重算真实结果,未硬造)

- 事件 22 / matches 2 / summary `{bo: 8, burst: 8, tb: 6, matches: 2}`。
- **`tb_293#0` / `tb_293#1`** 双实例真实存在(node_id='tb',同桶 (tb, 293, 293) 流序 0/1),且与验收 fixture 完全吻合:
  - match A `bb_v1@282-293#burst:burst_282_289#0|tb:tb_293#0` → node_index `{burst: 'burst_282_289#0', tb: 'tb_293#0'}`
  - match B `bb_v1@282-293#burst:burst_282_290#0|tb:tb_293#1` → node_index `{burst: 'burst_282_290#0', tb: 'tb_293#1'}`
- 事件行新契约验证:无 `event_id/source_tag/class_id/instance_key` 字段;`instance_id` 恒带 `#idx`;`node_id ∈ {bo, burst, tb}`;格式 = `span_id(node_id, start, end) + "#" + instance_idx`(点塌缩、区间保留 end,对齐 `path2/core.py::span_id`)。

### 验收测试

新增 `path2_web_ui/tests/instance-id-acceptance.spec.ts`(补回 Task 9 删除的 `instance-binding-acceptance.spec.ts` 丢失的「真实 scan 快照」数据级覆盖),加载新 JSON 断言:

1. **数据级**:事件行无旧身份字段;`instance_id` 恒带 `#idx` 且格式与 span_id 一致;`tb_293#0/#1` 各被**恰好一个** match 的 node_index 精确引用(字符串值),两引用对应不同 match;node_index 每个值都能在 events 中找到对应实例。
2. **实例级入口**:`focusEvent('tb_293#0')` → 直选 match A(`focusedMatchId` = m0.match_id、`focusedInstanceId` = 'tb_293#0'、无 pending);`focusEvent('tb_293#1')` → 直选 match B;均不弹待选择。
3. **真共享 fixture**(基于真实 scan 深拷贝,把两 match 的 node_index 都改成引用 `tb_293#0`)→ `pendingDisambigInstanceId` = 'tb_293#0'、candidateMatchIds 2、focusedMatchId null。

```
cd path2_web_ui && npx vitest run instance-id-acceptance.spec.ts
→ ✓ tests/instance-id-acceptance.spec.ts (3 tests) 16ms · PASS
```

## 四、遗留观察(非阻塞)

1. **值已迁名未改的 wire 字段名**(Task 6 裁定「参数名保留」的一致 wire 契约):后端 `Query.event_id` / api URL `src_event_id/dst_event_id` / `PairFailure.src_event_id/dst_event_id` / `GateFailure.class_id` / `eval_runner` 输出键 `leaf_event_id` / `debugTarget.eventId`(前端),值已全走 instance_id / `__name__`,字段名仍是旧名。彻底清零需后端同步改名 + 前端归一化层,列为后续独立收口项。
2. **pre-existing 名单变化**:
   - `test_throwback_debug_anchor_kinds.py` 在 Task 4 被改(debug 标签 `class_id` 迁移 `__name__`,文件 +26/-9),4 个失败计数不变、测试名不变(has_exactly_two_debug_break_calls / anchor_kind / class_id / joint distribution)——**失败集逐项未变**。
   - bb_v1/bb_v3 p2.yaml 2 项全程未动,与基线一致。
3. **Ruling J 迁移副作用**:path2_apps 4 项测试从 class_id 字符串断言改为 Python 类断言,语义更贴近「类型以 Python 类表达」的新契约。
4. **`anchor_bo_id` 形态**:真实数据下为 span_id(如 `BOEvent_289`,Ruling H 的 span 语义),与物化 instance_id 形态不同——既有设计,不影响本验收(焦点/marker 走 instance_id,anchor 走 span 级比较)。

## 五、验收判定

- [x] 全部 11 个 task 完成且每 task commit 到 `instance-id-refactor` 分支
- [x] 前端三绿(4 pre-existing + vue-tsc 0 + vite build)+ 后端 pytest 失败数 = 基线 6、无新增
- [x] 真实数据验收通过(APCX 双实例直选、真共享待选择、新契约字段零残留)
- [x] 验收报告入档(本文)
