# marker 实例绑定实施验收报告(2026-08-13)

> 实施主线:instance-flow 分支,Tasks 1-7 全部落地(commits 7426951..3040dc4 为设计/计划,Task 1-6 为 c280107..3040dc4,Task 7 为本报告)。设计 spec:docs/superpowers/specs/2026-08-13-marker-instance-binding-design.md。

## 1. 契约变更摘要

| 层 | 变更 | commit |
|---|---|---|
| 后端 serialize | match `node_index` 值从字符串对象化为 `{event_id, idx}`(idx 与事件行 `instance_key` 同源编号) | c280107 |
| 后端 diagnose | attr 行加 `instance_key`(与 serialize_analysis 同一编号函数,同源) | bd08c1e |
| 前端类型 | `NodeRef {event_id, idx}` 类型 + 全部消费点机械适配(删 kleene 残留) | f9c3051 |
| 前端 visible | 判定全实例级:`matchedIds` 精确初始集(双 match 各贡献自己实例)、`qualifiedIdsOf` 实例级、`eventTierOf` 三档实例级 | 9415e1c |
| 前端 view | `focusEvent` 双入口(实例直选/身份并集)+ 焦点实例级 `focusedEventKey` | 54d1a60 |
| 前端交互 | marker 点击绑定实例(event_key 解析)+ tooltip 实例级 | 3040dc4 |

不兼容性:旧 scan 文件 node_index 为字符串、无 idx,不兼容新契约——验收数据须用新后端重算生成(见 §5)。

## 2. 判定语义

- **实例级入口**(K 线 marker 点击,带 idx):复合键 `{event_id, idx}` 在 `match.node_index` 精确引用计数 0/1/≥2 → 只聚焦事件 / **直选 match** / 待选择(真共享实例)。
- **身份级入口**(侧栏 trace 行 / 候选表行,不带 idx):身份下全部实例的归属**并集**——一致则直选 / 分属或共享则待选择 / 无归属则只聚焦。
- **待选择收窄**:旧语义按 anchor/children 身份展开判定归属,单身份多 match 一律弹窗;新语义按复合键精确计数,实例分属(如 APCX 的 #0/#1 各属一个 match)不再误弹,只有真共享(同一实例被多 match 引用)或身份级分属才弹。

## 3. 回归摘要

### 后端(`uv run pytest tests/ -q`)

- **1112 passed, 6 failed, 2 skipped**。6 个失败全部为实施前 pre-existing 名单,无新增:
  - `tests/path2/atoms/test_throwback_debug_anchor_kinds.py` 4 个(debug 断点计数/锚点种类分布基线)
  - `tests/path2_apps/bb_v1/test_bb_v1.py::test_p2_yaml_loadable_and_mirrors_params_yaml`
  - `tests/path2_apps/bb_v3/test_bb_v3.py::test_p2_yaml_loadable_has_peak_age_min`
- 与实施前对照:失败名单逐字一致(6/6 同名),判定无回归。

### 前端(三绿)

- **vitest:78 文件通过、1 文件失败、815 passed / 4 failed**——4 个失败全部为 pre-existing `components.sidebar-result-list.spec.ts`(char forwarding 类),无新增。
- **vue-tsc --noEmit:exit 0**。
- **vite build:成功**(5.44s,chunk 体积警告为既有现象)。

## 4. 真实数据验收结果(APCX)

验收测试:`path2_web_ui/tests/instance-binding-acceptance.spec.ts`(4/4 PASS),数据源 `outputs/path2_web/scans/20260813T005540-instanced.json`(APCX 单股重算快照,bb_v1,22 events / 2 matches,tb_v1_293 双实例)。

| 场景 | 断言 | 结果 |
|---|---|---|
| ① 数据级 | tb_v1_293 两实例(#0/#1),各被一个 match 的 node_index 精确引用(idx 0/1,引用不同 match) | PASS |
| ② 实例级入口 | `focusEvent('tb_v1_293', 0)` → 直选引用 #0 的 match;`(…, 1)` → 直选引用 #1 的 match;均不弹待选择 | PASS |
| ③ 身份级入口 | `focusEvent('tb_v1_293')` → `pendingDisambigEventId='tb_v1_293'`,2 候选 | PASS |
| ④ 真共享 fixture | 基于真实数据构造:两 match 的 node_index 同引用 `{tb_v1_293, idx:0}` → 仍待选择(2 候选) | PASS |

## 5. 遗留观察

- **验收数据文件来由**:`outputs/path2_web/scans/20260813T005540-instanced.json` 是实施后(新契约)用新后端对 APCX 真实 pkl 单股重算的快照——与历史 scan `20260813T005540.json` 同窗(2025-01-01..2026-01-01)、同缓冲(2024-09-19..2026-03-08)、同 label_horizon(40)、同 filters(price 0.5-30 / volume>10000)、同 first_passage_k(5.0),仅 node_index 格式不同。历史文件本身按 spec「不兼容旧 scan 文件」保持不动;若未来需复用,应以旧文件作参照、用新后端重算。
- **brief 路径示例修正**:brief 建议的测试内 json 相对路径 `../../outputs/…` 对 cwd=path2_web_ui 而言多上一级(vitest 保持调用方 cwd),实际采用 `../outputs/…`(path2_web_ui 上一级即 repo root)。
- 其余无阻塞问题;Task 1-6 代码本任务未改动。
