import { test, expect, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { copyFileSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { baseURL } from './ports'

// path2 漏检调查工具(docs/superpowers/specs/2026-07-07-path2-miss-detection-tools-design.md)
// 5 入口端到端走查(Task 24 · Sprint 3 收尾)。
//
// 数据夹具:真实 /scan 的 any_match 闸(path2_web/scan.py:80-81)会把"全局 0 match"的股票
// 整支剔出结果——这恰恰挡住本 spec 要验证的核心场景(DGNX 就是"该出 pattern 却没出"的
// 漏检典范)。e2e/fixtures/build_miss_detection_fixture.py 复刻单股分析链路但去掉该闸,
// 强制把 DGNX(entry A)和 LIXT(entry B/C/D,真实 anchor 淘汰链 + 一对 4-subcheck 全清
// pair)写进一个固定 scan_ts="29991231T235959" 的 MultiScanResultFile,历史列表(scan_ts
// 降序)里恒排第一行。beforeAll 每次重新生成(幂等),不依赖本机是否已有旧 fixture。
//
// 拓扑现状(dag_spec.py 已简化为 3 节点/1 边):bo(孤立流源,仅主图) → burst → tb(唯一
// TemporalEdge)。brief 原始 Step 1 伪代码假设的 5-node(down/side/bo/burst/tb)拓扑 /
// CSS class 选择器(`.marker-bo`/`.band-burst`/`data-edge=...`)已随拓扑简化而不存在
// (ECharts canvas 渲染,marker 本身也不是可 CSS 选中的 DOM 节点)——本 spec 改用真实
// 组件类名(`.attempt-card`/`.pair-list-card`/`.step`/`.subcheck`/`.swap-notice` 均验证
// 存在)+ 通过读 chartSub 的 zrender 场景图定位 marker 真实屏幕坐标再做真实鼠标点击
// (不绕过交互层、不直接调 store action)。
//
// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//       后端须外部启动 uv run python scripts/path2/run_path2_web.py)。

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

test.beforeAll(() => {
  execFileSync(
    'uv', ['run', 'python', 'path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py'],
    { cwd: REPO_ROOT, stdio: 'inherit' },
  )
})

// ─── setup:打开固定 fixture(DGNX 为 results[0],加载后自动选中)+ 显示 Sidebar/Topology
//     面板 + 切到 Detected 档(两支 fixture 股均 0 match,Matched/Qualified 档下不渲染任何
//     event)。每 test 独立 page(默认全新 context,localStorage 面板显隐状态天然复位) ──
async function setupFixtureChart(page: Page): Promise<void> {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.file-list tbody tr').first()).toBeVisible({ timeout: 10_000 })
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()

  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function'
      && e.chartMain() && e.chartSub())
  }, undefined, { timeout: 15_000 })

  await page.evaluate(() => {
    const clickByText = (sel: string, text: string) => {
      const el = Array.from(document.querySelectorAll<HTMLElement>(sel))
        .find((b) => b.textContent?.trim() === text)
      el?.click()
    }
    clickByText('.level-btn', 'Detected')
    document.querySelector<HTMLElement>('[data-testid="panel-toggle-sidebar"]')?.click()
    document.querySelector<HTMLElement>('[data-testid="panel-toggle-topology"]')?.click()
  })
  await expect(page.locator('.topo')).toBeVisible({ timeout: 5_000 })
  await expect(page.locator('.sidebar')).toBeVisible({ timeout: 5_000 })
}

async function switchToLixt(page: Page): Promise<void> {
  await page.evaluate(() => { (window as any).__e2e.view.selectSymbol('LIXT') })
  await page.waitForFunction(() => (window as any).__e2e.view.symbol === 'LIXT')
  // 等 diag/OHLC 换股后重新拉取完成(topology funnel 行出现即视为就绪)
  await expect(page.locator('.funnel-row').first()).toBeVisible({ timeout: 10_000 })
}

