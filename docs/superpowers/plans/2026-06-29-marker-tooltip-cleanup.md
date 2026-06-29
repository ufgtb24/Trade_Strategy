# Marker Tooltip Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 event marker tooltip 重排为 `身份 / 诊断 / 属性` 三段 + 可选 match 顶行；失败 clause 置顶 + 加粗；浮点统一 4 位小数；跨 role 同 cid 不再覆盖；clauses 已引用字段从 raw 段去重；marker 是 match 端点时同时展示 match 归属与 event 详情（不再互斥）。

**Architecture:** 仅前端展示层重排。`visible.ts:resolveTooltipData` 重写为新签名（新增 `bars` 入参）+ 新返回结构（`identity / clauses[] / raw`）；`chart.ts:TooltipPayload` 接口扩展为三段；`chart.ts:buildMarkerTooltipFormatter` 重写渲染逻辑（含 `fmtNum` 4 位小数工具）；`KlineChart.vue:68` 调用点传 `bars.value`。

**Tech Stack:** TypeScript / Vue 3 / ECharts / vitest

**Spec:** `docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md`

## Global Constraints

- 工作目录：仓库根 `/home/yu/PycharmProjects/Trade_Strategy-vol`，所有命令前缀 `cd path2_web_ui &&` 进入前端子模块
- 包管理：`pnpm`（仓库已有 lockfile）
- 测试命令：`pnpm test --run <pattern>` （`--run` = 非 watch 模式）
- 类型检查：`pnpm vue-tsc --noEmit`
- 构建：`pnpm build`
- Dev server：从仓库根 `uv run python scripts/run_path2_web.py`（CLAUDE.md 入口脚本规则，无 argparse）
- 不动后端 (`path2_web/`)、K bar tooltip (`buildBarTooltipFormatter`)、DetailSidebar
- 不引入 HTML escape（spec §5 风险评估为低）
- 注释中文、commit message 中文 + 末尾 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer
- 不使用 `git --no-verify` / `--amend` / `--no-gpg-sign`；hook 失败修根因后再 commit
- 浮点格式化统一调用 `fmtNum`（见 Task 1 Step 8 内置实现）
- Playwright 卫生：使用过 playwright MCP 的回合，task 收尾时 `rm -rf .playwright-mcp/*`（保留目录本身）

---

## Task 1: 全量生产改动 + 单元测试同步

> 本 task 同时改 3 个生产文件 + 3 个测试文件。原因：`visible.ts:resolveTooltipData` 与 `chart.ts:TooltipPayload` 通过 `KlineChart.vue:68` 调用点强耦合，分拆任一文件都会导致 `vue-tsc` 中间态失败、违反"每 task 可独立绿"。本 task 内部按 TDD + 增量绿顺序推进 step。

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（接口 chart.ts:17-20；formatter chart.ts:748-770）
- Modify: `path2_web_ui/src/render/visible.ts`（resolveTooltipData visible.ts:85-103）
- Modify: `path2_web_ui/src/components/KlineChart.vue`（调用点 KlineChart.vue:68）
- Modify: `path2_web_ui/tests/visible.spec.ts`（resolveTooltipData describe 块 tests/visible.spec.ts:190-219）
- Modify: `path2_web_ui/tests/chart-helpers.spec.ts`（buildMarkerTooltipFormatter describe 块 tests/chart-helpers.spec.ts:225-251）
- Modify: `path2_web_ui/tests/chart.spec.ts`（D2 tooltipResolver describe 块 tests/chart.spec.ts:365-448）

**Interfaces:**

Produces（供 Task 2 真实数据消费的 API）：

```ts
// chart.ts 顶部新增类型
export interface TooltipClauseRow {
  cid: string
  role: string
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
}

export interface TooltipPayload {
  identity: {
    roles: string[]                 // 空数组 = 零 role（attr 找不到）
    dateStart: string               // bars[start_idx].date；越界 fallback 到 String(start_idx)
    dateEnd: string | null          // null = point event (start_idx == end_idx)
    eventId: string
  }
  clauses: TooltipClauseRow[]       // 已排序（失败 ✗ 在前、满足 ✓ 在后）
  raw: Record<string, unknown>      // 已去重（SKIP 集 + clauses 已引用 cid）
}

// visible.ts 签名
export function resolveTooltipData(
  eventId: string,
  diag: Diagnostics | null,
  events: EventDict[],
  bars: Bar[],
): TooltipPayload
```

---

### Step 1: 重写 visible.spec.ts 的 resolveTooltipData describe 块

- [ ] 删除 `path2_web_ui/tests/visible.spec.ts` 第 190-219 行整段 `describe('resolveTooltipData', ...)` 块，替换为下面内容（保持文件末尾换行）：

