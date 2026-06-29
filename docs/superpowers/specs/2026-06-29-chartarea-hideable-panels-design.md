# ChartArea 三处可隐藏面板（Topology / Sidebar / Slider）

**日期**：2026-06-29
**范围**：仅 `path2_web_ui/`（前端）。后端不动。
**主线**：path2 web UI 的「调试视图」精简——默认进入只看主图+副图,三个非主图面板按需 toggle 显隐。

---

## 1. 背景与动机

当前 `ChartArea.vue` 默认渲染四块内容,占满主区:

```
┌─ level-bar:Matched|Qualified|Detected  + active-pattern select  ─┐
├─ row1: TopologyControl 拓扑面板(常驻、占空间)                    ─┤
├─ row2: KlineChart(主图蜡烛+副图成交量+slider)  │ DetailSidebar  ─┤
└──────────────────────────────────── 1fr ───────┴── 280px ────────┘
```

三个面板各有用途但并非每次都需要:
- **Topology**:看 pattern 拓扑结构(role/edge 关系)——纯调试/教学场景
- **DetailSidebar**(右栏 280px):漏斗+候选表+match trace——逐条归因场景
- **dataZoom slider**(K 线下方一条):粗调可见区间——但 inside zoom(鼠标滚轮/拖选)已经够用

日常浏览扫描结果时,用户只想集中看主图 K 线与副图成交量;以上三块成了视觉噪声、挤压主图空间。本设计提供**独立、可持久化的三个 toggle**,默认全隐。

---

## 2. 目标与非目标

### 目标
- 三个面板各自可独立 toggle 显隐,互不影响
- 首次访问默认全隐,只见 K 线主图 + 成交量副图(+ inside zoom 能力)
- toggle 状态**跨刷新持久化**(localStorage),零后端改动
- 视觉风格与现有 `.level-btn` 一致,零新 CSS 概念
- 隐藏区域**真正收回空间**(grid 自动塌缩),不留空白占位
- 隐藏后**不清空** store 里的选中状态(`selected`/`expandedNode`/`selectedEventId`),重显仍是上次

### 非目标(YAGNI)
- URL query param 控制(`?topo=1` 等)
- 后端 config 持久化(`/config` 接口) —— UI 偏好不值得跨设备同步
- 副图(成交量)独立 toggle —— 用户明确要常驻
- 拖动边缘 resize 面板宽度 —— 与 toggle 正交,独立功能
- 隐 slider 时把 markers grid1 上扩占满下方 8% 空白 —— cosmetic only,先不动

---

## 3. UI 设计

### 3.1 Toggle Chip 位置

在现有 `level-bar`(顶部暗色 toolbar)右侧加三个 chip 按钮,紧跟 active-pattern `<select>` 之后:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [Matched|Qualified|Detected]  [bottom_burst ▾]   ···   [Topology] [Sidebar] [Slider] │
└─────────────────────────────────────────────────────────────────────────┘
```

- 复用现有 `.level-btn` CSS(暗底、active=亮蓝高亮),不引入新样式 token
- 三个 chip 顺序按空间贡献从大到小:Topology → Sidebar → Slider
- 文本英文,与同 bar 的 Matched/Qualified/Detected 风格一致

### 3.2 默认状态
- 首次访问 / localStorage 中无对应 key / 解析失败 → 三者全 `false`(全隐)
- 已有 key → 从 localStorage 恢复

---

## 4. 状态管理

### 4.1 新增 `stores/panels.ts`

```ts
// stores/panels.ts
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'path2_web_ui.panels.v1'

interface PanelsState {
  topology: boolean
  sidebar:  boolean
  slider:   boolean
}

function loadState(): PanelsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { topology: false, sidebar: false, slider: false }
    const obj = JSON.parse(raw)
    return {
      topology: !!obj.topology,
      sidebar:  !!obj.sidebar,
      slider:   !!obj.slider,
    }
  } catch {
    return { topology: false, sidebar: false, slider: false }
  }
}

