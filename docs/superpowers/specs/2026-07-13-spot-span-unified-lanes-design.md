# spot 与 span 统一 lane 语义 (path2_web_ui 副图)

日期: 2026-07-13
状态: brainstorming 定稿, 待 writing-plans

## 1 · 背景与问题

path2_web_ui 副图 (chartSub) 每个 band 内摆放两类 marker:

- **span** (start_idx < end_idx): 走 `packByBand → packLanes` 贪心分 lane, 渲染为 rect, 从 band 顶部往下按 lane 号堆叠。
- **spot** (start_idx === end_idx): 不参与 lane packing, 渲染为三角形, 一律画在 band 几何正中 `centerY = g.top + g.h / 2`。

**观察到的 bug**: 当某 band 内某条 span 的 lane 恰好落在几何中线附近, 会与同 band 的 spot 三角发生垂直位置重叠 (spot 三角与 span 矩形挤在同一 y), 读者无法辨认哪个是"点"哪个是"段"、也无法准确点中较小的 spot。与两个 event 的 start_idx 是否相等无关——只要 span 的时间跨度覆盖 spot 的 x 位置且 lane 落在中线附近, 就会重叠。

**根因**: spot 与 span 走两条互不感知的 y 位置计算路径 (splitGeometry 前置分流), 缺乏"同 band 内不重叠"的统一保证。

## 2 · 目标

- 同 band 内 spot 与 span 的 marker 永不视觉重叠。
- 保留 spot / span 的形状区分 (三角 vs 矩形), 不引入新形状。
- 交互 (点选/hover/tooltip/高亮) 语义不变——所有交互只依赖 `event_id`, 与 y 位置无关。
- 不改动 bracket / price-anchored / veil / tooltip / 侧栏等无关子系统。

## 3 · 核心机制变更

将"splitGeometry → 两条独立 y 路径"替换为"合并 packLanes → 按形状拆分渲染"。

### 3.1 合并 packing

`packByBand` 的输入从 `intervals` 扩展为 `[...intervals, ...points]` (二者一并进入同一次 packLanes 调用)。同 band 内 spot 与 span 按 start_idx 升序交错分 lane, packLanes 的 strict `<` 语义 (geometry.ts:23) 保证同 start_idx 的两 event (无论 spot/span) 一定分到不同 lane, 零重叠。

`splitGeometry` (geometry.ts:6-11) 仍保留, 但用途从"分流到不同 y 路径"降级为"分组投喂不同 renderer"——它在 packLanes **之后**执行, 依据 `start_idx === end_idx` 决定该 event 使用三角 renderer 还是矩形 renderer, 但 lane 号已由前一步分配好。

### 3.2 pointData 数据结构统一

`pointData.value` 从 `[start_idx, start_idx, band, nBands]` 扩展为 `[start_idx, start_idx, lane, band, nBands]`, 与 `intervalData.value = [start_idx, end_idx, lane, band, nBands]` 同 shape。

## 4 · Renderer 改动

### 4.1 `renderPointWithGeom` (chart.ts:762)

- 读 `api.value(2)` 作为 lane, `api.value(3)` 作为 band (原来 `api.value(2)` 是 band、无 lane 概念)。
- centerY 从 `g.top + g.h / 2` 改为 lane 中心公式 (与 `renderIntervalWithGeom` 同源):
  ```
  laneH = BAND_MARKER_H * zoomFactor
  gap = BAND_LANE_GAP * zoomFactor
  centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
  ```
- 三角形状/尺寸不变: 顶点相对 centerY 的偏移仍是 `+4·z / −3·z`, 半宽仍 ≤20 (乘 `zoomFactor` 常量维持 spec §4.1 语义)。

### 4.2 `renderIntervalWithGeom` (chart.ts:738)

**无需改**。原实现已按 `api.value(2)=lane / api.value(3)=band` 走 lane 公式 (chart.ts:753), 数据结构未动。

### 4.3 `makeRenderHighlightWithGeom` 的 point 分支 (chart.ts:795-806)

同源问题——当前也用 `centerY = g.top + g.h / 2`。改为读 `item.value[2]` 作为 lane、`item.value[3]` 作为 band, 用与 §4.1 完全相同的公式派生 centerY。放大版三角尺寸 (`+6·z / −4·z`, 半宽上限 28) 不变。

### 4.4 `makeRenderShiftVeil` 的 point 分支 (chart.ts:845-872)

同源问题第三处——`centerY = g.top + g.h / 2`, `band = api.value(2)`。改动:
- `band = api.value(3)`, `lane = api.value(2)` (与 pointData 新 shape 对齐)。
- centerY 用与 §4.1 相同的 lane 公式派生。
- 三角 shape 尺寸不变;黑横线的 y (`centerY`) 随 centerY 移动。