```ts
describe('resolveTooltipData', () => {
  const bars: Bar[] = [
    { date: '2024-03-01', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-02', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-03', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-04', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-05', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-06', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
  ]
  const events: EventDict[] = [
    { class_id: 'trend', event_id: 'd1', start_idx: 0, end_idx: 5, source_tag: 'trend0', drawdown: 0.42 } as any,
    { class_id: 'burst', event_id: 'b1', start_idx: 1, end_idx: 1, source_tag: 'burst', count: 3, first_drought: 0, members: [{}, {}] } as any,
    { class_id: 'burst', event_id: 'b2', start_idx: 2, end_idx: 4, source_tag: 'burst', count: 5, max_bar_vol_ratio: 2.6378544926831706 } as any,
  ]
  const diag: Diagnostics = {
    symbol: 'X', pattern_id: 'p', note: '',
    roles: {
      down: {
        attr: [{ event_id: 'd1', start_idx: 0, end_idx: 5,
          clauses: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } }],
        rel: [],
      },
      bo_burst: {
        attr: [{ event_id: 'b1', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: false, measured: 0, op: '>=', threshold: 20 },
            count: { satisfied: true, measured: 3, op: '>=', threshold: 2 },
          } }],
        rel: [],
      },
      tb_burst: {
        attr: [{ event_id: 'b1', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: true, measured: 0, op: '>=', threshold: 0 },
          } }],
        rel: [],
      },
    },
  }

  it('返回结构含 identity / clauses / raw 三键', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(Object.keys(r).sort()).toEqual(['clauses', 'identity', 'raw'])
  })

  it('identity.roles 单 role 时返回单元素数组', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.roles).toEqual(['down'])
  })

  it('identity.roles 多 role 时返回多元素数组（按 diag.roles 插入顺序）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    expect(r.identity.roles).toEqual(['bo_burst', 'tb_burst'])
  })

  it('identity.roles 零 role 时返回空数组', () => {
    const r = resolveTooltipData('b2', diag, events, bars)
    expect(r.identity.roles).toEqual([])
  })

  it('identity 区间事件 dateStart/End 均填', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe(null)   // d1 start_idx=0, end_idx=5；不,改成 b2 测试区间(2..4)
  })

  it('identity point 事件 dateEnd 为 null', () => {
    const r = resolveTooltipData('b1', diag, events, bars)   // b1 start_idx=end_idx=1
    expect(r.identity.dateStart).toBe('2024-03-02')
    expect(r.identity.dateEnd).toBe(null)
  })

  it('identity 区间事件 dateEnd 为 end_idx 对应日期', () => {
    const r = resolveTooltipData('b2', diag, events, bars)   // b2 start_idx=2, end_idx=4
    expect(r.identity.dateStart).toBe('2024-03-03')
    expect(r.identity.dateEnd).toBe('2024-03-05')
  })

  it('identity bars 越界时 fallback 到原索引字符串', () => {
    const shortBars: Bar[] = [bars[0]]
    const r = resolveTooltipData('d1', diag, events, shortBars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('5')   // end_idx=5 越界
  })

  it('identity.eventId 直返参数', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.eventId).toBe('d1')
  })

  it('clauses 失败 ✗ 排在满足 ✓ 之前', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const sats = r.clauses.map((c) => c.satisfied)
    const firstSat = sats.indexOf(true)
    const lastUnsat = sats.lastIndexOf(false)
    expect(lastUnsat).toBeLessThan(firstSat)
  })

  it('clauses 多 role 同 cid 各保留一行（不覆盖）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const firstDroughtRows = r.clauses.filter((c) => c.cid === 'first_drought')
    expect(firstDroughtRows.length).toBe(2)   // bo_burst 一条 + tb_burst 一条
    const roles = firstDroughtRows.map((c) => c.role).sort()
    expect(roles).toEqual(['bo_burst', 'tb_burst'])
    const thresholds = firstDroughtRows.map((c) => c.threshold).sort()
    expect(thresholds).toEqual([0, 20])
  })

  it('clauses 单 role cid 只有一条', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const countRows = r.clauses.filter((c) => c.cid === 'count')
    expect(countRows.length).toBe(1)
    expect(countRows[0].role).toBe('bo_burst')
  })

  it('raw 排除 SKIP 集（class_id/event_id/start_idx/end_idx/source_tag/members）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    expect('class_id' in r.raw).toBe(false)
    expect('event_id' in r.raw).toBe(false)
    expect('start_idx' in r.raw).toBe(false)
    expect('end_idx' in r.raw).toBe(false)
    expect('source_tag' in r.raw).toBe(false)
    expect('members' in r.raw).toBe(false)
  })

  it('raw 去重 clauses 已引用 cid（cid 名 ↔ 字段名命中时移除 raw 那份）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    // b1 字段含 count + first_drought；diag 里 bo_burst 也评估 first_drought + count
    expect('first_drought' in r.raw).toBe(false)
    expect('count' in r.raw).toBe(false)
  })

  it('raw 保留 clauses 未引用的字段', () => {
    const r = resolveTooltipData('b2', diag, events, bars)
    // b2 不在任何 role 的 attr 表 → clauses 为空 → raw 保留全部非 SKIP 字段
    expect(r.raw.count).toBe(5)
    expect(r.raw.max_bar_vol_ratio).toBeCloseTo(2.6378544926831706, 10)
  })

  it('未知 event_id → 空 clauses / 空 raw / identity 仅 eventId 有值', () => {
    const r = resolveTooltipData('zzz', diag, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.raw).toEqual({})
    expect(r.identity.eventId).toBe('zzz')
    expect(r.identity.roles).toEqual([])
  })

  it('diag === null → 空 clauses，identity / raw 正常', () => {
    const r = resolveTooltipData('d1', null, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.identity.eventId).toBe('d1')
    expect(r.identity.roles).toEqual([])   // 无 diag 无 role
    expect(r.raw.drawdown).toBe(0.42)
  })
})
```

