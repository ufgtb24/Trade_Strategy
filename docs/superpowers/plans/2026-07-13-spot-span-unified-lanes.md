# spot 与 span 统一 lane 语义 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 path2_web_ui 副图内 spot 三角与 span 矩形的视觉重叠 bug——让 spot 与 span 在同 band 内共享同一套 packLanes, 由 lane 号统一决定 y 位置。

**Architecture:** `splitGeometry` 前置分流退位, `packByBand` 输入合并为 `[...intervals, ...points]`, packLanes 的 strict `<` 保证同 start_idx 一定不同 lane。pointData 增加 lane 字段 (band 索引位置从 value[2] 移到 value[3], 与 intervalData 对齐)。三处 renderer (renderPointWithGeom / makeRenderHighlightWithGeom point / makeRenderShiftVeil point) 从"band 中心"改为"lane 中心"派生 centerY。KlineChart.vue bandLaneCounts 从"intervals lane + hasPoint" 简化为"合并 events 的 max lane + 1"。

**Tech Stack:** TypeScript / Vue 3 / vitest / ECharts custom series

## Global Constraints

- 保留 spot 三角形状与 span 矩形形状, 不引入新形状。
- 常量 `BAND_MARKER_H=7` / `BAND_LANE_GAP=2` / `BAND_TOP_PAD=4` / `BAND_BOT_PAD=4` 数值不变。
- 交互 (点选/hover/tooltip/高亮) 语义不变——所有交互只依赖 `event_id`, 与 y 位置无关。
- 不动 `packBrackets` (归属带 packing)。
- 不动 price-anchored events (`pricePointData` / `satelliteData`) 与主图 renderer。
- 不动后端 (path2_web) 与投影层。
- pointData.value shape 从 `[start_idx, start_idx, band, nBands]` (4 元组) 迁移为 `[start_idx, start_idx, lane, band, nBands]` (5 元组, 与 intervalData 同 shape); band 索引位置从 index 2 移到 index 3。

---

## File Structure

**修改的生产代码:**
- `path2_web_ui/src/render/chart.ts` — `computeEventData` 合并 pack + pointData shape 变更; `renderPointWithGeom` / `makeRenderHighlightWithGeom` point 分支 / `makeRenderShiftVeil` point 分支 三处 renderer 改 centerY 公式。
- `path2_web_ui/src/components/KlineChart.vue` — `deriveSubGeometry` 中 bandLaneCounts 计算简化。

**修改的测试:**
- `path2_web_ui/tests/geometry.spec.ts` — 新增混合 spot+span 用例。
- `path2_web_ui/tests/chart.spec.ts` — pointData shape 断言迁移; renderPointWithGeom 新增 lane>0 用例; makeRenderHighlightWithGeom point 分支断言 fakeApi 更新。

**不动:**
- `path2_web_ui/src/render/geometry.ts` (packLanes/packByBand 通用 API 不变, splitGeometry 保留但退位)。
- `path2_web_ui/src/render/subGeometry.ts` (computeSubGeometry 契约不变)。
- 其它 vue 组件、后端、投影层。

---

## Task 1: 契约锁定 — geometry 测试新增混合 spot+span 用例

**Files:**
- Modify: `path2_web_ui/tests/geometry.spec.ts` (在 `describe('packByBand')` block 内)

**Interfaces:**
- Consumes: `packByBand(items, bandOrder, bandKeyOf)` 现有 API。
- Produces: 无生产代码变更。测试用例文档化"同 band 内 spot(start=end) 与 span 同 start_idx 分到不同 lane"契约, 后续 Task 依赖此契约。

**目的:** 无生产代码改动即通过, 用来锁定"packByBand 对合并输入的行为符合预期"这个不变量; 后续 Task 若破契约, 此测试将红。

- [ ] **Step 1: 写用例**

在 `path2_web_ui/tests/geometry.spec.ts` 的 `describe('packByBand', () => {` 内追加:

