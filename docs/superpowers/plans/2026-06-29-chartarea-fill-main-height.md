# ChartArea 主图占满 main 剩余高度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ChartArea 占满 `.right` 全部可用高度,K 线主图 + 量能/markers/slider 副图自动随 main 大小伸缩,消除当前默认全隐场景下 ~640px 空白带。

**Architecture:** 三处纯 CSS:`.right` 改 `display: flex; flex-direction: column`,`.chart-area` 加 `flex: 1` + `grid-template-rows: auto auto 1fr`,`.kline` 由固定 `560px` 改 `100%`。ECharts 同一 canvas 内 grid 百分比布局自动等比映射;KlineChart 已有 `ResizeObserver` 触发 `chart.resize()`,零 JS 改动。

**Tech Stack:** Vue 3 SFC + scoped CSS;Playwright MCP(端到端度量 + 视觉)。

**Spec:** [docs/superpowers/specs/2026-06-29-chartarea-fill-main-height-design.md](../specs/2026-06-29-chartarea-fill-main-height-design.md)

## Global Constraints

- 仅改 `path2_web_ui/`,**后端零改**;仅 3 个 SFC 的 `<style>` 块,**0 行 JS / template 改动**
- 现有 271 测试零回归(本计划基线 = `af282a9` 提交时的 vitest 271 passed);每 task 结束三 gate 绿:`npx vitest run` + `npx vue-tsc -b` + `npx vite build`
- 不动 `prompts/command.md` 或与本任务无关的已 dirty 文件(若执行前 worktree 不干净需先 stash/commit 无关改动后再开 Task 1)
- 不引入 min-height 兜底(spec §2 明示);min-height: 0 在 grid item 处是为了**允许** 1fr 收缩、不是设下限
- Commit 消息中文 imperative;每 task 一 commit;末尾追加 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- 不使用 `--no-verify` / `--no-gpg-sign`
- Playwright 卫生:Task 2 用完 `.playwright-mcp/` 必须清空(`rm -rf /home/yu/PycharmProjects/Trade_Strategy/.playwright-mcp/*`,保目录本身;同步删 viewport 截图)
- e2e blank_gap 容差统一 ≤ 2px(浮点容差)

---

## File Structure

修改(3 文件,**纯 CSS,均在 `<style>` 块**):

- `path2_web_ui/src/components/App.vue` — 根布局 `.right` 改 flex column
- `path2_web_ui/src/components/ChartArea.vue` — `.chart-area` 加 `flex: 1 + min-h/w: 0`,row 3 由 `auto` 改 `1fr`
- `path2_web_ui/src/components/KlineChart.vue` — `.kline` 由 `height: 560px` 改 `height: 100%` + `min-height: 0`

无新建文件。无新建测试(纯 CSS 改动 vitest jsdom 不验布局,行为由 Task 2 e2e 度量验证)。

---

## Task 1: 三处 CSS 改动 + 三 gate 绿 + commit

**Files:**
- Modify: `path2_web_ui/src/components/App.vue`(`.right` 行)
- Modify: `path2_web_ui/src/components/ChartArea.vue`(`.chart-area` 块)
- Modify: `path2_web_ui/src/components/KlineChart.vue`(`.kline` 行)

**Interfaces:**
- Consumes: 无(独立 CSS 改动,不依赖任何上下文/接口)
- Produces:
  - `.right` 是 flex column 容器,子节点可拉伸
  - `.chart-area` 用 `flex: 1` 撑满 `.right`,`grid-template-rows: auto auto 1fr` 让 row 3 占剩余
  - `.kline { height: 100% }` 撑满 grid cell(其值由 row 3 = 1fr 决定)
  - 净效果:K 线 ECharts 容器自动随 `.right` 高度变化,内部 grid 百分比(price 72% / markers 18% / slider 4%)等比放大

### Step 1: 改 `path2_web_ui/src/components/App.vue`(`.right` 行)

定位 `<style>` 块内的 `.right { overflow: auto; }`(当前文件就这一行,grep `\.right\s*{`)。

修改前:
```css
.right { overflow: auto; }
```

修改后:
```css
.right { display: flex; flex-direction: column; min-height: 0; overflow: auto; }
```

**为什么 `min-height: 0`**:`.right` 是 `.app { display: grid }` 的子项,grid item 默认 `min-height: auto` 拒绝向下收缩。本身 `.right` 不会被父级压缩,加 `min-height: 0` 是 防御性正确(让 `.right` 的 flex 子节点 `.chart-area` 能在 `.right` 高度变化时正确响应,而不是被某个意外的 min-content 锁死)。`overflow: auto` 保留作极端窄视口兜底。

