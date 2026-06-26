# path2_web 复刻 Dev UI 关键交互 — 设计 spec

**日期**：2026-06-23
**范围**：把 BreakoutStrategy Dev UI 的几块 K 线交互行为忠实复刻到 path2_web（FastAPI 后端 + Vue3 + ECharts 前端）。
**唯一后端契约变更**：bars 序列化新增 `rv` 字段。其余完全前端实现。

## 0. Goal / Non-goal

### Goal
1. **初始显示范围**：缓冲区涂灰（左/右两段）+ 初始 viewport 严格贴 [scan_start, scan_end]。
2. **Grid 重排**：原 3 grid（价格 / 量 / markers）→ 2 grid（价格含量叠加 / markers）。
3. **成交量叠加**：与 Dev UI 1:1，灰色柱画在价格区底部 20% 高度，跟随 zoom 重算 scale。
4. **十字线**：竖线吸附 bar 中心、横线锁该 bar close（非 ECharts 默认）。
5. **Bar tooltip**：Date / OHLC / Chg / Volume / RV 五项。
6. **Marker tooltip 优先**：hover 落在 marker item 上时 series-level 接管，bar tooltip 让位。
7. **Ctrl 解锁**：按 Ctrl 横+竖线脱离 bar/close、跟鼠标、颜色变橙、bar tooltip 切 `Price: x.xx`。

### Non-goal（明确不做）
- 不复刻 dev 的"突破日金色高亮柱"——path2 无 BO 概念。
- 不复刻 ATR / Active peaks / BO / Peak 等 BreakoutStrategy 专属字段。
- 不复刻 dev 的 3 年最小窗下限（path2_web bars 只返回 [win_start, win_end] 之间数据、复刻无意义）。
- 不复刻 dev 的 degradation 橙虚线（path2_web 没有 actual 抵近语义）。
- lookback / atr_period 等不做可配，硬编码为常量。
- 不重构 chart.ts 拆 5 个独立模块（YAGNI）；在 chart.ts 内抽 4 个纯函数即可。

## 1. 背景上下文（implementer 实施前必读 → §1.x 已自包含，不必另查代码）

### 1.1 Dev UI 已知机制（来自 docs/research/2026-06-23_path2-web-dev-ui-replication/final_report.md）

- **成交量与 K 线共用同一 axes**，无 twinx。y 轴几何：`display_height = price_range / 0.8`、`display_bottom = price_min - display_height * 0.1`、`volume_scale_factor = (display_height * 0.2) / vis_vol_max`；zoom/pan 后用可见区间内 vol_max 重算。
- **颜色常量**：`volume_up=#D3D3D3`、`volume_down=#696969`、`crosshair_normal=#0088CC`、`crosshair_ctrl=#FF6600`、阴影 `#808080 alpha=0.15`。
- **RV 算法**：`vol[d] / mean(vol[d-63:d])`，实现 `df["volume"].rolling(63, min_periods=1).mean().shift(1)`，inf/nan 清零；hover 时 `rv > 0` 才显示数值、否则 N/A。
- **Chg**：`(close[x] - close[x-1]) / close[x-1] * 100`，首根 N/A。
- **十字线默认锁定**：竖线 = `int(round(event.xdata))`（最近 bar 中心）、横线 = `df.iloc[x]["close"]`（不是鼠标 y）。
- **Ctrl 模式**：横+竖线脱离吸附跟鼠标、颜色 `#FF6600`、tooltip 文本仅 `Price: {ydata:.2f}`。Release 时只刷颜色和锁定，下次 hover 才刷文本。
- **失焦防卡死**：tkinter `<FocusOut>` 强制 `_ctrl_pressed = False`。

### 1.2 path2_web 当前状态

