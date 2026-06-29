# Marker Tooltip Cleanup — Design

**日期**：2026-06-29
**范围**：path2_web 前端，event marker 的 tooltip（`buildMarkerTooltipFormatter` + `resolveTooltipData`）
**不在范围**：K bar tooltip（`buildBarTooltipFormatter`，OHLC + 成交量八行）、DetailSidebar、后端 serialize.py

---

## 1. 背景与现状

K 线主图 / 副图上 event marker 的 tooltip 由 `chart.ts:buildMarkerTooltipFormatter` (chart.ts:748) 渲染，数据由 `visible.ts:resolveTooltipData` (visible.ts:87) 提供。当前实现把两段内容直接拼接：

- **clauses 段**：跨所有 role 收集该 `event_id` 的 ClauseWitness，逐行输出 `{cid}: {measured} {op} {threshold} {✓|✗}`
- **raw 段**：event dict 平铺，跳过固定字段（`class_id / event_id / start_idx / end_idx / source_tag / members`）

观察到的"杂乱"根因：

1. **clauses 与 raw 字段重复**：同一字段（如 `first_drought` / `distinct_pk`）在两段都出现，前者带阈值证据、后者裸值。
2. **无段头 / 无分组**：两段无视觉分隔，混排难辨。
3. **数字未截位**：浮点直接 `String(v)`，出现 `2.6378544926831706` 完整 IEEE754 精度。
4. **无身份信息**：tooltip 不展示 event 在 dag 中的位置（role）、时间范围、事件 id，无法快速跨 console / DetailSidebar 跳转。
5. **match 端点信息互斥**：marker 同时是 match 端点时（chart.ts:752-754），仅渲染 match 标签单行、吞掉 event 自身的诊断与属性。

---

## 2. 整治目标

**信息全保留 + 分组重排**。零信息损失，只动展示层；不影响后端、不动 K bar tooltip、不动 DetailSidebar。

---

## 3. 设计

### 3.1 整体结构

Marker tooltip 由 **可选顶行 + 三段** 组成，顺序固定：

```
[顶行] Match: <matchLabel(match_id)>      ← 仅 match 端点出现

── Identity ──
role: <role_id> [/ <role_id>...]            ← 多 role 用 / 分隔；零 role 时该行省略
time: <date_start> [→ <date_end>]           ← point event（start_idx==end_idx）退化为单日期
id:   <event_id>

── Clauses ──
<cid>: <measured> <op> <threshold> ✗    ← 失败置顶、加粗（HTML <b>...</b>）
<cid>: ...                              ← 失败行同上
<cid>: <measured> <op> <threshold> ✓    ← 满足在后、正常字重

── Attributes ──
<key>: <value>                                  ← 去重后剩余字段
...
```

**段头**：HTML 加粗段头 `Identity` / `Clauses` / `Attributes`（字号同正文，仅靠加粗与正文区分），前后各一道淡色横线 `<hr>`。`echarts` tooltip formatter 已用 `<br/>`（chart.ts:738），`<b>` / `<hr>` 同链路、无新依赖。

所有 tooltip 内容字号一致（即不做小字降权），段头与正文的视觉差异仅靠加粗 + 横线，参见 §3.2 "字号"。

**段省略规则**：

- 身份段恒存在（三字段从 event 本体推导，至少 `time` 和 `id` 有值）。
- 诊断段为空（event 在 `diag.roles` 任何 role 中都无 attr 行）→ 整段（含段头）不渲染。
- 属性段为空（去重后无剩余字段）→ 整段（含段头）不渲染。
- 顶行仅在 `params.data.match_id` 命中时出现。

**互斥 → 拼接**：chart.ts:752-754 的 `if (matchId) return matchLabel(matchId)` early-return 改为"先 match 顶行再 event 三段"。

### 3.2 身份段

三字段取值：

| 字段 | 取值方式 | 边界 |
|---|---|---|
| `role` | 反查 `diag.roles`：扫所有 role 的 `attr` 表，找哪些 role 的 `attr` 里有这条 `event_id` | 单 role → `role: bo_burst`；多 role → `role: bo_burst / tb`（`/` 分隔，单行）；零 role → 整行省略 |
| `time` | `bars[event.start_idx].date` 与 `bars[event.end_idx].date` | 区间 → `time: 2024-03-15 → 2024-03-30`；point（`start_idx == end_idx`） → `time: 2024-03-15` |
| `id` | event dict `event_id` 直读 | 恒有 → `id: burst_120_135` |