注：上述 `'identity 区间事件 dateStart/End 均填'` case 名沿用，但断言以 b2 / b1 分别覆盖区间 vs point；保留三条独立 case 区分。

---

### Step 2: 调整修复上一步的 case 误配

- [ ] 上一步 `'identity 区间事件 dateStart/End 均填'` 这条 case 名误用 d1 测，但 d1 是区间事件（start=0, end=5），dateEnd 应 = `'2024-03-06'`，不是 null。修正这条 case：

将 `it('identity 区间事件 dateStart/End 均填', ...)` 块替换为：

```ts
  it('identity 区间事件 dateStart/End 均填日期', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('2024-03-06')
  })
```

---

### Step 3: 跑 visible.spec.ts 确认红

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/visible.spec.ts`
- [ ] 预期：`resolveTooltipData` 块全部 case 失败（旧实现签名不匹配、返回结构不同）；文件其它块（unrelated 的 isolatedNodeIds / deriveTagMap 等）应仍绿。
- [ ] 若 unrelated 块也红，停下来 diagnose：你的 Step 1 编辑是否动到了 describe 块外的内容？

---

### Step 4: 扩展 chart.ts:TooltipPayload 接口

- [ ] 编辑 `path2_web_ui/src/render/chart.ts`，将第 10-20 行（`TooltipClause` + `TooltipPayload` 两接口）替换为：

```ts
export interface TooltipClauseRow {
  cid: string
  role: string
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
}

export interface TooltipPayload {
  identity: {
    roles: string[]
    dateStart: string
    dateEnd: string | null
    eventId: string
  }
  clauses: TooltipClauseRow[]
  raw: Record<string, unknown>
}
```

- [ ] 注意：原 `TooltipClause` 接口被删除（不再需要）；如果文件其他位置 import 了 `TooltipClause`（按 spec 推断只有 chart.ts 内部用），grep 确认后清理：

```bash
cd path2_web_ui && grep -rn "TooltipClause\b" src/ tests/
```

- [ ] 若 grep 命中 `TooltipClause` 引用，将它们改为 `TooltipClauseRow` 或直接消除依赖（视上下文）。

---

### Step 5: 重写 visible.ts:resolveTooltipData

- [ ] 编辑 `path2_web_ui/src/render/visible.ts`。先在文件顶部 import 区追加（如果还没引入）：

```ts
import type { TooltipPayload, TooltipClauseRow } from './chart'
import type { Bar } from '../types'   // 若 Bar 类型已在其他位置 import 或 visible.ts 不需要它，请按现有导入结构调整
```

- [ ] 将 visible.ts:85-103 整段 `resolveTooltipData` 函数（含文档注释）替换为：

```ts
/** tooltip 数据组装（纯）：
 *  - identity：role 反查 diag.roles（多 role 时各保留）；时间 = bars[idx].date，point 时 dateEnd=null；
 *              bars 越界 fallback 到 String(idx)
 *  - clauses：跨 role 累积为 ClauseRow[]，按 satisfied 排序（失败 ✗ 在前）
 *  - raw：event dict 平铺，去掉 SKIP 集 + clauses 已引用 cid
 *  spec 见 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md */
