# Marker Tooltip Confine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `chart.ts` 里 K bar tooltip 与 marker tooltip 两个配置对象各加 `confine: true`，让 ECharts 自动把 tooltip 限制在 chart 容器内、不再被边界截断（前置 cleanup spec 落地后 marker tooltip 高度增加，在 chart 底部 hover 时 Attributes 段被截断的 bug）。

**Architecture:** 改动两处 ECharts tooltip 配置对象。零内容变化、零额外依赖。

**Tech Stack:** TypeScript / Vue 3 / ECharts / vitest

**Spec:** `docs/superpowers/specs/2026-06-29-marker-tooltip-confine-design.md`

## Global Constraints

- 工作目录：仓库根 `/home/yu/PycharmProjects/Trade_Strategy`，前端命令前缀 `cd path2_web_ui &&`
- 包管理：`pnpm`
- 测试命令：`pnpm test --run <pattern>`（`--run` = 非 watch 模式）
- 类型检查：`pnpm vue-tsc --noEmit`
- 构建：`pnpm build`
- 不动后端、不动 tooltip 内容/formatter/字号/间距、不引入 `appendToBody` / `position` 函数 / `extraCssText`（YAGNI）
- 注释中文、commit message 中文 + 末尾 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer
- 不使用 `git --no-verify` / `--amend` / `--no-gpg-sign`；hook 失败修根因后再 commit
- Playwright 卫生：使用过 playwright MCP 的回合，task 收尾时 `rm -rf .playwright-mcp/*`

---

## Task 1: confine: true 配置 + 单元测试

> 按 TDD：先写两个 expect confine=true 的失败测试，跑红 → 加 confine: true 两处 → 跑绿 → 类型检查 + build → commit。

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts:237-252`（两个 tooltip 配置对象各加 `confine: true`）
- Modify: `path2_web_ui/tests/chart.spec.ts:365-448`（D2 describe 块新增 2 个 case）

**Interfaces:**

Produces：无新增 export；仅修改 `buildKlineOption` 返回的 `tooltip` 与 marker series `tooltip` 对象内字段。

---

### Step 1: 在 chart.spec.ts D2 块末尾新增 2 个失败测试

- [ ] 编辑 `path2_web_ui/tests/chart.spec.ts`，在 `describe('buildKlineOption — D2 tooltipResolver', ...)` 闭合大括号之前（即文件第 447 行 `})` 之前）插入下面两个 it 块。新插入位置应在 D2 块最后一个 `it(...)` 之后、与同级 it 同样缩进：

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

- [ ] 若 D2 块内的 `stubResolver` 与 `baseInput` 命名与本 step 不一致（implementer 落地前请 grep 一遍），保持与该 describe 块上文相同的 stub 名即可，不要重新定义。

---

### Step 2: 跑测试确认红

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/chart.spec.ts`
- [ ] 预期：新增的两个 `confine: true` 断言失败（旧 chart.ts 未配置 confine，`tt.confine` 为 `undefined`）；D2 块其它 case 与文件其余块零回归。
- [ ] 若其它 case 也红，diagnose：是否 Step 1 编辑误改了同级 it 块或污染了 stubResolver 定义？

---

### Step 3: chart.ts 给两个 tooltip 加 confine: true

- [ ] 编辑 `path2_web_ui/src/render/chart.ts` 第 237-248 行的 `const tooltip = { ... }`，在 `trigger` 行下一行插入 `confine: true,`。改后整段：

```ts
  const tooltip = {
    trigger: 'axis' as const,
    confine: true,
    axisPointer: {
      // 普通模式 'line'(只竖线),横线由 KlineChart.vue 的 markLine 锁 close;
      // Ctrl 模式 KlineChart.vue 切回 'cross' 让 ECharts 自带横线跟鼠标。
      type: 'line' as const,
      lineStyle: { color: '#0088CC', type: 'dashed', width: 1.5, opacity: 0.7 },
      label: { show: false },
      snap: true,
    },
    formatter: buildBarTooltipFormatter(bars, ctrlState),
  }
```

