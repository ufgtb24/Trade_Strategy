# Spec — path2_web 主/副图拆分（双 ECharts 实例）+ 副图 lane 固定/band 溢出滚动 + 主副图可拖拽分区

> **状态**:brainstorm 已完成（2026-07-01 user approval 方案 B）,待 writing-plans。
> **范围**:副图 grid1 重构 —— (1) bracket 与时间轴间加主/副图 divider、(2) bracket/band 之间副图内部 divider + "matches" 左标签、(3) band 加 zebra 交替色 + 保留 role 名左标签、(4) lane 高度固定、band 高度按 lane 数动态、(5) 副图内容超出可视区时**副图独立滚动**（主图不动）、(6) 主副图之间**可拖拽 handle** 调整占比、(7) 保留贯穿主副图的鼠标垂直虚线（axisPointer 联动）。
> **前置**:2026-06-30 M+M' disambig spec 已实施完成（bracket ordinal 右移、renderBracket closure、highlight closure 全部落地）。

---

## 0. 必读上下文（实施前）

1. **当前 chart.ts 架构**:`path2_web_ui/src/render/chart.ts:66-405` `buildKlineOption` 是单大函数,产出**单一 ECharts option**,内含 `grid: [grid0, grid1]` + `xAxis: [xAxis0, xAxis1]` + `yAxis: [yAxis0, yAxis1, yAxis2]` + 10 个 series。`axisPointer.link: [{ xAxisIndex: [0, 1] }]`(chart.ts:328)是**同实例内**跨 grid 联动,拆双实例后失效,需换 `echarts.connect`。
2. **当前 KlineChart.vue**:`path2_web_ui/src/components/KlineChart.vue` 单 canvas 单 ECharts 实例;`onMounted` 内 `chart.on('click', ...)` + `chart.getZr().on('click', ...)` 分别处理 series item click 与 blank click,`chart.on('datazoom', ...)` 重算 volume/yAxis。
3. **panels store**:`path2_web_ui/src/stores/panels.ts` 现有 `showSlider` / `showSidebar` / `showTopology` 三 boolean,持久到 localStorage。本次新增 `mainSubRatio` 走同套路径。
4. **view store**:`path2_web_ui/src/stores/view.ts` 承载 selectedMatchId / candidateMatchIds / highlightedEventIds / pendingDisambigEventId 等,**不变**——所有 click 分流均写同一 view store,主/副图 chart 只是 render 层的两个消费者。
5. **e2e**:`path2_web_ui/e2e/match-event-disambig.spec.ts` 靠 `page.locator('canvas')` 定位单 canvas + `window.__e2e.chart()` 单实例。拆分后 `__e2e` 暴露 `chartMain()` 与 `chartSub()`,e2e 元素定位需按主/副图 canvas 区分。

---

## 1. 目标与用户问题

### 1.1 用户问题

副图 grid1 当前布局有五个不足:
1. **bracket ordinal ①②... 与 grid0 的 xAxis 日期 label 垂直区间重叠**(bracket 落在 grid1 顶部 +18px、xAxis label 悬到 grid1 +8~+20)
2. **band 之间无视觉分割**——多 band(bo / burst / tb)相邻但边界不显,用户识别 band 归属靠仅存的左侧 10px 文字标签
3. **band 高度平均分**(bandH = grid1.h / nBands),某 band lane 多时挤在 band 底部,靠 clamp 兜底,视觉拥挤
4. **副图高度固定**——lane 数无论多少都被压进固定 grid1.h,溢出不可见
5. **主/副图占比固定**(64%/72% 主 · 26%/24% 副)——用户想看多细节时无法把主图缩小、把副图放大

### 1.2 设计原则

- **主图始终可见**:任何滚动/交互都不能把主图推出视野
- **副图内容真溢出真滚动**:lane 一多就有滚动条,不是压缩到看不清
- **视觉边界显式**:主副图之间 + 副图内部 bracket/band 之间用同粗同色的 1px 实线明确分区
- **联动无缝可接受微断口**:鼠标垂直虚线跨主副图,`echarts.connect` 保证 x 对齐;divider 位置有 1-2px 视觉断口——是可接受的折衷
- **零改 view store 语义**:所有 click 分流仍写同一 view store;主/副 chart 各自 install 一份 click handler,handleChartClick 分流函数不变(输入 payload 相同、动作相同)

---

## 2. 布局设计