export function resolveTooltipData(
  eventId: string,
  diag: Diagnostics | null,
  events: EventDict[],
  bars: Bar[],
): TooltipPayload {
  // ── clauses 累积（不覆盖；多 role 同 cid 各保留）─────────────────────────
  const clauses: TooltipClauseRow[] = []
  const roles: string[] = []
  if (diag) {
    for (const [roleId, role] of Object.entries(diag.roles)) {
      const row = role.attr.find((r) => r.event_id === eventId)
      if (!row) continue
      roles.push(roleId)
      for (const [cid, w] of Object.entries(row.clauses)) {
        const witness = w as ClauseWitness
        clauses.push({
          cid, role: roleId,
          measured: witness.measured, op: witness.op, threshold: witness.threshold,
          satisfied: witness.satisfied,
        })
      }
    }
  }
  // 排序：失败 ✗ (satisfied=false) 在前；同档稳定保序
  clauses.sort((a, b) => Number(a.satisfied) - Number(b.satisfied))

  // ── identity 组装 ──────────────────────────────────────────────────────
  const ev = events.find((e) => e.event_id === eventId)
  const startIdx = (ev?.start_idx as number | undefined) ?? -1
  const endIdx = (ev?.end_idx as number | undefined) ?? -1
  const dateStart = bars[startIdx]?.date ?? String(startIdx)
  const dateEnd = startIdx === endIdx ? null : (bars[endIdx]?.date ?? String(endIdx))

  // ── raw 平铺 + 去重 ─────────────────────────────────────────────────────
  const cidsInClauses = new Set(clauses.map((c) => c.cid))
  const SKIP = new Set(['class_id', 'event_id', 'start_idx', 'end_idx', 'source_tag', 'members'])
  const raw: Record<string, unknown> = {}
  if (ev) for (const [k, v] of Object.entries(ev)) {
    if (SKIP.has(k)) continue
    if (cidsInClauses.has(k)) continue
    raw[k] = v
  }

  return {
    identity: { roles, dateStart, dateEnd, eventId },
    clauses,
    raw,
  }
}
```

- [ ] 检查文件其他位置是否还有对 `resolveTooltipData` 旧返回结构的引用（grep `r.clauses` / `r.raw` / `resolveTooltipData`），按需修补 import。

---

### Step 6: 同步 KlineChart.vue:68 调用点

- [ ] 编辑 `path2_web_ui/src/components/KlineChart.vue` 第 68 行：

旧：
```ts
      tooltipResolver: (id: string) => resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? []),
```

新：
```ts
      tooltipResolver: (id: string) => resolveTooltipData(id, diag.value, effectiveAnalysis.value?.events ?? [], bars.value),
```

- [ ] 确认 `bars` 在 KlineChart.vue 第 19 行已有定义 (`const bars = ref<Bar[]>([])`)，无须额外 import。

---

### Step 7: 跑 visible.spec.ts 确认绿

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/visible.spec.ts`
- [ ] 预期：`resolveTooltipData` 全部新 case 通过；文件其他块零回归。
- [ ] 若仍红，diagnose：失败 case 名 → 比对 Step 5 实现逻辑 → 修正。

---

### Step 8: 重写 chart.ts:buildMarkerTooltipFormatter

- [ ] 编辑 `path2_web_ui/src/render/chart.ts` 第 742-770 行（含文档注释）整段 `buildMarkerTooltipFormatter` 函数，替换为：