- [ ] 编辑 `path2_web_ui/src/render/chart.ts` 第 250-252 行的 `markerTooltip` 三元表达式，在三元 truthy 分支对象里 `trigger` 与 `formatter` 之间插入 `confine: true,`。改后整段：

```ts
  const markerTooltip = (tooltipResolver || matchLabel)
    ? { trigger: 'item' as const, confine: true, formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel) }
    : undefined
```

---

### Step 4: 跑测试确认绿

- [ ] 运行：`cd path2_web_ui && pnpm test --run tests/chart.spec.ts`
- [ ] 预期：D2 块全部绿（含新增两个 confine case）；文件其它块零回归。
- [ ] 若仍红，diagnose：是否两个 confine 插入位置写错（如插到 markerTooltip 外层 / tooltip 内层错位）。

---

### Step 5: 全集回归 + tsc + build

- [ ] 运行：`cd path2_web_ui && pnpm test --run`
- [ ] 预期：所有 spec 全绿。
- [ ] 运行：`cd path2_web_ui && pnpm vue-tsc --noEmit`
- [ ] 预期：零类型错误（`confine` 是 ECharts `EChartsOption['tooltip']` / series tooltip 的合法字段，类型签名内置）。
- [ ] 运行：`cd path2_web_ui && pnpm build`
- [ ] 预期：build 成功。

---

### Step 6: Commit

- [ ] 暂存改动：

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/chart.spec.ts
```

- [ ] 创建 commit：

```bash
git commit -m "$(cat <<'EOF'
fix(web-ui): marker / K bar tooltip 加 confine: true 防溢出

前置 cleanup spec 落地后 marker tooltip 高度增加,在 chart 底部
hover 时 Attributes 段被截断。ECharts confine: true 让 tooltip
内容超出容器边界时自动翻转方向,整块保持可见。

按 docs/superpowers/specs/2026-06-29-marker-tooltip-confine-design.md。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] 运行 `git status` 确认 working tree 干净（除 unrelated 改动如 `SidebarResultList.vue`）。

---

## Task 2: 真实数据视觉验证（可选）

> 在真实数据上复现 spec §3.4 验收点。无生产改动，仅人工/playwright 视觉验证。

**Files:** 无生产改动；可能产生 `.playwright-mcp/*` 临时产物（收尾清理）。

---

### Step 1: 启 dev server

- [ ] 在终端启后端 + 前端：`uv run python scripts/run_path2_web.py`
- [ ] 等待两端就绪，记下前端本地 URL。

---

### Step 2: 复现该截图同位置 hover

- [ ] 用 Playwright 或浏览器打开前端 URL。
- [ ] 选用 burst 命中股（若不确定，参 [[project_path2_web_ui_levels_lanes]] memory 提到的 ACRS）。
- [ ] hover 一个位于 chart 底部附近的 burst event marker（重现原截图场景：tooltip 默认向下展开会撞底部边界）。
- [ ] 验证：tooltip 整块完全可见，Attributes 段头不再被截断；ECharts 应自动把 tooltip 翻转向上展开。

---

### Step 3: hover chart 右边缘 marker 验证横向 confine

- [ ] hover 一个位于 chart 右边缘附近的 marker，验证 tooltip 向左展开、不撞右边界。

---

### Step 4: Playwright 卫生

- [ ] 关闭 dev server。
- [ ] 清理 `.playwright-mcp/*`：`rm -rf .playwright-mcp/*`（保留目录本身）。

---

## Self-Review

- 覆盖 spec §3.1 改动（两个 tooltip 加 confine: true）→ Task 1 Step 3 完整对应
- 覆盖 spec §3.3 测试（D2 块新增 2 个 case）→ Task 1 Step 1 完整代码
- 覆盖 spec §3.4 验收（vitest + tsc + build + 真实数据）→ Task 1 Step 5 + Task 2
- 覆盖 spec §4 否决方案（appendToBody / position 函数）→ Global Constraints 已显式列出"不引入"
- 类型一致：`confine: true` 字面值，无 type drift 风险
- 命令一致：所有 `cd path2_web_ui &&` 前缀统一
- 无 placeholder、无 TODO、所有代码块完整可粘贴