- [ ] **Step 2: 改 `path2_web_ui/src/components/ChartArea.vue`(`.chart-area` 块)**

定位 `<style scoped>` 内 `.chart-area { ... }` 块(grep `\.chart-area\s*{` 在 ChartArea.vue 里;在重写后的 line 76-81 附近)。

修改前:
```css
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto auto;
  gap: 0;
}
```

修改后:
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

**关键**:
- `flex: 1` 让 chart-area 撑满父 `.right` 的剩余高度(父此时是 flex column,本元素是唯一子)
- `grid-template-rows: auto auto 1fr` —— row 1 (level-bar, auto) + row 2 (topology-row v-if, auto, v-if 隐时塌缩 0) + row 3 (K 线 + sidebar, 1fr 占剩余)
- `min-height: 0` / `min-width: 0` —— 让 1fr row 在 `.right` 缩小时可以收缩,而不是被内部 min-content(560px 的 .kline 旧值)撑住
- **不动** `.chart-area.no-sidebar { grid-template-columns: 1fr }` 和 `.level-bar, .chart-area > .topology-row { grid-column: 1 / -1 }` 等其他规则

- [ ] **Step 3: 改 `path2_web_ui/src/components/KlineChart.vue`(`.kline` 行)**

定位 `<style>` 内 `.kline { ... }`(grep `\.kline\s*{` 在 KlineChart.vue;line 186 附近)。

修改前:
```css
.kline { width: 100%; height: 560px; min-width: 0; overflow: hidden; }
```

修改后:
```css
.kline { width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
```

`height: 100%` 让 .kline 撑满其 grid cell(row 3 col 1,大小由父 1fr 决定);`min-height: 0` 同上,允许收缩。`overflow: hidden` 保留以隔离 ECharts canvas 偶发溢出。

- [ ] **Step 4: 三 gate 全绿**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```
Expected:
- vitest:**271 passed**(零回归,纯 CSS 改无新增测)
- vue-tsc:0 errors
- vite build:成功

**为什么 vitest 不会跑出新失败**:既有 ChartArea.spec.ts / ChartArea.panels.spec.ts / ChartArea.activePattern.spec.ts 都不 assert 具体 CSS 值或 layout 尺寸(在 jsdom 里 layout 也不准),只验 DOM 树和 class 切换。本改未动 template/script/type,只改 `<style>` 内属性值。

- [ ] **Step 5: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/App.vue \
        path2_web_ui/src/components/ChartArea.vue \
        path2_web_ui/src/components/KlineChart.vue
git commit -m "$(cat <<'EOF'
feat(web-ui): ChartArea 主图占满 main 剩余高度

.right 改 flex column;.chart-area 加 flex:1 + grid row3=1fr;
.kline 由 560px 改 100%。ECharts 同 canvas 内 grid 百分比(price 72%/
markers 18%/slider 4%)自动等比映射,KlineChart 既有 ResizeObserver 触发
chart.resize(),0 JS 改动。消除「ChartArea 三处可隐藏面板」默认全隐
场景下 K 线下方 ~640px 空白带。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 端到端 playwright 度量 + 视觉验证

**Files:**
- (无源码改动;仅运行 + 截图 + 度量断言 + 清场)

**Interfaces:** N/A(验收 task)

**目的:** 在真浏览器里跑 4 个场景 + 截图,确认 Task 1 的 CSS 改动行为正确、ECharts 自适应工作。**这是验收门,不通过则 Task 1 有未发现实施缺陷。**

- [ ] **Step 1: 起 server**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
# 清掉可能的 stale server
pkill -f "run_path2_web.py" 2>/dev/null
pkill -f "vite --port 5173" 2>/dev/null
pkill -f "path2_web.main" 2>/dev/null
sleep 1
```

然后用 Bash `run_in_background: true` 启动:`uv run python scripts/run_path2_web.py`。

用 `until grep -qE "Uvicorn running" <bg-output-file>; do sleep 1; done` 等就绪(参考上一轮 Task 5)。

- [ ] **Step 2: Playwright 加载页面 + 打开历史(应见 4825 hits 那条扫描)**

通过 Playwright MCP:
1. `mcp__plugin_playwright_playwright__browser_navigate('http://localhost:5173/')`
2. `browser_snapshot` 找 "打开历史…" 按钮 → `browser_click`
3. 在 Scan Results dialog 双击最新一行(应是 4825 / 6048 / bottom_burst+bo_only)
4. 等待数据加载(`browser_wait_for time:3` 或 snapshot 直到看到 K 线 main 渲染)