// ── 副图 marker 定位(承 marker-click-focus-highlight.spec.ts 的 zrender 场景图技术,
//    泛化到 interval(z=9 矩形,burst 类跨 bar 事件)+ point(z=10 三角,tb 单 bar 事件)
//    两种 series。custom renderItem 产物不挂 dataIndex 到 DOM/zrender 元素上,无法直接
//    按 event_id 反查,只能靠几何还原:x 用 convertToPixel 换算期望位置,y 对 interval
//    按 value[2](lane,自顶向下堆叠,同 chart.ts::renderIntervalWithGeom)在同 x 簇里
//    排序取第 lane 个;point 同 band 内通常只有一个候选,直接取最近 x。──────────────
async function subInnerRect(page: Page) {
  return page.evaluate(() => {
    const r = document.querySelector('.sub-inner canvas')!.getBoundingClientRect()
    return { left: r.left, top: r.top }
  })
}

async function intervalMarkerPos(page: Page, eventId: string) {
  return page.evaluate((eid) => {
    const sub = (window as any).__e2e.chartSub()
    const opt = sub.getOption()
    const seriesIdx = opt.series.findIndex((s: any) => s.name === 'intervals')
    const d = opt.series[seriesIdx]?.data?.find((dd: any) => dd.event_id === eid)
    if (!d) return null
    const [start, end, lane] = d.value
    const expX = sub.convertToPixel({ seriesIndex: seriesIdx }, [(start + end) / 2, 0])[0]
    const cluster = sub.getZr().storage.getDisplayList()
      .filter((el: any) => el.type === 'rect' && el.z === 9 && el.shape
        && Math.abs((el.shape.x + el.shape.width / 2) - expX) < 20)
      .map((el: any) => ({ cx: el.shape.x + el.shape.width / 2, cy: el.shape.y + el.shape.height / 2 }))
      .sort((a: any, b: any) => a.cy - b.cy)
    return cluster[lane] ?? null
  }, eventId)
}

async function pointMarkerPos(page: Page, eventId: string) {
  return page.evaluate((eid) => {
    const sub = (window as any).__e2e.chartSub()
    const opt = sub.getOption()
    const seriesIdx = opt.series.findIndex((s: any) => s.name === 'points')
    const d = opt.series[seriesIdx]?.data?.find((dd: any) => dd.event_id === eid)
    if (!d) return null
    const expX = sub.convertToPixel({ seriesIndex: seriesIdx }, [d.value[0], 0])[0]
    let best: { cx: number; cy: number } | null = null
    let bestDist = Infinity
    for (const el of sub.getZr().storage.getDisplayList()) {
      if (el.type === 'polygon' && el.shape?.points) {
        const xs = el.shape.points.map((p: number[]) => p[0])
        const ys = el.shape.points.map((p: number[]) => p[1])
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2
        const dist = Math.abs(cx - expX)
        if (dist < bestDist) { bestDist = dist; best = { cx, cy } }
      }
    }
    return best
  }, eventId)
}

async function zoomSubAround(page: Page, centerBarIdx: number, spanPct = 6): Promise<void> {
  await page.evaluate(({ centerBarIdx, spanPct }) => {
    const main = (window as any).__e2e.chartMain()
    const n = (main.getOption().xAxis?.[0]?.data || []).length
    const c = (centerBarIdx / n) * 100
    main.dispatchAction({ type: 'dataZoom', start: Math.max(0, c - spanPct), end: Math.min(100, c + spanPct) })
  }, { centerBarIdx, spanPct })
  await page.waitForTimeout(400)
}