```ts
/**
 * Marker tooltip formatter (series-level item-trigger)。
 * 三段结构 + 可选 match 顶行：
 *   - 顶行 (仅 params.data.match_id 命中)：Match: {matchLabel(id)}
 *   - 段 1 Identity：role / time / id
 *   - 段 2 Clauses：失败 ✗ 置顶 + 加粗；多 role 同 cid 行末加 (in: <role>)
 *   - 段 3 Attributes：raw（已去重）
 *
 * 段空时省略段头；身份段恒存在但 role 行可省。
 * HTML：使用 <br/> <b> <hr>（echarts tooltip formatter 支持）。
 * 注：当前 measured 类型受控（数字 / 字符串 / 元组），不引入 HTML escape；
 *     未来若 detector 引入用户输入字符串型 measured 且可能含 HTML，
 *     需在 fmtNum 旁追加 escape 步骤。
 * spec 见 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md
 */
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
  matchLabel: ((matchId: string) => string | null) | undefined,
) {
  return (params: { data?: { event_id?: string; match_id?: string } } | null): string => {
    const data = params?.data
    if (!data) return ''
    const lines: string[] = []

    // ── 顶行：match 归属 ─────────────────────────────────────────────────
    const matchId = data.match_id
    if (matchId && matchLabel) {
      const ml = matchLabel(matchId)
      if (ml) lines.push(`Match: ${ml}`)
    }

    // ── event 三段 ──────────────────────────────────────────────────────
    const eventId = data.event_id
    if (eventId && tooltipResolver) {
      const { identity, clauses, raw } = tooltipResolver(eventId)

      // 段 1 Identity
      const idBody: string[] = []
      if (identity.roles.length > 0) idBody.push(`role: ${identity.roles.join(' / ')}`)
      const timeStr = identity.dateEnd == null
        ? `time: ${identity.dateStart}`
        : `time: ${identity.dateStart} → ${identity.dateEnd}`
      idBody.push(timeStr)
      idBody.push(`id:   ${identity.eventId}`)
      if (lines.length > 0) lines.push('<hr/>')
      lines.push('<b>Identity</b>')
      lines.push(...idBody)

      // 段 2 Clauses（失败已置顶；多 role 同 cid 行末加 (in: <role>)）
      if (clauses.length > 0) {
        const cidCounts: Record<string, number> = {}
        for (const c of clauses) cidCounts[c.cid] = (cidCounts[c.cid] ?? 0) + 1
        const clauseLines = clauses.map((c) => {
          const opStr = c.op != null ? ` ${c.op} ${fmtNum(c.threshold)}` : ''
          const mark = c.satisfied ? '✓' : '✗'
          const inSuffix = cidCounts[c.cid] > 1 ? ` (in: ${c.role})` : ''
          const body = `${c.cid}: ${fmtNum(c.measured)}${opStr} ${mark}${inSuffix}`
          return c.satisfied ? body : `<b>${body}</b>`
        })
        lines.push('<hr/>')
        lines.push('<b>Clauses</b>')
        lines.push(...clauseLines)
      }

      // 段 3 Attributes（raw 已去重）
      const rawEntries = Object.entries(raw)
      if (rawEntries.length > 0) {
        lines.push('<hr/>')
        lines.push('<b>Attributes</b>')
        for (const [k, v] of rawEntries) lines.push(`${k}: ${fmtNum(v)}`)
      }
    }

    return lines.join('<br/>')
  }
}

/** 浮点统一 4 位小数；整数 / 非数字原样 String 化。 */
function fmtNum(v: unknown): string {
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(4)
  return String(v)
}
```

- [ ] 注意：函数末尾 `fmtNum` 是新增的模块级辅助函数（非 export），与 `buildMarkerTooltipFormatter` 同文件。

---

### Step 9: 跑 vue-tsc 确认编译绿

- [ ] 运行：`cd path2_web_ui && pnpm vue-tsc --noEmit`
- [ ] 预期：零类型错误（旧 `TooltipClause` 被替换为 `TooltipClauseRow`；旧 `TooltipPayload.clauses` 由 Record 改为 Array，所有消费点已同步）。
- [ ] 若报错，diagnose：是否有遗漏的 import / 类型注解；修正后重跑直至绿。

---

### Step 10: 重写 chart-helpers.spec.ts 的 buildMarkerTooltipFormatter describe 块

- [ ] 编辑 `path2_web_ui/tests/chart-helpers.spec.ts` 第 225-251 行（含 import 行 + describe 块），替换为：

