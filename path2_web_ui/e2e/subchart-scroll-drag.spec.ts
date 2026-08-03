import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/path2/run_path2_web.py)。
// 固定 fixture:2026-06-30 17:52:56 扫描历史(outputs/path2_web/scans/20260630T175256.json)
// 含 bottom_burst pattern 下 BTMWW(2 条 match,event_id 前缀 bottom_burst@),用于驱动
// candidate/disambig 相关断言。

const SCAN_TS = '2026-06-30 17:52:56'
const TICKER = 'BTMWW'

test.beforeEach(async ({ page }) => {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst(main select,DOM 元素固定不虚拟化,按原计划 dispatch change)
  await page.evaluate(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement | null
    if (!sel) return
    sel.value = 'bottom_burst'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForTimeout(300)

  // 选股:直接调 view.selectSymbol(与 SidebarResultList.vue td.sym 的 click handler 同函数)
  // 而非 DOM 查找 td 文本点击——sidebar 列表按 symbol 字母序虚拟滚动渲染(SidebarResultList.vue
  // visibleRows = sortedRows.slice(startIdx,endIdx)),BTMWW 在本 fixture 4825 只股票中字母序
  // 排第 715 位,不在初始可见窗口内,DOM 查找会找不到该行、click 静默 no-op。
  await page.evaluate((sym) => {
    ;(window as any).__e2e?.view?.selectSymbol(sym)
  }, TICKER)
  await page.waitForTimeout(1500)
})

test('main-chart + sub-chart canvases both mount', async ({ page }) => {
  await expect(page.locator('.main-chart canvas')).toBeVisible()
  await expect(page.locator('.sub-inner canvas')).toBeVisible()
  await expect(page.locator('.resizable-divider')).toBeVisible()
})

test('initial sub-outer height equals subCanvasH (auto-fit)', async ({ page }) => {
  // 初始 subHeightOffset === null → sub-outer.clientHeight === subCanvasH
  const outerH = await page.locator('.sub-outer').evaluate((el) => (el as HTMLElement).clientHeight)
  const subCanvasH = await page.evaluate(() => {
    const chart = (window as any).__e2e?.chartSub?.()
    return chart ? chart.getHeight() : 0
  })
  expect(subCanvasH).toBeGreaterThan(0)
  expect(outerH).toBe(subCanvasH)
  // localStorage 无 subHeightOffset 字段或为 null
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('path2_web_ui.panels.v1') || '{}').subHeightOffset)
  expect(stored === null || stored === undefined).toBe(true)
})

test('drag divider down compresses sub-outer + shows scrollbar', async ({ page }) => {
  const initialOuterH = await page.locator('.sub-outer').evaluate((el) => (el as HTMLElement).clientHeight)
  const divider = page.locator('.resizable-divider')
  const box = await divider.boundingBox()
  if (!box) throw new Error('divider not visible')
  const startY = box.y + box.height / 2
  // 向下拖 100px → 副图变小 100px
  await page.mouse.move(box.x + box.width / 2, startY)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, startY + 100, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  const compressed = await page.locator('.sub-outer').evaluate((el) => {
    const e = el as HTMLElement
    return { client: e.clientHeight, scroll: e.scrollHeight }
  })
  expect(compressed.client).toBeLessThan(initialOuterH)
  // sub-inner 保持 subCanvasH → scrollHeight > clientHeight → 出滚动条
  expect(compressed.scroll).toBeGreaterThan(compressed.client)

  // localStorage 里 subHeightOffset 已被写入(负值 = 藏掉的像素数)
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('path2_web_ui.panels.v1') || '{}').subHeightOffset)
  expect(typeof stored).toBe('number')
  expect(stored).toBeLessThan(0)
})