### 2.1 总体几何(垂直方向,自上而下)

```
┌─────────────────────────────────────────────────────┐
│  <div class="kline-wrap-v2"> (flex column)          │
│  ┌────────────────────────────────────────────────┐ │
│  │ <div class="main-chart" flex-basis:70%>        │ │
│  │  ECharts 主图实例 chartMain                    │ │
│  │  ├─ 价格 K 线 (candlestick)                    │ │
│  │  ├─ 成交量 (bar)                               │ │
│  │  ├─ price-points (BO 方框)                     │ │
│  │  ├─ satellites (PK 三角)                       │ │
│  │  ├─ highlight-price (grid0 高亮描边)           │ │
│  │  ├─ xAxis: dates (labels 显示)                 │ │
│  │  ├─ yAxis: price (axisLabel formatter 保留)    │ │
│  │  └─ dataZoom slider (若 showSlider)            │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ <ResizableDivider /> 4px cursor:row-resize    │ │
│  │  背景 #e0e6f1,hover 时 6px + 深色              │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ <div class="sub-outer" flex-basis:30%          │ │
│  │      overflow-y:auto position:relative>        │ │
│  │  ┌─ CandidateStatusBar sticky top:0 (仅       │ │
│  │  │    candidate 态可见,深底琥珀字,16px)        │ │
│  │  └─────────────────────────────────────────    │ │
│  │  <div class="sub-inner"                        │ │
│  │       :style="{ height: subCanvasH + 'px' }">  │ │
│  │   ECharts 副图实例 chartSub                    │ │
│  │   ┌── bracket 区(动态高度 = max_lane * 10 + 6)│ │
│  │   │  ├─ "matches" 左标签 10px #94a3b8          │ │
│  │   │  ├─ bracket rects(灰/琥珀 alpha 0.35/0.85)│ │
│  │   │  └─ ordinal ①②... 右侧 12px               │ │
│  │   ├── divider #2(bracket/band 副图内部)       │ │
│  │   │   1px 实线 #e0e6f1,居中偏 2px             │ │
│  │   └── band 区(每 band 独立高度)               │ │
│  │       ├─ zebra 交替(rgba(0,0,0,0.03) / 透明)  │ │
│  │       ├─ role 名左标签(bandLabel 复用)         │ │
│  │       └─ markers(points/intervals/highlight)  │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**主/副图 divider(divider #1)**:是 DOM 级 `<ResizableDivider />` 组件,同时兼任视觉分割线与拖拽 handle,不需要在 canvas 内再画一次。

**副图内部 divider(divider #2)**:在 chartSub canvas 内用 custom series 画,y 位置 = `16 + bracket_h + 2`(见 §2.2 公式)。xAxis 日期 label 归主图,副图无 TIME_AXIS_BUFFER。

**Canvas 内 z 层叠**(自底到顶):
| z | series | 作用 |
|---|---|---|
| 1 | bandZebra | band 交替底色 |
| 2 | subDivider | divider #2 分割线 |
| 5 | bandLabels | band 左侧 role 名 + matches 左标签 |
| 9 | intervals | interval marker |
| 10 | points | point marker |
| 11 | brackets | matched pattern bracket |
| 20 | highlight | 描边高亮(组/焦点/待消歧) |

### 2.2 副图内部几何(chartSub 局部坐标系,y=0 是 canvas 顶)

```
y = 0
├─ [0, BANNER_RESERVE) = [0, 16) — banner 预留(banner 是 DOM sticky 位于 canvas 上方并跨主+副视口,当 candidate=on 时覆盖 canvas 顶 16px;当 candidate=off 时 canvas 顶 16px 空白,布局不跳变)
├─ [16, 16 + bracket_h) — bracket 区
│   常量:BRACKET_LANE_STRIDE = 10, BRACKET_RECT_H = 6, BRACKET_BOT_PAD = 4
│   公式:bracket_h = max_lane_count × BRACKET_LANE_STRIDE + BRACKET_BOT_PAD, 空 matches 时 = 0
│   lane_i 的 rect 位置:y = 16 + i × 10, height = 6
│   例:max_lane_count=3 → bracket_h=34, 三 rect 在 [16,22)/[26,32)/[36,42), 42<50=16+34 ✓
├─ [16 + bracket_h, 16 + bracket_h + DIVIDER_GAP) 内画 1px divider #2
│   常量:DIVIDER_GAP = 4, divider y = 16 + bracket_h + 2
│   空 matches 时 bracket_h=0, divider 仍画在 y=18(视觉上直接坐在 canvas 顶,可接受)
└─ [16 + bracket_h + 4, subCanvasH) — band 区
    常量:BAND_LANE_H = 9 (复用 interval laneH=7 + gap=2)
    常量:BAND_TOP_PAD = 4, BAND_BOT_PAD = 4
    公式:band_i.h = max(BAND_MIN_H=20, laneCount_i × BAND_LANE_H + BAND_TOP_PAD + BAND_BOT_PAD)
    band_i.top = 16 + bracket_h + 4 + Σ(band_j.h for j < i)
    subCanvasH = 16 + bracket_h + 4 + Σ band_i.h
    最小 subCanvasH = SUB_CANVAS_MIN_H = 120px (空数据时不塌陷)