**class_id / source_tag**：默认不显示。理由：字面值已隐含在 `event_id` 前缀里（path2/stdlib/_ids.py:22-28 `span_id`），独立列出零信息增量。仅当 `source_tag != class_id`（即引擎已自动派生 `class_id0/class_id1`）时作为休眠能力激活的信号、单列显示。

**字号**：身份段三字段（含 `event_id`）与其他段同字号，不做小字降权处理。此规则与 §3.1 段头规则一致——整个 tooltip 仅有一种字号，区分靠加粗 + 横线 + 段头标签。

### 3.3 诊断段（Clauses）

**行格式**（保持现有结构 + 视觉强弱）：

```
<cid>: <measured> <op> <threshold> <mark>
```

- 失败：`<b>first_drought: 0 >= 20 ✗</b>`
- 满足：`vol_spike: 12.3456 >= 8 ✓`（正常字重）

**排序**：失败 ✗ 置顶、满足 ✓ 在后；同档内按 cid 在原 `diag.roles` 遍历到的顺序（稳定）。

**加粗**：HTML `<b>...</b>` 包整行。

**数字格式化**（`measured` 与 `threshold` 双向作用）：

```ts
function fmtNum(v: unknown): string {
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(4)
  return String(v)
}
```

- 整数（`0`, `2`, `20`） → 原样
- 浮点（`2.6378544926831706`） → `2.6379`
- 非数字（字符串 / 数组 / null） → `String(v)`

**跨 role 同 cid 冲突修复**：

visible.ts:94-96 当前是覆盖式写入：

```ts
for (const role of Object.values(diag.roles)) {
  const row = role.attr.find((r) => r.event_id === eventId)
  if (row) for (const [cid, w] of Object.entries(row.clauses))
    clauses[cid] = { ... }   // ← 后写覆盖前写
}
```

举例：event `burst_120_135` 同时被 `bo_burst` 和 `tb_burst` 两 role 用 `first_drought >= ?` 评估、阈值不同（20 vs 15），当前只见后遍历那个 role 版本。

**修复方案**：把 cid 提升为 `(cid, role)` 二元键，累积成数组。formatter 按 cid 分桶判断"是否多 role"：

- 单 role 出现的 cid：保持原行格式（不带 `(in: ...)` 后缀）
- 多 role 出现的 cid：每条单独一行，行末追加 `(in: <role_id>)`

`visible.ts:resolveTooltipData` 内部累积结构：

```ts
type ClauseRow = {
  cid: string
  role: string
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
}
// 累积为 ClauseRow[]，formatter 端做 multi-role 检测决定是否追加 (in: ...) 后缀
```

### 3.4 属性段（Raw, 去重后）

**去重粒度**：按字段名直接匹配。

```ts
const cidsInClauses = new Set(clauseRows.map(r => r.cid))
const SKIP = new Set(['class_id', 'event_id', 'start_idx', 'end_idx', 'source_tag', 'members'])
for (const [k, v] of Object.entries(event)) {
  if (SKIP.has(k)) continue
  if (cidsInClauses.has(k)) continue   // ← 新增：clauses 已引用的字段不再 raw 段出现
  raw[k] = v
}
```

**已知 limitation**：去重只看名字。`ClauseWitness`（path2/dag/result.py:25-31）只带 `satisfied / measured / op / threshold` 四字段，**不带 source field name**——后端 dump 无法还原"某条 clause 测的是哪个 raw 字段"。所以只能靠"detector 作者把 cid 名与字段名对齐"才能命中去重。

例：截图中 `vol_spike` clause 的 measured 字面是 BurstEvent 的 `max_bar_vol_ratio` 字段值，但 cid 名（`vol_spike`）≠ 字段名（`max_bar_vol_ratio`），名字层无法匹配 → tooltip 仍会同时出现 `vol_spike: 2.6379 >= 8 ✗` 与 `max_bar_vol_ratio: 2.6379`。这一局限**不在本次 fix 范围**，留待 detector 作者后续把 cid 命名与字段名对齐解决。

**数字格式化**：与诊断段 `fmtNum` 同函数，作用于 raw 段所有值。

**raw 段省略**：去重后 `raw` 对象为空 → 整段（含段头）不渲染。

### 3.5 改动落点

#### A. `path2_web_ui/src/render/visible.ts:resolveTooltipData`

**当前签名**（visible.ts:87-89）：