export const usePanelsStore = defineStore('panels', () => {
  const init = loadState()
  const showTopology = ref(init.topology)
  const showSidebar  = ref(init.sidebar)
  const showSlider   = ref(init.slider)

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        topology: showTopology.value,
        sidebar:  showSidebar.value,
        slider:   showSlider.value,
      }))
    } catch { /* 静默:配额满/隐私模式都不阻塞 UI */ }
  }
  watch([showTopology, showSidebar, showSlider], persist)

  function toggle(key: 'topology' | 'sidebar' | 'slider') {
    if (key === 'topology') showTopology.value = !showTopology.value
    else if (key === 'sidebar') showSidebar.value = !showSidebar.value
    else showSlider.value = !showSlider.value
  }

  return { showTopology, showSidebar, showSlider, toggle }
})
```

**为什么独立 store 而非 ChartArea local state**:
- 未来若想从别处触发(如点击命中行自动开 Sidebar、tour 模式自动开 Topology)零成本
- 持久化逻辑集中,不污染 ChartArea
- 测试隔离:store 测试不依赖组件挂载

**localStorage key 选 v1 后缀**:未来若状态形状变更便于 schema 迁移。

---

## 5. 组件改动

### 5.1 `components/ChartArea.vue`

```vue
<template>
  <div class="chart-area" :class="{ 'no-sidebar': !showSidebar }">
    <div class="level-bar" data-testid="level-control">
      <!-- 现有 Matched/Qualified/Detected 三个 button (不动) -->
      <!-- 现有 active-pattern select (不动) -->
      <!-- 新增:三个 toggle chip,放在最右侧 -->
      <span class="spacer" />
      <button
        v-for="t in PANEL_TOGGLES"
        :key="t.key"
        :class="['level-btn', 'panel-toggle', { active: panels[t.refKey] }]"
        :data-testid="`panel-toggle-${t.key}`"
        :title="t.title"
        @click="panels.toggle(t.key)"
      >{{ t.label }}</button>
    </div>
    <TopologyControl v-if="showTopology" @hover-role="onHoverRole" />
    <KlineChart />
    <DetailSidebar v-if="showSidebar" />
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { usePanelsStore } from '../stores/panels'
// ... 现有 imports

const panels = usePanelsStore()
const { showTopology, showSidebar, showSlider } = storeToRefs(panels)

const PANEL_TOGGLES = [
  { key: 'topology' as const, refKey: 'showTopology' as const, label: 'Topology', title: '显示/隐藏拓扑面板' },
  { key: 'sidebar'  as const, refKey: 'showSidebar'  as const, label: 'Sidebar',  title: '显示/隐藏右侧诊断侧栏' },
  { key: 'slider'   as const, refKey: 'showSlider'   as const, label: 'Slider',   title: '显示/隐藏 K 线下方缩放滑块' },
]
</script>

<style scoped>
/* grid 列数由 .no-sidebar 切换:有 sidebar → '1fr 280px';无 → '1fr' */
.chart-area { display: grid; grid-template-columns: 1fr 280px; grid-template-rows: auto auto 560px; gap: 0; }
.chart-area.no-sidebar { grid-template-columns: 1fr; }
.level-bar, .chart-area > :nth-child(2) { grid-column: 1 / -1; }   /* -1 自适应列数变化 */

