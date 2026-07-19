# 入口 D shift marker 视觉重设计(变浅 + 黑横线)· 设计

**日期**:2026-07-11
**范围**:path2_web_ui · 修正入口 D shift+click marker 视觉表达
**前置**:`docs/superpowers/specs/2026-07-10-shift-pair-feedback-design.md`(入口 D 沉默期反馈初版,已实施,commit ad26a23..d7e7c99)

---

## 背景

初版实施(2026-07-10 spec)在 shift 命中的 marker 上叠加 **金黄描边**(`borderColor='#fbbf24' + borderWidth=2`),用 `render/chart.ts::shiftItemStyleFor` helper 直接 mutate 本体 marker 的 `itemStyle`。上线后暴露两个问题:

**问题 1:黄色描边不明显**
`#fbbf24` 在很多角色色(matched 层 tier 色 = 角色本色,detected/qualified 层 = 灰)之上视觉可辨性弱,单独 shift 命中时用户不易注意到。

**问题 2:与 group 选中黑边冲突且被完全遮盖**
既有 highlight overlay 三通道(`group` / `focus` / `pendingDisambig`,`z2: 21`,`render/chart.ts::buildHlShape`)是**放大实心版**盖在本体 marker 之上——把本体 marker 连同 Task 4 加的黄边一起遮住。所以 shift+click 一个已经在 group 选中集里的 marker,黄边**完全不显示**,不是描边色不对,是 z 层遮盖。

**用户结论**(2026-07-11 brainstorm):
- 换视觉表达为 **fill 变浅 + marker 内一条黑横线**,两者互补
- 变浅原因:黑横线在深色 marker 上撞色不清
- 黑横线原因:变浅无对照物时无语义(shift 只选 1 个时看不出"浅")

---

## 决策(brainstorm 已锁)

| # | 决策点 | 结论 |
| --- | --- | --- |
| 1 | 层叠架构 | **独立 shift-veil overlay**,`z2: 22`,压过既有 highlight overlay(21);不再 mutate 本体 marker itemStyle |
| 2 | 视觉主体 | **两层 group children**:底层半透明白蒙 fill + 上层黑横线,四种几何(point/interval/pricePoint/satellite)各自渲染 |
| 3 | 白蒙参数 | `rgba(255,255,255,0.45)`,`stroke: 'none'` |
| 4 | 黑横线参数 | `stroke: '#000000'`,`lineWidth = HL_FOCUS_STROKE_WIDTH`(与 focus 深边同宽,当前值 2.5px;复用 chart.ts 既有常量,防未来漂移),`length = marker 宽度 × 0.7`(长度比例可视觉微调) |
| 5 | 事件穿透 | `silent: true`(与既有 highlight overlay 惯例一致,hover/click 穿透到本体系列) |
| 6 | 覆盖范围 | 沿用现有 `shiftSelectedEventIds` computed,length ∈ {1, 2} 全期段染;清空由 clearFocus / clearShiftSelection / clearDetailCard 三条既有路径负责 |
| 7 | 弃案(YAGNI) | 跨图连线 SVG overlay · 射线 · 色计算(lighten)· 动画/呼吸 · 公共 CSS 抽层 |

---

## 视觉正交性

既有 highlight overlay 三通道不动(全部保留原视觉),shift-veil 独立通道叠加其上。任意组合下两通道信号并存:

| 组合 | 视觉表现 |
| --- | --- |
| shift only | 变浅 fill + 黑横线 |
| shift + group | group 深细边(slate-800, 1.5px)+ 阴影完好;内部 fill 变浅 + 黑横线 |
| shift + focus | focus 粗深边(slate-800, 2.5px)+ 阴影完好;内部变浅 + 黑横线 |
| shift + pending | pending 白底 + 琥珀边 + 闪烁本色;叠加变浅 + 黑横线(edge case,视觉密集但两通道信号仍并存,不冲突) |