test('drag divider up cannot expand sub-outer beyond subCanvasH (hard cap)', async ({ page }) => {
  // 先向下拖 100px 压缩(为 override 建立初值)
  const divider = page.locator('.resizable-divider')
  const box1 = await divider.boundingBox()
  if (!box1) throw new Error('divider not visible')
  await page.mouse.move(box1.x + box1.width / 2, box1.y + box1.height / 2)
  await page.mouse.down()
  await page.mouse.move(box1.x + box1.width / 2, box1.y + box1.height / 2 + 100, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  const subCanvasH = await page.evaluate(() => (window as any).__e2e.chartSub().getHeight())
  const compressedH = await page.locator('.sub-outer').evaluate((el) => (el as HTMLElement).clientHeight)
  expect(compressedH).toBeLessThan(subCanvasH)

  // 再向上强拖 500px(远超 subCanvasH 上界)
  const box2 = await divider.boundingBox()
  if (!box2) throw new Error('divider gone')
  await page.mouse.move(box2.x + box2.width / 2, box2.y + box2.height / 2)
  await page.mouse.down()
  await page.mouse.move(box2.x + box2.width / 2, box2.y + box2.height / 2 - 500, { steps: 12 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  const finalH = await page.locator('.sub-outer').evaluate((el) => (el as HTMLElement).clientHeight)
  // clamp 到 subCanvasH: sub-outer 高度不超过 subCanvasH(内容不留白)
  expect(finalH).toBeLessThanOrEqual(subCanvasH)
})

test('double-click divider restores auto-fit', async ({ page }) => {
  // 先压缩到 override 状态
  const divider = page.locator('.resizable-divider')
  const box = await divider.boundingBox()
  if (!box) throw new Error('divider not visible')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 100, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  // 双击 → 恢复 auto-fit
  await divider.dblclick()
  await page.waitForTimeout(200)

  const subCanvasH = await page.evaluate(() => (window as any).__e2e.chartSub().getHeight())
  const restoredH = await page.locator('.sub-outer').evaluate((el) => (el as HTMLElement).clientHeight)
  expect(restoredH).toBe(subCanvasH)

  // localStorage 里 subHeightOffset === null
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('path2_web_ui.panels.v1') || '{}').subHeightOffset)
  expect(stored).toBeNull()
})

test('decor graphics survive zoom in (matches / bandLabels / subDivider / zebra remain in option.graphic)', async ({ page }) => {
  // trigger dataZoom to smallest window: start=90 end=100
  await page.evaluate(() => {
    const c = (window as any).__e2e.chartSub()
    c.dispatchAction({ type: 'dataZoom', start: 90, end: 100 })
  })
  await page.waitForTimeout(300)

  // 读 chartSub.getOption().graphic — 应有装饰元素
  const graphic = await page.evaluate(() => {
    const c = (window as any).__e2e.chartSub()
    const opt = c.getOption()
    return opt.graphic ?? []
  })
  expect(Array.isArray(graphic)).toBe(true)
  // graphic 是 GraphicComponentOption[]; ECharts 内部规范化后可能是 { elements: [...] } 包裹格式,兼容两种:
  const elements: any[] = Array.isArray(graphic) && graphic.length > 0 && graphic[0].elements
    ? graphic[0].elements
    : (graphic as any[])
  // 至少含 1 subDivider(#94a3b8 rect) + 至少 1 matchesLabel/bandLabel(text,fill 颜色不作断言,只查存在性)
  const rects = elements.filter((e: any) => e.type === 'rect')
  const texts = elements.filter((e: any) => e.type === 'text')
  expect(rects.length).toBeGreaterThanOrEqual(1)
  expect(texts.length).toBeGreaterThanOrEqual(1)
  // subDivider: fill = SUB_DIVIDER_COLOR(#94a3b8)
  const dividers = rects.filter((r: any) => r.style?.fill === '#94a3b8')
  expect(dividers.length).toBeGreaterThanOrEqual(1)
})

test('candidate banner sits outside sub-outer and stays put when scrolling', async ({ page }) => {
  // 先下压副图制造滚动空间(fit 态无滚动可言;banner 已移出滚动容器)
  const divider = page.locator('.resizable-divider')
  const box = await divider.boundingBox()
  if (!box) throw new Error('divider not visible')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 60, { steps: 6 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  // 就绪守卫:等 active pattern 的 analysis.matches 填充(≥2)后再置 candidate 态,
  // 消除 effectiveAnalysis 异步就绪与固定 timeout 的竞态(banner 依赖 matches.length>=2)。
  await page.waitForFunction(() => ((window as any).__e2e?.view?.effectiveAnalysis?.matches ?? []).length >= 2)
  await page.evaluate(() => {
    const view = (window as any).__e2e?.view
    const matches = view?.effectiveAnalysis?.matches ?? []
    if (matches.length >= 2) {
      view.setCandidateMatches(matches.slice(0, 2).map((m: any) => m.event_id))
      view.setPendingDisambig(matches[0].children?.[0] ?? 'x')
    }
  })
  await page.waitForTimeout(200)
  const banner = page.locator('.candidate-banner')
  await expect(banner).toBeVisible()

  // 结构断言:banner 不在滚动容器内
  const insideSubOuter = await page.evaluate(() => !!document.querySelector('.sub-outer .candidate-banner'))
  expect(insideSubOuter).toBe(false)

  // banner 位于 sub-outer 上方;滚动 sub-outer 不改变 banner 位置
  const bannerY0 = (await banner.boundingBox())!.y
  const outerBox = await page.locator('.sub-outer').boundingBox()
  expect(bannerY0).toBeLessThanOrEqual(outerBox!.y)
  await page.evaluate(() => {
    const el = document.querySelector('.sub-outer') as HTMLElement
    el.scrollTop = Math.min(50, el.scrollHeight - el.clientHeight)
  })
  await page.waitForTimeout(200)
  await expect(banner).toBeVisible()
  const bannerY1 = (await banner.boundingBox())!.y
  expect(bannerY1).toBeCloseTo(bannerY0, 0)
})

test('fit 态无滚动条:常态与 candidate 态 scrollHeight === clientHeight', async ({ page }) => {
  const probe = () => page.locator('.sub-outer').evaluate((el) => {
    const e = el as HTMLElement
    return { client: e.clientHeight, scroll: e.scrollHeight }
  })
  const normal = await probe()
  expect(normal.scroll).toBe(normal.client)

  // candidate 态:banner 出现在滚动容器外,不产生滚动(spec 验收 #1)
  // 就绪守卫:等 matches 填充(≥2)后再置 candidate 态,消除 effectiveAnalysis 异步就绪竞态。
  await page.waitForFunction(() => ((window as any).__e2e?.view?.effectiveAnalysis?.matches ?? []).length >= 2)
  await page.evaluate(() => {
    const view = (window as any).__e2e?.view
    const matches = view?.effectiveAnalysis?.matches ?? []
    if (matches.length >= 2) {
      view.setCandidateMatches(matches.slice(0, 2).map((m: any) => m.event_id))
      view.setPendingDisambig(matches[0].children?.[0] ?? 'x')
    }
  })
  await page.waitForTimeout(200)
  await expect(page.locator('.candidate-banner')).toBeVisible()
  const withBanner = await probe()
  expect(withBanner.scroll).toBe(withBanner.client)
})

test('drag 后 shift+wheel:分界线随 zoom 移动、隐藏量守恒;dblclick 回 fit 且 zoom 不变', async ({ page }) => {
  // 起点归零:factor 若非 1.0 先点 ↺(disabled 即已是 1.0)
  const resetBtn = page.locator('.band-zoom-reset')
  if (await resetBtn.isEnabled()) {
    await resetBtn.click()
    await page.waitForTimeout(200)
  }

  // 下压 40px → offset=-40(隐藏量 40)
  const divider = page.locator('.resizable-divider')
  const box = await divider.boundingBox()
  if (!box) throw new Error('divider not visible')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 40, { steps: 6 })
  await page.mouse.up()
  await page.waitForTimeout(200)

  const probe = () => page.locator('.sub-outer').evaluate((el) => {
    const e = el as HTMLElement
    return { client: e.clientHeight, scroll: e.scrollHeight }
  })
  const before = await probe()
  const hiddenBefore = before.scroll - before.client
  expect(hiddenBefore).toBeGreaterThan(0)
  const mainBefore = await page.locator('.main-chart').evaluate((el) => (el as HTMLElement).clientHeight)

  // Shift+wheel ×12 zoom-in(合成事件直达 capture 监听,见 subchart-band-zoom.spec.ts 同款技法;
  // SUB_CANVAS_MIN_H 已收窄为空数据专用兜底,非空内容增长从首个 tick 即可观测,×12 只为放大信号)
  await page.locator('.sub-outer').evaluate((el) => {
    for (let i = 0; i < 12; i++) {
      el.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, shiftKey: true, bubbles: true, cancelable: true }))
    }
  })
  await page.waitForTimeout(400)

  const after = await probe()
  const mainAfter = await page.locator('.main-chart').evaluate((el) => (el as HTMLElement).clientHeight)
  // 内容实际增长(scroll = subCanvasH 随 z 增长)
  expect(after.scroll).toBeGreaterThan(before.scroll)
  // 分界线随 zoom 移动:容器长高、主图缩小
  expect(after.client).toBeGreaterThan(before.client)
  expect(mainAfter).toBeLessThan(mainBefore)
  // 隐藏量守恒(spec 验收 #3;±1 容差:z=1.1^n 时 subCanvasH 非整数,client/scrollHeight 取整可差 1px)
  expect(Math.abs((after.scroll - after.client) - hiddenBefore)).toBeLessThanOrEqual(1)

  // dblclick 回 fit:容器 == 内容;zoom readout 不变(spec 验收 #5)
  const readoutBefore = await page.locator('.band-zoom-readout').textContent()
  await divider.dblclick()
  await page.waitForTimeout(200)
  const fit = await probe()
  // ±1 容差同上(非整 zoom 下取整误差);z=1 整数场景的严格无滚动条断言由上一个 test 覆盖
  expect(Math.abs(fit.scroll - fit.client)).toBeLessThanOrEqual(1)
  const readoutAfter = await page.locator('.band-zoom-readout').textContent()
  expect(readoutAfter).toBe(readoutBefore)
})
