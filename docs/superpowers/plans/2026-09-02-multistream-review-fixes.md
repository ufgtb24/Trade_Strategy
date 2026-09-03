# 多流引擎 review 修复 · 实施计划

> **本 plan 中所有项目内路径均相对 repo root。** 系统路径（`~/.claude/...`、scratchpad）保持绝对。
> 执行方式：subagent-driven（Implementer = `sonnet`，Reviewer = `opus`），每 task 一个 commit，任一 task 验证关卡失败即 BLOCKED 停下汇报，不带病推进。
> 输入文档：`docs/tmp/2026-09-01-multistream-spec-review.md`（review 结论 + 已拍板项）。两份 spec（`docs/superpowers/specs/2026-09-01-multistream-*.md`）已归档为历史记录，**禁止反向修改**。

## Context

多流 detector 引擎（`produces` + `yield (流名, event)` + `ref_slots` 引用翻译）已落地，7 个 app 的 `BODetector` 全部走 bo + pk 双流。review 对照代码发现四类问题：

1. **引用协议的输出没进 payload，输入反而漏出去了**：`_translate_refs` 把翻译结果写成非 dataclass 字段属性，序列化看不见；`broken_refs` / `superseded_refs` 原始对象元组被 `_jsonable` 递归展开（实测占事件 payload 39.8%，嵌套 6 层）。
2. **「声明了但未绑定的流」是未定义状态**：只绑 bo 不建 pk node 时 `analyze` 在翻译阶段抛「事件池外」错误（误导），`gate_collector` 另有一套只在诊断路径生效的检查。
3. **`PeakEvent.state` 是唯一的未来信息字段**，与 `ref_slots` 表达同一份信息；用户已拍板走关系合成、删 `state`。`broken_peak_ids` / `pk_count` 是 `broken_refs` 的投影，一并派生。
4. **峰登记阶段的 6 个 gate failure 标 `stream="bo"`**，用户已拍板改归 pk（下拉选 pk 看 pk 的失败，选 bo 看 bo 的）。

外加小项（多流 detector 多余的 `event_cls`、bear `volume_peak=0.0` 占位）与 authoring skill 同步（两处过时事实 + 设计规则 + 措辞）。

**明确不做**：A9 tune-gates 同步（用户拍板搁置，等另一分支合并后处理）；`price` / `original_price` 双字段与 elevation 的 yield 后演化（只在 skill 写规则，代码不动）；spec 文档反向修改。

## 顶层契约（所有 task 共同遵守，实施者不得自行更改）

| 契约 | 定义 |
|---|---|
| C1 `Event.ref_ids` | `Event` 基类新增声明字段 `ref_ids: Tuple[Tuple[str, Tuple[str, ...]], ...] = field(kw_only=True, default=())`，与 `instance_id` 同为引擎物化注入。形状 = 按槽名字典序排列的 `(槽名, (instance_id, ...))` 对。用 tuple 而非 dict：保持 frozen 容器一律 tuple、可哈希。基类加便利方法 `ref_ids_of(slot) -> Tuple[str, ...]`（缺槽返回 `()`）。`{槽名}_ref_ids` 这种属性注入**整体删除**。 |
| C2 payload 对称 | `_event_to_dict` 跳过 `ref_slots()` 的槽名（与 `child_slots()` 同款），输出 `"ref_ids": {槽名: [instance_id, ...]}`（dict）。`broken_refs` / `superseded_refs` 等原始对象字段**不再出现**在任何事件 dict 里。 |
| C3 全绑定规则 | `PatternSpec` 构造期校验：按 `(id(detector), consumes_stream)` 分组，每组 detector 声明的每条流（`stream_schema(det)` 的键）必须被组内某个 node 的 `produces_stream` 认领。缺 → `ValueError`，信息形如 `detector 声明的流 ['pk'] 没有 node 认领(node 组 ['bo']);多流 detector 的每条流都必须建 node,只显示不匹配用 solve=False`。`gate_collector.attach_and_collect` 的同类检查**保留**作兜底。 |
| C4 三态合成 | 前端按本股**全部** events（level / nodeVisible 过滤之前）合成：某 pk 的 instance_id 出现在任一事件 `ref_ids.broken` 里 → `broken`；否则出现在任一事件 `ref_ids.superseded` 里 → `eaten`；否则 `alive`。与被删的 `state` 三条突变规则逐条等价。pk 事件的判别子从「带 `state`」改为「带 `peak_idx`（number）」。 |
| C5 派生字段 | `BOEvent.broken_peak_ids` / `pk_count` 从字段改为 `@property`：`tuple(p.pk_id for p in self.broken_refs)` / `len(self.broken_refs)`。构造点不再传这两个 kwarg。前端 bo 盒文本改为 `ref_ids.broken` → 本股 pk 索引查 `pk_id`。 |
| C6 gate 归属 | `_detect_peak_in_window` 内 6 处 `GateFailure(... stream="bo")` 改 `stream="pk"`；`_check_breakout` 的 `no_active_peak_broken` 保持 `"bo"`。 |
| C7 类型无关红线 | 渲染器对其他 event 零改动。bo/pk 特有语义（槽名 `broken` / `superseded`、字段 `pk_id` / `peak_idx`）只允许出现在一个独立的纯函数模块 `path2_web_ui/src/render/peakState.ts` 与 `chart.ts` 现有的 pk/bo 分支里。 |