**正交性关键**:
- 黑横线走 stroke,画在 shape **内部水平线**上;既有 highlight overlay 的深边走 stroke,画在 shape **轮廓**上——两条 stroke 空间上不重合,不冲突
- 白蒙走 fill,冲淡的是本体 marker + highlight overlay 的 fill;stroke(深边、阴影、pending 琥珀边)不受影响

**单击场景的对照物问题解决**:
- 变浅需要对照物才能识别"浅"—— 单 shift(length=1)时无对照
- 黑横线是绝对信号:marker 内出现一条黑横线 = shift 命中,不需要对照物
- 两层叠加:变浅让黑横线更清晰(浅底衬深线),黑横线保证信号绝对可辨

---

## 架构

### shift-veil custom series

参照既有 highlight overlay(`chart.ts::buildHlShape` + `makeRenderPricePointHighlight` + `makeRenderHighlightWithGeom`)的双 renderer 模式:

- **主图**(grid0,price-anchored):`shift-veil-price` custom series
  - 数据源:`bundle.veilPriceData`(pricePoint + satellite 命中的条目)
  - renderer:`makeRenderShiftVeilPrice`
  - `z: 22`,`animation: false`,`xAxisIndex: 0`,`yAxisIndex: 0`
- **副图**(band-anchored):`shift-veil` custom series
  - 数据源:`bundle.veilData`(point + interval 命中的条目)
  - renderer:`makeRenderShiftVeil`
  - `z: 22`,`animation: false`
- 两 series 都 `silent: true`

### EventBundle 扩展

```ts
export interface EventBundle {
  pointData: any[]
  intervalData: any[]
  pricePointData: any[]
  satelliteData: any[]
  bracketData: any[]
  highlightData: any[]
  highlightPriceData: any[]
  veilData: any[]          // ★ 新增(副图 point + interval)
  veilPriceData: any[]     // ★ 新增(主图 pricePoint + satellite)
  candle: number[][]
  volume: number[]
  dates: string[]
}
```

每个 veil 条目携带:
- `value`:与本体 marker 相同的 value(供 renderer `api.value(i)` / `api.coord` 换算屏幕坐标)
- `event_id`:标识 + 断言用
- `kind`:`'point' | 'interval' | 'pricePoint' | 'satellite'`(供 renderer 分支)
- `anchorY` / `hasPks`(仅 pricePoint 需要,同既有 pricePointData 结构)

### computeEventData 装配

在既有 4 种 marker 数据装配之后、既有 highlight overlay 三分支之后,新增 veil 装配段:

```ts
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

### renderer 工厂

**`makeRenderShiftVeil`**(副图 point / interval):
- 派生 shape:point → 三角形(参照 `renderPointWithGeom`);interval → 矩形(参照 `renderIntervalWithGeom`)
- 输出 `{ type: 'group', silent: true, z2: 22, children: [veilShape, blackLine] }`
  - `veilShape`:同 shape,`style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' }`
  - `blackLine`:`{ type: 'line', shape: { x1, y1, x2, y2 }, style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } }`(复用 chart.ts 既有常量,与 focus 深边同宽)
    - point(三角):水平线穿过三角形中心,长度 = 三角形半宽 × 2 × 0.7
    - interval(矩形):水平中线,长度 = 矩形宽度 × 0.7

**`makeRenderShiftVeilPrice`**(主图 pricePoint / satellite):
- 派生 shape:pricePoint → 圆角矩形(参照 `renderPricePoint` / `makeRenderPricePointHighlight` 的 `boBoxDims`);satellite → 圆
- 输出 group,同上双 children 结构:
  - pricePoint:圆角矩形白蒙 + 水平中线(长度 = box 宽度 × 0.7)
  - satellite:圆白蒙 + 水平直径线(长度 = 直径 × 0.7)

### series 装配

`buildSubOption`(参 chart.ts:544 附近既有 series 装配):