- **后端**：`path2_web/scan.py` 已经在结果 JSON `scan` 节返回 `win_start / win_end`（缓冲后实际切窗）+ `start_date / end_date`（严格 scan 窗）；`path2_web/serialize.py` 序列化 bars 时含 OHLCV + label_horizon 内的 forward return 字段，**不含 rv**。
- **前端**：
  - `render/visible.ts:121` 已有 `windowOf(scan)` 返回 `{ start: scan.win_start ?? scan.start_date, end: scan.win_end ?? scan.end_date }`。
  - `components/KlineChart.vue:33-37` 已经把 `scan.start_date / end_date` 在 bars 数组里定位成 `startIdx / endIdx` 传给 chart。
  - `render/chart.ts:219-225` 在 candlestick series 上挂了 `markLine`（两条 dashed 虚线标 scan_start/scan_end，**本 spec 删之**）。
  - `render/chart.ts:231-258` 当前 grid 配置：
    ```
    grid0: 价格   top:40   height:'48%'
    grid1: 量     top:'58%' height:'12%'
    grid2: markers top:'72%' height:'18%'
    ```
    dataZoom `xAxisIndex: [0,1,2]`、初始 `start:0 end:100`。
  - `render/chart.ts:190-213` 当前 tooltip 是 `trigger: 'item'`，formatter 处理 marker 的 clauses + raw 字段（path2 内省）。**本 spec 把此 formatter 搬到 series-level item-trigger，global 改 axis-trigger 接 bar tooltip**。

## 2. 后端契约变更

### 2.1 唯一变更：bars 加 `rv` 字段

**位置**：`path2_web/serialize.py`，在 bars 序列化函数内（由 implementer grep 定位，约在 OHLCV 序列化处）。

**算法**：
```python
import numpy as np
# 序列化 bars 前一次性算
avg_vol = df["volume"].rolling(63, min_periods=1).mean().shift(1)
rv_series = (df["volume"] / avg_vol).replace([np.inf, -np.inf], 0).fillna(0)
# 然后每根 bar dict 加: "rv": float(rv_series.iloc[i])
```

**口径与 dev 完全一致**：lookback=63 硬编码、`shift(1)` 分母不含当日、inf/nan→0。

### 2.2 不变更的契约

- 不新增 `scan_start_idx / scan_end_idx / initial_zoom_*` 等派生字段——前端 `findIndex` 自己算（守 path2_web "纯投影层"红线）。
- 接口签名、其它字段一律不动。

## 3. 前端 chart.ts 五大改动

### 3.1 Grid 重排（3 → 2）

**改 `chart.ts:231-258`**：

**Grid 索引重编号**：原 grid0(价格) 保留为新 grid0；原 grid1(量) **删除**；原 grid2(markers) **重编号为新 grid1**。后文统一用"新 grid0 / 新 grid1"指代。

```typescript
grid: [
  { left: 56, right: 16, top: 40, height: '72%' },     // 新 grid0 价格（含量叠加层）
  { left: 56, right: 16, top: '76%', height: '18%' },  // 新 grid1 markers（原 grid2）
],
xAxis: [
  { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
    axisLine: { onZero: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' },
  { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
    axisLine: { onZero: false }, axisLabel: { show: false }, splitLine: { show: false } },
],
yAxis: [
  // index 0: 价格(grid0)——min/max 由 buildVolumeSeriesAndYAxis() 动态计算填充
  // 必须固定 min/max（不能 scale:true），以让 volume bar baseline 落在 displayBottom
  { gridIndex: 0, splitArea: { show: true }, min: /* displayBottom */, max: /* displayTop */ },
  // index 1: 隐藏 bracket 轴(grid0)
  { scale: true, gridIndex: 0, show: false },
  // index 2: 隐藏 marker 轴(grid1)
  { scale: true, gridIndex: 1, show: false },
],
dataZoom: [
  { type: 'inside', xAxisIndex: [0, 1], start: ..., end: ... },  // 见 3.4
  { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: ..., end: ... },
],
```

- 所有原 `xAxisIndex: 1`（量）的 series 改 `xAxisIndex: 0`、`yAxisIndex: 0`。
- 所有原 `xAxisIndex: 2`（markers）的 series 改 `xAxisIndex: 1`、`yAxisIndex: 2`。
- 所有原 `yAxisIndex: 3`（bracket 隐藏轴）改 `yAxisIndex: 1`。
- `axisPointer.link: [{ xAxisIndex: [0, 1, 2] }]` 改 `[{ xAxisIndex: [0, 1] }]`。
- 数字（grid0 72% / grid1 18% / top 40 / margin 4%）以"价格区独占大头、markers 紧贴下方"为目标，实施时按视觉微调；spec 不锁死像素值。

### 3.2 Volume 叠加（dev 1:1）

**机制说明**（关键先讲）：
ECharts `type: 'bar'` 的柱从 yAxis 基线（即 yAxis.min）画起、高度 = data 值 - yAxis.min。dev 的"volume 占价格区底部 20%"必须靠**固定 yAxis[0].min/max** 实现——把 yAxis.min 设为 `displayBottom`、让每根 volume bar 的 data 值设为 `displayBottom + b.v * volScale`，柱就从 displayBottom 画到 displayBottom + b.v * volScale。这意味着 yAxis[0] **不能用 `scale: true`**（与 §3.1 一致）。