## 5 · bandLaneCounts 计算简化

**当前** (KlineChart.vue:249-257):

```ts
const bandLaneCounts: number[] = subTags.map((_, band) => {
  let maxLane = 0
  for (const d of bundle.intervalData) {
    if (d.value[3] === band && d.value[2] + 1 > maxLane) maxLane = d.value[2] + 1
  }
  const hasPoint = bundle.pointData.some((d: any) => d.value[2] === band)
  return Math.max(maxLane, hasPoint ? 1 : 0)
})
```

**简化为** (spot lane 已由合并 packing 计入):

```ts
const bandLaneCounts: number[] = subTags.map((_, band) => {
  let maxLane = -1
  for (const d of [...bundle.intervalData, ...bundle.pointData]) {
    // interval: value[3] = band, point (新): value[3] = band
    if (d.value[3] === band && d.value[2] > maxLane) maxLane = d.value[2]
  }
  return maxLane + 1
})
```

副效应: pointData 的 band 索引位置从 `value[2]` 移到 `value[3]` (与 intervalData 对齐), 上述代码统一读 `value[3]`。

## 6 · Out-of-scope

以下明确不动:

- `packBrackets` (归属带 packing) 语义, bracket 独立渲染路径。
- price-anchored events (pricePointData / satelliteData), 不进 subGeometry。
- 常量 `BAND_MARKER_H` / `BAND_LANE_GAP` / `BAND_TOP_PAD` / `BAND_BOT_PAD` 数值。
- spot 三角形状 / 颜色 / emphasis / tier 语义。
- tooltip 内容, 侧栏, 诊断面板, veil。
- 后端投影层 (path2_web) 无任何改动。

## 7 · 回归风险

1. **副图垂直高度增长**: 某些 band 若 spot 密集但 span 稀疏, `bandLaneCounts` 可能从 1 跳到 N (spot 数量), band 高度增加、整个副图高度增加, 可能触发 `factorCap` 变化 (KlineChart.vue:264+)。实施时需对现有 fixture 拉基线对比; 若跳增不合理, 回到 spec 讨论"是否为 spot 引入更小 lane stride" (默认不引入)。
2. **shift-veil 覆盖**: veil 按 bandGeom 全 band 覆盖 (chart.ts:593-596), 不涉及 marker y, 免疫。
3. **selectedEventId 高亮**: 高亮 y 与本体 y 一致 (都改), 视觉上"闪烁三角"在原 marker 位置, 不错位。
4. **bracket lane**: 独立走 `packBrackets`, 不改。
5. **cross-band 视觉一致性**: 之前所有 band 无 span 时 spot 都在中线, 现在都紧贴顶部 pad。跨 band 目视对齐会变——预期变化, 非 bug。

## 8 · 测试

### 8.1 单测更新 (path2_web_ui/tests)

- `tests/geometry.spec.ts`: 新增用例——同 band 内 spot + span 混合, 其中一 spot 与一 span 同 start_idx, 断言二者分到不同 lane。
- 引用 `pointData` 结构的测试 (grep `pointData.*value` / `value:\s*\[.*start_idx.*band.*nBands\]`): 3 元组期望改成 4 元组 (含 lane、band 位置移到 index 3)。
- `tests/subGeometry.spec.ts`: 新增用例——某 band 只含 N 个同 bar spot 时 `bandLaneCounts[band] === N` (每个 spot 独占一 lane); spot + span 同 band 时 `= max(lane) + 1`。
- `tests/chart.spec.ts` 已覆盖 `renderPointWithGeom` / `makeRenderHighlightWithGeom` point 分支: 新增 lane>0 用例, 断言 centerY 随 lane 递增。

### 8.2 fixture

构造最小 fixture (2 event: 1 spot + 1 span / 同 start_idx / 同 band) 专门给 §8.1 geometry 单测用, 避免脏染现有 fixture。

### 8.3 e2e / 视觉验收

用一个已知含 spot+span 同 start_idx 的 (ticker, 窗口) 跑 playwright 副图截图, 肉眼确认无重叠。此环节在实施完成后按 CLAUDE.md 的 playwright 惯例做, 不预跑。

## 9 · 交付判据

- 全部单测绿 (含 §8.1 新增用例)。
- `vue-tsc` / `vite build` 无错。
- playwright 视觉验收: spot 与 span 同 start_idx 场景下垂直位置分离。
- 无回归: 现有 fixture 下 bandLaneCounts 变化在预期范围 (§7.1 基线对比通过)。