```

`subCanvasH` 是**内容真实需要的 px 高度**。设置到 `<div class="sub-inner">` 的 `style.height`。若 `sub-outer` 可视高度 < `subCanvasH` → `sub-outer` 的 `overflow-y:auto` 触发滚动条。

### 2.3 主/副图占比(拖拽)

- `mainSubRatio` 存储主图占外层 wrapper 高度的比例,初值 0.70(主 70% / 副 30%)
- 拖拽 divider 时,mainSubRatio 实时更新,两 chart 各自 `resize()`
- 边界钳制:`ratio ∈ [0.20, 0.85]`,防止一边完全塌到 0
- 持久化:同 `showSlider` 落 localStorage,`panels` store `setMainSubRatio(v: number)`
- 拖拽体验:`pointerdown` 起、`pointermove` 中、`pointerup` 止;`document.body.style.cursor = 'row-resize'` 期间强制、`user-select: none` 防选中文字

### 2.4 zebra + role 名左标签

**zebra**(band 区):新增 custom series `bandZebra`,每 band 一个 rect(x=cs.x,width=cs.width,y=band_i_top,height=band_i_h),`itemStyle.color` 按 band_i 索引奇偶取 `rgba(0,0,0,0.03)` / `rgba(0,0,0,0)` 交替。**z: 1**(低于所有其他 series,确保在最底层)。

**role 名左标签**:复用现有 `bandLabels` 逻辑,`makeRenderBandLabel` 内的 `bandTop`/`bandH` 从"cs.height / nBands 平均分"改为"从 `bandGeometry` 表查累积 offset + 各自 band_h"。文字位置公式:`x: cs.x + 2, y: band_i_top + band_i_h / 2`,`textVerticalAlign: 'middle'`,fill `#94a3b8` fontSize 10 保持不变。

### 2.5 "matches" 左标签

`bracket 区`只在 matches.length > 0 时显示。新增 custom series `matchesLabel`(单 data item):
- 文字位置:`x: cs.x + 2, y: 16 + bracket_h / 2`(bracket 区垂直中心)
- 样式:同 bandLabel,`fill: #94a3b8, fontSize: 10, textVerticalAlign: 'middle'`
- data 空时(matches.length === 0)series data 为 `[]`,不渲染

### 2.6 divider #2(bracket / band 副图内部)

新增 custom series `subDivider`(单 data item):
- rect:`x: cs.x, y: 16 + bracket_h + 2, width: cs.width, height: 1`
- 填色 `#e0e6f1`,无 stroke
- z: 2(在 zebra 之上、marker 之下)

### 2.7 CandidateStatusBar(banner)

- 从"CSS absolute 定位到 grid1 顶部"改为"`sub-outer` div 内的 `position: sticky; top: 0` 元素"
- v-if 保留(candidateMatchIds.size > 0 才渲染),显时 sticky 使其在副图滚动时**恒在视口顶部可见**——用户滚动查看远端 band 时不会失去 candidate 上下文
- CSS 从 CandidateStatusBar.vue 内当前 `.candidate-banner` 改为 sticky 版本(去掉 absolute + var + left/right/top,改 `position: sticky; top: 0; z-index: 5`,宽度自动跟父容器)
- KlineChart.vue 内的 `--grid1-top-px` CSS var 全部删除(不再需要)

### 2.8 主图 xAxis 日期 label

- 位置不变(chartMain grid0 底,axisLabel.margin=8)
- 因 chartMain 现在是独立实例、其容器 flex-basis 由 ratio 决定,label **不会** overflow 到 chartSub 容器(两 chart DOM 独立)
- 结果:bracket 与 xAxis label 之间的重叠**从根本上消除**(不同 DOM,不共享像素坐标系)
- 不需要 TIME_AXIS_BUFFER 常量

