# 副图拆分后 tooltip / hover / crosshair 三症状分析报告

**日期**:2026-07-02
**分支**:`align` @ HEAD
**Team**:archeo(diff 挖掘)/ specreader(spec 意图)/ verifier(Playwright 实测)
**性质**:分析报告,不涉及代码修改。修复方案供用户拍板后另开 spec + plan 实施。

---

## 0 · Executive Summary

主副图拆分为两个 ECharts 实例(commit `8479f6d`)后出现三症状,Playwright **全部 100% 复现**:

- **S1** — 悬停副图 marker/bracket → sub-outer 出滚动条 + tooltip 显示不全
- **S2** — 悬停副图 marker → 主图 K 线 tooltip **同时错位**出现(单实例时互斥)
- **S3** — 主图与副图无贯穿悬停竖虚线

**归类**(spec 视角):

| 症状 | 归类 | 一句话理由 |
|---|---|---|
| S1 | **(b) 拆分副作用,spec 未预见** | spec 只保证 axisPointer 不受 scrollTop 影响,未规定 marker tooltip 需 `appendToBody / confine` 免撑高 sub-outer |
| S2 | **(b) 拆分副作用,spec 未预见** | spec §3.5 一笔带过 "connect 同步 tooltip",未定义同步语义;单实例天然互斥契约拆散后失效 |
| S3 | **(c) spec 明确要求,实现漏落(明确回归)** | 范围行 (7)、§1.2、§3.5、§5.5、§6.1 硬约束"贯穿虚线,断口 ≤ 2px",Plan Final Verification 硬承诺,当前完全无贯穿 |

**共同上游根变量**:
- **`echarts.connect([chartMain, chartSub])`**(KlineChart.vue:206-207)= S2 与 S3 的共同开关(连了 → S2 错位广播出现;没配 `link` → S3 无同步);
- **S1 独立** = 纯 DOM/CSS + ECharts tooltip 挂载语义,与 connect 无关。

**综合建议**:一次收口修复三症状,方案概览(详见 §4):
1. chartSub 顶层 tooltip 加 `appendToBody:true + confine:true`(修 S1)
2. 删除 `echarts.connect`,改 manual 同步 axisPointer + dataZoom(不同步 tooltip)(修 S2 + S3 位置同步)
3. 可选:DOM crosshair overlay 覆盖 divider handle + banner 断口(彻底消除物理断口,修 S3 视觉完美化)

---

## 1 · S1:hover 副图 → sub-outer 出滚动条 + tooltip 显示不全

### 1.1 Playwright 实测证据(verifier)

| 指标 | Baseline | Hover 后 |
|---|---|---|
| `.sub-outer` scrollHeight | 120 | **476** |
| `.sub-outer` clientHeight | 120 | 120 |
| `subOuter_hasScrollbar` | false | **true** |
| `.sub-inner` scrollHeight | 120 | **476** |
| tooltip DOM rect | — | x=605 y=1007 w=221 **h=348** |
| **tooltip parentElement.className** | — | **`sub-inner`** |
| tooltip zIndex | — | 9999999 |

复现率 100%。截图 `verifier_shots/03_sym1_tooltip_scrollbar.png`。

DOM 关键切片:

```
.sub-outer  {height:120px, overflow-y:auto, sh:476, ch:120}
  .sub-inner  {height:120px, position:relative, sh:476, ch:120}
    <div><canvas 722×120></div>
    <div style="position:absolute; z-index:9999999; ...">TOOLTIP h:348  ← 撑高源
```

### 1.2 根因

- ECharts v5 中 `tooltip.appendToBody` **只在顶层 tooltip 组件级生效**;系列级 tooltip 上的 `appendToBody:true` 被静默忽略。
- 当前 `chartSub` 顶层 tooltip 为 `{ trigger:'item', show:false }`(chart.ts:503-506),**无 appendToBody / confine**;marker 三系列各自 `series[i].tooltip.appendToBody:true`(chart.ts:483-489)不生效。
- 结果:tooltip DOM 作为绝对定位子节点插入 `.sub-inner`(position:relative),其自身高 348px **撑高 sub-inner scrollHeight 120 → 476**,`.sub-outer` `overflow-y:auto` 显滚动条。
- Tooltip 自身 `extraCssText: max-height:calc(100vh-16px); overflow-y:auto` 只让 tooltip 内部滚动,但 tooltip 底 y=1355 > viewport 底 1000 → 部分内容裁掉 → "显示不全"。