## 基线（Task 0 记录，后续每 task 对照）

- Python：`uv run pytest tests -q`（**只跑 `tests/`**；根目录含 `BreakoutStrategy/` 旧测试会收集报错，不算回归）。
- 前端：`cd path2_web_ui && npx vitest run && npx vue-tsc -b && npx vite build`。已知预存失败：`tests/components.sidebar-result-list.spec.ts` 4 个（HEAD 基线同样失败，与本 plan 无关）。
- 真实数据：`/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl`（主目录绝对路径，worktree 内该目录为空）。

---

## Task 0 · 基线与对拍快照

**目的**：给 Task 4 的「bo 语义逐字不变」提供机器可比的基线。

1. 跑 Python 与前端全套，把通过/失败数记进 `/tmp/claude-*/scratchpad/baseline.txt`（预存失败逐条列出）。
2. 写临时脚本 `scratchpad/snapshot_bb.py`（**不入库**）：对 `ACRS MBI NVX BRNS ABAT` 五只票，用 `path2_apps.bb_v1.dag_spec.analyze`（默认 params，`bear_drop=None` 即 bear OFF）跑 `analyze`，导出 JSON：每个 match 的 `match_id`；**每个 node 的事件计数**；每个 bo 事件的 `instance_id / drought / pk_count / broken_peak_ids / peak_age_max / peak_vol_max`；每个 burst 事件的 `instance_id / distinct_pk / first_drought`（`distinct_pk` 是唯一经 `broken_peak_ids` 派生进 where 的量）；每个 pk 事件的 `instance_id / pk_id / kind / peak_idx / price / original_price`。存 `scratchpad/snapshot_before.json`。
3. 不 commit。

---

## Task 1 · 引擎：`Event.ref_ids` 声明字段（契约 C1）

**文件**：`path2/core.py`、`path2/dag/engine.py`、tests。

1. **RED**：新测试 `tests/path2/dag/test_ref_ids_field.py`：
   - 多流假 detector（可复制 `tests/path2/dogfood_multistream.py` 的 RangeNoteDetector 骨架）跑 `run_streams` 后，`note.ref_ids == (("anchor", (range.instance_id,)),)`，`note.ref_ids_of("anchor") == (range.instance_id,)`，`note.ref_ids_of("nope") == ()`；
   - `hasattr(note, "anchor_ref_ids") is False`（旧属性注入已删）；
   - 无引用事件 `ref_ids == ()`；
   - `dataclasses.replace(note, start_idx=...)` 保留 `ref_ids`（声明字段的好处，锁住）；
   - `hash(note)` 不抛（tuple 可哈希）。
2. **GREEN**：
   - `path2/core.py` `Event`：在 `instance_id` 后加 `ref_ids` 字段 + `ref_ids_of`；docstring 补一段「引用槽翻译结果，引擎 `_translate_refs` 注入，detector 阶段恒 `()`」。
   - `path2/dag/engine.py::_translate_refs`：收集 `{slot: ids}` 后 `object.__setattr__(e, "ref_ids", tuple(sorted(pairs)))`，删 `{slot}_ref_ids` 写入。错误信息改为：`引用的事件没有 instance_id(不在任何已绑定流里):{type} @bar {start}(ref_slots[{slot}]);PatternSpec 已校验全绑定,此处只剩 detect 引用了池外对象`。