- [ ] **Step 3: 度量「默认全隐」场景**

`browser_evaluate`:

```js
() => {
  const right = document.querySelector('.right');
  const ca = document.querySelector('.chart-area');
  const lb = document.querySelector('.level-bar');
  const tr = document.querySelector('.topology-row');     // v-if=false 时不存在
  const kl = document.querySelector('.kline');
  const r = (el) => el?.getBoundingClientRect();
  const right_r = r(right), ca_r = r(ca), lb_r = r(lb), kl_r = r(kl);
  return {
    right_h: right_r?.height,
    chart_area_h: ca_r?.height,
    level_bar_h: lb_r?.height,
    topology_row_present: !!tr,
    kline_h: kl_r?.height,
    no_sidebar: ca?.classList.contains('no-sidebar'),
    grid_template_rows: getComputedStyle(ca).gridTemplateRows,
    // 关键断言变量
    chart_area_fills_right: Math.abs((ca_r?.height ?? 0) - (right_r?.height ?? 0)) <= 2,
    blank_gap: ca_r ? ca_r.height - ((lb_r?.height ?? 0) + 0 + (kl_r?.height ?? 0)) : null,
  };
}
```

Expected:
- `topology_row_present === false`(默认隐)
- `no_sidebar === true`
- `chart_area_fills_right === true`(.chart-area height ≈ .right height,容差 ≤ 2px)
- `kline_h ≈ right_h - level_bar_h`(差不超过 2px)
- `blank_gap ≤ 2`(K 线无尾部空白)

- [ ] **Step 4: 度量「Topology 开」场景**

`browser_click('[data-testid="panel-toggle-topology"]')`,然后 `browser_wait_for time:1`(给 ResizeObserver 一拍),再跑:

```js
() => {
  const right = document.querySelector('.right');
  const ca = document.querySelector('.chart-area');
  const lb = document.querySelector('.level-bar');
  const tr = document.querySelector('.topology-row');
  const kl = document.querySelector('.kline');
  const r = (el) => el?.getBoundingClientRect();
  const right_r = r(right), ca_r = r(ca), lb_r = r(lb), tr_r = r(tr), kl_r = r(kl);
  return {
    topology_row_present: !!tr,
    topology_row_h: tr_r?.height,
    kline_h: kl_r?.height,
    blank_gap: ca_r ? ca_r.height - ((lb_r?.height ?? 0) + (tr_r?.height ?? 0) + (kl_r?.height ?? 0)) : null,
    chart_area_h: ca_r?.height,
    right_h: right_r?.height,
  };
}
```

Expected:
- `topology_row_present === true`
- `topology_row_h > 50`(具体值取决于 TopologyControl 实际渲染高度,只要 > 50 即视为正常展开)
- `blank_gap ≤ 2`(level + topology + kline 加起来 ≈ chart-area;K 线自动让出 topology_h 后仍撑满)
- `chart_area_h ≈ right_h`(容差 ≤ 2px)

- [ ] **Step 5: 度量「三档全开」场景 + 视觉截图**

依次 click 余下两个 chip:
- `browser_click('[data-testid="panel-toggle-sidebar"]')`
- `browser_click('[data-testid="panel-toggle-slider"]')`

各等 `browser_wait_for time:1`。然后:

```js
() => {
  const right = document.querySelector('.right');
  const ca = document.querySelector('.chart-area');
  const lb = document.querySelector('.level-bar');
  const tr = document.querySelector('.topology-row');
  const kl = document.querySelector('.kline');
  const sidebar = Array.from(ca?.children ?? []).find(c => c.className === 'sidebar');
  const r = (el) => el?.getBoundingClientRect();
  const right_r = r(right), ca_r = r(ca), lb_r = r(lb), tr_r = r(tr), kl_r = r(kl), sb_r = r(sidebar);
  return {
    no_sidebar_class: ca?.classList.contains('no-sidebar'),
    grid_cols: getComputedStyle(ca).gridTemplateColumns,
    sidebar_present: !!sidebar,
    sidebar_h: sb_r?.height,
    kline_h: kl_r?.height,
    kline_sidebar_row_equal: sb_r && kl_r ? Math.abs(sb_r.height - kl_r.height) <= 2 : null,
    blank_gap: ca_r ? ca_r.height - ((lb_r?.height ?? 0) + (tr_r?.height ?? 0) + (kl_r?.height ?? 0)) : null,
  };
}
```