### 1.3 归类

**(b) 拆分副作用,spec 未预见**。
- spec1 §5.6 "sub-outer 滚动 + hover 竞态"(line 367-371)只保证 axisPointer x 不受 scrollTop 影响,**未规定 tooltip DOM 定位**。
- Plan1 marker tooltip 定义(line 1063-1069, 1151-1157)只带 `position:viewportAwareTooltipPosition`,无 appendToBody / confine 字段。
- spec 假设 "canvas 局部坐标搞定一切",未预见 tooltip DOM 反过来撑高滚动内容。

---

## 2 · S2:hover 副图 marker → 主图 K 线 tooltip 同时错位出现

### 2.1 Playwright 实测证据(verifier)

clean 会话中,dispatch `showTip` 到 sub 后:

```json
step0_baseline: {count: 0}
step1_after_sub_showTip: {
  count: 2,
  tips: [
    { text: "Identity role:burst time:2025-05-14→2025-05-15 id:burst_162_163 ...",
      rect: {x:605, y:1007, w:221, h:348}, parent: "sub-inner" },     // sub tooltip
    { text: "Date: 2025-01-02  Open:0.06 High:0.07 Low:0.06 Close:0.07 ...",
      rect: {x:300, y:685, w:131, h:190}, parent: "" }                // ← 意外的 main K 线 tooltip
  ]
}
```

复现率 100%。截图 `verifier_shots/04_sym2_dual_tooltips.png`。

**关键**:sub tooltip 对应 2025-05-14(index 162),main tooltip 却是 2025-01-02(index 0)—— 位置完全错位。

### 2.2 根因

- KlineChart.vue:206-207 `echarts.connect([chartMain, chartSub])` 把两 instance 挂同 group(实测 `main.group === sub.group === "g_1782923107694"`)。
- ECharts connect 语义:同组一图的 `showTip / hideTip / dataZoom` action **广播**给同组其他图,广播时**复用相同 `seriesIndex + dataIndex`**。
- sub 的 `showTip(seriesIndex:0, dataIndex:0)` = intervals[0] = burst_162_163(2025-05-14),被广播到 main → main.series[0] = kline + dataIndex=0 = 首根 2025-01-02 K 线 → main 侧弹 K 线 tooltip。
- 单实例时靠**共享同一 tooltip 组件 DOM**天然互斥(marker series.tooltip override 顶层配置);双实例时**每图独立 tooltip 组件**,connect 只做 action 广播,不做互斥仲裁。

### 2.3 归类

**(b) 拆分副作用,spec 未预见**。
- spec1 §3.5 line 242 只写 "connect 自动同步 axisPointer + dataZoom + **tooltip**",**未定义**同步语义 = "两图各自显示" 还是 "只显示一个"。
- Plan1 line 1023 删除 axisPointer.link 交给 connect,未同步交代 tooltip 互斥性。
- 单实例天然互斥是隐式契约,拆分后消失,spec 静默未预见。

---

## 3 · S3:主副图无贯穿悬停竖虚线

### 3.1 Playwright 实测证据(verifier)

**方向 A(main hover)**(`07_sym3_main_hover.png`):
- 主图 y=31–875:清晰竖虚线 @ x≈670
- 副图 y=879–999:**同 x=670 无线**;副图残留一条旧 dashed line @ x≈595(其自身惰性 axisPointer,非从主图贯穿)

**方向 B(sub hover)**(`08_sym1_sym2_clean.png`):
- 副图 y=879–999:竖虚线 @ x≈595
- 主图 y=31–875:**同 x=595 无线**;仅一条水平 dashed y-line @ y≈420(主图自身的 K 线 tooltip y-axisPointer)

复现率 100%。

### 3.2 根因