```ts
  it('同 band 内 spot (start=end) 与 span 同 start_idx 分到不同 lane', () => {
    // 混合输入:spot start=end=3, span start=3 end=8, 同 band=trend0
    // packLanes 的 strict < 语义应让二者一定分到不同 lane
    const items = [
      evB('spot', 'trend0', 3, 3),
      evB('span', 'trend0', 3, 8),
    ]
    const out = packByBand(items, ['trend0'], (e) => e.source_tag as string)
    const spot = out.find(o => o.event_id === 'spot')!
    const span = out.find(o => o.event_id === 'span')!
    expect(spot.band).toBe(0)
    expect(span.band).toBe(0)
    expect(spot.lane).not.toBe(span.lane)
  })

  it('同 band 内多 spot 同 start_idx 分到不同 lane', () => {
    // 3 个 spot 同 bar (start=end=5), 同 band
    // packLanes strict < → 三个 lane 号必两两不同
    const items = [
      evB('s1', 'trend0', 5, 5),
      evB('s2', 'trend0', 5, 5),
      evB('s3', 'trend0', 5, 5),
    ]
    const out = packByBand(items, ['trend0'], (e) => e.source_tag as string)
    const lanes = out.map(o => o.lane).sort()
    expect(lanes).toEqual([0, 1, 2])
  })
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd path2_web_ui && npx vitest run tests/geometry.spec.ts`

Expected: 所有测试通过 (包括新增 2 个)。无生产代码改动。

- [ ] **Step 3: 提交**

```bash
git add path2_web_ui/tests/geometry.spec.ts
git commit -m "test(geometry): 锁定 packByBand 合并 spot+span 的 lane 分离契约"
```

---

## Task 2: 迁移 pointData shape + 合并 packing + 三 renderer 改 centerY

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts` 多处 (见下方 Step 详情)
- Modify: `path2_web_ui/tests/chart.spec.ts` 多处 (pointData shape 断言 + renderer 测试)

**Interfaces:**
- Consumes: 现有 `packByBand`, `splitGeometry` (Task 1 已锁定契约)。
- Produces:
  - `pointData: any[]` — 每项 `value: [start_idx, start_idx, lane, band, nBands]` (5 元组);
  - `intervalData: any[]` — 每项 `value: [start_idx, end_idx, lane, band, nBands]` (5 元组, 未变);
  - `renderPointWithGeom(params, api, bandGeom, zoomFactor?)` — 读 `api.value(2)=lane`, `api.value(3)=band`;
  - `makeRenderHighlightWithGeom(items, bandGeom, zoomFactor?)` — point 分支读 `item.value[2]=lane`, `item.value[3]=band`;
  - `makeRenderShiftVeil(items, bandGeom, zoomFactor?)` — point 分支读 `api.value(2)=lane`, `api.value(3)=band`;
  - Task 3 消费:`pointData.value[3] === band`。

**目的:** 此任务是原子改动——pointData shape 变更牵动三 renderer 和多处测试, 拆开会产生"shape 变了但 renderer 未更新"的红态中间态。全部同 commit 落地。

### 2.1 修改生产代码

- [ ] **Step 1: 修改 `computeEventData` — 合并 pack + 新 shape + 删死代码**

**1a.** 编辑 `path2_web_ui/src/render/chart.ts` 第 184-201 行 (从 `const packedIntervals` 到 `const pointData = points.map(...)` 结束), 用以下代码整体替换:

```ts
  // 合并 spot + span 一并送 packByBand,同 band 内共享同一次 packLanes 分 lane
  // (spec 2026-07-13:spot 从 band 中心固定位置改为参与 lane packing,消除视觉重叠 bug)
  const packedAll = packByBand(timeAnchored, subTags, bandKeyOf)
  const intervalData: any[] = []
  const pointData: any[] = []
  for (const e of packedAll) {
    const isPoint = e.start_idx === e.end_idx
    const record = {
      value: [e.start_idx, e.end_idx, e.lane, e.band, e.nBands],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
    }
    if (isPoint) pointData.push(record)
    else intervalData.push(record)
  }