```ts
{ type: 'custom', name: 'shift-veil', xAxisIndex: 1, yAxisIndex: 1,
  data: veilData, animation: false, silent: true,
  renderItem: (p: any, api: any) =>
    makeRenderShiftVeil(veilData, subGeom.bandGeom, z)(p, api),
  z: 22 },
```

`buildMainOption`(参 chart.ts:373 附近):

```ts
{ type: 'custom', name: 'shift-veil-price', xAxisIndex: 0, yAxisIndex: 0,
  data: veilPriceData, animation: false, silent: true,
  renderItem: makeRenderShiftVeilPrice(veilPriceData),
  z: 22 },
```

---

## 回滚 Task 4 旧路径

`render/chart.ts` 需要**删除**以下代码(2026-07-10 spec Task 4 落地):

1. `computeEventData` 顶部解构里的 `shiftSelectedEventIds` 消费 + `shiftItemStyleFor` helper 定义:

   删除:
   ```ts
   shiftSelectedEventIds: _shiftSelectedEventIds } = input
   ...
   const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
   const shiftItemStyleFor = (event_id: string, base: Record<string, unknown>) =>
     shiftSelectedEventIds.has(event_id)
       ? { ...base, borderColor: '#fbbf24', borderWidth: 2 }
       : base
   ```

2. 4 处 map 装配里对 `shiftItemStyleFor` 的调用,回改为原始 `itemStyle: { color: eColor(e) }`(pointData / intervalData / pricePointData / satelliteData)

**保留**:
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>` 字段本身(新方案继续消费)
- `computeEventData` 顶部对 `shiftSelectedEventIds` 的解构与 `?? new Set<string>()` fallback(新方案继续用)
- KlineChart.vue 传参路径(Task 5 落地的透传逻辑)
- view store 的 `shiftSelectedEventIds` computed + Task 1 补丁(clearFocus / clearShiftSelection / shiftPairPending)
- ShiftPairBanner.vue 组件

---

## 文件改动清单

**修改**:
- `path2_web_ui/src/render/chart.ts`:
  - 删除 `shiftItemStyleFor` helper 与 4 处调用(回滚 Task 4 mutate 路径)
  - `EventBundle` interface 加 `veilData` / `veilPriceData` 字段
  - `computeEventData` 装配 `veilData` / `veilPriceData`(在既有 highlight overlay 装配之后)
  - `computeEventData` return 加两字段
  - 新增 `makeRenderShiftVeil`(副图 point + interval renderer 工厂)
  - 新增 `makeRenderShiftVeilPrice`(主图 pricePoint + satellite renderer 工厂)
  - `buildSubOption` 追加 `shift-veil` custom series 装配
  - `buildMainOption` 追加 `shift-veil-price` custom series 装配

**测试**:
- `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`:
  - 删除断言 `itemStyle.borderColor === '#fbbf24'` / `itemStyle.borderWidth === 2`
  - 新增断言:`bundle.veilData` / `bundle.veilPriceData` 里含目标 event_id + 对应 `kind`
  - shiftSelectedEventIds undefined / 空集时 `veilData` / `veilPriceData` 为空(向后兼容)
- `path2_web_ui/e2e/shift-pair-feedback.spec.ts`:
  - 场景 1 断言改用 `page.evaluate` 读 `__e2e.chartSub().getOption().series.find(s => s.name === 'shift-veil').data` 非空且含 event_id;主图 pricePoint/satellite 命中类似,读 `chartMain()` 的 `shift-veil-price`
  - 或改用 `toHaveScreenshot` 视觉快照对照(依项目 e2e 现行惯例)

**不动**:
- `src/stores/view.ts`(shiftSelectedEventIds computed / clearFocus 补丁 / setShiftSelectedEvents 均不变)
- `src/components/ShiftPairBanner.vue`
- `src/components/KlineChart.vue`(shiftSelectedEventIds storeToRefs 与传参不变)
- 其他 highlight overlay(group / focus / pendingDisambig)相关代码

---

## 边缘情况

| 场景 | 处理 |
| --- | --- |
| shift 命中的 marker 因 level 门控 / roleVisible 而被过滤 | 走既有 `filtered` 逻辑;`shiftSelectedEventIds` 里含但 pointData/intervalData/pricePointData/satelliteData 里不含 → veilData 空 → 不画。banner 仍显示(与本体 marker 可见性解耦,与既有黄边行为一致) |
| shift + pending 共存 | 白蒙叠加在 pending 的白底+闪烁本色之上,pending 闪烁被弱化(视觉密集,edge case,不特殊处理) |
| shift 命中但 event 在 zoom 视口外 | ECharts custom series 自动裁剪,veil 也不画;shift 状态不变 |
| 主副图 divider 拖拽 / band-zoom 变化 | veil renderer 与既有 renderPointWithGeom / renderIntervalWithGeom 一样按 `bandGeom` / `z` 派生,自动跟随 |
| 三角形黑横线穿过尖端时的视觉 | point renderer 里三角形是尖端朝下(BandRow 上端向下伸)或朝上(依 renderPointWithGeom 现行);黑横线穿过三角形几何中心(即 renderPointWithGeom 里的 top + bandH/2 位置),不穿尖端 |

---

## 测试与验收

### 单元 / 组件测

- `computeEventData` 4 种几何 × {shiftSelectedEventIds 命中 vs 未命中} = 8 分支:
  - 命中 → veilData / veilPriceData 里含条目,`kind` 正确,`event_id` 正确
  - 未命中 → veil 里不含该 event_id
- `shiftSelectedEventIds` undefined / 空集时,veilData / veilPriceData 为空(向后兼容)
- 4 处 map 装配中 `itemStyle` **不带** `borderColor` / `borderWidth`(旧 Task 4 mutate 路径彻底移除)

### Playwright e2e(承 2026-07-10 spec 5 场景)

- **场景 1** 断言重写:shift+click 后主图 / 副图相应 chart option 的 `shift-veil-price` / `shift-veil` series 数据非空,且 renderer 输出 group 里有 fill 为 `rgba(255,255,255,0.45)` 的 shape + stroke 为 `#000000` 的 line(或改用 screenshot 快照对照)
- **场景 2 / 3 / 4 / 5**:与 2026-07-10 spec 一致,断言 banner + 累积器 length + PairDetailCard 显隐;shift-veil series 数据同步随累积器变化(空 → 非空 → 空)