```ts
export function resolveTooltipData(
  eventId: string, diag: Diagnostics | null, events: EventDict[],
): { clauses: Record<...>; raw: Record<string, unknown> }
```

**新签名**：

```ts
export function resolveTooltipData(
  eventId: string,
  diag: Diagnostics | null,
  events: EventDict[],
  bars: Bar[],          // ← 新增：用于把 start_idx/end_idx 翻成日期
): {
  identity: {
    roles: string[]                 // 空数组 = 零 role
    dateStart: string               // bars[start_idx].date 或 '<idx>' 越界 fallback
    dateEnd: string | null          // null = point event（start_idx == end_idx）
    eventId: string
  }
  clauses: ClauseRow[]              // 见 §3.3
  raw: Record<string, unknown>      // 见 §3.4
}
```

**注**：`Bar` 类型从 `../types` 或 chart 模块 import；如果已有 type alias 走现有 path。

#### B. `path2_web_ui/src/render/chart.ts`

**`TooltipPayload` 接口**（chart.ts:17-20）扩展：

```ts
export interface TooltipClauseRow {
  cid: string; role: string
  measured: unknown; op: string | null; threshold: unknown
  satisfied: boolean
}
export interface TooltipPayload {
  identity: {
    roles: string[]
    dateStart: string; dateEnd: string | null
    eventId: string
  }
  clauses: TooltipClauseRow[]
  raw: Record<string, unknown>
}
```

**`buildMarkerTooltipFormatter`**（chart.ts:748-770）按 §3.1–§3.4 渲染：

1. 顶行：`params.data.match_id` 命中 → `Match: <matchLabel(match_id)>`，否则跳过
2. 身份段：`── Identity ──` + role / time / id（按 §3.2 规则）
3. 诊断段：按 `satisfied` 排序后渲染（失败置顶 + 加粗 + `<br/>` 分隔）；多 role 同 cid 时行末加 `(in: <role>)`；段空则省略段头
4. 属性段：按 §3.4 去重 + `fmtNum` 格式化；段空则省略段头

去掉 chart.ts:752-754 的 early-return。

#### C. `path2_web_ui/src/components/KlineChart.vue:tooltipResolver`

调用点（KlineChart.vue:68）追加 `bars`：

```ts
tooltipResolver: (id: string) => resolveTooltipData(
  id, diag.value, effectiveAnalysis.value?.events ?? [], bars,  // ← 新增 bars
),
```

`bars` 在 `KlineChart.vue` 当前作用域是否已可用，由 implementer 在编辑时确认；若没在该作用域，需要从同模块上游 props/state 取（不应需要新增网络请求或全局 store）。

---

## 4. 数据流

```
event marker hover
  ↓
echarts dispatch → buildMarkerTooltipFormatter(params)
  ↓                                 ↓
matchLabel(match_id)?         tooltipResolver(event_id)
  ↓                                 ↓
顶行字符串                  resolveTooltipData(event_id, diag, events, bars)
                                    ↓
                          { identity, clauses[], raw }
                                    ↓
                    formatter 拼接 → HTML 字符串 → ECharts 渲染
```

无新增数据来源、无新增网络请求；纯展示层重排 + 字段映射。

---

## 5. 边界 / 错误处理

| 情形 | 处理 |
|---|---|
| `diag === null`（discovery 阶段未 reify） | 身份段 / raw 段照常；clauses 段空 → 整段省略 |
| `bars[idx]` 索引越界（`start_idx` / `end_idx` ≥ `bars.length`） | `time:` 行 fallback 到原索引数字（`time: 120 → 135`）；不抛错 |
| event 在所有 role 的 attr 表都找不到（零 role） | identity 段 `role:` 行省略，`time` / `id` 正常 |
| 去重后 raw 段为空 | 整段（含段头）不渲染 |
| `source_tag === class_id` | 不展示 source_tag（沿用 §3.2 决定） |
| `event_id` 在 `events[]` 中找不到 | `resolveTooltipData` 返回空 `raw`，identity 仍能从 `event_id` 字符串本身推导（time/role 缺失走 fallback） |

**HTML 注入风险**：ECharts tooltip 按 HTML 解析 formatter 返回值。理论上 cid 名 / raw 字段名 / measured 字符串含 `<` 会被解析。当前路径：

- cid 名 / 字段名来自 Python detector 源码（受版本控制，不接受用户输入）
- measured / threshold 来自 `_jsonable`（serialize.py:25-32），可能是数字、字符串、元组、数组——detector 不会传 HTML 字符串

