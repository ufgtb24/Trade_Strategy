# class_id 彻底清除（统一到 node_id）· 设计 spec

> 绑定权限文档。实施 plan 从本 spec 论证；冲突以本 spec 为准。
> 研究全文（四份，含全部 file:line 论证与裁定轨迹）：`docs/research/2026-08-14_classid-elimination-study/`（final_report.md 为准）。
> 本 spec 中所有项目内路径均相对 repo root。

## 0. 背景与目标

instance-id 重构 Task 4 把 `class_id` 的值从"event 子类声明的 tag（bo/tb 风格）"迁为 `event_cls.__name__`（Python 类名），导致类名泄漏到 web UI（入口 A 显示 `ThrowbackEventV1`）。用户裁定：**整个 repo 不再有 class_id 这个概念，身份统一到 node_id/instance_id 双轴**。agent team 研究结论（2026-08-14）：值得（无保留条件）、方案 A' 为最优、authoring 纯减负。

class_id 现存三源头（后端 18 文件 68 处 / 前端 4 文件 8 处全部收敛于此）：

| 源头 | 位置 | 处置 |
|---|---|---|
| `TopoNode.class_id` | `path2/dag/spec.py` | 删字段（全库零读者，零连带） |
| `GateFailure.class_id` | `path2/dag/gate_failure.py:65` | 删 class_id，加 `node_id`，gate_collector 注入 |
| `debug_break` class 参数 + class 门 | `path2/debug_ctx.py:79-81` + 30 埋点 | 四门→三门，删 |

## 1. 设计原则（binding）

1. **身份双轴**：`node_id`（结构位置，声明层）+ `instance_id`（实例唯一性，物化层）。`event_cls` 退回 Python 类型系统（`isinstance` 判别），**不进任何字符串契约**（序列化 / 过滤 / 分组 / 显示 / debug 门）。
2. **"彻底"判据**：变更后不得有任何字段 / 参数 / 环境变量 / 契约名再承担"类型-身份轴职能"（分组键 / 过滤键 / 归属键）。非身份字段合法（如 `gate_name`——判据名；`code_location`——行级指纹）。
3. **概念死亡边界 = 代码 + web 契约 + skill 文档三层**。skill 是 AI authoring 教学源，不清 = 概念复活通道。
4. **兼容性事实**：GateFailure 不落盘（serialize 零输出 failed_attempts，前端 gf 全来自 /diagnose 实时响应）→ 无 scan 文件兼容问题，零迁移。

## 2. 变更设计

### 2.1 TopoNode.class_id：删字段

`path2/dag/spec.py` 中 `TopoNode` 的 `class_id` 字段删除。已实证全库零读者（serialize_pattern 不输出、前端类型无此字段、引擎零引用）。dag_spec 层零代码改动（`NodeSpec` 无此字段）。

### 2.2 GateFailure：删 class_id → node_id

- `path2/dag/gate_failure.py`：`GateFailure` 删 `class_id` 字段；新增 `node_id: str = ''`（**带默认值**——13 生产 + 6 测试构造点全 kwargs 形态，零位置参数风险；先例：`code_location` 默认值字段 gate_failure.py:71-74）。docstring 同步。
- **atoms 构造点**：13 处 `class_id=XXX.__name__` kwarg 全删（breakout.py、throwback.py、throwback_v0/v1/v3.py；`_emit_tb_gate` 类 helper 同步）。
- **值注入（gate_collector per-node wrapper）**：`path2_web/gate_collector.py` `attach_and_collect` 改为 per-node 挂 wrapper：收到 gf 后 `collector.add(dataclasses.replace(gf, node_id=node.node_id))`。detector 作者零感知；链式兼容先例：throwback.py:299-307（detect 内层包装 → collector wrapper → collector.add）。
- **★共享防护（挂雷式延迟 raise）**：attach 循环内 `seen` dict by `id(detector)`；同一 detector 对象被 ≥2 node 引用 → 覆盖挂 `_boom` wrapper，该 detector **首条 gate failure 到达时** `raise RuntimeError`（文案含 detector 类名 + 修法："产 gate failure 的 detector 须一 node 一实例"）。
  - 零误杀：不 emit gf 的 detector（如 TrendSegmentDetector 合法共享）雷永不动（trend.py 零 on_gate 调用实证）。
  - 冒泡面已实证：engine.py 零 try/except 无损冒泡；scan.py:136-137 / eval_runner.py:117-118 `except Exception` per-symbol 兜底（不裸崩进程池）；api /diagnose 走 FastAPI 默认 500。**不引入专门异常类型**（现状 except Exception 已全覆盖）。eval 不豁免。
  - detach 复位：现有 finally detach 语义保持，`_boom`/wrapper 随 `on_gate = None` 复位，跨 symbol 无泄漏。
- **不实施**：spec 声明期禁令（研究记为可选增强）、哨兵值降级（已淘汰）。

### 2.3 debug：四门 → 三门

- `path2/debug_ctx.py`：删 class 门（:79-81）、`_read_class_id`、`DEBUG_EVENT_CLASS` 环境变量读取。门 = `_DEBUG_MODE ∧ bar∈range ∧ anchor_kind`。
- `debug_break` 签名删 `class_id` 参数；**30 个埋点**（throwback 系全部，bo/burst/trend 零埋点）删 `class_id=XXX.__name__` kwarg。
- 定位唯一性已实证：(bar, anchor_kind) 在 30 埋点单 pattern 形态下唯一命中（真理由：class 门区分度上限 = detector 粒度，(bar, anchor_kind) 恰达同一粒度；同 detector 内多出口埋点 class 门本就区分不了，靠 pause 行号）。
- **顺手修复双 bug**（d64083be 引入）：前端 view.ts:825 传 `event.node_id`（'tb'）→ 后端 class 门比 `'ThrowbackEventV1'` 恒 false → 右键 debug 三锚全不命中 + diagnose.py:215 过滤恒空。本变更删除 class 通道后两个 bug 随之消灭。