3. 同步既有测试（把 `xxx_ref_ids` 断言改成 `ref_ids_of("xxx")`）：`tests/path2/dag/test_engine_multistream.py:84,116`、`tests/path2/test_multistream_end_to_end.py:36`、`tests/path2/atoms/test_peak_event.py:53`、`tests/path2/atoms/test_breakout_multistream.py:62-65`、`tests/path2/dogfood_multistream.py`（若有断言）。
4. 关卡：`uv run pytest tests -q` 与基线一致（只允许本 task 目标测试从红变绿）。
5. Commit：`refactor(engine): ref_slots 翻译结果落为 Event.ref_ids 声明字段,删 {slot}_ref_ids 属性注入`

---

## Task 2 · 序列化对称（契约 C2）

**文件**：`path2_web/serialize.py`、`tests/path2_web/test_serialize.py`、`tests/path2_web/test_serialize_pk.py`。

1. **RED**：
   - 重写 `tests/path2_web/test_serialize.py::test_serialize_analysis_bo_events_have_broken_refs` → 改名 `..._have_ref_ids`：bo dict **无** `broken_refs` 键、有 `ref_ids["broken"]`（list[str]，每个是某 pk 事件的 `instance_id`）；pk dict 无 `superseded_refs`，有 `ref_ids`（可为 `{}`）。
   - 新测试：`json.dumps(out["events"])` 里不出现嵌套事件 dict（断言任何事件 dict 的值都不是 `dict` 含 `instance_id`，且总长度相对旧实现显著缩小无需断言数字）。
   - `test_serialize_pk.py::test_peak_event_state_kind_serialized` → 改为 `..._kind_serialized`：去 `state`（Task 4 才删字段，这里先用 `PeakEvent(...)` 不传 state；若 Task 4 未到而字段仍在，本测试只断言 `kind`，并断言 `"superseded_refs" not in row`）。
2. **GREEN**：`_event_to_dict` 的 `skip_slots = set(e.child_slots()) | set(e.ref_slots())`；末尾 `d["ref_ids"] = {slot: list(ids) for slot, ids in e.ref_ids}`；docstring 同步（「持有型 child 走 child_refs、引用型 ref 走 ref_ids，原始对象字段一律不进 payload」）。
3. 前端类型：`path2_web_ui/src/types.ts` `EventDict` 加 `ref_ids?: Record<string, string[]>`（与 `child_refs` 并列，注释同款）。
4. 关卡：Python 全套 + `npx vue-tsc -b`。
5. Commit：`fix(serialize): 事件 dict 输出 ref_ids、跳过原始引用槽字段(payload 去递归嵌套)`

---

## Task 3 · PatternSpec 全绑定校验（契约 C3）

**文件**：`path2/dag/spec.py`、`path2_web/gate_collector.py`（不改逻辑，只改 docstring）、tests。

1. **RED**：新测试 `tests/path2/dag/test_spec_streams_bound.py`：
   - 多流假 detector 只建一个 node → `PatternSpec(...)` 抛 `ValueError`，`match="没有 node 认领"` 且信息含缺的流名 `pk`；
   - 两条流都建 node → 通过；
   - 单流 detector 不写 `produces_stream` → 通过（声明 `{None}` = 认领 `{None}`）；
   - 同一 detector 两次不同 `consumes_stream` 的调用各自独立校验（构造两个 node 组，其中一组缺流 → 报错信息指向那一组）；
   - 子结构 node（`detector=None`）不参与。
   - 回归：用真实 `BODetector` 只建 bo node → 构造期即报错（把 review §1.2 的实验固化成测试，错误不再是「事件池外」）。