**新增纯函数** `buildVolumeSeriesAndYAxis(bars, visStart, visEnd) → { volSeries, yAxisOverride }`：

```typescript
function buildVolumeSeriesAndYAxis(bars: Bar[], visStart: number, visEnd: number) {
  const visBars = bars.slice(visStart, visEnd + 1)
  const priceMin = Math.min(...visBars.map(b => b.l))
  const priceMax = Math.max(...visBars.map(b => b.h))
  const priceRange = priceMax - priceMin
  const displayHeight = priceRange / 0.8
  const displayBottom = priceMin - displayHeight * 0.1
  const displayTop = displayBottom + displayHeight
  const visVolMax = Math.max(...visBars.map(b => b.v), 1)  // 兜底 1 防除零
  const volScale = (displayHeight * 0.2) / visVolMax

  const volSeries = {
    type: 'bar',
    name: 'volume',
    xAxisIndex: 0,
    yAxisIndex: 0,
    barWidth: '100%',
    z: 1,  // candlestick 默认 z 更高自然盖上
    data: bars.map(b => ({
      value: displayBottom + b.v * volScale,  // 标量值，bar 从 yAxis.min 画到此值
      itemStyle: {
        color: b.c >= b.o ? '#D3D3D3' : '#696969',
        borderColor: 'black',
        borderWidth: 0.5,
        opacity: 0.8,
      },
    })),
  }
  const yAxisOverride = { min: displayBottom, max: displayTop }
  return { volSeries, yAxisOverride }
}
```

**datazoom 联动**：chart 实例上 `chart.on('datazoom', () => { ... })`：
1. 从 `chart.getOption().dataZoom[0].start/end` 反推 visStart/visEnd（百分比 × bars.length，四舍五入）
2. 调 `buildVolumeSeriesAndYAxis` 重算 volSeries.data 和 yAxisOverride
3. `chart.setOption({ series: [{ name: 'volume', data: newData }], yAxis: [{ min: ..., max: ... }, ...] })`

**关键点**：
- 用**可见区间**算 vol_max、price_min/max（不是全集），与 dev 一致。
- 初始渲染时 visible = [startIdx, endIdx]（严格 scan 窗）。
- yAxis[0].min/max 也跟随 zoom 重算（与 volScale 同步），保证视觉上始终是"价格区独占 80% / 上下 10% 留白 / volume 占下 20% 留白带"。
- 不复刻金色高亮（path2 无 BO 概念）。

### 3.3 阴影 markArea（取代 markLine）

**新增纯函数** `buildShadingMarkArea(bars, scanStart, scanEnd) → markArea | null`：

```typescript
function buildShadingMarkArea(bars: Bar[], scanStart: string, scanEnd: string) {
  if (bars[0].date >= scanStart && bars[bars.length - 1].date <= scanEnd) return null
  const startIdx = bars.findIndex(b => b.date >= scanStart)
  let endIdx = bars.length - 1
  for (let i = bars.length - 1; i >= 0; i--) {
    if (bars[i].date <= scanEnd) { endIdx = i; break }
  }
  const areas: any[] = []
  if (startIdx > 0) areas.push([{ xAxis: 0 }, { xAxis: startIdx - 1 }])  // 左段
  if (endIdx < bars.length - 1) areas.push([{ xAxis: endIdx + 1 }, { xAxis: bars.length - 1 }])  // 右段
  if (areas.length === 0) return null
  return {
    itemStyle: { color: '#808080', opacity: 0.15 },
    data: areas,
  }
}
```

**off-by-one 修正验证**：左段右界 = `startIdx - 1`、右段左界 = `endIdx + 1`。即 `bars[startIdx]`（严格 scan 窗的第一根）和 `bars[endIdx]`（最后一根）本身**在白色侧**，不在灰区。

**挂载**：
- 在 candlestick series 上挂 markArea（覆盖 grid0）。
- **同时在某个 grid1 markers 系列上也挂**（例如 `points` 或专门一个 dummy series）——覆盖 grid1 markers 区，保持视觉一致。

**删 `chart.ts:219-225` 的 `markLine`**。

### 3.4 初始 zoom 贴 [startIdx, endIdx]