---

## 3. 数据流与状态管理

### 3.1 view store(不改)

`view.ts` 的 `selectedEventId / selectedMatchId / highlightedEventIds / candidateMatchIds / pendingDisambigEventId` 全部保留原样,setter / clearer 全部不改。**click 分流函数 `handleChartClick`(KlineChart.ts)也不改**:输入 `p: ChartClickPayload`,输出写 view store。主图/副图 chart 各自的 `chart.on('click', ...)` 都调 `handleChartClick(p, matches, view)`,匹配 seriesName 分流即可(主图触发的 payload 只会带 `points`/`intervals`/`brackets` 之外的 seriesName,副图触发反之——但函数逻辑对未匹配 seriesName 是 no-op,天然安全)。

### 3.2 panels store 新增

```ts
// path2_web_ui/src/stores/panels.ts
const mainSubRatio = ref<number>(loadFromLocalStorage('mainSubRatio', 0.70))
function setMainSubRatio(v: number) {
  const clamped = Math.max(0.20, Math.min(0.85, v))
  mainSubRatio.value = clamped
  saveToLocalStorage('mainSubRatio', clamped)
}
```

### 3.3 副图几何(band 累计 offset)派生

在 chart.ts 内新增纯函数:

```ts
// 输入:tagList (band 列表)、points (band-marker point events)、intervals (interval events)、
// matches (bracket)
// 输出:副图每 band 的 top offset / height 表 + bracket_h + subCanvasH
export function computeSubGeometry(
  tagList: string[],
  points: PointDatum[],       // 已 splitGeometry + band 归属
  intervals: PackedInterval[], // 已 packByBand
  matches: MatchDict[],
): {
  bracketH: number;              // max_bracket_lane * 10 + 6, 至少 10
  bandGeom: Array<{ top: number; h: number; laneCount: number }>;
  subCanvasH: number;
  dividerY: number;              // divider #2 y 位置
}
```

其中:
- `max_bracket_lane` 从 `packBrackets(matches)` 结果的最大 lane + 1 得到
- `laneCount_i` = max(该 band 内 point 的 lane、该 band 内 interval 的 max lane) + 1;点事件 lane 恒 0 → laneCount 至少 1
- band_h_i = max(20, laneCount_i × 9 + 8)(下限 20px 保左标签 role 名可读)
- subCanvasH = 16 + bracketH + 4 + Σ band_h_i,下限 120px

### 3.4 chart.ts 拆分

`buildKlineOption` 拆成两个:

**`buildMainOption(bars, priceAnchoredEvents, {...})`** ——生产主图 option
- series: kline, volume, price-points, satellites, highlight-price
- xAxis[0]: dates
- yAxis[0]: price (axisLabel formatter)
- dataZoom(inside + slider)
- grid: 单 grid,填满 chartMain 容器
- markArea 阴影(strict scan window)

**`buildSubOption(bars, timeAnchoredEvents, matches, subGeometry, {...})`** ——生产副图 option
- series: bandZebra, bandLabels, matchesLabel, subDivider, brackets, points, intervals, highlight
- xAxis: dates(labels 隐藏)
- yAxis: 隐藏 marker 轴 + 隐藏 bracket 轴
- dataZoom(inside only,不带 slider,slider 归主图)
- grid: 单 grid,顶部 16(banner 预留)、左 56 右 16、底 0
- 无 markArea

两函数共享 `pointData/intervalData/pricePointData/satelliteData/bracketData/highlightData` 的**同一份计算逻辑**(通过共享辅助函数 `computeEventData(...)` 提取),避免重复 CPU。

### 3.5 echarts.connect

`KlineChart.vue` onMounted:
```ts
chartMain = echarts.init(mainEl.value!)
chartSub = echarts.init(subInnerEl.value!)
echarts.connect([chartMain, chartSub])   // 自动同步 axisPointer + dataZoom + tooltip
```

group name 用 default(空串)即可——本页只有这一组两 chart,不会误联动其他实例。

**若 connect axisPointer 联动实测竖线断口过大**(spec §6.1 实测项),fallback 到 manual 同步:两 chart 各监听 `updateAxisPointer` 事件,重发 `dispatchAction` 给对方(但要防抖抑制回环)。

