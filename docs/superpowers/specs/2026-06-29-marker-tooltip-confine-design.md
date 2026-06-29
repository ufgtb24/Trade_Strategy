# Marker Tooltip Confine — Design

**日期**：2026-06-29
**范围**：path2_web 前端，`chart.ts` 内 `tooltip` 与 `markerTooltip` 两个 ECharts tooltip 配置对象
**不在范围**：tooltip 内容、formatter 逻辑、字号、间距

---

## 1. 背景与现状

`buildMarkerTooltipFormatter` 整治落地后（[[2026-06-29-marker-tooltip-cleanup-design]]），marker tooltip 含三段内容（身份 / 诊断 / 属性），整体高度比原先增加。真实数据 hover 测试发现 tooltip 在 chart 容器底部 hover 时，"Attributes" 段头及其下行被截断（截图场景：burst event marker 在主图底部、tooltip 默认向下右展开 → 超出 chart 容器底边界）。

当前 tooltip 配置（`path2_web_ui/src/render/chart.ts:237-252`）：

- 全局 K bar tooltip：仅有 `trigger / axisPointer / formatter`
- Marker tooltip：仅有 `trigger / formatter`

**无任何防溢出配置**。ECharts 默认按"鼠标右下"渲染 tooltip，遇 chart 容器边界会被裁剪。

## 2. 整治目标

让 tooltip 在 chart 容器内自动重定位、永不被边界截断。零内容变化、零额外依赖。

## 3. 设计

### 3.1 改动

**K bar tooltip**（chart.ts:237-248）配置对象顶层加 `confine: true`：

```ts
const tooltip = {
  trigger: 'axis' as const,
  confine: true,           // ← 新增
  axisPointer: {
    type: 'line' as const,
    lineStyle: { color: '#0088CC', type: 'dashed', width: 1.5, opacity: 0.7 },
    label: { show: false },
    snap: true,
  },
  formatter: buildBarTooltipFormatter(bars, ctrlState),
}
```

**Marker tooltip**（chart.ts:250-252）同样加 `confine: true`：

```ts
const markerTooltip = (tooltipResolver || matchLabel)
  ? { trigger: 'item' as const, confine: true, formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel) }
  : undefined
```

### 3.2 ECharts 行为

`confine: true` 是 ECharts tooltip 原生选项。开启后，渲染器在每次 tooltip show 时检测内容矩形与 chart 容器矩形的相对位置，若内容向下/向右超出，自动翻转方向（向上/向左展开），整块 tooltip 保持完全可见。

不影响内容、formatter、字号、间距；纯位置约束。

### 3.3 测试

`path2_web_ui/tests/chart.spec.ts` D2 块新增两个 case：

```ts
it('global tooltip has confine: true to prevent overflow', () => {
  const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
  const tt = opt.tooltip as any
  expect(tt.confine).toBe(true)
})

it('marker series tooltip has confine: true to prevent overflow', () => {
  const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
  const series = opt.series as any[]
  const points = series.find((s: any) => s.name === 'points')
  expect(points.tooltip.confine).toBe(true)
})
```

### 3.4 验收标准

- vitest 全集绿（新增 2 case + 零回归）
- `pnpm vue-tsc --noEmit` 绿
- `pnpm build` 绿
- 真实数据复现该截图场景：hover burst marker（截图同位置）时整块 tooltip 完全可见、Attributes 段头不再被截断

## 4. 备选方案讨论（决策记录）

- **`appendToBody: true`**：tooltip DOM 提到 document.body 摆脱 chart 边界。但本场景溢出是 chart 容器边界、不是 window 边界，confine 已够；且 appendToBody 在 grid 多子图 / sidebar 邻接场景可能引入 DOM 层级冲突。否决。
- **`position` 函数自定义位置**：函数式控制 `position(point, params, dom, rect, size)`，可基于 `size.viewSize - size.contentSize` 手算。最细粒度但代码量大，仅在 confine 后仍有遗留问题时再考虑。当前否决。

## 5. Out of Scope

- tooltip 内容、formatter、字号、间距
- 其他 chart 元素（markLine / markArea / dataZoom）
- 拓扑面板 / DetailSidebar 的 tooltip（如有）

## 6. 参考

- `path2_web_ui/src/render/chart.ts:237-252` — tooltip 与 markerTooltip 配置
- `path2_web_ui/tests/chart.spec.ts:365-448` — D2 tooltipResolver 集成测试
- [[2026-06-29-marker-tooltip-cleanup-design]] — 前置 spec，导致 tooltip 内容增大触发本溢出问题