```ts
import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { TooltipPayload } from '../src/render/chart'

describe('buildMarkerTooltipFormatter', () => {
  const emptyPayload: TooltipPayload = {
    identity: { roles: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
    clauses: [],
    raw: {},
  }

  it('非 match 端点 + 非空 payload 渲染身份段 + 段头 Identity', () => {
    const resolver = (_eid: string): TooltipPayload => emptyPayload
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('<b>Identity</b>')
    expect(html).toContain('role: bo_burst')
    expect(html).toContain('time: 2024-03-15')
    expect(html).toContain('id:   b1')
  })

  it('match 端点 + event 信息：顶行 + 三段拼接（不再互斥）', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { roles: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [{ cid: 'first_drought', role: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false }],
      raw: { count: 2 },
    })
    const matchLabel = (id: string) => `MATCH:${id}`
    const fmt = buildMarkerTooltipFormatter(resolver, matchLabel)
    const html = fmt({ data: { event_id: 'b1', match_id: 'm1' } })
    expect(html).toContain('Match: MATCH:m1')
    expect(html).toContain('<b>Identity</b>')
    expect(html).toContain('<b>Clauses</b>')
    expect(html).toContain('<b>Attributes</b>')
  })

  it('失败 clause 用 <b>...</b> 加粗', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { roles: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'first_drought', role: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false },
        { cid: 'count', role: 'bo_burst', measured: 3, op: '>=', threshold: 2, satisfied: true },
      ],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('<b>first_drought: 0 >= 20 ✗</b>')
    expect(html).toContain('count: 3 >= 2 ✓')
    expect(html).not.toContain('<b>count:')   // 满足行不加粗
  })

  it('浮点截到 4 位小数（measured 与 threshold 双向）', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { roles: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'vol_spike', role: 'bo_burst',
          measured: 2.6378544926831706, op: '>=', threshold: 8, satisfied: false },
      ],
      raw: { max_bar_vol_ratio: 2.6378544926831706 },
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('2.6379')   // measured 截位
    expect(html).not.toContain('2.6378544926831706')   // 原始精度不应出现
    expect(html).toContain('max_bar_vol_ratio: 2.6379')   // raw 段也截位
  })

  it('多 role 同 cid 行末加 (in: <role>)', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { roles: ['bo_burst', 'tb_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'first_drought', role: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false },
        { cid: 'first_drought', role: 'tb_burst', measured: 0, op: '>=', threshold: 0, satisfied: true },
        { cid: 'count', role: 'bo_burst', measured: 3, op: '>=', threshold: 2, satisfied: true },
      ],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('first_drought: 0 >= 20 ✗ (in: bo_burst)')
    expect(html).toContain('first_drought: 0 >= 0 ✓ (in: tb_burst)')
    expect(html).toContain('count: 3 >= 2 ✓')
    expect(html).not.toContain('count: 3 >= 2 ✓ (in:')   // 单 role 不加后缀
  })

  it('零 role 时 identity.role 行省略', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { roles: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('role:')
    expect(html).toContain('time: 2024-03-15')
    expect(html).toContain('id:   b1')
  })

  it('point 事件 time 单日期；区间事件 time 带箭头', () => {
    const resolverPoint = (_eid: string): TooltipPayload => ({
      identity: { roles: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [], raw: {},
    })
    const resolverRange = (_eid: string): TooltipPayload => ({
      identity: { roles: [], dateStart: '2024-03-15', dateEnd: '2024-03-30', eventId: 'b1' },
      clauses: [], raw: {},
    })
    expect(buildMarkerTooltipFormatter(resolverPoint, undefined)({ data: { event_id: 'b1' } }))
      .toContain('time: 2024-03-15')
    expect(buildMarkerTooltipFormatter(resolverPoint, undefined)({ data: { event_id: 'b1' } }))
      .not.toContain('→')
    expect(buildMarkerTooltipFormatter(resolverRange, undefined)({ data: { event_id: 'b1' } }))
      .toContain('time: 2024-03-15 → 2024-03-30')
  })

  it('clauses 段为空时段头 Clauses 不渲染', () => {
    const fmt = buildMarkerTooltipFormatter((_eid) => emptyPayload, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('<b>Clauses</b>')
  })

  it('raw 段为空时段头 Attributes 不渲染', () => {
    const fmt = buildMarkerTooltipFormatter((_eid) => emptyPayload, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('<b>Attributes</b>')
  })

  it('match 端点但 matchLabel 返回 null 时不渲染顶行', () => {
    const resolver = (_eid: string): TooltipPayload => emptyPayload
    const matchLabel = (_id: string) => null
    const fmt = buildMarkerTooltipFormatter(resolver, matchLabel)
    const html = fmt({ data: { event_id: 'b1', match_id: 'm1' } })
    expect(html).not.toContain('Match:')
    expect(html).toContain('<b>Identity</b>')   // 但 event 三段仍渲染
  })

  it('params 为 null 或 data 缺失返回空串', () => {
    const fmt = buildMarkerTooltipFormatter(undefined, undefined)
    expect(fmt(null)).toBe('')
    expect(fmt({ data: undefined })).toBe('')
  })
})
```

---