### 3.6 click 与 keyboard 事件

**click**:两 chart 各 install 一套:
```ts
chartMain.on('click', p => handleChartClick(p, matches, view))
chartSub.on('click',  p => handleChartClick(p, matches, view))
chartMain.getZr().on('click', e => { if (!e.target) handleChartClick(null, matches, view) })
chartSub.getZr().on('click',  e => { if (!e.target) handleChartClick(null, matches, view) })
```

`handleChartClick` 天然支持:brackets/points/intervals/price-points/satellites 各自 seriesName 分流,不匹配的 seriesName no-op。主图空白 click 与副图空白 click 都清四样(view.clear...),行为一致。

**Esc keydown**:`window.addEventListener('keydown', ...)` 在 KlineChart.vue 顶层保留一份(不因两 chart 拆分而复制),清四样。

**mousemove(ctrlState.mouseY)**:目前 `chart.getZr().on('mousemove', ...)` 在主图内挂,继续挂主图 chart,副图不挂——因为 mouseY 仅供主图价格线 tooltip 使用,副图无价格轴。

**datazoom(volume/yAxis 重算)**:主图 `chart.on('datazoom', ...)` 保留,重算 volSeries + yAxisOverride。副图 dataZoom 通过 connect 自动同步,副图内**不需要**listen datazoom(副图无 volume/价格轴)。

**updateAxisPointer(锁 close 横线)**:主图 `chart.on('updateAxisPointer', ...)` 保留(markLine 锁 close 是主图专属)。副图不 listen。

### 3.7 CandidateStatusBar 位置

Vue 组件从"KlineChart.vue 内 CSS absolute 定位到 grid1 顶部"改为"`<div class="sub-outer">` 内第一个子节点、`position: sticky; top: 0`"。

`KlineChart.vue` template 结构:
```vue
<template>
  <div class="kline-wrap-v2">
    <div ref="mainEl" class="main-chart" :style="{flex: mainSubRatio}" />
    <ResizableDivider @drag="onRatioDrag" />
    <div class="sub-outer" :style="{flex: 1 - mainSubRatio}" ref="subOuterEl">
      <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
      <div ref="subInnerEl" class="sub-inner" :style="{ height: subCanvasH + 'px' }" />
    </div>
  </div>
</template>
```

CandidateStatusBar CSS:
```css
.candidate-banner {
  position: sticky;
  top: 0;
  height: 16px;
  padding: 0 8px;
  background: rgba(15, 23, 42, 0.92);
  color: #fbbf24;
  border-radius: 3px;
  z-index: 5;
  pointer-events: none;
}
```

---

## 4. 改动清单（file:line）

### 4.A 新建文件

| # | 文件 | 说明 |
|---|---|---|
| N1 | `path2_web_ui/src/components/ResizableDivider.vue` | 4px 高的 drag handle,pointerdown/move/up 触发 emit('drag', delta_y);hover 时 6px 高 + 深色;`cursor: row-resize` |
| N2 | `path2_web_ui/src/components/ResizableDivider.spec.ts` | 单测:emit 触发次数 + delta 正确性 |
| N3 | `path2_web_ui/tests/computeSubGeometry.spec.ts` | 单测:各 band lane 数 0/1/3/5 时 band_h 与 subCanvasH 计算正确 |

### 4.B 修改文件

