# shift marker 视觉重设计 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 替换 shift+click 累积器命中的 marker 视觉从"金黄描边(mutate 本体 itemStyle)"改为"z2:22 独立 overlay:半透明白蒙 fill + 黑横线(与 focus 深边同宽)",与既有 highlight overlay(group/focus/pending)完全正交。

**Architecture:** 拆两步——先**回滚** Task 4 落地的 mutate 路径,再**新增** z2:22 独立 shift-veil custom series(主图与副图各一)。renderer 输出 `{ type: 'group', silent: true, children: [veilShape, blackLine] }`,4 种几何(point/interval/pricePoint/satellite)复用现有 shape 派生逻辑。view store / ShiftPairBanner / KlineChart 传参链均不动。

**Tech Stack:** Vue 3 · Pinia · ECharts custom series(zrender)· Vitest · @playwright/test · TypeScript。

## Global Constraints

- **Spec 源文件**:`docs/superpowers/specs/2026-07-11-shift-marker-veil-line-redesign-design.md`(所有决策以此为准)
- **前置 spec**:`docs/superpowers/specs/2026-07-10-shift-pair-feedback-design.md`(入口 D 沉默期反馈初版,已实施,commit ad26a23..d7e7c99)
- **subagent 模型选择**(用户约定 `CLAUDE.md`):Implementer 一律 `sonnet`(禁 haiku);Reviewer(Spec / Code Quality / Final)一律 `opus`
- **视觉参数**(spec §决策):
  - 白蒙 `rgba(255,255,255,0.45)` · `stroke: 'none'`
  - 黑横线 `stroke: '#000000'` · `lineWidth = HL_FOCUS_STROKE_WIDTH`(chart.ts 既有常量,当前 2.5)· `length = markerWidth × 0.7`
  - overlay z2 = 22(高于既有 highlight overlay 的 21)
  - `silent: true`(hover/click 穿透到本体系列)
- **不引入新常量**:黑横线宽度绑现有 `HL_FOCUS_STROKE_WIDTH`;白蒙 fill 与长度比 0.7 可 inline 或抽小常量,implementer 决定
- **不动**:`view.ts` / `ShiftPairBanner.vue` / `KlineChart.vue` / 既有 highlight overlay 三分支 renderer
- **verification-before-completion**:每 Task 收尾必须真跑 `vitest` + `vue-tsc` + `npm run build`;Task 5 必须真跑 `npx playwright test`;不得凭"应该没问题"提交
- **playwright 卫生**:每次用 playwright MCP 后任务收尾清空 `.playwright-mcp/*`(保留目录)
- **CWD 约定**:除非显式 `cd /home/yu/PycharmProjects/Trade_Strategy`,所有 Bash 命令的 CWD 都是 `/home/yu/PycharmProjects/Trade_Strategy/path2_web_ui`
- **YAGNI**(spec §未纳入):跨图连线 SVG overlay · 射线 · 动画/呼吸 · 色计算 lighten · 公共 CSS 抽层

---

## File Structure

**Modify only**:
- `path2_web_ui/src/render/chart.ts` — 全部改动集中在这一文件:
  - 移除 `shiftItemStyleFor` helper + 4 处 map 装配调用(Task 1 回滚)
  - `EventBundle` interface 加 `veilData` / `veilPriceData`(Task 2)
  - `computeEventData` 装配 veil 数据 + return 加字段(Task 2)
  - 新增 `makeRenderShiftVeil`(Task 3)+ `makeRenderShiftVeilPrice`(Task 4)renderer 工厂
  - `buildSubOption` 加 `shift-veil` custom series(Task 3)
  - `buildMainOption` 加 `shift-veil-price` custom series(Task 4)
- `path2_web_ui/tests/render/chart.marker-highlight.spec.ts` — 断言重写(Task 1 删旧断言;Task 2 加 veil 数据断言)
- `path2_web_ui/e2e/shift-pair-feedback.spec.ts` — 场景 1 断言从 borderColor 改为 shift-veil series 数据(Task 5)

**保留(下游 Task 消费)**:
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>` 字段声明
- `computeEventData` 顶部对 `shiftSelectedEventIds` 的 destruct + `?? new Set<string>()` fallback
- KlineChart.vue → BandRenderInput 传参链
- view store `shiftSelectedEventIds` computed

---

### Task 1: 回滚 shift 黄边(mutate 本体 itemStyle)路径

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`
- Modify: `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`