```

**1b.** 上一步后, `path2_web_ui/src/render/chart.ts` 第 136 行的 `const { points, intervals } = splitGeometry(timeAnchored)` 变成死代码 (points/intervals 局部变量已无消费者)。删除该行。

**1c.** 上一步后, `splitGeometry` 已不再从 chart.ts 引用。修改 chart.ts 第 4 行的 import, 从:

```ts
import { splitGeometry, packByBand, packBrackets } from './geometry'
```

改为:

```ts
import { packByBand, packBrackets } from './geometry'
```

`splitGeometry` 保留在 `geometry.ts` 里 (仍被 `geometry.spec.ts:6` 直接测), 不动源文件。

注意:此 pointData 已不含 point-only fields (原来的 pointData 除 value 外只有 event_id/tier/itemStyle, 与新代码一致);intervalData 亦一致。

- [ ] **Step 2: 修改 `renderPointWithGeom` (chart.ts:762-780)**

用以下代码整体替换 `renderPointWithGeom` 函数体:

```ts
export function renderPointWithGeom(
  params: any,
  api: any,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  const x = api.coord([api.value(0), 0])[0]
  const lane = api.value(2) || 0
  const band = api.value(3) || 0
  const g = bandGeom[band]
  if (!g) return { type: 'group', children: [] }
  const laneH = BAND_MARKER_H * zoomFactor
  const gap = BAND_LANE_GAP * zoomFactor
  const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
  const unitW = api.size([1, 0])[0]
  const w = Math.max(5, Math.min(20, unitW * 0.35))
  return {
    type: 'polygon',
    shape: { points: [[x, centerY + 4 * zoomFactor], [x - w, centerY - 3 * zoomFactor], [x + w, centerY - 3 * zoomFactor]] },
    style: api.style(),
  }
}
```

- [ ] **Step 3: 修改 `makeRenderHighlightWithGeom` 的 point 分支 (chart.ts:794-810 附近)**

定位到 `if (!isInterval) {` 分支内, 将以下段落:

```ts
    if (!isInterval) {
      const x = api.coord([api.value(0), 0])[0]
      const band = (item?.value?.[2] as number) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const centerY = g.top + g.h / 2
```

替换为:

```ts
    if (!isInterval) {
      const x = api.coord([api.value(0), 0])[0]
      const lane = (item?.value?.[2] as number) || 0
      const band = (item?.value?.[3] as number) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const laneH = BAND_MARKER_H * zoomFactor
      const gap = BAND_LANE_GAP * zoomFactor
      const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
```

其余 (放大三角 shape 计算) 保持不变。

- [ ] **Step 4: 修改 `makeRenderShiftVeil` 的 point 分支 (chart.ts:845-872)**

定位到 `if (item.kind === 'point') {` 分支, 将以下段落:

```ts
    if (item.kind === 'point') {
      // 参 renderPointWithGeom:三角 polygon,底顶点在下、两上角在上
      const x = api.coord([api.value(0), 0])[0]
      const band = api.value(2) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const centerY = g.top + g.h / 2
```

替换为:

```ts
    if (item.kind === 'point') {
      // 参 renderPointWithGeom:三角 polygon,底顶点在下、两上角在上
      const x = api.coord([api.value(0), 0])[0]
      const lane = api.value(2) || 0
      const band = api.value(3) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const laneH = BAND_MARKER_H * zoomFactor
      const gap = BAND_LANE_GAP * zoomFactor
      const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
```

其余 (三角 points / 白蒙 shape / 黑横线) 保持不变——lineLen / 三角 shape 都基于 centerY, 自动跟随新 y。

### 2.2 更新测试断言

- [ ] **Step 5: 更新 chart.spec.ts 中 pointData shape 断言**

编辑 `path2_web_ui/tests/chart.spec.ts:773-775`, 将:

```ts
    const tb16 = bundle.pointData.find((d: any) => d.event_id === 'tb16')!
    expect(tb16.value[2]).toBe(1)    // band:tagList 空间本应是 2
    expect(tb16.value[3]).toBe(2)    // nBands
```

替换为:

```ts
    const tb16 = bundle.pointData.find((d: any) => d.event_id === 'tb16')!
    // pointData.value 新 shape (spec 2026-07-13):[start, start, lane, band, nBands]
    expect(typeof tb16.value[2]).toBe('number')   // lane (>=0, 具体值取决于同 band 内 pack 顺序)
    expect(tb16.value[3]).toBe(1)                  // band:tagList 空间本应是 2
    expect(tb16.value[4]).toBe(2)                  // nBands
```

- [ ] **Step 6: 更新 renderPointWithGeom 单测的 fakeApi (chart.spec.ts:913-932)**

将该 `it(...)` 用例整体替换为:

```ts
  it('renderPointWithGeom(_, _, bandGeom, 2):三角 y 偏移 +4/-3 全按 factor,半宽 x 不变;lane 决定 centerY', () => {
    const fakeApi: any = {
      value: (i: number) => [10, 10, 0, 0][i] ?? 0,   // [x, x, lane=0, band=0]
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 0, 200],
      size: () => [10, 0],
      style: () => ({}),
    }
    // band top=20 h=40 → lane0 centerY = 20 + BAND_TOP_PAD(4) + 0*(7*z+2*z) + 7*z/2
    // z=2 → centerY = 20 + 4 + 0 + 7 = 31;offsets +4*2 / -3*2
    const shape = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom, 2)
    expect(shape.type).toBe('polygon')
    const pts = shape.shape.points
    expect(pts[0][1]).toBe(31 + 8)   // 39
    expect(pts[1][1]).toBe(31 - 6)   // 25
    expect(pts[2][1]).toBe(31 - 6)   // 25
    // 单参 backward-compat(z=1):centerY = 20 + 4 + 0 + 3.5 = 27.5
    const shape1 = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom)
    expect(shape1.shape.points[0][1]).toBe(27.5 + 4)   // 31.5
    expect(shape1.shape.points[1][1]).toBe(27.5 - 3)   // 24.5
  })

  it('renderPointWithGeom lane=2:centerY 随 lane 递增 (BAND_MARKER_H + BAND_LANE_GAP)·z', () => {
    const fakeApi: any = {
      value: (i: number) => [10, 10, 2, 0][i] ?? 0,   // [x, x, lane=2, band=0]
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 0, 200],
      size: () => [10, 0],
      style: () => ({}),
    }
    // z=1:centerY = 20 + 4 + 2*(7+2) + 7/2 = 20+4+18+3.5 = 45.5
    const shape = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom)
    expect(shape.shape.points[0][1]).toBe(45.5 + 4)   // 49.5
    expect(shape.shape.points[1][1]).toBe(45.5 - 3)   // 42.5
  })
```

注意:此测试假设 `bandGeom` 是 `[{ top: 20, h: 40, laneCount: N }]`。核对 chart.spec.ts 顶部 fixture:

```bash
grep -n "^const bandGeom\|const bandGeom =" path2_web_ui/tests/chart.spec.ts
```

若 `bandGeom` 是 `[{ top: 20, h: 40, laneCount: 1 }]`, 上述算数正确;若不是 `top=20, h=40`, 相应调整测试期望值 (用同一公式:`centerY = top + 4 + lane * (7*z + 2*z) + 7*z/2`)。

- [ ] **Step 7: 更新 makeRenderHighlightWithGeom point 分支单测 (chart.spec.ts:934-947)**

将该 `it(...)` 用例整体替换为:

```ts
  it('makeRenderHighlightWithGeom(items, bandGeom, 2) point 分支:放大版高 +6/-4 按 factor;lane 决定 centerY', () => {
    const fakeApi: any = { value: () => 0, coord: () => [100, 200], size: () => [10, 0] }
    // pointData 新 shape:[start, start, lane, band, nBands]
    // band top=20 h=20 → lane0 centerY = 20 + 4 + 0*(7*z+2*z) + 7*z/2 = 24 + 3.5*z
    // z=2 → centerY = 24 + 7 = 31;offsets +6*2 / -4*2
    const items = [{ value: [0, 0, 0, 0, 1], event_id: 'e1', itemStyle: { color: '#22c55e' }, kind: 'group' as const }]
    const shape = makeRenderHighlightWithGeom(items, [{ top: 20, h: 20, laneCount: 1 }], 2)({ dataIndex: 0 }, fakeApi) as any
    expect(shape.shape.points[0][1]).toBe(31 + 12)   // 43
    expect(shape.shape.points[1][1]).toBe(31 - 8)    // 23
    expect(shape.shape.points[2][1]).toBe(31 - 8)    // 23
    // 单参 backward-compat(z=1):centerY = 24 + 3.5 = 27.5
    const shape1 = makeRenderHighlightWithGeom(items, [{ top: 20, h: 20, laneCount: 1 }])({ dataIndex: 0 }, fakeApi) as any
    expect(shape1.shape.points[0][1]).toBe(27.5 + 6)   // 33.5
    expect(shape1.shape.points[1][1]).toBe(27.5 - 4)   // 23.5
  })
```

### 2.3 验证 + 提交

- [ ] **Step 8: 跑 chart 相关测试**

Run: `cd path2_web_ui && npx vitest run tests/chart.spec.ts tests/geometry.spec.ts`

Expected: 全部通过。若失败, 优先检查:
- pointData/intervalData 记录中 `value` 数组的元素顺序是否为 `[start, end, lane, band, nBands]`。
- fakeApi 的 `value: (i) => ...` 是否覆盖了 index 3。
- bandGeom fixture 的 top/h 值是否与算数一致。

- [ ] **Step 9: 跑全 vitest 抓 pointData 相关的其它测试红点**

Run: `cd path2_web_ui && npx vitest run`

Expected: 若有其它测试引用 `pointData.value[?]` 的旧位置断言, 会红。已知覆盖:
- `chart.spec.ts:71-72` 用 `d.event_id === 'tb_1'` 匹配, 不依赖 shape, 免疫。
- `chart.spec.ts:193, 205, 219, 222, 224, 773-778, 810` 都是 event_id 匹配, 免疫。
- `render.chart.marker-highlight.spec.ts:38, 47` 使用 `[...bundle.pointData, ...]`, 若断言只看 event_id/kind/存在性, 免疫。

若出现新红点, 定位方式:`grep -n "pointData\[" path2_web_ui/tests/` 或 `grep -n "\.value\[2\]\|\.value\[3\]" path2_web_ui/tests/`。修复原则:

- 断言 pointData `value[2]` 为 band → 改为 `value[3]` (新 band 位置)。
- 断言 pointData `value[3]` 为 nBands → 改为 `value[4]` (新 nBands 位置)。
- 断言 pointData `value[2]` 为 lane → 保留 (新 lane 位置就是 value[2])。
- fakeApi 对 renderPointWithGeom / shift-veil-point 的 `value: (i) => [x, x][i]` → 扩展为 `[x, x, lane, band]`。

记录到 Step 10 commit message 里。

- [ ] **Step 10: 提交**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart.spec.ts
git commit -m "$(cat <<'EOF'
feat(chart): spot 与 span 统一 packLanes,消除同 band 视觉重叠 bug

- computeEventData: [...intervals, ...points] 合并送 packByBand
- pointData.value shape: [start, start, lane, band, nBands] (5 元组)
- renderPointWithGeom / highlight point 分支 / shift-veil point 分支:
  centerY 从 band 中心改为 lane 中心公式
- 测试:pointData shape 断言迁移、新增 lane>0 用例

spec: docs/superpowers/specs/2026-07-13-spot-span-unified-lanes-design.md
EOF
)"
```

---

## Task 3: KlineChart.vue bandLaneCounts 简化

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue:249-257`

**Interfaces:**
- Consumes: Task 2 产出的 pointData.value[3] = band, intervalData.value[3] = band。
- Produces: bandLaneCounts 计算移除"hasPoint ? 1 : 0"补丁。行为等价 (spot 现已参与 lane 计数)。

- [ ] **Step 1: 修改 bandLaneCounts 计算**

编辑 `path2_web_ui/src/components/KlineChart.vue` 第 249-257 行, 将:

```ts
  const bandLaneCounts: number[] = subTags.map((_, band) => {
    let maxLane = 0
    for (const d of bundle.intervalData) {
      if (d.value[3] === band && d.value[2] + 1 > maxLane) maxLane = d.value[2] + 1
    }
    // points lane 恒 0 → +1
    const hasPoint = bundle.pointData.some((d: any) => d.value[2] === band)
    return Math.max(maxLane, hasPoint ? 1 : 0)
  })
```

替换为:

```ts
  const bandLaneCounts: number[] = subTags.map((_, band) => {
    // spec 2026-07-13:spot 与 span 已合并 packLanes,统一读 value[3]=band, value[2]=lane
    let maxLane = -1
    for (const d of [...bundle.intervalData, ...bundle.pointData]) {
      if (d.value[3] === band && d.value[2] > maxLane) maxLane = d.value[2]
    }
    return maxLane + 1
  })
```

- [ ] **Step 2: 跑 vitest 全测**

Run: `cd path2_web_ui && npx vitest run`

Expected: 全部通过。如果 subGeometry 类测试通过 (subGeometry 契约未变), 且 chart.spec 通过 (Task 2 已处理), 此改动是纯计算等价 (spot 现已产生 lane, 无需外部补丁)。

- [ ] **Step 3: 提交**

```bash
git add path2_web_ui/src/components/KlineChart.vue
git commit -m "refactor(kline): bandLaneCounts 从合并 events 统一派生,移除 hasPoint 补丁"
```

---

## Task 4: 全绿闸 + Playwright 视觉验收

**Files:**
- 无源码改动, 仅验证

**Interfaces:**
- Consumes: Task 1-3 的全部改动。
- Produces: 交付判据的 4 个 gate 全绿证据。

- [ ] **Step 1: 全 vitest**

Run: `cd path2_web_ui && npx vitest run`

Expected: 0 failed. 若有失败, 回 Task 2/3 定位。

- [ ] **Step 2: TypeScript 检查**

Run: `cd path2_web_ui && npx vue-tsc --noEmit`

Expected: 0 error.

- [ ] **Step 3: 构建**

Run: `cd path2_web_ui && npx vite build`

Expected: 构建成功, 无错误。

- [ ] **Step 4: Playwright 视觉验收准备**

启动前后端:

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && uv run python scripts/run_path2_web.py
```

后台运行, 后端默认 8000, 前端默认 5173 (核对 `scripts/run_path2_web.py` 的输出)。

- [ ] **Step 5: 选一个已知含 spot + span 同 start_idx 的 (pattern, ticker, 窗口)**

从 configs 里选个含 tb (spot) 与 trend / bo_burst (span) 的 pattern 跑扫描。若不确定选哪个, 用 `bottom_breakout_burst` (path2_apps/bottom_breakout_burst/), 触发一次扫描后从命中中挑一个 marker 密集的 (ticker, 命中)。

- [ ] **Step 6: 用 playwright MCP 截图副图区域**

```
browser_resize(2560, 1440)
browser_navigate("http://localhost:5173")
# 选 pattern → 触发扫描 → 打开命中的 K 线图
browser_take_screenshot(fullPage=False, element="副图容器", ref=".sub-outer", scale="device")
```

副图容器 selector 为 `.sub-outer` (KlineChart.vue:7, 含分界条 + 副图 ECharts 实例, 便于对照)。若 `.sub-outer` 命中不到, 退回 `.sub-inner` (KlineChart.vue:23, 纯 ECharts 容器)。

Expected: 副图 band 内, spot 三角与 span 矩形在垂直方向清晰分离, 无重叠。若发现在同 band 同 start_idx 上仍重叠, 属于回归, 回 Task 2 排查 renderer / pointData shape。

- [ ] **Step 7: Playwright 卫生清理**

```bash
rm -rf /home/yu/PycharmProjects/Trade_Strategy/.playwright-mcp/*
```

- [ ] **Step 8: 停后端进程 (若需要)**

如果 Step 4 起了后台进程, 按 CLAUDE.md 惯例清理。

- [ ] **Step 9: 不做单独 commit** (验证 gate 无产出)

若 Step 6 视觉验收未通过, 修 → 回 Task 2/3 → 重跑 Task 4 全部 Step。