### Step 11: 跑 chart-helpers.spec.ts 确认绿

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/chart-helpers.spec.ts`
- [ ] 预期：`buildBarTooltipFormatter` 8 个旧 case 全部仍绿（K bar tooltip 未动）；`buildMarkerTooltipFormatter` 11 个新 case 全部通过。
- [ ] 若 K bar tooltip 测试红，立即停下来：你在 Step 8 是否误改了 `buildBarTooltipFormatter`？

---

### Step 12: 重写 chart.spec.ts D2 块的 stubResolver

- [ ] 编辑 `path2_web_ui/tests/chart.spec.ts` 第 365-448 行 `describe('buildKlineOption — D2 tooltipResolver', ...)` 整块，替换为：

```ts
// ── D2: tooltipResolver ───────────────────────────────────────────────────────
// 全局 tooltip = axis-trigger bar formatter (buildBarTooltipFormatter)
// marker 的 event/clause 信息 → 各 marker series 的 series-level tooltip.formatter
// (来自 buildMarkerTooltipFormatter)。
// 2026-06-29 整治后：TooltipPayload 结构改为 identity / clauses[] / raw 三段。
describe('buildKlineOption — D2 tooltipResolver', () => {
  const baseInput = makeInput('detected', roleColors)

  const stubResolver = (eventId: string) => ({
    identity: { roles: ['bo_burst'], dateStart: '2024-01-01', dateEnd: null, eventId },
    clauses: [
      { cid: 'clause_a', role: 'bo_burst', measured: 42, op: '>=', threshold: 10, satisfied: true },
      { cid: 'clause_b', role: 'bo_burst', measured: 3,  op: '<',  threshold: 5,  satisfied: true },
    ],
    raw: {
      foo: 'bar',
      vol: 1.23456,
    } as Record<string, unknown>,
  })

  it('global tooltip is axis-trigger (bar formatter) regardless of tooltipResolver', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const tt = opt.tooltip as any
    expect(tt.trigger).toBe('axis')
    expect(typeof tt.formatter).toBe('function')
  })

  it('marker series tooltip is undefined when tooltipResolver not provided', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    expect(points.tooltip).toBeUndefined()
  })

  it('marker series tooltip.formatter exists when tooltipResolver provided', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    expect(points.tooltip).toBeDefined()
    expect(typeof points.tooltip.formatter).toBe('function')
  })

  it('marker series formatter returns identity + clauses content when params has event_id', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    const result: string = formatter({ data: { event_id: 'bo9' } })
    expect(result).toContain('Identity')
    expect(result).toContain('role: bo_burst')
    expect(result).toContain('Clauses')
    expect(result).toContain('clause_a')
    expect(result).toContain('42')
    expect(result).toContain('✓')
  })

  it('marker series formatter raw section includes foo/vol (with vol 4-digit truncation)', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    const result: string = formatter({ data: { event_id: 'bo9' } })
    expect(result).toContain('Attributes')
    expect(result).toContain('foo: bar')
    expect(result).toContain('vol: 1.2346')   // 4 位截断
  })

  it('marker series formatter returns empty string when no event_id in params', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    expect(formatter({ data: {} })).toBe('')
    expect(formatter({ data: null })).toBe('')
    expect(formatter(null)).toBe('')
  })
})
```

---

### Step 13: 跑 chart.spec.ts 确认绿

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/chart.spec.ts`
- [ ] 预期：D2 块 6 个 case 全绿；文件其他块（非 D2 的 buildKlineOption 主体测试）零回归。

---

### Step 14: 全集回归

- [ ] 运行：`cd path2_web_ui && pnpm test --run`
- [ ] 预期：所有 spec 全绿；总数应在原 vitest 数量基础上增加（visible.spec.ts +14 / chart-helpers +8 / chart.spec D2 块净增减为 -1）。
- [ ] 运行：`cd path2_web_ui && pnpm vue-tsc --noEmit`，预期零类型错误。
- [ ] 运行：`cd path2_web_ui && pnpm build`，预期 build 成功。

---

### Step 15: Commit

- [ ] 暂存所有改动：

```bash
git add path2_web_ui/src/render/chart.ts \
        path2_web_ui/src/render/visible.ts \
        path2_web_ui/src/components/KlineChart.vue \
        path2_web_ui/tests/visible.spec.ts \
        path2_web_ui/tests/chart-helpers.spec.ts \
        path2_web_ui/tests/chart.spec.ts
```

- [ ] 创建 commit：