.spacer { flex: 1; }
.panel-toggle { /* 复用 .level-btn,无新样式 */ }
/* 其余样式不动 */
</style>
```

**关键技术点**:
1. `grid-column: 1 / -1` 替代原来的 `1 / 3` —— 用负索引让最后一列自动适配 1 或 2 列布局
2. `.spacer` 用 `flex: 1` 把 toggle chip 推到 level-bar 最右(已确认 `.level-bar { display: flex }`)
3. `<TopologyControl v-if=…>` 不渲染时 grid row1 自动塌缩(空 row,无元素时高度 0)
4. `<DetailSidebar v-if=…>` 不渲染 + 列模板从 2 列切 1 列 → 主图占满宽度

**⚠ 必须改的脆弱 CSS**:原 `.chart-area > :nth-child(2)` 用「位置序」选中 TopologyControl 让它跨满两列;当 Topology 被 `v-if` 移除后,nth-child(2) 会错位选中 KlineChart,导致主图被强制跨两列、DetailSidebar 错位。**实施时必须把这条改成精准选择器**:给 `<TopologyControl>` 外加包装类 `.topology-row`,或用 `<TopologyControl class="topology-row" …>`(组件根 class 透传),CSS 改为:

```css
.level-bar, .chart-area > .topology-row { grid-column: 1 / -1; }
```

或更稳:把 TopologyControl 套一层占位 wrapper:
```vue
<div v-if="showTopology" class="topology-row"><TopologyControl @hover-role="onHoverRole" /></div>
```
两条路任选,实施时统一一种。

### 5.2 `components/KlineChart.vue` + `render/chart.ts`

**ECharts dataZoom slider 显隐**:

`render/chart.ts` 现有:
```ts
dataZoom: [
  { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
  { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd },
],
```

改造:
- `BandRenderInput` 接口加 `sliderShow?: boolean`(**可选,默认 true**,保旧调用零回归——`tests/labels.spec.ts` 等不传也能工作)
- `buildKlineOption` 在 dataZoom 处理:
  ```ts
  const sliderShow = input.sliderShow ?? true
  // ...
  dataZoom: [
    { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
    { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd, show: sliderShow },
  ],
  ```
- **保留 inside zoom 项**(总是 enabled),所以鼠标滚轮 + 拖选区域仍可用
- KlineChart.vue 的 `render()` 把 `panels.showSlider` 通过 input 传进去:
  ```ts
  const opt = buildKlineOption(bars.value, …, { …, sliderShow: panels.showSlider })
  ```
- 现有 `watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag], render, { deep: true })` **加入 `showSlider`**(同 watch 内,触发 re-render 即可):
  ```ts
  watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag, showSlider], render, { deep: true })
  ```
- 注意 `panels` store 通过 `storeToRefs` 解构出 `showSlider`(ref),才能进 watch 数组

**为什么用 `show: false` 而非 remove dataZoom 项**:
- ECharts 中 dataZoom 的初始 start/end 是状态,remove/add 会丢失用户已 zoom 的区间
- `show: false` 只隐 UI,start/end 状态保留,重新打开 slider 即恢复

**为什么用 `show: false` 而非 remove dataZoom 项**:
- ECharts 中 dataZoom 的初始 start/end 是状态,remove/add 会丢失用户已 zoom 的区间
- `show: false` 只隐 UI,start/end 状态保留,重新打开 slider 即恢复

### 5.3 `components/DetailSidebar.vue` 和 `components/TopologyControl.vue`

**不动**。父级 `v-if` 决定是否挂载;它们内部状态(`expandedNode` 等)在重新挂载时由 store/computed 自动恢复(本来就靠 store)。

---

## 6. 数据流

```
用户点 chip
  → panels.toggle(key)
  → showXxx ref 变化
  → watch([…]) 触发 persist() 写 localStorage
  → 模板 v-if / :class 重新计算
  → Vue 重排 DOM:
      Topology: 挂载/卸载 TopologyControl
      Sidebar: 挂载/卸载 DetailSidebar + grid 列变化
      Slider: KlineChart.render() 重新 setOption(sliderShow 变化)