**Interfaces produced**: (无新 interface;仅移除旧 helper)
**Interfaces consumed**: 无

**目的**:让代码库回到"shift 命中的 marker 视觉上无信号"状态(banner + 拓扑传参链保留),为 Task 2-4 从零加新方案清场,保证 git bisect 清晰。

- [ ] **Step 1: 定位现有黄边落地位置**

```bash
grep -n "shiftItemStyleFor\|shiftSelectedEventIds\|borderColor.*fbbf24\|borderWidth.*2" path2_web_ui/src/render/chart.ts
```

Expected:定位到
- `shiftItemStyleFor` helper 定义(约 line 117 附近,在 computeEventData 顶部)
- 4 处 map 装配点调用(pointData/intervalData/pricePointData/satelliteData 的 itemStyle 装配)
- `BandRenderInput.shiftSelectedEventIds` 字段声明(不动)
- `computeEventData` 顶部 destruct(部分保留,详见 Step 3)

- [ ] **Step 2: 更新 chart.marker-highlight.spec.ts 断言(RED)**

编辑 `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`,把 3、4 号测试(shiftSelectedEventIds 含 event_id → 描边)删除,保留 1、2 号(undefined/空集 → 无 borderColor)兼作向后兼容 sentinel:

原(节选 · 需要删除的 3、4 号):
```typescript
  it('shiftSelectedEventIds 含 e_bo_1 → 该 event 的 marker 数据带 #fbbf24 描边', () => {
    ...
    expect(hit!.itemStyle.borderColor).toBe('#fbbf24')
    expect(hit!.itemStyle.borderWidth).toBe(2)
  })

  it('shiftSelectedEventIds 含 e_bo_1,其他 event 不受影响', () => {
    ...
  })
```

**整块删除这两个 it 段**;保留:
```typescript
  it('shiftSelectedEventIds undefined → 各 series itemStyle 不带 borderColor', () => { ... })
  it('shiftSelectedEventIds 空集 → 同上,零副作用', () => { ... })
```

(这两个测试在 Task 1 回滚后依然通过;Task 2 会再加新的 veilData 断言,不冲突。)

- [ ] **Step 3: 跑测试确认删除断言无 broken 回归**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -15
```

Expected:2 tests passed(删除后剩下的 undefined/空集断言仍绿——因为回滚前它们本就绿,回滚后依然绿;RED 阶段就跳过这个 spec)

- [ ] **Step 4: 实现回滚(chart.ts)**

编辑 `path2_web_ui/src/render/chart.ts`,3 处改动:

**改动 A**:删除 `shiftItemStyleFor` helper 定义(约 line 113-118 附近)。原:

```typescript
  const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
  const shiftItemStyleFor = (event_id: string, base: Record<string, unknown>) =>
    shiftSelectedEventIds.has(event_id)
      ? { ...base, borderColor: '#fbbf24', borderWidth: 2 }
      : base
```

改为(仅保留 fallback,helper 删):
```typescript
  const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
```

**改动 B**:4 处 map 装配点回改。分别是:

- **pricePointData**(chart.ts:142-156):

  原:
  ```typescript
      itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
  ```
  改为:
  ```typescript
      itemStyle: { color: eColor(e) },
  ```

- **satelliteData**(chart.ts:158-175 内 push):

  原:
  ```typescript
        itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
  ```
  改为:
  ```typescript
        itemStyle: { color: eColor(e) },
  ```

- **intervalData**(chart.ts:178-183 map):

  原:
  ```typescript
    itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
  ```
  改为:
  ```typescript
    itemStyle: { color: eColor(e) },
  ```

- **pointData**(chart.ts:185-194 map):

  原:
  ```typescript
      itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
  ```
  改为:
  ```typescript
      itemStyle: { color: eColor(e) },
  ```

(4 处装配点每处一行;grep 确认 4 处都改到,避免遗漏。)

**注意保留**:
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>` 字段声明(Task 2 消费)
- `computeEventData` 顶部的 destruct `shiftSelectedEventIds: _shiftSelectedEventIds` + `const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()`(Task 2 消费)