**dataZoom 初始 start/end**（替换 `chart.ts:256-257`）：

```typescript
const startIdx = bars.findIndex(b => b.date >= scan.start_date)
let endIdx = bars.length - 1
for (let i = bars.length - 1; i >= 0; i--) {
  if (bars[i].date <= scan.end_date) { endIdx = i; break }
}
const zoomStart = (startIdx / bars.length) * 100
const zoomEnd = ((endIdx + 1) / bars.length) * 100  // +1 让 endIdx 完整可见

dataZoom: [
  { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
  { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd },
],
```

无 buffer 时（`scan.win_start === scan.start_date`）退化为 `start: 0, end: 100`。

### 3.5 AxisPointer override 横线锁 close

**Global tooltip**（替换 `chart.ts:190`）：
```typescript
const tooltip = {
  trigger: 'axis',
  axisPointer: {
    type: 'cross',
    lineStyle: { color: '#0088CC', type: 'dashed', width: 1.5, opacity: 0.7 },
    label: { show: false },  // 不显轴上的数字标签
    snap: true,  // 竖线吸附 bar 中心（Ctrl 模式动态改 false）
  },
  formatter: buildBarTooltipFormatter(bars, ctrlState),
}
```

**横线锁 close** —— 两种实现允许 implementer 现场二选一：

**方案 1（首选）**：监听 `chart.on('updateAxisPointer', e => {...})`，从 e 拿 dataIndex → `bars[idx].c`，调 `chart.setOption({ ... y 锁到 close })`。具体 ECharts API 字段名实施时查文档。

**方案 2（fallback）**：禁用内置 y axisPointer（`tooltip.axisPointer.type` 改 `'line'` 只竖线）+ 手画一根 markLine（y=bars[idx].c）随 hover 动态更新。

**Ctrl 模式**：handler 内读 `ctrlState.isPressed()`，true → 跳过 y override（让 ECharts 默认横线跟鼠标）+ axisPointer.snap=false（竖线脱离 bar 中心）+ lineStyle.color 改 `#FF6600`。

## 4. Tooltip 拆分

### 4.1 Bar tooltip（global, axis-trigger）

**新增纯函数** `buildBarTooltipFormatter(bars, ctrlState)`：

**关于 Ctrl 模式拿鼠标 ydata**：ECharts axis-trigger formatter 的 params 数组**不直接含鼠标 y 数据**（只有 axis x 值）。要实现 `Price: {ydata:.2f}` 必须额外维护 mouseY 状态：在 chart 实例上 `chart.getZr().on('mousemove', e => { const [, y] = chart.convertFromPixel({ yAxisIndex: 0 }, [e.offsetX, e.offsetY]); ctrlState.setMouseY(y) })`，formatter 内 `ctrlState.mouseY()` 读取。ctrlState 扩展见 §5。

```typescript
function buildBarTooltipFormatter(bars: Bar[], ctrlState: CtrlState) {
  return (params: any[]) => {
    if (ctrlState.isPressed()) {
      const y = ctrlState.mouseY()
      return `Price: ${y.toFixed(2)}`
    }
    // 普通模式
    const klineParam = params.find(p => p.seriesName === 'kline')
    if (!klineParam) return ''
    const idx = klineParam.dataIndex
    const b = bars[idx]
    const prev = idx > 0 ? bars[idx - 1] : null
    const chgStr = prev
      ? `${((b.c - prev.c) / prev.c * 100 >= 0 ? '+' : '')}${((b.c - prev.c) / prev.c * 100).toFixed(2)}%`
      : 'N/A'
    const rvStr = b.rv > 0 ? b.rv.toFixed(2) : 'N/A'
    const volStr = Math.round(b.v).toLocaleString('en-US')  // 千分位逗号
    return [
      `Date: ${b.date}`,
      `Open:  ${b.o.toFixed(2)}`,
      `High:  ${b.h.toFixed(2)}`,
      `Low:   ${b.l.toFixed(2)}`,
      `Close: ${b.c.toFixed(2)}`,
      `Chg:   ${chgStr}`,
      `Volume: ${volStr}`,
      `RV:    ${rvStr}`,
    ].join('<br/>')
  }
}
```

字段顺序、首根 Chg=N/A、RV ≤ 0 → N/A 都与 dev 1:1。

### 4.2 Marker tooltip（series-level, item-trigger）