2. 同步会被新校验打断的既有测试（子代理逐文件核实过，其余多流测试均双绑或单流，安全）：
   - `tests/path2_web/test_gate_collector_multistream.py::test_unbound_stream_attach_raises`：`PatternSpec` 现在构造期就拒，改为用 `types.SimpleNamespace(nodes=[...])` 伪 spec 直接喂 `attach_and_collect`，保住 collector 兜底检查的覆盖。
   - `tests/path2_web/test_serialize_multistream.py:35-37`：`_Multi()` 构造了**两个实例**各绑一条流，每个实例声明 {a,b} 只认领一条 → 改为共享同一个实例喂两个 node。
   - `tests/path2_web/test_discovery_eval_meta_required.py:31,57,81,105`：生成的临时 app 模块只写 `NodeSpec('bo', BODetector(), produces_stream='bo')`，pk 未认领 → 模块 import 期就抛错、discovery 拒绝原因失配。四处都补 `NodeSpec('pk', det, produces_stream='pk', solve=False, render_grid='price')`（共享同一 `det`）。
3. **GREEN**：`PatternSpec.__post_init__` 校验链加 `self._validate_streams_bound()`（放 `_validate_no_self_feed` 之后）。实现模板照 `_validate_no_self_feed`：按 `(id(n.detector), n.consumes_stream)` 分组，`declared = set(stream_schema(det))`，`bound = {n.produces_stream for n in group}`，`missing = declared - bound`。`stream_schema` 从 `path2.core` 导入。
4. `gate_collector.py` docstring：把「挂载期校验」改述为「PatternSpec 构造期已校验；此处保留作兜底（伪 spec / 测试路径）」。
5. 关卡：Python 全套。7 个 app 的 `build_pattern(Params.default())` 全部可构造（写一个参数化测试或在既有 app 测试中确认）。
6. Commit：`feat(spec): PatternSpec 构造期校验多流 detector 的每条流都有 node 认领`

---

## Task 4 · breakout.py：删 state、派生字段、gate 归 pk、小项（契约 C5 / C6）

**文件**：`path2/atoms/breakout.py`、tests。

**4a 删 `state`（先做，RED→GREEN）**
1. RED：`tests/path2/atoms/test_peak_event.py`：删 `state` 断言；新增「构造 `PeakEvent` 不接受 `state` kwarg」（`TypeError`）。`tests/path2/atoms/test_breakout_multistream.py`：把「state 定稿三态」改为按 `ref_ids` 断言——`bo.ref_ids_of("broken")` 非空且每个 id 都对应 pk 流里的事件；`pk.ref_ids_of("superseded")` 里的 id 都对应 pk 流事件；`tests/path2_web/test_serialize_pk.py` 去 `state`。
2. GREEN：删 `PeakEvent.state` 字段与 docstring「显示专用 / 未来信息豁免」段；删 `_check_breakout` 的 `object.__setattr__(peak, "state", "broken")`；`_register_peak` 里 `eaten.append(old)` 无条件（删 `if old.state == "alive"` 分支）；两处构造去 `state="alive"`；`BODetector` docstring 相应删「state」句，补一句「**事件 yield 即定稿**是通例；本 detector 的 elevation 抬价（`price` / `original_price`）是现存例外，见 authoring-path2-detector reference §2」。