- 两 instance 各自 xAxis 独立,axisPointer 只在**同 instance grid 内**画。
- **`mainAxisPointer[0].link = []` + `subAxisPointer[0].link = []`** —— `axisPointer.link` 未配置。
- `echarts.connect` 只广播 `showTip`,广播时用相同 seriesIndex/dataIndex 落在两图**不同 xAxis position**(sub 的 index 162 广播到 main 落在 index 0)—— 两图各在自己错位 index 上画一条局部虚线,**不是贯穿**。
- 即便配 link,ResizableDivider handle 4px + candidate 态 banner sticky 16px 造成**物理断口 ≥ 4px**,spec §6.1 line 379 承诺 "断口 ≤ 2px" 本身与 handle 4px 冲突,axisPointer 无法穿越 handle,除非 DOM overlay。

### 3.3 归类

**(c) spec 明确要求,实现漏落(明确回归)**。全线硬约束:
- 范围行(7) "保留贯穿主副图鼠标垂直虚线"
- §1.2 line 35 设计原则
- §3.5 line 236-247 connect 契约("若断口过大 fallback manual sync"预留但未实现)
- §5.5 line 362-365 断口 fallback
- §6.1 line 379 实测承诺 "两竖线断口 ≤ 2px"
- §9 line 431 引用文档结论
- Plan1 line 2093 Final Verification 第 1 项硬承诺

---

## 4 · 修复方案

### 4.1 单症状可行方案对比

| 症状 | 方案 A(推荐) | 方案 B(备选) | 方案 C(不推荐) |
|---|---|---|---|
| S1 | chartSub 顶层 tooltip 加 `appendToBody:true, confine:true`,让 tooltip 挂到 body(1 处配置) | CSS 隔离:sub-inner 去 `position:relative` / 加 `contain:layout` | 无 |
| S2 | 删 `echarts.connect`,改 **manual 同步 axisPointer + dataZoom**(不同步 tooltip);符合 spec §3.5 fallback 契约 | 保留 connect,`main.on('showtip', p ⇒ ...)` 检测源头并 dispatchAction hideTip 抑制(hacky,fragile) | kline-hit-spanner + kline 系列改 axis-trigger:破坏主图 K 线 hover UX,违反 spec §3.5 硬约束 |
| S3 | 与 S2 方案 A 合并 —— **manual 同步 axisPointer**;可选补 DOM crosshair overlay 消 handle 物理断口 | 保 connect + 配 `axisPointer.link`(跨 instance 支持不完全可靠,官方文档警告 link 主要给单 chart 多 xAxis 用) | 依赖 connect 隐式行为(现状) |

### 4.2 推荐一次收口的综合方案

**Step 1**:chartSub 顶层 tooltip 加 appendToBody + confine
```ts
// chart.ts:503-506 (buildSubOption)
tooltip: { trigger: 'item', show: false, appendToBody: true, confine: true }
```
**修复目标**:S1(tooltip DOM 从 sub-inner 迁到 body,不再撑高)

**Step 2**:删除 `echarts.connect`,改 manual 同步 axisPointer + dataZoom
```ts
// KlineChart.vue:206-207 —— 删除
// echarts.connect([chartMain, chartSub])

// 新增双向 manual 同步:
chartMain.getZr().on('mousemove', e => {
  const rel = chartMain.convertFromPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])
  chartSub.dispatchAction({
    type: 'updateAxisPointer',
    currTrigger: 'mousemove',
    x: chartSub.convertToPixel({ gridIndex: 0 }, rel)[0],
    y: 5   // sub grid 内任意 y,只为触发 axisPointer
  })
})
// sub → main 反向同步同理
// dataZoom:main.on('datazoom', p => sub.dispatchAction({type:'dataZoom', start:p.start, end:p.end}))
```
**修复目标**:
- S2:拆 connect → 无跨图 showTip 广播 → main tooltip 不再错位
- S3 位置层:manual updateAxisPointer 保证两图 xAxisValue 严格一致