### 验收标准

- 全套 vitest 绿(基线 517 + 新增变动净数)
- vue-tsc --noEmit 无 error
- npm run build 无 error
- 5 条 Playwright 场景全通过
- 视觉验收(实施时用 playwright MCP 截图存证):
  - 单击 shift → marker 变浅 + 黑横线可辨
  - shift + group 选中同一 marker → group 深细边+阴影完好,内部变浅+黑横线
  - 深色角色色(如 matched 层 slate-800)与浅色角色色(如 detected 层浅灰)上,黑横线都清晰可见

---

## 未纳入(YAGNI)

- **跨图连线**(brainstorm 曾评估的 SVG DOM overlay 方案):代价明显高,且第 2 击后 pair query 立刻返回、连线存续期极短,ROI 低
- **单击射线**(brainstorm 曾评估的 60-100px 短虚线):"变浅 + 黑横线"已表达 shift 命中语义;射线独立引导下一步,YAGNI
- **动画 / 呼吸**:静态视觉信号足够,动画增加视觉噪音
- **黑横线色计算 lighten**:黑色 `#000000` 绝对信号,不需要按 tier / role 调
- **白蒙透明度动态**:固定 0.45,不按 tier 分档
- **公共 CSS 抽层**:纯 chart.ts 内部,无 Vue 组件 CSS 联动

---

## Handoff

**执行方式**:subagent-driven(承 2026-07-10 spec 惯例)
**Implementer 模型**:sonnet
**Reviewer 模型**:opus