| # | 文件 | 改动摘要 |
|---|---|---|
| M1 | `path2_web_ui/src/stores/panels.ts` | 新增 `mainSubRatio` ref + `setMainSubRatio(v: number)` action + `loadFromLocalStorage/save...` 持久化。初值 0.70。 |
| M2 | `path2_web_ui/src/stores/__tests__/panels.spec.ts` | 追加 mainSubRatio 测试:边界钳制 [0.20, 0.85] + 持久化 + 初始值 |
| M3 | `path2_web_ui/src/render/chart.ts` | 拆分 `buildKlineOption` 为 `buildMainOption` + `buildSubOption`;新增 `computeSubGeometry`;新增 `computeEventData`(共享 event data 抽取);新增 `renderBandZebra` / `renderMatchesLabel` / `renderSubDivider`;`makeRenderBandLabel` 改为从 subGeometry 表查累积 offset(不再 `cs.height/nBands`);`makeRenderHighlight` / `renderPoint` / `renderInterval` 同改 band 定位来源;删除 `axisPointer.link`(拆双实例后失效)、删除 `CANDIDATE_BANNER_H` bracket 偏移(新副图局部 y=0 是 canvas 顶,banner 是 sticky DOM 元素、不占 canvas y)、删除 `TIME_AXIS_BUFFER`(主副图物理分离后消失)。原 `renderBracket` 保留(3 态 fill + 右侧 ordinal),`top` 起点改为 `params.coordSys.y + 16 + lane * 10`(16 = 副图 canvas 顶到 bracket 顶的 banner 预留,与 grid1.y 无关) |
| M4 | `path2_web_ui/src/components/KlineChart.vue` | template 改成 main-chart + ResizableDivider + sub-outer + sub-inner 三层;script `onMounted` init 两个 ECharts 实例、`echarts.connect([main, sub])`;click/blank click 各挂一套;`onRatioDrag(delta)` action 更新 panels.mainSubRatio;`subCanvasH` computed 从 `computeSubGeometry(...).subCanvasH` 派生;watch 数组同步分流(effectiveAnalysis 变 → 两 chart 各 setOption);ResizeObserver 观测两 chart 容器 + subInnerEl;`import { handleChartClick } from './KlineChart'` 保留、按 main/sub 分别调用相同函数;删除 --grid1-top-px CSS var |
| M5 | `path2_web_ui/src/components/CandidateStatusBar.vue` | CSS 从 `position: absolute + var(--grid1-top-px)` 改为 `position: sticky; top: 0`;去掉 left/right/absolute-only 相关 rule |
| M6 | `path2_web_ui/src/components/DetailSidebar.vue` | **不改**(click 分流仍走 view store) |
| M7 | `path2_web_ui/e2e/match-event-disambig.spec.ts` | 元素定位改为 `page.locator('.main-chart canvas')` 与 `page.locator('.sub-inner canvas')`;`window.__e2e.chart()` 改为 `window.__e2e.chartMain()` / `window.__e2e.chartSub()`;三条 test 各自识别在哪个 chart 上找 series item |
| M8 | `path2_web_ui/src/components/__tests__/KlineChart-click.test.ts` | handleChartClick 输入契约不变,测试不改 |

### 4.C 内部命名约定

- ECharts 实例暴露:`window.__e2e = { view, chartMain: () => chartMain, chartSub: () => chartSub }`
- 主/副图 canvas 元素 class 分别 `.main-chart canvas` 与 `.sub-inner canvas`(playwright 定位契约)

---

## 5. 错误处理与边界

### 5.1 副图内容空(matches=0 + events=0)

- `bracketH = 0`(无 bracket lane)
- `bandGeom = []`(无 band,tagList 空)
- `subCanvasH = 120`(下限,保持副图容器可见,避免坍缩到零高度导致 ECharts 报错)
- matchesLabel data = [](不渲染)
- subDivider data = [](不渲染)

### 5.2 极多 lane(band_i.laneCount > 20)

- band_h_i 按公式计算,可能 > 200px;subCanvasH 相应变大
- sub-outer 触发滚动,用户可滚
- 无上限 → 若 CPU 慢:防抖 setOption 触发(现有 watch 已 `deep: false`,但 chart.ts:97 `chart.setOption(opt, true)` 是全量替换;副图 setOption 频率高时可加 `debounce(200)` 兜底,首版不加)

### 5.3 拖拽越界

- ratio 钳制在 [0.20, 0.85]
- pointerup 时若外部 wrapper 高度变化(如页面 resize),按新 wrapper 高度重算 subCanvasH → chart.resize()

### 5.4 ResizeObserver + drag 竞态

- ResizeObserver 观测 mainEl、subInnerEl、subOuterEl 三处
- drag 结束触发 flex 变化 → ResizeObserver 触发 chart.resize()
- 顺序保证:先设 mainSubRatio → next tick → ResizeObserver 触发 → chart.resize
- 若竞态导致 chart 尺寸滞后一帧:视觉上短暂空白,不影响功能

### 5.5 echarts.connect axisPointer 断口

- 实测项(§6.1),若断口 > 4px 视觉不可接受 → fallback 到 manual sync(见 §3.5)
- 若 fallback 也不满意 → v2 增量:在两 chart 之间画一条覆盖 divider 的 DOM 层 fake 竖线(pointerEvents:none),按 axisPointer 位置定位

### 5.6 sub-outer 滚动 + hover 竞态