### 2.4 web 契约层（后端）

- `path2_web/diagnose.py`：
  - `TimePayload.all_classes` → **改名 `all_nodes`**，值 = `sorted({n.node_id for n in spec_nodes})`（替代 `event_cls.__name__`，:203）。
  - 过滤 `_class_ok`（:214-215）→ 按 `gf.node_id == query.node`。
  - `Query.event_class` 参数 → **改名 `node`**（scope=time 的载荷，types.ts:165 区域契约同步）。
- `path2_web/api.py`：scope=time 请求参数 `event_class` → `node`；`DEBUG_EVENT_CLASS` 设置通道删；`debug_enabled_classes`（:245）→ **改名 `debug_enabled_nodes`**（值已全是 node_id、前端零消费，改名保语义零破坏）。
- `path2_web/serialize.py`：`debug_enabled_classes`（:267-284）同步改名 `debug_enabled_nodes`。
- **诊断过滤链命名统一 node 语义**（lead 裁定，防名字残留成定时炸弹）：`all_classes`/`event_class`/`debug_enabled_classes` 及前端对应 props/store 字段（见 2.5）全部改为 node 命名，值域 = node_id。

### 2.5 前端

- `types.ts`：`TimePayload.all_classes`→`all_nodes`；`debug_enabled_classes`→`debug_enabled_nodes`；确认 EventDict 无 class_id（已无）。
- `FailedAttemptsCard.vue`：attempt 行显示 `a.class_id` → `a.node_id`；select filter 数据源 `allClasses/failedClasses/classOptions` → node 语义命名；props/emit `eventClass`/`update:eventClass` → `node`/`update:node`。
- `stores/view.ts`：`currentTimeEventClass` → node 语义命名（如 `currentDiagnoseNode`）；`triggerEventDebug` 的 getTimeDiagnose 调用**删 eventClass 实参**（第 7 参）；`anchorsOf`/tbAnchorProfile 保留（仍为锚点算 bar），不产出任何 class 字段。
- `DetailSidebar.vue`：debug 卡片 `debugTarget.className` → 显示 node_id；`onTimeEventClassChange` 等链上命名同步。
- `KlineChart.vue`：brush handler 透传的过滤态命名同步。
- 前端已完成的 node_id 化不动（anchorsOf 键、tbAnchorProfile child_refs 区分变体）。

### 2.6 文档 / 注释 / 残渣清理

- apps docstring 5 处过时 class_id 文案：bb_v0/v1/v3 各 `__init__.py` + `dag_spec.py`、`try_conplex_where/dag_spec.py:50`、`bottom_burst/dag_spec.py:60`。
- `gate_collector.py:10-12` 注释同步。
- `scripts/gate_burst_2x2.py:94`：`e.class_id` 运行必 AttributeError（实测），改 `e.node_id` 并验证脚本可跑。

### 2.7 skill 文档同步（概念死亡第三层，binding）

- `.claude/skills/authoring-path2-detector/reference.md`：重写 stale 节（:97-99 等仍在教已消灭的旧体系），删 class_id 教学内容；§4 补一句："**产 gate failure 的 detector 不可被多 node 共享（attach 侧会 raise）**"。
- `.claude/skills/diagnose-event/detectors/`：按类名组织的 2 份文件改按 node_id 组织（throwback.md / throwback_v3.md）。

## 3. 验收（binding）

1. **grep 清零锚**：`grep -rn "class_id" path2/ path2_web/ path2_apps/ path2_web_ui/src/ scripts/ .claude/skills/authoring-path2-detector/ .claude/skills/diagnose-event/` → **零命中**；`grep -n "__name__" path2/dag/gate_failure.py path2/debug_ctx.py path2_web/diagnose.py` → 零命中。
2. **后端**：全量 pytest 0 failed（baseline 0 failed / 2 skipped；受影响 24 测试文件约 107 处断言同步改后全绿）。
3. **前端三绿**：vitest（baseline 4 failed = sidebar-result-list pre-existing，其余全过）+ vue-tsc 0 error + build success。
4. **★右键 debug e2e**（真实数据 APCX）：右键 tb marker，entry/confirm/end 三锚触发 debug 断点命中（双 bug 修复的端到端验收）。
5. **入口 A e2e**：brush 时段查询卡片显示 `tb`（node_id）非 `ThrowbackEventV1`；下拉 filter 选项为 node_id 全集。
6. **新增测试**（TDD）：① 非法共享（同一产 gate detector 挂 2 node）真 emit → raise 含修法关键词；② 合法共享（Trend 类 detector 挂 2 node）→ 零行为差异；③ wrapper 注入：gf 进 collector 后 `node_id` == 所属 node。
7. skill 文档无 class_id 残留（含在验收 1 的 grep 范围内）。

## 4. 非目标

- spec 声明期共享禁令（可选增强，不实施）。
- eval 对 raise 的豁免（不做）。
- 共享 detector 机制本身（休眠特性）不动；`best_ever_v1` 分支不动。
- scan 结果文件 / fixture 无需任何迁移（gf 不落盘；APCX fixture 事件行本就无 class_id）。

## 5. 实施约束

- 分支：`instance-id-refactor`（延续未并 master；完成后 commit+push 该分支，禁开 PR——沿用既有交付约定）。
- 受影响面参考（coder-notes §5 全清单）：后端 ~12 文件、前端 ~6 文件、测试 24 文件 ~107 处、skill 2 份。
- 实施模型：implementer=sonnet / reviewer=opus（subagent-driven 既有约定）。