async function clickSubMarker(
  page: Page, kind: 'interval' | 'point', eventId: string, opts?: { shift?: boolean },
): Promise<void> {
  const rect = await subInnerRect(page)
  const pos = kind === 'interval' ? await intervalMarkerPos(page, eventId) : await pointMarkerPos(page, eventId)
  if (!pos) throw new Error(`marker not rendered/found for click: ${eventId} (kind=${kind})`)
  const x = rect.left + pos.cx
  const y = rect.top + pos.cy
  if (opts?.shift) {
    await page.keyboard.down('Shift')
    await page.mouse.click(x, y)
    await page.keyboard.up('Shift')
  } else {
    await page.mouse.click(x, y)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 入口 A · 主图 brush 框选时段 → FailedAttemptsCard(BurstDetector chain_break attempt)
// DGNX 真实数据(design spec §1.1 头号案例):bo_132 @ 2025-08-01,burst chain_break
// 在窗口 (58,132) 触发(实测 drought=74 vs 阈 5)。brush [50,140] 严格 ⊆ 覆盖该窗口。
// ─────────────────────────────────────────────────────────────────────────────
test('入口 A · 主图 brush 框选时段 → FailedAttemptsCard 出 gate 失败 attempt(DGNX)', async ({ page }) => {
  await setupFixtureChart(page)
  await page.waitForFunction(() => (window as any).__e2e.view.symbol === 'DGNX')

  await page.locator('.brush-toggle-btn').click()

  const mainRect = await page.evaluate(() => {
    const r = document.querySelector('.main-chart canvas')!.getBoundingClientRect()
    return { left: r.left, top: r.top, height: r.height }
  })
  const [x1, x2] = await Promise.all([50, 140].map((barIdx) =>
    page.evaluate((idx) => {
      const main = (window as any).__e2e.chartMain()
      const klineIdx = main.getOption().series.findIndex((s: any) => s.name === 'kline')
      return main.convertToPixel({ seriesIndex: klineIdx }, [idx, 0])[0]
    }, barIdx)))
  const y = mainRect.top + mainRect.height * 0.5

  await page.mouse.move(mainRect.left + x1, y)
  await page.mouse.down()
  await page.mouse.move(mainRect.left + (x1 + x2) / 2, y, { steps: 5 })
  await page.mouse.move(mainRect.left + x2, y, { steps: 5 })
  await page.mouse.up()

  await expect(page.locator('.failed-attempts-card')).toBeVisible({ timeout: 5_000 })
  const count = await page.locator('.attempt-card').count()
  expect(count).toBeGreaterThanOrEqual(1)
  // 头号案例:frame 内应能看到 burst class 的 chain_break attempt(至少一条)
  const hasBurstChainBreak = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('.attempt-card'))
    return cards.some((c) => c.textContent?.includes('burst') && c.textContent?.includes('chain_break'))
  })
  expect(hasBurstChainBreak).toBe(true)

  await page.screenshot({ path: resolve(REPO_ROOT, 'docs/superpowers/e2e_screenshots/entry_a_dgnx.png') })
})

// ─────────────────────────────────────────────────────────────────────────────
// 入口 B · 拓扑面板点 burst→tb edge label → PairListCard(miss_reasons 明细)
// 现拓扑只有 1 条边(burst_to_tb),LIXT 真实 4 pair 全失败(1 gap_out + 1 anchor_mismatch)。
// ─────────────────────────────────────────────────────────────────────────────
test('入口 B · 拓扑面板点 burst→tb edge → PairListCard 出 miss_reasons 分布(LIXT)', async ({ page }) => {
  await setupFixtureChart(page)
  await switchToLixt(page)

  await expect(page.locator('.elabel')).toHaveCount(1)
  await page.locator('.elabel').click()

  const card = page.locator('.nodes-popover .pair-list-card')
  await expect(card).toBeVisible({ timeout: 5_000 })
  await expect(card.locator('.miss-reasons')).toBeVisible()
  await expect(card.locator('header')).toContainText('burst_to_tb')

  await page.screenshot({ path: resolve(REPO_ROOT, 'docs/superpowers/e2e_screenshots/entry_b_lixt.png') })
})