**4b 派生字段（契约 C5）**
3. RED：`tests/path2/atoms/test_breakout_multistream.py` 加：`bo.broken_peak_ids == tuple(p.pk_id for p in bo.broken_refs)`、`bo.pk_count == len(bo.broken_refs)`、`"broken_peak_ids" not in {f.name for f in dataclasses.fields(bo)}`；`W.attr("pk_count", ">=", 1)` 对 bo 实例可求值（property 经 getattr 可读）。
4. GREEN：`BOEvent` 删 `pk_count` / `broken_peak_ids` 字段与 `__post_init__` 的 tuple 强转（若 `__post_init__` 只剩 `super().__post_init__()` 则整个删掉）；加两个 `@property`；`_check_breakout` 构造 `BOEvent` 时删这两个 kwarg 与前面两行计算；docstring 字段表改「派生自 broken_refs」。`BurstDetector` 第 209 行 `m.broken_peak_ids` 不用动。
5. 同步用构造 kwarg 的既有测试 fixture（改 property 后传 `pk_count=` / `broken_peak_ids=` 会 `TypeError`；子代理核实共 6 个文件）。统一改法：**把 fixture 改成先构造 `PeakEvent(start_idx=i, end_idx=i, confirm_idx=i, pk_id=p, peak_idx=i, price=...)`，再以 `broken_refs=tuple(peaks)` 传给 `BOEvent`**，让派生值与原 fixture 意图一致：
   - `tests/path2/dag/test_multilayer.py:61-62`（`_bo` 靠 `broken_peak_ids=peaks` 裸 int 喂 `BurstDetector` 算 `distinct_pk`，若不改则 `distinct_pk` 全 0、多条断言翻）
   - `tests/path2/atoms/test_burst_on_gate.py:17`
   - `tests/path2_web/test_subcheck_helpers.py:19`
   - `tests/path2/dag/test_reify_kind_aware.py:12,20`
   - `tests/path2/dag/test_result.py:54`
   - `tests/path2/atoms/test_breakout_dataclasses.py:9-26`：其中「list 强转 tuple」与「默认值」两条测试的对象已不存在，**删掉**；「frozen 赋值抛错」保留但改成对 `broken_refs` 赋值。
   - `tests/path2/atoms/test_breakout_detector.py:217-220` 读 `broken_peak_ids` 与 `broken_refs` 的对应关系，property 下仍成立，跑到即可。

**4c gate 归 pk（契约 C6）**
5. RED：`tests/path2/atoms/test_bo_on_gate.py` 加断言：所有 `gate_name` 以 `peak_` 开头的 gf `.stream == "pk"`，`no_active_peak_broken` 的 `.stream == "bo"`。`tests/path2_web/test_gate_collector_multistream.py` 加一例：真 `BODetector` + bb_pk 拓扑跑 `attach_and_collect` → 单调下跌 df（复用 `test_bo_on_gate.py` 的 fixture）→ collector 里 peak 类 gf 的 `node_id == "pk"`。
6. GREEN：`_detect_peak_in_window` 内 6 处 `stream="bo"` → `"pk"`（`peak_no_local_max` ×2、`peak_side_bars_insufficient` ×2、`peak_already_active`、`peak_relative_height_insufficient`），注释同步。

**4d 小项**
7. 删 `BODetector.event_cls = BOEvent`（`stream_schema` 以 `produces` 为准；生产路径零读点：`serialize.py:278-279` 用 `type(n.detector).has_debug_hooks` + `n.event_cls`；`spec.py:187` docstring 里「detector.event_cls」改「node.event_cls」）。同步唯一断言它的测试 `tests/path2_apps/bottom_burst/test_dag_spec.py:33`：`assert by["bo"].detector.event_cls is BOEvent` 改为 `assert by["bo"].event_cls is BOEvent`（node 级归一化值），同文件 burst/tb 两行不动。
8. `PeakEvent.volume_peak: Optional[float] = None`；convex 路径照旧传 float，bear 路径不传；`_check_breakout` 的 `peak_vol_max = max((p.volume_peak for p in broken_peaks if p.volume_peak is not None), default=0.0)`。`tests/path2/atoms/test_breakout_bear.py` 若断言 `volume_peak == 0.0` 改为 `is None`。

**关卡（本 task 最重）**
9. Python 全套。
10. **对拍**：重跑 Task 0 的 `snapshot_bb.py` 得 `snapshot_after.json`，与 `snapshot_before.json` 比：match_id 集合逐字相同；每 node 事件计数逐字相同；每个 bo 的 `drought / pk_count / broken_peak_ids / peak_age_max` 逐字相同；每个 burst 的 `distinct_pk / first_drought` 逐字相同；`peak_vol_max` 允许仅在 bear 参与时不同（bb_v1 默认 bear OFF，应逐字相同）；pk 的 `pk_id / kind / peak_idx / price / original_price` 逐字相同。任何差异 → BLOCKED。
11. Commit：`refactor(breakout): 删 PeakEvent.state(三态改关系合成)、broken_peak_ids/pk_count 派生、峰 gate 归 pk、去 event_cls、bear volume_peak=None`

---

## Task 5 · 前端：三态合成 + bo 盒文本派生（契约 C4 / C5 / C7）

**文件**：`path2_web_ui/src/render/peakState.ts`（新）、`path2_web_ui/src/render/chart.ts`、`path2_web_ui/src/types.ts`、tests。