```

---

## 7. 错误与边界处理

| 场景 | 行为 |
|---|---|
| localStorage 不可用(隐私模式/配额满) | `try/catch` 静默吞,UI 正常,只是状态本会话内不持久 |
| localStorage 中 JSON 损坏 | `JSON.parse` 抛 → catch → 回默认全隐 |
| 旧 key(未来 schema 变更) | 新 v2/v3 key 共存,旧 v1 保留待迁移工具 |
| Sidebar 隐藏时用户点 K 线 event | `selectEvent` 仍写入 store,Sidebar 重显时直接看到选中态 |
| Topology 隐藏时用户从 SidebarResultList 切股 | 不受影响,store 与 KlineChart 都正常 |

---

## 8. 测试

### 8.1 单元测试(vitest)

`tests/stores.panels.spec.ts`(新建):
1. 首次创建 store(localStorage 空) → 三个 ref 都 false
2. `toggle('topology')` → showTopology=true,localStorage 写入正确 JSON
3. 重新创建 store(同一 localStorage) → 恢复上次状态
4. localStorage 中 JSON 损坏 → 回默认全 false
5. localStorage `setItem` 抛(模拟配额满) → toggle 不抛,UI ref 仍更新

### 8.2 组件测试(vitest + @vue/test-utils)

`tests/components/ChartArea.panels.spec.ts`(新建):
1. 默认渲染:TopologyControl 不存在,DetailSidebar 不存在,主图占满(查 `.chart-area.no-sidebar` 类)
2. 点 `data-testid="panel-toggle-topology"` → TopologyControl 出现
3. 点 `data-testid="panel-toggle-sidebar"` → DetailSidebar 出现 + `.no-sidebar` 类消失
4. 三 chip active 态正确切换(`.level-btn.active` 类)

`tests/components/KlineChart.slider.spec.ts`(新建或并入既有 chart 测试):
1. `panels.showSlider=false` 时 `setOption` 的 dataZoom 数组里 type='slider' 项 `show:false`,type='inside' 项常驻(无 show 字段或 show=true)
2. 切到 `showSlider=true` 触发 re-render,slider 项 `show:true`

### 8.3 E2E(playwright,通过 path2_web 启动 + 加载现有扫描)

`e2e/panels.spec.ts`(新建,可放在已有 e2e 目录下):
1. 进入页面 + 加载历史扫描 → 默认看不到 Topology / Sidebar / Slider;只见 K 线主+副
2. 三个 chip 各点一次 → 三个面板分别出现
3. 刷新页面 → 三个面板仍可见(localStorage 持久化)
4. 全部 toggle off + 刷新 → 仍全隐

---

## 9. 实施顺序(给 writing-plans 的参考)

1. **panels store**(独立、可单测)
2. **ChartArea 模板 + 样式**(加 chip + v-if + grid 列切换)
3. **KlineChart / chart.ts**(slider show:bool 串通)
4. **测试**(store 单测 → 组件测 → e2e)
5. **playwright 实测三档场景**(默认/全开/刷新持久化)

每步可独立验证。整个工作量小,**一份 plan 一 session 跑完即可**(不拆段)。

---

## 10. 影响面盘点

| 模块 | 改动 |
|---|---|
| `path2_web_ui/src/stores/panels.ts` | 新建 |
| `path2_web_ui/src/components/ChartArea.vue` | template/script/style 三段都改 |
| `path2_web_ui/src/components/KlineChart.vue` | render() 增传 sliderShow + 新增 watch |
| `path2_web_ui/src/render/chart.ts` | `buildKlineOption` 接受 `sliderShow`,slider 项加 show 字段 |
| 测试 | 新增 3 个 spec 文件 |
| 后端 | **零改动** |
| 文档 | `.claude/docs/modules/path2_web.md` 可选追一行(update-ai-context 走) |

---

## 11. 验收

- 三 gate 绿:vitest + vue-tsc + vite build
- 浏览器实测三档(默认全隐 / 全开 / 刷新持久化)截图保留至会话结束清场
- 现有 258 测试零回归;新增至少 9 个测试(store 5 + ChartArea 4)