把 `chart.ts:192-213` 现有 formatter 抽成纯函数 `buildMarkerTooltipFormatter(tooltipResolver, matchLabel)`，逻辑不变。

在每个 marker series 上挂 series-level tooltip：
```typescript
const markerTooltip = { trigger: 'item', formatter: buildMarkerTooltipFormatter(...) }
// 挂载到下列 series（跨新 grid0 和新 grid1）：
//   新 grid1 markers: points, intervals, bandLabels, highlight
//   新 grid0 价格区上的 marker: brackets, price-points, satellites, highlight-price
// 每个 series 加 tooltip: markerTooltip
```

**ECharts 优先级**：item-trigger 在 hover 到具体 item 时接管，axis-trigger fall back 处理 marker 之间的空白 hover。**这是 ECharts 原生支持的两层 tooltip 模式**——implementer 实施时直接挂即可，无需手动协调。

**Ctrl 模式不影响 marker tooltip**——marker 仍按 path2 内省字段（clauses + raw）显示。

## 5. Ctrl state 模块（新文件 `path2_web_ui/src/render/ctrlState.ts`）

模块同时维护两块状态：(a) Ctrl 键按下与否（订阅模式），(b) 最近鼠标 y 数据（拉模式、供 Ctrl 模式 tooltip 读）。

```typescript
let isPressed = false
let mouseY = 0
const subs = new Set<(p: boolean) => void>()
let initialized = false

function notify() { subs.forEach(fn => fn(isPressed)) }

function init() {
  if (initialized) return
  initialized = true
  document.addEventListener('keydown', e => {
    if (e.key === 'Control' && !isPressed) { isPressed = true; notify() }
  })
  document.addEventListener('keyup', e => {
    if (e.key === 'Control' && isPressed) { isPressed = false; notify() }
  })
  window.addEventListener('blur', () => {
    if (isPressed) { isPressed = false; notify() }
  })
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && isPressed) { isPressed = false; notify() }
  })
}

export const ctrlState = {
  isPressed: () => isPressed,
  mouseY: () => mouseY,
  setMouseY: (y: number) => { mouseY = y },  // chart 实例 mousemove 时调用
  subscribe: (fn: (p: boolean) => void) => {
    init()
    subs.add(fn)
    return () => subs.delete(fn)
  },
}
```

**失焦兜底**：window blur + visibilitychange 双层（前者切窗、后者切 tab）。

**mouseY 不走订阅**——拉模式即可：formatter 每次 hover 现场读 `ctrlState.mouseY()`，无需 reactive。

## 6. KlineChart.vue 订阅与切换

```typescript
// onMounted
const unsub = ctrlState.subscribe(onCtrlChange)

// chart 实例上挂 mousemove，把 zr 像素坐标转 yAxis 数据坐标存到 ctrlState
chart.getZr().on('mousemove', e => {
  const arr = chart.convertFromPixel({ yAxisIndex: 0 }, [e.offsetX, e.offsetY])
  if (Array.isArray(arr)) ctrlState.setMouseY(arr[1] ?? 0)
})

function onCtrlChange(pressed: boolean) {
  chart.setOption({
    tooltip: {
      axisPointer: {
        lineStyle: { color: pressed ? '#FF6600' : '#0088CC' },
        snap: !pressed,  // unpressed: snap to bar; pressed: follow cursor
      },
    },
  })
  // updateAxisPointer 监听器内闭包读 ctrlState.isPressed() 决定是否 override y；setOption 仅切色和 snap
}

// onUnmounted
unsub()
chart.getZr().off('mousemove')
```

**注意**：tooltip 文本切换靠 formatter 闭包持有 `ctrlState` 引用、下一次 hover 自动重跑 formatter——与 dev 一致（release 时不立刻刷文本，下次 hover 才刷）。

## 7. 测试策略

### 7.1 后端 pytest

新增 `path2_web/tests/test_serialize_rv.py`：
- **算法测试**：70 根 bar fixture，断言 bar[63].rv == volume[63] / mean(volume[0:63])（手算对比）
- **边界**：i < 63 时 min_periods=1 不抛错；volume[0]=0 时不抛 ZeroDivisionError；分母 0 → rv=0
- **集成**：扩现有 serialize 测试，断言 bars 每根含 `rv: float`

### 7.2 前端 vitest 单测