1. **RED**：新 `path2_web_ui/tests/peakState.spec.ts`：
   - `derivePeakStates(events)`：bo `ref_ids.broken=[pkA]`、pk B `ref_ids.superseded=[pkC]` → A=broken、C=eaten、其余 pk=alive；
   - elevation 后被吃：A 同时在 broken 与 superseded 里 → broken；
   - 多 bo 反复突破同一 pk → broken；
   - 非 pk 事件（无 `peak_idx`）不进结果；
   - `peakIdIndex(events)`：`instance_id → pk_id`。
   - `path2_web_ui/tests/render.chart.mainoption.spec.ts`：pk fixture 去 `state`，加 `ref_ids`；bo fixture 加 `ref_ids: { broken: ['pk_1#0'] }` 且**不带** `broken_peak_ids`；断言 pricePointData 里 pk 的 `state` 由合成得出、bo 的 `text === '[7]'`（7 = 对应 pk 的 `pk_id`）；新增「bo 被 nodeVisible 隐藏 / level 过滤掉时，pk 三态不变」；pk 判别子改 `peak_idx`（去掉 `state` 的 fixture 后仍被识别为 pk marker）。
2. **GREEN**：
   - `peakState.ts`：两个纯函数，注释写明这是 bo/pk 语义唯一落点（契约 C7）。
   - `chart.ts::computeEventData`：在 `filtered` 之前对入参 `events` 调 `derivePeakStates` / `peakIdIndex`；`isPk = typeof e.peak_idx === 'number'`；`state: isPk ? states.get(e.instance_id) ?? 'alive' : undefined`；bo 文本 `'[' + (ref_ids.broken ?? []).map(id => pkIds.get(id)).filter(n => n != null).join(',') + ']'`；删对 `e.state` / `e.broken_peak_ids` 的读取；相关注释同步（第 148-190 行区）。渲染器（`makeRenderPricePoint` / highlight / veil）按 `item.state` 分派的逻辑**不动**。
   - tooltip raw 平铺在 `path2_web_ui/src/render/visible.ts:206-213`：`Object.entries(ev)` 减去 SKIP 集（含 `child_refs`）。把 `'ref_ids'` 加进同一个 SKIP 集（一行），否则会以对象形式落进 raw 显示成 `[object Object]`。`stores/view.ts:44-47` 只读 `child_refs`，不用动。
3. 关卡：`npx vitest run`（新增全绿，其余与基线一致）+ `vue-tsc -b` + `vite build`。
4. **真跑实证**（必做）：`uv run python scripts/path2/run_path2_web.py` 起服务（端口见 `configs/path2_web.yaml`），playwright 打开 `http://localhost:<frontend_port>`，「打开历史」选最新 bb_pk 扫描、点 ABAT：
   - `window.__e2e.chartMain().getOption().series` 里 `price-points` 的 pk 项 `state` 分布含三态且 alive 非零；
   - 任一 bo 项 `text` 形如 `[n,...]` 且 n 与同图 ▽ 标签数字一致；
   - 网络响应里事件 dict 无 `broken_refs` 键、有 `ref_ids`。
   - 截图一张确认实心/空心/虚线三种 ▽ 与 bo 盒文本都在。完成后 `rm -rf .playwright-mcp/*`。
5. Commit：`feat(web-ui): pk 三态由 ref_ids 关系合成、bo 盒文本派生自 ref_ids+pk_id,删 state 读取`

---

## Task 6 · authoring skill 同步（review §6）

**文件**：`.claude/skills/authoring-path2-detector/{SKILL.md,reference.md}`、`.claude/skills/authoring-path2-app/{SKILL.md,design-heuristics.md}`。无测试，Reviewer 逐条核对与代码一致。

**6.1 过时事实（两处）**
- `authoring-path2-detector/reference.md` §4「**node 共享禁止**」段 → 改为：同一条流不可被 ≥2 node 绑定；同一 detector 的**不同**流各绑一个 node 是合法且标准的多流用法（`BODetector` bo/pk 即例）；不 emit gf 的 detector 共享同一流仍合法。
- `authoring-path2-app/design-heuristics.md` 第 44–45 行「产 gate failure 的 detector 共享更会被 gate_collector 直接拒绝(一 node 一实例)」→ 同上口径。