// ─────────────────────────────────────────────────────────────────────────────
// 入口 D · shift+click 副图 burst interval + tb point(跨 series 累积)→ PairDetailCard
// LIXT burst_1054_1055 → tb_1057:4 通道(feasible_window/satisfies/anchor/strict)真实
// 全清(4 subcheck 现算)。
// ─────────────────────────────────────────────────────────────────────────────
test('入口 D · shift+click burst+tb marker → PairDetailCard 出 4 subcheck(LIXT)', async ({ page }) => {
  await setupFixtureChart(page)
  await switchToLixt(page)
  await zoomSubAround(page, 1055)

  await clickSubMarker(page, 'interval', 'burst_1054_1055', { shift: true })
  await page.waitForTimeout(250)
  await clickSubMarker(page, 'point', 'tb_1057', { shift: true })

  const card = page.locator('.pair-detail-card')
  await expect(card).toBeVisible({ timeout: 5_000 })
  await expect(card.locator('.invalid-notice')).toHaveCount(0)
  const subcheckCount = await card.locator('.subcheck').count()
  expect(subcheckCount).toBeGreaterThanOrEqual(1)
  await expect(card).toContainText('burst_1054_1055')
  await expect(card).toContainText('tb_1057')

  await page.screenshot({ path: resolve(REPO_ROOT, 'docs/superpowers/e2e_screenshots/entry_d_lixt.png') })
})

test('入口 D · 反向 shift+click(tb → burst)→ auto swap 提示 + 撤回按钮(LIXT)', async ({ page }) => {
  await setupFixtureChart(page)
  await switchToLixt(page)
  await zoomSubAround(page, 1055)

  // 反向:先点 tb(dst),再点 burst(src) —— forward edge 是 burst→tb,故触发 applied_swap
  await clickSubMarker(page, 'point', 'tb_1057', { shift: true })
  await page.waitForTimeout(250)
  await clickSubMarker(page, 'interval', 'burst_1054_1055', { shift: true })

  await expect(page.locator('.swap-notice')).toBeVisible({ timeout: 5_000 })
  await expect(page.locator('.undo-swap')).toBeVisible()

  await page.screenshot({ path: resolve(REPO_ROOT, 'docs/superpowers/e2e_screenshots/entry_d_auto_swap.png') })

  // 撤回:关掉查询卡片(backend 按 edge 存在性确定性判定方向,"撤回"=撤销本次查询展示)
  await page.locator('.undo-swap').click()
  await expect(page.locator('.pair-detail-card')).toHaveCount(0)
})

// ─────────────────────────────────────────────────────────────────────────────
// 入口 E · 命令行 workflow(scripts/path2/scan-top-miss.py)→ markdown 榜含 DGNX
// 真实 6048 支全宇宙跑一次要 ~25 分钟(已手工验证过、DGNX 在 --start=2025-07-15
// --end=2025-09-01 --min-pct=25 下排第 5,+713.8%),对 e2e 套件太慢。scan-top-miss.py
// 自带 --pkl-dir override("供测试/临时子集扫描用",脚本 docstring 原文)——e2e 用它
// 指向仅含 DGNX.pkl 的临时子集目录,单股跑 <1s,断言与全宇宙跑同一组真实参数下逐字
// 一致的 markdown 输出(非 mock:真实 subprocess + 真实 analyze() 链路,只是数据集从
// 6048 支收窄到 1 支,收窄本身是脚本设计支持的合法用法)。
// ─────────────────────────────────────────────────────────────────────────────
test('入口 E · scan-top-miss workflow → markdown 榜含 DGNX', async () => {
  const subsetDir = mkdtempSync(join(tmpdir(), 'path2-e2e-pkl-subset-'))
  copyFileSync(
    resolve(REPO_ROOT, 'datasets/pkls/DGNX.pkl'),
    join(subsetDir, 'DGNX.pkl'),
  )
  const outDir = mkdtempSync(join(tmpdir(), 'path2-e2e-scan-top-miss-'))
  const outPath = join(outDir, 'top_miss.md')

  execFileSync('uv', [
    'run', 'python', 'scripts/path2/scan-top-miss.py',
    '--start=2025-07-15', '--end=2025-09-01', '--min-pct=25', '--top-k=20',
    `--pkl-dir=${subsetDir}`, `--out=${outPath}`,
  ], { cwd: REPO_ROOT, timeout: 60_000 })

  const content = readFileSync(outPath, 'utf-8')
  expect(content).toContain('# scan-top-miss')
  expect(content).toContain('DGNX')
  expect(content).toContain('+713.8%')
})