**新增 `chart-helpers.test.ts`**：
- `buildShadingMarkArea`：含 buffer / 无 buffer / 仅左 buffer 三种 fixture；断言 off-by-one 修正（startIdx 本身在白区）
- `buildVolumeSeriesAndYAxis`：vol_max=0 时不抛；scale 公式 `(displayHeight * 0.2) / visVolMax`；返回 `{ volSeries, yAxisOverride: { min, max } }`
- `buildBarTooltipFormatter`：普通模式 8 行（Date / Open / High / Low / Close / Chg / Volume / RV）+ 首根 Chg=N/A + rv≤0 → RV=N/A；Ctrl 模式 1 行 `Price: x.xx`（mock ctrlState.mouseY 返回固定值）

**新增 `ctrlState.test.ts`**：
- keydown('Control') → isPressed=true、订阅者收到 true
- keyup('Control') → false
- 重复 keydown 不重复 notify
- window blur 强制 false
- document visibilitychange (hidden) 强制 false

### 7.3 前端组件测

扩 `KlineChart.test.ts`：
- mount + mock bars + scan (含 buffer) → 断言 ECharts option grid 数=2、xAxis 数=2、markArea 两段、dataZoom 初始 start/end 对应 [startIdx, endIdx+1] 比例
- 模拟 datazoom 事件 → 断言 volume series data 被重算

### 7.4 Playwright E2E

复用 path2web2 项目既有 chromium 自动化路径，截图四场景：
1. 初始加载：viewport 贴 [scan_start, scan_end]，灰区不可见
2. 左滑后：左侧灰区可见，`bars[startIdx]` 在白区（off-by-one 修正）
3. hover bar + Ctrl 切换：普通 8 行（Date/OHLC×4/Chg/Volume/RV）+ 蓝、Ctrl 1 行（Price）+ 橙
4. hover marker：marker tooltip 显示，bar tooltip 不显

## 8. 验收清单

- [ ] grid 数 = 2（价格含量 / markers）
- [ ] volume 灰柱叠在价格区底部 20%，浅灰/深灰（不复刻金色）
- [ ] zoom 后 vol 高度按可见 vol_max 重算
- [ ] 初始 viewport 严格 [scan_start, scan_end]、左右灰区不可见
- [ ] markers 区有同样灰阴影
- [ ] hover bar：8 行（Date / Open / High / Low / Close / Chg / Volume / RV）；首根 Chg=N/A、RV≤0=N/A
- [ ] hover marker：path2 内省字段优先于 bar tooltip
- [ ] 默认竖线吸附 bar 中心、横线锁该 bar close、颜色蓝
- [ ] 按 Ctrl：横+竖线跟鼠标、颜色橙、bar tooltip 切 `Price: x.xx`
- [ ] 松 Ctrl 立即复位（颜色/锁定/snap）；tooltip 文本下次 hover 才刷
- [ ] window blur / visibilitychange (hidden) → Ctrl 状态强制复位

## 9. 关键文件索引

**后端**：
- `path2_web/serialize.py`（rv 字段注入点）
- `path2_web/tests/test_serialize_rv.py`（新增）

**前端**：
- `path2_web_ui/src/render/chart.ts`（grid 重排 + 4 个纯函数 + axisPointer override + ctrl 联动）
- `path2_web_ui/src/render/ctrlState.ts`（新增）
- `path2_web_ui/src/components/KlineChart.vue`（订阅 ctrlState + onCtrlChange）
- `path2_web_ui/src/render/__tests__/chart-helpers.test.ts`（新增）
- `path2_web_ui/src/render/__tests__/ctrlState.test.ts`（新增）
- `path2_web_ui/src/components/__tests__/KlineChart.test.ts`（扩）

**调研依据**（implementer 可按需查阅但 §1.1 已自包含）：
- `docs/research/2026-06-23_path2-web-dev-ui-replication/final_report.md`（dev 机制详解）

## 10. 实施顺序建议

1. 后端 rv 字段 + 测试（独立单元，最先 land）
2. ctrlState.ts + 单测（无依赖，可与 1 并行）
3. chart.ts 拆 4 个纯函数（保持当前行为不变，只重构）
4. grid 重排（3 → 2）+ 改 series xAxisIndex/yAxisIndex
5. 阴影 markArea 替换 markLine + 初始 zoom 落点
6. volume 叠加 + datazoom 联动重算
7. axisPointer override（横线锁 close）
8. tooltip 拆分（global axis + series-level item）
9. KlineChart.vue 订阅 ctrlState
10. Playwright E2E 三/四场景截图验证
