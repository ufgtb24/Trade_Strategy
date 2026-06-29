# ChartArea 主图 + 副图占满 main 剩余高度 设计

## 1. 背景

刚完成的「ChartArea 三处可隐藏面板」(2026-06-29-chartarea-hideable-panels-design.md) 之后,默认全隐场景下 K 线主图下方仍有约 640px 空白带。

根因(已实测):

- `App.vue:.app { display: grid; height: 100vh }` 给 `.right`(main) 100vh 高度
- `.right { overflow: auto }` — 仅声明溢出处理,未主动撑开子节点
- `ChartArea.vue:.chart-area { grid-template-rows: auto auto auto }` — 三行均 auto 大小,合计 = `level-bar(31px) + topology-row(0,默认隐) + kline(560px)` = 591px,远小于 main 可用空间
- `KlineChart.vue:.kline { height: 560px }` — K 线 ECharts 容器固定 560px

实测视口高度场景,默认全隐时 K 线下方约 640px 空白。

## 2. 目标

让 ChartArea 占满 `.right` 的全部可用高度,K 线主图 + 量能/markers 副图自动随 main 大小伸缩。

**不目标**:

- 不改 ECharts 内部布局(chart.ts:259-261 的 grid 百分比 `top/height` 不动 —— 同一 canvas 内的价格 72%、markers 18%、slider 4% 比例由 ECharts 自动按容器高度等比放大)
- 不引入 min-height 兜底(用户已选「不限,完全跟随 main」)
- 不改 DetailSidebar、TopologyControl 内部结构

## 3. 设计

**纯 CSS,改 3 文件:**

### 3.1 `path2_web_ui/src/components/App.vue` —— `.right`

由:

```css
.right { overflow: auto; }
```

改为:

```css
.right { display: flex; flex-direction: column; min-height: 0; overflow: auto; }
```

`display: flex` 让 `.right` 成为 flex 容器,子节点(`.chart-area`)可通过 `flex: 1` 拉伸;`min-height: 0` 是 flex 默认 `min-height: auto` 在 grid 子项里的标准修正(否则 main 会被内部内容撑大、不会向上收缩);`overflow: auto` 保留作极端窄视口时的兜底。

### 3.2 `path2_web_ui/src/components/ChartArea.vue` —— `.chart-area`

由:

```css
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto auto;
  gap: 0;
}
```

改为:

```css
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto 1fr;
  gap: 0;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
```

- `flex: 1` 撑满父 `.right` 高度
- `grid-template-rows: auto auto 1fr` —— row3(K 线 + sidebar)占剩余空间(row1=level-bar、row2=topology v-if)
- `min-height: 0` / `min-width: 0` —— grid item 默认 `min-content` 会拒绝收缩,必须显式 0 让 1fr 真的收缩(K 线区被压不撑爆 main)

### 3.3 `path2_web_ui/src/components/KlineChart.vue` —— `.kline`

由:

```css
.kline { width: 100%; height: 560px; min-width: 0; overflow: hidden; }
```

改为:

```css
.kline { width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
```

- `height: 100%` 撑满 grid cell(row 3 高度由 `1fr` 决定)
- `min-height: 0` 同上,保证 grid item 可以缩

KlineChart 既有 `ResizeObserver`(`:97`)自动调 `chart.resize()`,容器尺寸变化即触发 ECharts 重布局;无 JS 改动。

### 3.4 DetailSidebar 列(row 3 col 2)

无须改动。DetailSidebar 默认 grid cell stretch,跟随 row 3 高度自动撑满。

## 4. 行为矩阵(三档 × 不同 main 高度)

| 场景 | row 1 | row 2 | row 3 | K 线高度 |
|---|---|---|---|---|
| 默认(全隐)| level-bar | (无) | 1fr 占剩余 | main_h - 31 |
| Topology 开 | level-bar | topology-row(自适应 ≈ 150-200px) | 1fr 占剩余 | main_h - 31 - topology_h |
| Sidebar 开 | level-bar | (无) | 1fr 占剩余、col2 sidebar 同高 | main_h - 31 |
| 三档全开 | level-bar | topology-row | 1fr 占剩余(col1 K 线 col2 sidebar)| main_h - 31 - topology_h |
| Slider 开 | 同上 | 同上 | 同上 | K 线 ECharts 内部 slider 4% 区域显隐切换;不影响 .kline 容器高度 |

ECharts 内部 grid 百分比(price 72% + markers 18% + slider 4%)等比映射到 `.kline` 高度上,故 K 线变大、量能/markers 也成比例变大。

(矩阵中 `main_h` = `.right` 容器的实际高度 ≈ `100vh - body 边距`;`topology_h` = TopologyControl 自然渲染高度,无 v-if 时为 0。)

## 5. 风险

1. **极端窄 main(< 200px)**:K 线 1fr 会被压成 0(因 min-height: 0),仅 level-bar 可见。`.right { overflow: auto }` 提供水平/垂直滚动兜底。用户已选「不限」,接受此风险。
2. **DetailSidebar 已有内部 height 假设**:不预期。如果出现 sidebar 内部 overflow 问题,在实施 plan 阶段一并修;e2e 验证会暴露。
3. **App.vue:.left flex column 容器内嵌的 sidebars 是否被 `.right` 的 flex 改动间接影响**:不影响 —— `.app` 是 grid,`.left`/`.right` 是平级 grid item,各自的 display 互不传染。

## 6. 测试

### 6.1 单测

无新单测。本改纯 CSS,vitest jsdom 不验布局;既有 271 测应零回归(`vitest` + `vue-tsc` + `vite build` 三 gate 不破)。

### 6.2 端到端(Playwright 视觉 + 度量)

复用上一轮 Task 5 的 server 启动 + 历史扫描加载流程。新增 4 场景度量断言:

| 场景 | 操作 | 断言 |
|---|---|---|
| 默认全隐 | 加载页面 | `.chart-area` height ≈ `main` height;`.kline` height ≈ main_h - level_bar_h |
| Topology 开 | click `panel-toggle-topology` | `.kline` height = main_h - level_bar_h - topology_row_h(留少量 gap 容差) |
| 三档全开 | 三 chip 全点 | K 线 + sidebar 各占满 row 3 高度;DOM 无 ~640px 空白带 |
| 默认 + 截图比对 | 全屏截图 | K 线主图占满 viewport 视觉确认 |

度量断言用 `browser_evaluate` 跑 `getBoundingClientRect`,把 `blank_gap = chart_area.height - (level_bar.height + topology_row.height + kline.height)` 断成 ≤ 2px(浮点容差;此容差统一用于所有场景的"K 线占满剩余"断言)。

### 6.3 三 gate(每 task 验收门)

```
cd path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```

## 7. 文件清单

修改(3 文件,纯 CSS):

- `path2_web_ui/src/components/App.vue` —— `.right` flex 改造
- `path2_web_ui/src/components/ChartArea.vue` —— `.chart-area` flex + 1fr row
- `path2_web_ui/src/components/KlineChart.vue` —— `.kline` height 100%

无新建文件。

## 8. 实施范围

预估 1 个实施 task + 1 e2e 验收 task:

- Task 1:三处 CSS 改动 + 三 gate 绿 + commit
- Task 2:Playwright e2e 度量 + 截图 + 清场

后续按 subagent-driven 单 session 跑。