**风险评估为低**，本次不引入 escape；在 `buildMarkerTooltipFormatter` 顶部加一行注释提示"若未来 measured 引入字符串型且可能含 HTML，需在 fmtNum 旁边追加 escape"。

---

## 6. 测试计划

**vitest 单元测试**（扩展现有 `path2_web_ui/tests/visible.spec.ts` + `chart-helpers.spec.ts`）：

### `resolveTooltipData` 新增 case

1. 返回结构含 `identity / clauses / raw` 三键
2. `identity.roles` 单 role / 多 role / 零 role 三态
3. `identity.dateStart/End`：区间 vs point（`start_idx == end_idx` → `dateEnd === null`）两态
4. `identity` bars 越界 fallback 到索引数字字符串
5. `clauses` 排序：失败 ✗ 在前、满足 ✓ 在后
6. 多 role 同 cid：累积为多个 `ClauseRow`（不再覆盖式写入）
7. raw 去重：clauses cid 与 raw 字段名同名时 raw 那份消失
8. raw 数字格式化：整数原样 / 浮点截 4 位 / 非数字 `String(v)`

### `buildMarkerTooltipFormatter` 新增 case

1. match 端点：顶行（`Match: ...`） + 三段拼接（区别于现状的"仅 match 标签"）
2. 非 match 端点：仅三段（无顶行）
3. 失败行含 `<b>` 标签包裹
4. 段头存在性：clauses 段为空 → 段头消失；raw 段为空 → 段头消失
5. 单 role clauses 行不带 `(in: <role>)`，多 role 才带

### `buildBarTooltipFormatter` 回归

现有 8 case（chart-helpers.spec.ts:169-225）全部保留，期望零回归（本设计不动 K bar tooltip）。

### Playwright e2e（视觉回归）

构造一个 burst 命中场景，把整治后的 tooltip 截图作为视觉回归基线。fixture 是否复用现有 e2e 资源由 implementer 在写 plan 时确认。

---

## 7. 验收标准

- vitest 全部测试绿（新增 + 现有零回归）
- `vue-tsc` 类型检查绿
- `pnpm build` 绿
- 在真实数据（如 path2 主线 dag_spec、6048 pkl）上人工跑通 web UI：
  - 截图 7 行 tooltip → 整治后变为 9 行（身份 3 + 诊断 3 + 属性 2，含 2 段头）
  - 失败 clause 加粗显示
  - 数字截到 4 位小数
  - hover match 端点 marker → 既看到 match 标签又看到 event 三段
- K bar tooltip 完全不变

---

## 8. 已知 Limitations / Out of Scope

- **cid 名 ↔ 字段名失配时无法去重**（§3.4）：`ClauseWitness` 不带 source field name，靠名字硬匹配。`vol_spike ↔ max_bar_vol_ratio` 类失配需 detector 作者改 cid 名解决，不在本次范围。
- **K bar tooltip 不动**：本次只整治 marker tooltip。
- **DetailSidebar 不动**：tooltip 是悬停层；DetailSidebar 是完整列表层，二者职责分离不调整。
- **后端 serialize.py 不动**：所有改动在前端展示层。
- **`source_tag != class_id` 的 UI 升级**：当前 dag_spec 共享单实例，`source_tag === class_id` 恒成立 → tooltip 不展示 source_tag 行。引擎已具备自动派生能力（[[project_path2_auto_source_tag]]），未来 dag_spec 出现多实例时此条会自动激活；不需要现在写代码、只需 §3.2 已给出的条件渲染逻辑。
- **HTML escape**：当前 measured 类型受控，不引入 escape；预留注释。

---

## 9. 参考

- `path2_web_ui/src/render/chart.ts:705-770`（buildBarTooltipFormatter + buildMarkerTooltipFormatter）
- `path2_web_ui/src/render/visible.ts:85-103`（resolveTooltipData）
- `path2_web_ui/src/components/KlineChart.vue:68`（tooltipResolver 调用点）
- `path2_web_ui/src/types.ts:24-27`（ClauseWitness 前端类型）
- `path2/dag/result.py:24-33`（ClauseWitness 后端定义）
- `path2/atoms/breakout.py:69-104`（BurstEvent 字段示例）
- `path2_web/serialize.py:36-53,105-118`（event dict 序列化）
- `path2/stdlib/_ids.py:22-28`（span_id / event_id 命名规则）