- [ ] **Step 5: 跑测试 + tsc + build 三绿**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -10
```

Expected:2 tests passed(undefined/空集断言仍绿)

```bash
npx vitest run 2>&1 | tail -6
```

Expected:全套绿(相对基线 -2 tests,因为 Step 2 删了 2 个 it)

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected:无 error(若报"'shiftItemStyleFor' is declared but never used"或类似,说明 helper 未删干净,回 Step 4 检查)

```bash
npm run build 2>&1 | tail -5
```

Expected:`built in Xs`,无 error

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/render/chart.marker-highlight.spec.ts
git commit -m "$(cat <<'EOF'
revert(chart): 移除 shift 黄边 mutate 本体 itemStyle 路径

回滚 2026-07-10 Task 4 的 shiftItemStyleFor helper 与 4 处 map
装配调用。原黄边被既有 highlight overlay(z2:21)完全遮盖,且
色不明显。shiftSelectedEventIds 字段与 fallback 保留,供后续
z2:22 独立 shift-veil overlay 消费。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: EventBundle 加 veil 字段 + computeEventData 装配 + 单元测

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`(interface + computeEventData)
- Modify: `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`

**Interfaces produced**:
```ts
// EventBundle 扩两字段
veilData: any[]         // 副图 point + interval 命中条目;{...原 pointData/intervalData item, kind: 'point'|'interval'}
veilPriceData: any[]    // 主图 pricePoint + satellite 命中条目;{...原 pricePointData/satelliteData item, kind: 'pricePoint'|'satellite'}
```