**6.2 设计规则**
- `authoring-path2-detector/reference.md` §2「继承契约」后新增小节「**因果封闭与引用**」：① 字段值必须在 `confirm_idx` 时刻可知；事件之间的关系（谁突破谁、谁吃掉谁）用 `ref_slots` 表达、由消费侧合成，不写成被引用方身上的结果字段（state / outcome 类），不存在「显示专用豁免」。② 事件 `yield` 即定稿；需要演化的工作量放 detector 私有结构，别复用事件对象（现存例外：`BODetector` elevation 抬价，勿新增）。③ 从 `ref_slots` 可派生的量（id 列表、计数）做 `@property`，不做平行字段。④ 无值用 `Optional`，不用 `0.0` 占位。
- `authoring-path2-detector/reference.md` §4 与 `SKILL.md` Step 5、`authoring-path2-app/SKILL.md`「多流 node 的 on_gate 归属」段：补原则「gf 归**本该诞生的那个事件所在的流**」+ 例子（`BODetector` 峰登记四类 gate 归 pk，`no_active_peak_broken` 归 bo）。
- `authoring-path2-app/SKILL.md`「多流 node 声明纪律」段：补「多流的省只有一层：同一 detect 调用只跑一次。detector 声明的每条流都必须有 node 认领（`PatternSpec` 构造期报错）；不想看某条流 → 仍建 node，`solve=False` + 前端隐藏 band，不是不建 node」。
- `authoring-path2-detector/SKILL.md`「多流写法」：加「多流 detector 不写 `event_cls`」。

**6.3 措辞同步**
- `authoring-path2-detector/SKILL.md` 第 115 行与第 183 行注释：`{槽名}_ref_ids` → `ref_ids`（`Tuple[(槽名, ids)]`，`ref_ids_of(槽名)` 取值）；补「引用槽字段本身不进 payload，下游只拿 ids」。
- `authoring-path2-app/SKILL.md`「多流 node 的 on_gate 归属」段与 `design-heuristics.md` 第 125–128 行 NodeSpec 字段表：「挂 collector 时报错」→「`PatternSpec` 构造期报错」；字段表加 `produces_stream` 一行。

Commit：`docs(skills): 多流 authoring 规则同步——全绑定/因果封闭/gate 归属/ref_ids 措辞,修两处过时事实`

---

## Task 7 · AI 上下文与 review 文档收口

1. 运行 `update-ai-context` skill，更新 `.claude/docs/modules/path2.md`、`path2_web.md`、`path2_apps.md`（它们目前对多流 / `ref_ids` / `solve` 只字未提）。
2. `docs/tmp/2026-09-01-multistream-spec-review.md` 末尾加「实施记录」：各 task 的 commit hash、对拍结果、A9 仍搁置。
3. Commit：`docs: 多流 review 修复实施记录 + AI 上下文刷新`

---

## 最终验证（holistic，Reviewer opus）

1. `uv run pytest tests -q`：通过数 ≥ 基线，失败集 ⊆ 基线预存失败集。
2. `cd path2_web_ui && npx vitest run && npx vue-tsc -b && npx vite build`：同上。
3. `grep -rn "_ref_ids\b" path2 path2_web path2_web_ui/src .claude/skills` → 仅允许出现在 `ref_ids` 字段名与历史文档；`grep -rn "\.state\b" path2 path2_web path2_web_ui/src` → 仅剩渲染器 `item.state`（合成值）。
4. 用 `/preview` 或扫描文件重测 payload：任一 bo 事件 dict 无嵌套事件 dict；事件 payload 总量相对 review 记录的 11.3 MB 明显下降（预期约 −40%）。
5. 对拍：`snapshot_before.json` vs `snapshot_after.json` 逐字一致（peak_vol_max 例外规则见 Task 4）。
6. 7 个 app `build_pattern(Params.default())` 全部可构造；只绑 bo 的实验 spec 在构造期被拒且信息说人话。

## 交付

批准后把本文件复制为 `docs/superpowers/plans/2026-09-02-multistream-review-fixes.md`（不执行），并给出新 session 粘贴命令。