Expected:
- `no_sidebar_class === false`
- `grid_cols` 是 2 列(类似 `"... 280px"`)
- `sidebar_present === true`
- `kline_sidebar_row_equal === true`(K 线 col1 与 sidebar col2 同 row,高度一致)
- `blank_gap ≤ 2`

然后 `browser_take_screenshot fullPage:true filename:"task2-three-open.png"` 抓全屏,人眼确认 K 线 + topology + sidebar + slider 四元素铺满,无尾部空白。

- [ ] **Step 6: 度量「默认场景」回归(关掉三个 chip)**

依次 click 三个 chip 关掉(它们是 toggle),`browser_wait_for time:1`,重跑 Step 3 的 evaluate。Expected: 与 Step 3 一致(blank_gap ≤ 2、chart_area_fills_right === true)。

也截一张默认态的 viewport 全屏:`browser_take_screenshot filename:"task2-default-no-gap.png"`,人眼确认 K 线主图占满 main 区域、无 ~640px 空白带。

- [ ] **Step 7: 清场**

```bash
# 通过 TaskStop 杀启动的后台 server task(或 pkill 兜底)
pkill -f "run_path2_web.py" 2>/dev/null
pkill -f "vite --port 5173" 2>/dev/null
pkill -f "path2_web.main" 2>/dev/null
sleep 1
rm -rf /home/yu/PycharmProjects/Trade_Strategy/.playwright-mcp/*
rm -f /home/yu/PycharmProjects/Trade_Strategy/task2-three-open.png \
      /home/yu/PycharmProjects/Trade_Strategy/task2-default-no-gap.png
```

- [ ] **Step 8: 无 commit;若 Step 3-6 任一断言失败,回 Task 1 修后重跑 Task 2**

如果 `blank_gap > 2` 或 `chart_area_fills_right === false`:
- 检查 `.right` 是否真的成了 flex column(`getComputedStyle(.right).display === 'flex'`)
- 检查 `.chart-area` 是否 `flex: 1`(`flexGrow === '1'`)
- 检查 `.kline` 是否 `height: 100%`(实际 height 应 ≈ row 3 高度)

回 Task 1 修后,**全 task 重跑**(三 gate + Task 2 全部场景)。

---

## Self-Review 结果(plan 作者自检)

### Spec coverage

- spec §3.1(`.right` flex 改造)→ Task 1 Step 1
- spec §3.2(`.chart-area` flex + 1fr)→ Task 1 Step 2
- spec §3.3(`.kline` 100%)→ Task 1 Step 3
- spec §3.4(DetailSidebar 自动跟随,无须改)→ Task 1 不涉及代码、Task 2 Step 5 度量验证
- spec §4 行为矩阵 4 场景 → Task 2 Step 3(默认) / Step 4(Topology 开) / Step 5(三档全开) / Step 6(回默认)
- spec §5 风险 1(极端窄 main)→ 当前 viewport 不复现,plan 不强测;ECharts 既有自适应 + min-height: 0 + .right overflow:auto 兜底已覆盖
- spec §5 风险 2(DetailSidebar 内部 height 假设)→ Task 2 Step 5 度量 sidebar_h 和 kline_sidebar_row_equal 暴露
- spec §6.1(单测零回归 271)→ Task 1 Step 4 三 gate 验
- spec §6.2(e2e 4 场景)→ Task 2 全程
- spec §6.3(三 gate)→ Task 1 Step 4

全覆盖,无缺口。

### Placeholder scan

- 全部 step 有具体 CSS 改动 before/after、命令、预期值
- 容差 ≤ 2px 在 Global Constraints 和 spec 都明确
- 无 TBD/TODO/"similar to"

### Type consistency

- CSS 属性名跨 task 一致:`flex: 1`、`min-height: 0`、`grid-template-rows: auto auto 1fr`、`height: 100%`
- e2e selector 一致:`.right` / `.chart-area` / `.level-bar` / `.topology-row` / `.kline` / `.sidebar` / `[data-testid="panel-toggle-..."]`
- 度量变量名一致:`blank_gap` / `chart_area_fills_right` / `kline_sidebar_row_equal`

### 细节修正

- Task 2 Step 4 给 Topology 展开后等 1s 让 ResizeObserver 触发(避免在 chart.resize() 完成前度量)
- Task 2 Step 7 清场包含 server kill + .playwright-mcp 清空 + 截图删除,完整符合 CLAUDE.md 卫生约定