**Interfaces consumed**:
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>`(Task 1 保留)
- 各 `pointData` / `intervalData` / `pricePointData` / `satelliteData` 装配后的形态(参 chart.ts:142-194)

- [ ] **Step 1: 写单元测试(RED)**

编辑 `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`,在保留的 2 个 undefined/空集测试之后,新增 4 个 veil 断言测试:

```typescript
  it('shiftSelectedEventIds undefined → veilData / veilPriceData 为空', () => {
    const bundle = computeEventData(makeBars(), [eBo], [], makeInput())
    expect(bundle.veilData).toEqual([])
    expect(bundle.veilPriceData).toEqual([])
  })

  it('shiftSelectedEventIds 空集 → veilData / veilPriceData 为空', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set() }))
    expect(bundle.veilData).toEqual([])
    expect(bundle.veilPriceData).toEqual([])
  })

  it('shiftSelectedEventIds 含 e_bo_1 → veil* 里含 event_id + kind 正确', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const all = [...bundle.veilData, ...bundle.veilPriceData]
    const hit = all.find(d => d.event_id === 'e_bo_1')
    expect(hit).toBeDefined()
    expect(['point', 'interval', 'pricePoint', 'satellite']).toContain(hit!.kind)
  })

  it('shiftSelectedEventIds 命中的 event 未命中的 event 不进 veil', () => {
    const eOther: EventDict = { ...eBo, event_id: 'e_other', start_idx: 5, end_idx: 5 } as any
    const bundle = computeEventData(makeBars(), [eBo, eOther], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const all = [...bundle.veilData, ...bundle.veilPriceData]
    expect(all.find(d => d.event_id === 'e_other')).toBeUndefined()
  })
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -15
```

Expected:4 新用例 FAIL(`bundle.veilData is undefined` / `Cannot read properties of undefined`)

- [ ] **Step 3: 实现 EventBundle 字段扩展**

编辑 `path2_web_ui/src/render/chart.ts`,`EventBundle` interface(约 line 88-99)加两字段。原:

```typescript
export interface EventBundle {
  pointData: any[]
  intervalData: any[]
  pricePointData: any[]
  satelliteData: any[]
  bracketData: any[]
  highlightData: any[]
  highlightPriceData: any[]
  candle: number[][]
  volume: number[]
  dates: string[]
}
```

改为:

```typescript
export interface EventBundle {
  pointData: any[]
  intervalData: any[]
  pricePointData: any[]
  satelliteData: any[]
  bracketData: any[]
  highlightData: any[]
  highlightPriceData: any[]
  // ── spec 2026-07-11: shift+click 累积器命中 marker 的白蒙+黑线 overlay 数据 ──
  veilData: any[]         // 副图 point + interval
  veilPriceData: any[]    // 主图 pricePoint + satellite
  candle: number[][]
  volume: number[]
  dates: string[]
}
```

- [ ] **Step 4: 实现 computeEventData 装配**

编辑 `path2_web_ui/src/render/chart.ts`,在 `computeEventData` 里的既有 highlight overlay 三分支装配之后(即在 `return { pointData, intervalData, ... }` 之前,约 line 253 附近),追加 veil 装配段:

```typescript
  // ── spec 2026-07-11: shift-veil overlay 数据(z2:22 独立层,fill 白蒙 + 黑横线) ──
  const veilData: any[] = []
  const veilPriceData: any[] = []
  if (shiftSelectedEventIds.size > 0) {
    for (const d of pointData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilData.push({ ...d, kind: 'point' })
    }
    for (const d of intervalData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilData.push({ ...d, kind: 'interval' })
    }
    for (const d of pricePointData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilPriceData.push({ ...d, kind: 'pricePoint' })
    }
    for (const d of satelliteData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilPriceData.push({ ...d, kind: 'satellite' })
    }
  }
```

然后修改 `computeEventData` 的 `return`(约 line 254-258)。原:

```typescript
  return {
    pointData, intervalData, pricePointData, satelliteData,
    bracketData, highlightData, highlightPriceData,
    candle, volume, dates,
  }
```

改为(在 highlightPriceData 之后加 veilData/veilPriceData):

```typescript
  return {
    pointData, intervalData, pricePointData, satelliteData,
    bracketData, highlightData, highlightPriceData,
    veilData, veilPriceData,
    candle, volume, dates,
  }
```

- [ ] **Step 5: 跑测试确认通过 + 全套无回归**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -12
```

Expected:6 tests passed(原 2 + 新 4)

```bash
npx vitest run 2>&1 | tail -6
```

Expected:全套绿(相对 Task 1 基线 +4)

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected:无 error

```bash
npm run build 2>&1 | tail -5
```

Expected:built in Xs,无 error

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/render/chart.marker-highlight.spec.ts
git commit -m "$(cat <<'EOF'
feat(chart): EventBundle 加 veilData / veilPriceData

computeEventData 遍历 4 种 marker 数据装配 shift-veil overlay
输入(fill 白蒙 + 黑横线的数据源)。仅数据装配,renderer 与
series 装配在 Task 3/4。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 副图 shift-veil series + `makeRenderShiftVeil` renderer

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`(新增 renderer + buildSubOption 装配 series)

**Interfaces produced**:
```ts
makeRenderShiftVeil(
  items: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }>,
  bandGeom: BandGeom[],
  zoomFactor?: number,
): (params: any, api: any) => any
```

**Interfaces consumed**:
- `bundle.veilData`(Task 2)
- 既有 `renderIntervalWithGeom` / `renderPointWithGeom` 里的 shape 派生逻辑(不复用函数,复制 shape 计算)
- 既有常量:`BAND_MARKER_H`、`BAND_LANE_GAP`、`BAND_TOP_PAD`、`BAND_BOT_PAD`、`HL_FOCUS_STROKE_WIDTH`

- [ ] **Step 1: 定位副图 series 装配点**

```bash
grep -n "buildSubOption\|type: 'custom'.*points\|type: 'custom'.*intervals\|type: 'custom'.*highlight'" path2_web_ui/src/render/chart.ts | head -10
```

Expected:定位到 `buildSubOption` 函数(约 chart.ts:490 附近)+ 内部 4 处 custom series 装配(intervals / points / brackets / highlight)。shift-veil 装配位置紧接 highlight 之后(z 更高)。

- [ ] **Step 2: 实现 `makeRenderShiftVeil` renderer 工厂**

编辑 `path2_web_ui/src/render/chart.ts`,在既有 `makeRenderHighlightWithGeom`(约 line 753)之后追加:

```typescript
// ── spec 2026-07-11: shift-veil 副图 renderer(point + interval,fill 白蒙 + 黑横线) ──
// 每条 veil 数据一个 group,children = [半透明白蒙 shape, 黑横线],
// 复用与 renderPointWithGeom / renderIntervalWithGeom 同一 shape 派生逻辑。
// silent:true → hover/click 穿透到本体 marker;z2:22 高于 highlight overlay(21)。
export function makeRenderShiftVeil(
  items: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }>,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  return function renderShiftVeil(params: any, api: any) {
    const item = items[params.dataIndex] ?? null
    if (!item) return { type: 'group', children: [] }

    if (item.kind === 'point') {
      // 参 renderPointWithGeom:三角 polygon,底顶点在下、两上角在上
      const x = api.coord([api.value(0), 0])[0]
      const band = api.value(2) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const centerY = g.top + g.h / 2
      const unitW = api.size([1, 0])[0]
      const w = Math.max(5, Math.min(20, unitW * 0.35))
      const triPoints = [
        [x, centerY + 4 * zoomFactor],
        [x - w, centerY - 3 * zoomFactor],
        [x + w, centerY - 3 * zoomFactor],
      ]
      const lineLen = w * 2 * 0.7   // 横线长度 = 三角底宽 × 0.7
      return {
        type: 'group',
        silent: true,
        z2: 22,
        children: [
          { type: 'polygon', shape: { points: triPoints },
            style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
          { type: 'line',
            shape: { x1: x - lineLen / 2, y1: centerY, x2: x + lineLen / 2, y2: centerY },
            style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
        ],
      }
    }

    // interval 分支:参 renderIntervalWithGeom
    const x0 = api.coord([api.value(0), 0])[0]
    const x1 = api.coord([api.value(1), 0])[0]
    const lane = api.value(2) || 0
    const band = api.value(3) || 0
    const g = bandGeom[band]
    if (!g) return { type: 'group', children: [] }
    const laneH = BAND_MARKER_H * zoomFactor
    const gap = BAND_LANE_GAP * zoomFactor
    const rawY = g.top + BAND_TOP_PAD + lane * (laneH + gap)
    const y = Math.max(g.top + BAND_TOP_PAD, Math.min(rawY, g.top + g.h - BAND_BOT_PAD - laneH))
    const width = Math.max(2, x1 - x0)
    const midY = y + laneH / 2
    const lineLen = width * 0.7
    const lineCenterX = x0 + width / 2
    return {
      type: 'group',
      silent: true,
      z2: 22,
      children: [
        { type: 'rect', shape: { x: x0, y, width, height: laneH },
          style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
        { type: 'line',
          shape: { x1: lineCenterX - lineLen / 2, y1: midY,
                   x2: lineCenterX + lineLen / 2, y2: midY },
          style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
      ],
    }
  }
}
```

- [ ] **Step 3: 在 buildSubOption 追加 shift-veil series 装配**

编辑 `path2_web_ui/src/render/chart.ts`,`buildSubOption` 里既有 highlight custom series 装配(约 chart.ts:562-566)之后追加:

原(节选,highlight series 装配位置):
```typescript
      // highlight (z:20)。animation:true 为 series 级显式开关:keyframeAnimation(pending 闪烁)
      { type: 'custom', name: 'highlight', xAxisIndex: 1, yAxisIndex: 1,
        data: highlightData, animation: true,
        renderItem: makeRenderHighlightWithGeom(highlightData, subGeom.bandGeom, z),
        z: 20 },
```

追加(紧接在 highlight 之后 ` }` 之前或平齐):
```typescript
      // shift-veil (z:22 高于 highlight,spec 2026-07-11):fill 白蒙 + 黑横线,与 highlight 三分支正交
      { type: 'custom', name: 'shift-veil', xAxisIndex: 1, yAxisIndex: 1,
        data: veilData, animation: false, silent: true,
        renderItem: makeRenderShiftVeil(veilData, subGeom.bandGeom, z),
        z: 22 },
```

**注**:如果 `buildSubOption` 顶部的 `{ ..., highlightData }` 解构里没有 `veilData`,加进去。参考解构位置(chart.ts:490 附近):

原:
```typescript
  const { dates, pointData, intervalData, bracketData, highlightData } = bundle
```

改为:
```typescript
  const { dates, pointData, intervalData, bracketData, highlightData, veilData } = bundle
```

- [ ] **Step 4: 跑 tsc + build + vitest 三绿(视觉验证在 Task 5)**

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected:无 error(若报 `Property 'veilData' does not exist on type 'EventBundle'`,回 Task 2 Step 3 检查)

```bash
npm run build 2>&1 | tail -5
```

Expected:built in Xs,无 error

```bash
npx vitest run 2>&1 | tail -6
```

Expected:全套绿(相对 Task 2 基线不变;renderer 新增无单元测,视觉在 Task 5)

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/render/chart.ts
git commit -m "$(cat <<'EOF'
feat(chart): 副图 shift-veil custom series + makeRenderShiftVeil

point/interval 两种几何各画 group children = [半透明白蒙 shape,
黑横线(长=marker宽×0.7,linewidth=HL_FOCUS_STROKE_WIDTH)]。
silent:true 让 hover/click 穿透到本体 marker;z2:22 高于既有
highlight overlay(21),与 group/focus/pending 完全正交。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 主图 shift-veil-price series + `makeRenderShiftVeilPrice` renderer

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`

**Interfaces produced**:
```ts
makeRenderShiftVeilPrice(
  items: Array<{ value: number[]; event_id: string; kind: 'pricePoint' | 'satellite';
                 anchorY?: number; text?: string; hasPks?: boolean }>,
): (params: any, api: any) => any
```

**Interfaces consumed**:
- `bundle.veilPriceData`(Task 2)
- 既有 shape 派生逻辑:`makeRenderPricePoint` / `makeRenderSatellite`(不复用函数,复制 shape 计算)
- 既有常量:`BO_STACK_PT`、`BO_STACK_PT_NO_PKS`、`BO_BOX_RADIUS`、`boBoxDims`、`TRIANGLE_STACK_PT`、`PK_TRIANGLE_HALF_WIDTH`、`PK_TRIANGLE_HEIGHT`、`HL_FOCUS_STROKE_WIDTH`

- [ ] **Step 1: 定位主图 series 装配点**

```bash
grep -n "buildMainOption\|type: 'custom'.*price-points\|type: 'custom'.*satellite\|type: 'custom'.*highlight-price" path2_web_ui/src/render/chart.ts | head -10
```

Expected:定位到 `buildMainOption`(约 chart.ts:263 附近)+ 内部 highlight-price custom series 装配(约 line 373)。shift-veil-price 装配位置紧接 highlight-price 之后。

- [ ] **Step 2: 实现 `makeRenderShiftVeilPrice` renderer 工厂**

编辑 `path2_web_ui/src/render/chart.ts`,在 `makeRenderShiftVeil`(Task 3 新增)之后追加:

```typescript
// ── spec 2026-07-11: shift-veil 主图 renderer(pricePoint + satellite,fill 白蒙 + 黑横线) ──
export function makeRenderShiftVeilPrice(
  items: Array<{ value: number[]; event_id: string; kind: 'pricePoint' | 'satellite';
                 anchorY?: number; text?: string; hasPks?: boolean }>,
) {
  return function renderShiftVeilPrice(params: any, api: any) {
    const item = items[params.dataIndex] ?? null
    if (!item) return { type: 'group', children: [] }

    if (item.kind === 'pricePoint') {
      // 参 makeRenderPricePoint:圆角矩形背景,box 中心 = anchorPx - stackOffset
      const anchorY = item.anchorY ?? api.value(1)
      const text = item.text ?? ''
      const hasPks = item.hasPks ?? false
      const [cx, anchorPx] = api.coord([api.value(0), anchorY])
      const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
      const cy = anchorPx - stackOffset
      const { w, h } = boBoxDims(text)
      const lineLen = w * 0.7
      return {
        type: 'group',
        silent: true,
        z2: 22,
        children: [
          { type: 'rect',
            shape: { x: cx - w / 2, y: cy - h / 2, width: w, height: h, r: BO_BOX_RADIUS },
            style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
          { type: 'line',
            shape: { x1: cx - lineLen / 2, y1: cy, x2: cx + lineLen / 2, y2: cy },
            style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
        ],
      }
    }

    // satellite 分支:参 makeRenderSatellite,倒三角(顶点在下,两上角在上)
    // 三角形 fill='none' 原本空心;白蒙给 fill 半透明白,让原轮廓仍在、内部变白
    const anchorY = item.anchorY ?? api.value(1)
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const triCy = anchorPx - TRIANGLE_STACK_PT
    const tw = PK_TRIANGLE_HALF_WIDTH
    const th = PK_TRIANGLE_HEIGHT
    const triPoints = [
      [cx - tw, triCy - th / 2],
      [cx + tw, triCy - th / 2],
      [cx,      triCy + th / 2],
    ]
    const lineLen = 2 * tw * 0.7
    return {
      type: 'group',
      silent: true,
      z2: 22,
      children: [
        { type: 'polygon', shape: { points: triPoints },
          style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
        { type: 'line',
          shape: { x1: cx - lineLen / 2, y1: triCy, x2: cx + lineLen / 2, y2: triCy },
          style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
      ],
    }
  }
}
```

- [ ] **Step 3: 在 buildMainOption 追加 shift-veil-price series 装配**

编辑 `path2_web_ui/src/render/chart.ts`,`buildMainOption` 里既有 highlight-price custom series 装配(约 chart.ts:373)之后追加:

原(节选):
```typescript
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData, animation: true,
        renderItem: makeRenderPricePointHighlight(highlightPriceData),
      },
```

追加(紧邻 highlight-price series 之后):
```typescript
      { type: 'custom', name: 'shift-veil-price', xAxisIndex: 0, yAxisIndex: 0,
        data: veilPriceData, animation: false, silent: true,
        renderItem: makeRenderShiftVeilPrice(veilPriceData),
        z: 22 },
```

**注**:如果 `buildMainOption` 顶部的 `{ ..., highlightPriceData }` 解构里没有 `veilPriceData`,加进去。参考解构位置(chart.ts:269 附近):

原:
```typescript
  const { dates, candle, pricePointData, satelliteData, highlightPriceData } = bundle
```

改为:
```typescript
  const { dates, candle, pricePointData, satelliteData, highlightPriceData, veilPriceData } = bundle
```

- [ ] **Step 4: 跑 tsc + build + vitest 三绿**

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected:无 error

```bash
npm run build 2>&1 | tail -5
```

Expected:built in Xs,无 error

```bash
npx vitest run 2>&1 | tail -6
```

Expected:全套绿(相对 Task 3 基线不变)

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/render/chart.ts
git commit -m "$(cat <<'EOF'
feat(chart): 主图 shift-veil-price custom series + renderer

pricePoint/satellite 两种几何各画 group children = [半透明白蒙
shape, 黑横线]。satellite 空心倒三角上叠白蒙 fill 让轮廓仍在
内部变白。silent:true 穿透 hover/click,z2:22 高于 highlight-
price(21),4 种几何视觉一致。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: e2e 场景 1 断言更新 + Playwright 5 场景验收

**Files:**
- Modify: `path2_web_ui/e2e/shift-pair-feedback.spec.ts`

**Interfaces produced**: (无新 interface;仅测试断言更新 + 视觉验收)
**Interfaces consumed**:
- `chart*.getOption().series` 里 `shift-veil` / `shift-veil-price` custom series(Task 3/4 装配)
- 各 series 的 `data` 属性(与 bundle.veilData/veilPriceData 对齐)

- [ ] **Step 1: 启动后端**

在项目根 `/home/yu/PycharmProjects/Trade_Strategy` 起后端:

```bash
uv run python scripts/run_path2_web.py &
```

Expected:uvicorn 启动信息(端口以 `configs/path2_web.yaml` 为准);前端由 playwright.config.ts webServer 自动起

- [ ] **Step 2: 更新场景 1 断言**

编辑 `path2_web_ui/e2e/shift-pair-feedback.spec.ts` 场景 1,把 `borderColor === '#fbbf24'` 断言删除,改用观测 shift-veil / shift-veil-price series 数据。

原(节选,场景 1):
```typescript
    const bordered = await page.evaluate((eid) => {
      const sub = (window as any).__e2e.chartSub()
      const pts = sub.getOption().series.find((s: any) => s.name === 'points')
      const d = pts?.data?.find((x: any) => x.event_id === eid)
      return d?.itemStyle?.borderColor
    }, m.event_id)
    expect(bordered).toBe('#fbbf24')
```

改为:
```typescript
    // shift-veil 数据(spec 2026-07-11):副图 shift-veil / 主图 shift-veil-price series
    // 之一含此 event_id;不再断言本体 marker itemStyle.borderColor(Task 4 mutate 路径已回滚)。
    const veilHit = await page.evaluate((eid) => {
      const readVeilData = (chart: any, name: string) => {
        const s = chart.getOption().series.find((x: any) => x.name === name)
        return s?.data ?? []
      }
      const sub = (window as any).__e2e.chartSub()
      const main = (window as any).__e2e.chartMain()
      const combined = [...readVeilData(sub, 'shift-veil'), ...readVeilData(main, 'shift-veil-price')]
      return combined.some((d: any) => d.event_id === eid)
    }, m.event_id)
    expect(veilHit).toBe(true)
```

**注**:场景 4 里 length=2 场景可能已有断言 `expect(len).toBe(2)` 之类,不改;若曾断言"两 marker 都有 borderColor",同样按上述模式改为"两 marker 都在 shift-veil / shift-veil-price 里"。grep 一下确认:

```bash
grep -n "borderColor\|shiftSelectedEventIds" path2_web_ui/e2e/shift-pair-feedback.spec.ts
```

Expected:定位所有旧 borderColor 断言,同一模式改。若无其他,只场景 1 一处。

- [ ] **Step 3: 跑 e2e 确认 5 场景全绿**

```bash
npx playwright test e2e/shift-pair-feedback.spec.ts 2>&1 | tail -30
```

Expected:5 tests passed(或 4 + 1 skipped——场景 4 fixture 依赖);全 fail 需回溯前置 Task。

**若失败**:
- **shift-veil 数据空** → 检查 Task 2 `computeEventData` 装配逻辑;检查 Task 3/4 buildOption 里解构是否加了 veilData/veilPriceData
- **series 找不到 'shift-veil' / 'shift-veil-price'** → 检查 Task 3/4 series 装配是否 push 到 series 数组;检查 name 字段拼写
- **场景 4 依旧 skip**:非本 spec 引入,与原 fixture 相关,不阻塞

- [ ] **Step 4: MCP 视觉验证**(spec §测试与验收 视觉验收段落)

用 playwright MCP 手动截图对照,场景:

1. **单击 shift**:任一 marker → 变浅 + 黑横线可辨(整页 fullPage=true)
2. **shift + group 同一 marker**(先点其他 event 让某 match 成 focus/group,再 shift+click 组员):group 深细边+阴影完好,内部变浅+黑横线可辨
3. **深色 vs 浅色角色色对照**:matched(role 本色,如 slate/深蓝)与 detected(灰) 上黑横线都清晰

截图分别存证。前置:`browser_resize(2560, 1440)` · `scale="device"`。整体 `fullPage=True`,细节 `target=".main-chart"` / `.sub-outer canvas` + `fullPage=False`。

- [ ] **Step 5: 最终 gate — 三绿 + 清理 + Commit**

**verification-before-completion**:必须真跑,不得凭空断言。

```bash
npx vitest run 2>&1 | tail -6
```

Expected:全套绿

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected:无输出

```bash
npm run build 2>&1 | tail -5
```

Expected:built in Xs,无 error

**清 playwright MCP 缓存**:

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && rm -rf .playwright-mcp/*
```

**关掉后端后台进程**(Ctrl+C 或 kill)。

**Commit**:

```bash
git add path2_web_ui/e2e/shift-pair-feedback.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): shift-veil overlay 场景 1 断言 + 视觉验收

场景 1 断言从本体 marker borderColor 改为 shift-veil /
shift-veil-price series 数据观测。5 场景全绿;MCP 截图验证
group 深边+shift 变浅+黑横线正交,深/浅色角色色黑横线均可辨。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 完成判据

累计验收:
- 全套 vitest 绿(相对 2026-07-10 spec 结束时基线:Task 1 删 2 断言、Task 2 加 4 断言,净 +2;Task 3/4/5 不改测试计数)
- vue-tsc --noEmit 无 error
- npm run build 无 error
- Playwright 5 场景全通过(场景 1 断言已更新为 shift-veil series)
- 视觉验收:group 深边+shift 变浅+黑横线正交 · 深/浅色底黑横线均可辨
- 5 commit(Tasks 1-5 各 1)

**未纳入**(spec §YAGNI):跨图连线 · 射线 · 动画/呼吸 · 色计算 lighten · 公共 CSS 抽层

---

## Handoff

**执行方式**:subagent-driven(默认,承 2026-07-10 spec 惯例 · 用户 CLAUDE.md 明示)
**Implementer 模型**:sonnet
**Reviewer 模型**:opus
**验证约束**:每 Task 收尾必须真跑 `vitest` / `vue-tsc` / `npm run build`;Task 5 必须真跑 `npx playwright test`;不得凭空断言"应该通过"
