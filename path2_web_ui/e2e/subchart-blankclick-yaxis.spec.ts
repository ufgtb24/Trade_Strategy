import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 回归 e2e:水平 zoom-in 后触发全量 render(false)(点副图空白 / Esc 清选中)不得让主图
// y 轴范围回跳到「全窗价格」——那会把可见段 K 线压到底部、上方留大片留白。
//
// 根因:buildMainOption 曾用固定 strictWindow/全窗算 yAxis min/max,忽略当前 zoom;
// 修复后 y 轴计算窗口跟随 zoomOverride,与 datazoom handler 口径一致。
//
// fixture 用当前分支可用的 scan 20260629T100219(含 bottom_burst + BTMWW,低价前低后高,
// 与截图同股)。setupChart 模式复用 subchart-band-zoom.spec.ts。
// 须 --workers=1 串行(并行下共享后端 flaky);后端须外部启动。

const SCAN_TS = '2026-06-29 10:02:19'
const TICKER = 'BTMWW'
const LS_KEY_BAND_ZOOM = 'kline-band-zoom-v1'

async function setupChart(page: import('@playwright/test').Page) {
  await page.goto(baseURL + '/')
  await page.evaluate((key) => {
    try { localStorage.removeItem(key) } catch { /* noop */ }
  }, LS_KEY_BAND_ZOOM)
  await page.reload()
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst
  await page.waitForFunction(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement | null
    return !!sel && Array.from(sel.options).some((o) => o.value === 'bottom_burst')
  })
  await page.evaluate(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement
    sel.value = 'bottom_burst'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForFunction(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement | null
    return sel?.value === 'bottom_burst'
  })

  await page.evaluate((sym) => {
    ;(window as any).__e2e?.view?.selectSymbol(sym)
  }, TICKER)
  await page.waitForTimeout(1500)

  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  })
  await page.waitForTimeout(200)
}

test.beforeEach(async ({ page }) => {
  await setupChart(page)
})

// 水平 zoom-in 到低价前段,读回 datazoom handler 贴合可见窗后的 y 轴上界。
async function zoomInAndReadMax(page: import('@playwright/test').Page): Promise<number> {
  await page.evaluate(() => {
    ;(window as any).__e2e.chartMain().dispatchAction({ type: 'dataZoom', start: 0, end: 25 })
  })
  await page.waitForTimeout(300) // 等 datazoom handler 重算 y 轴
  return await page.evaluate(() => {
    return (window as any).__e2e.chartMain().getOption().yAxis[0].max as number
  })
}

test('zoom-in 后点副图空白触发全量 render → 主图 y 轴不回跳全窗(无留白)', async ({ page }) => {
  const visMax = await zoomInAndReadMax(page)

  // 全窗上界:临时 zoom 回全集读一次,确认"可见窗上界 ≪ 全窗上界"(否则本 case 无鉴别力)。
  await page.evaluate(() => {
    ;(window as any).__e2e.chartMain().dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
  })
  await page.waitForTimeout(200)
  const fullMax = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().yAxis[0].max as number)
  expect(fullMax).toBeGreaterThan(visMax * 2) // BTMWW 前低后高,全窗 max 远大于前段

  // 回到 zoom-in 状态
  const visMax2 = await zoomInAndReadMax(page)
  expect(visMax2).toBeCloseTo(visMax, 6)

  // 铺垫非空态(选一个 match),再点副图空白清空 —— 两步各触发一次 render(false)。
  await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const m = view.effectiveAnalysis?.matches?.[0]
    if (m) view.focusMatch(m.event_id)
  })
  await page.waitForTimeout(200)

  // 点副图空白(.sub-inner 顶部边缘,band lane 之外) → ZRender blank click → 清 store。
  const subInner = page.locator('.sub-inner')
  const box = (await subInner.boundingBox())!
  await page.mouse.click(box.x + box.width - 6, box.y + 4)
  await page.waitForTimeout(300)

  // render(false) 后 y 轴上界仍贴合可见窗,未回跳到全窗(修复前会等于 fullMax)。
  const afterMax = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().yAxis[0].max as number)
  expect(afterMax).toBeCloseTo(visMax, 6)
  expect(afterMax).toBeLessThan(fullMax) // 冗余护栏:绝不回跳全窗
})

test('zoom-in 后 Esc 清选中触发全量 render → 主图 y 轴不回跳全窗(波及面同因)', async ({ page }) => {
  const visMax = await zoomInAndReadMax(page)

  await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const m = view.effectiveAnalysis?.matches?.[0]
    if (m) view.focusMatch(m.event_id)
  })
  await page.waitForTimeout(200)

  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)

  const afterMax = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().yAxis[0].max as number)
  expect(afterMax).toBeCloseTo(visMax, 6)
})