```bash
git commit -m "$(cat <<'EOF'
feat(web-ui): marker tooltip 整治 — 三段结构 + 失败置顶 + 4 位小数

按 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md：
- resolveTooltipData 重写：新增 bars 入参，返回 identity / clauses[] / raw
- TooltipPayload 接口扩展为三段，旧 TooltipClause 替换为 TooltipClauseRow
- buildMarkerTooltipFormatter 重写：可选 match 顶行 + 三段；
  失败 clause 置顶 + <b> 加粗；多 role 同 cid 行末加 (in: <role>)；
  浮点统一 fmtNum 截 4 位；段空时省略段头
- KlineChart.vue:68 调用点同步传 bars.value
- visible.spec.ts 替换旧 3 case → 新 18 case
- chart-helpers.spec.ts 替换旧 3 case → 新 11 case
- chart.spec.ts D2 块 stubResolver 与断言适配新接口

不动 K bar tooltip / 后端 / DetailSidebar。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] 运行 `git status` 确认 working tree 干净（除了 unrelated 的 `configs/path2_web.yaml` 已 modified 与本次无关）。

---

## Task 2: 真实数据端到端实证 + 视觉回归

> 用真实数据（仓库已有 pkl）跑通整链路、手动 hover 截图与 spec §7 验收点对照；不引入生产改动。

**Files:**
- 临时产物：`.playwright-mcp/*` （收尾清理）
- 可选撰写：实证报告（与 commit 一同提交，路径由 implementer 决定，建议 `docs/research/2026-06-29_marker-tooltip-impl/notes.md`）

**Interfaces:**

Consumes：
- 从 Task 1 落地的新 `TooltipPayload` 接口与 `buildMarkerTooltipFormatter` 渲染
- 仓库现有真实数据（如 path2 主线 dag_spec 扫描产物，参 [[project_path2_web_ui_levels_lanes]] 端到端实证用过的 6048 pkl）

---

### Step 1: 启 dev server

- [ ] 在终端启后端 + 前端：

```bash
uv run python scripts/run_path2_web.py
```

- [ ] 等待两端就绪（脚本会一并启 FastAPI 与 Vite dev server）。
- [ ] 浏览器或 Playwright 打开本地 URL（通常 `http://localhost:5173`，以脚本输出为准）。

---

### Step 2: 用 Playwright 打开 UI 并扫描出 burst 命中场景

- [ ] 调用 `mcp__plugin_playwright_playwright__browser_navigate` 打开前端 URL。
- [ ] 选择仓库内已有 scan 结果文件，找到一个 burst 命中股票。若不确定，可优先尝试 `ACRS`（在历次端到端实证中验证过）；或用 `scripts/path2_filter_<走势>.py` 脚本预先跑一次扫描产生新 scan 文件。
- [ ] 切到该股、确认 K 线图与 markers 已渲染。

---

### Step 3: hover event marker 截图（非 match 端点）

- [ ] 用 `mcp__plugin_playwright_playwright__browser_hover` 悬停到一个 burst event marker。
- [ ] 用 `mcp__plugin_playwright_playwright__browser_take_screenshot` 抓 tooltip 区域截图。
- [ ] 对照 spec §3.1 ASCII 结构 + §7 验收：
  - Identity / Clauses / Attributes 三段都出现（如该 event 有诊断信息）
  - 失败 clause 在前、加粗
  - 浮点 4 位（如截图里 `vol_spike: 2.6379` 而非 `2.6378544926831706`）
  - 段头之间有 `<hr/>` 分隔（视觉上是一条横线）

---

### Step 4: hover match 端点 marker 截图

- [ ] 找一个 match 端点的 marker（同股已有命中、marker 渲染时数据带 match_id），悬停 + 截图。
- [ ] 对照：顶行 `Match: ret_<N>: +x.x%` + 下方三段都在；不再是仅 match 单行。

---

### Step 5: 边界场景人工验证（可选，时间允许）

- [ ] hover 一个未匹配的孤立 event marker（应仅显示 Identity，Clauses 段空时省略段头）
- [ ] hover 一个 point event marker（time 行应是单日期、无 `→`）
- [ ] hover 一个区间 event marker（time 行应有 `→`）

---

### Step 6: 撰写实证报告（建议）

- [ ] 在 `docs/research/2026-06-29_marker-tooltip-impl/notes.md` 写一份简短端到端实证记录：哪只股、哪个 event_id、hover 截图链接、与 spec 对照结果（pass/fail）。
- [ ] 与本任务的 Playwright 截图（不入 git，仅作参考）一同验证。

---

### Step 7: Playwright 卫生

- [ ] 关闭 dev server。
- [ ] 清理 `.playwright-mcp/*`（CLAUDE.md 规则；保留目录本身）：

```bash
rm -rf .playwright-mcp/*
```

---

### Step 8: Commit 实证报告（如有撰写）

- [ ] 暂存 `docs/research/2026-06-29_marker-tooltip-impl/`：

```bash
git add docs/research/2026-06-29_marker-tooltip-impl/
git commit -m "$(cat <<'EOF'
docs(research): marker tooltip 整治 端到端实证

真实数据 hover 截图与 spec §7 验收点对照。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] 若未撰写报告，本步跳过。

---

## Self-Review

- 覆盖 spec §1 现状痛点 5 项 → Task 1 Step 1-11 全部对应（去重 / 分组 / 4 位 / 失败置顶 / match 拼接）
- 覆盖 spec §3 五节设计 → Task 1 各 step 完整实现
- 覆盖 spec §6 测试计划（18 + 11 + 6 个 case）→ Task 1 Step 1 / 10 / 12
- 覆盖 spec §7 验收标准（vitest + tsc + build + 真实数据）→ Task 1 Step 14 + Task 2
- 覆盖 spec §8 limitation（cid 名 ↔ 字段名失配）→ Step 5 `resolveTooltipData` 实现按字段名匹配，与 spec 限制一致
- 类型一致：`TooltipClauseRow` / `TooltipPayload` 在 chart.ts 定义、visible.ts 与 chart-helpers.spec.ts 全部 import 同名
- 命令一致：所有 `cd path2_web_ui &&` 前缀统一；vitest 命令 `pnpm test --run <pattern>` 统一
- 无 placeholder、无 TODO、所有代码块完整可粘贴