**Step 3(可选)**:DOM crosshair overlay 消物理断口
- 用一个跨 `.main-chart + ResizableDivider handle + .sub-outer(含 banner)` 的绝对定位 DOM 元素(z-index 覆盖 handle),画一条视觉贯穿的竖线(rgba 微透明 dashed,x 由 manual sync 事件驱动)
- Spec §7 line 402-409 v2 增量提到 "DOM fake line" 兜底,此为该 idea 的落地
- **修复目标**:S3 视觉完美化,消除 handle 4px + banner 16px 物理断口

### 4.3 修复覆盖矩阵

| 症状 | Step 1 | Step 2 | Step 3 |
|---|---|---|---|
| S1 | ✓ | — | — |
| S2 | — | ✓ | — |
| S3 位置同步 | — | ✓ | — |
| S3 物理断口 | — | 4px 残留 | ✓ 消除 |

### 4.4 侵入范围与风险评估

| 步骤 | 侵入文件 | 代码量 | 风险 |
|---|---|---|---|
| Step 1 | chart.ts (1 处) | +2 属性 | 低 |
| Step 2 | KlineChart.vue (删 connect + 加 listener) | +30~50 行 | 中(需实测 axisPointer.link + 边界:hover 出图外时清 sub 侧、reload 后 re-bind、convertFromPixel 在 dataZoom 变化时口径一致等) |
| Step 3 | KlineChart.vue + KlineChart.vue template + CSS | +30~50 行 | 低-中(纯视觉 overlay,不影响业务逻辑) |

---

## 5 · 下一步建议

1. **用户拍板方向**:采纳综合方案(Step 1+2+可选 3)还是只做 Step 1+2?
2. **一次修订两 spec + 一 plan**:
   - 修订 spec1 §3.5 明确 "manual 同步替代 connect,拆 tooltip 广播";
   - 新增 spec3(或补 spec1 v2 增量)记录 tooltip appendToBody 契约与 DOM overlay 设计;
   - 单 plan 覆盖三 step,subagent-driven 实施。
3. **Playwright 回归**:三症状 e2e 断言应从 "复现" 反转为 "不复现"(scrollHeight ≡ clientHeight / tooltip count == 1 / 两图同 x 竖线断口 ≤ 2px)。

---

## 附录 · 证据与产物路径

- archeo report:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-align/e9161059-3b17-43f6-8fc5-7d655c0d58f8/scratchpad/archeo_report.md`
- specreader report:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-align/e9161059-3b17-43f6-8fc5-7d655c0d58f8/scratchpad/specreader_report.md`
- verifier report:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-align/e9161059-3b17-43f6-8fc5-7d655c0d58f8/scratchpad/verifier_report.md`
- verifier 截图:`/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy-align/e9161059-3b17-43f6-8fc5-7d655c0d58f8/scratchpad/verifier_shots/{01..08}*.png`
- 相关 spec:
  - `docs/superpowers/specs/2026-07-01-path2-web-subchart-scroll-drag-design.md`
  - `docs/superpowers/specs/2026-07-01-path2-web-subchart-fixed-decor-design.md`
- 关键 commit 序列(自旧到新):`b2bdfa9`(banner sticky)→ `95f5554`(chart.ts builders)→ **`8479f6d`(双实例 + connect)** → `0bc6eae`(graphic 迁移)→ `fa5696b`(subHeightOverride)→ `9148647`(常量)

---

## 附录 · 关键代码定位

- KlineChart.vue: 2-9 (template), 44-48 (effectiveSubH), **206-207 (echarts.connect)**, 244-283 (datazoom + updateAxisPointer listener), 333-338 (sub-outer CSS)
- chart.ts: 295-308 (chartMain tooltip), **313 (axisPointer.link 删除注释)**, 319-325 (chartMain xAxis axisPointer), 483-489 (chartSub markerTooltip 系列级), **503-506 (chartSub 顶层 tooltip,缺 appendToBody)**, 513-519 (chartSub xAxis axisPointer), 522 (chartSub dataZoom)
- CandidateStatusBar.vue: 47-59 (sticky, flex-shrink:0, height:16px)
- ResizableDivider.vue: 70-72 (4px handle → hover 6px)