- 副图滚动时 sub-outer.scrollTop 变化,canvas 内 hover 坐标(offsetY)相对 canvas 顶不变
- ECharts axisPointer 触发用 canvas 局部坐标,不受 scrollTop 影响,竖线仍在正确 x
- sticky banner 在滚动时保持顶部可见,遮挡 bracket 区顶 16px——已在 subCanvasH 计算预留

---

## 6. 测试与验证

### 6.1 web-loop 实测承诺(必须 pass)

1. **axisPointer 竖线断口**:hover chartMain 任一位置 → chartSub 同 x 位置显示竖线,主副图两竖线**中间断口 ≤ 2px**(divider handle 4px 宽,竖线在其两侧对齐)。若 > 2px 走 fallback。
2. **拖拽 divider 平滑度**:拖动过程无卡顿(FPS ≥ 30);ratio 落在 [0.20, 0.85];松手后持久化到 localStorage,刷新页面恢复
3. **副图溢出滚动**:构造 band lane 总高 > sub-outer 可视高的场景(可用 evaluate 注入 mock 数据),验证 sub-outer 出现滚动条、滚动时 sticky banner 恒在顶部、主图完全不动、竖线跟随
4. **切股/切 pattern 后**:subCanvasH 重算、两 chart resize、mainSubRatio 不变
5. **candidate 态 sticky banner**:滚动副图到最底 → banner 仍在视口顶部;Esc → banner 消失、滚动位置保留

### 6.2 单元测试(vitest)

- `computeSubGeometry`:各 lane 计数场景下 bandGeom / bracketH / subCanvasH 精确对
- `panels.mainSubRatio`:边界钳制、初值、持久化
- `ResizableDivider`:pointerdown/move/up emit 序列
- `renderBandLabel` / `renderBracket` / `renderHighlight`:传入 subGeometry closure 后 y 位置正确(用 mock coordSys)

### 6.3 e2e(playwright)

- 更新 `match-event-disambig.spec.ts`:candidate banner 断言 `page.locator('.candidate-banner')`,click 定位到 `.main-chart canvas` 与 `.sub-inner canvas` 各自
- 新增 `subchart-scroll-drag.spec.ts`:
  - 拖拽 divider → 观测两 chart height 变化 + localStorage 更新
  - 触发副图滚动 → 观测 sub-outer.scrollTop 可增
  - refresh → mainSubRatio 恢复

---

## 7. 不进首版 / v2 增量

| 方案 | 启用条件 | 备注 |
|---|---|---|
| 竖线跨 divider 视觉无缝(DOM fake line) | 6.1 实测 axisPointer 断口 > 4px 且用户明反馈难看 | 在 kline-wrap-v2 顶层加 `<div class="crosshair-overlay">`,pointerEvents:none |
| 副图 band 高度按 lane 数自适应但整体不滚动(clamp mode) | 用户觉得滚动烦、想固定副图高度 | 增加 panels.subMode: 'scroll' | 'clamp',默认 scroll |
| 主/副图独立 zoom | 用户想副图 zoom 到某窄窗、主图看全景 | 需 disconnect,复杂,暂不做 |
| 副图内 band 折叠/展开 | band 太多(> 5) | 单独 UI,暂不做 |

---

## 8. 残留未决事项

- **拖拽 handle 视觉细节**(hover 变色 vs 不变、是否显示上下箭头 hint)——实施时按 web-loop 手感调,不影响接口
- **副图 xAxis category 与主图完全同步的边界**——两 chart 都用 `bars.map(b => b.date)`,`connect` 自动同步 zoom start/end,理论无边界。若实测有偏差,加 fallback:副图 dataZoom 显式 `disabled`,只跟主图

---

## 9. 引用文档

- `docs/superpowers/specs/2026-06-30-path2-web-match-event-disambig-design.md`(前一版 spec)
- 本次 brainstorm 决策(会话内):
  - zebra: 灰 alternate(rgba(0,0,0,0.03) / transparent)
  - divider: 1px 实线 #e0e6f1(两处同粗同色)
  - bracket 高度: 动态 lane × 10 + 6
  - matched label 文案: "matches"
  - 方案 B: 双 ECharts 实例 + `echarts.connect`
  - lane 高度固定 + band 高度按 lane 数 + 副图内容溢出 sub-outer 滚动
  - 主/副图之间可拖拽 divider 调占比
  - 保留 axisPointer 联动竖线(connect 覆盖,fallback manual sync)
