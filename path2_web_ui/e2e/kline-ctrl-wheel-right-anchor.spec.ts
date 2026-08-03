import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// Ctrl+wheel 右锚定 x 缩放 e2e:
// 前置 = 后端在线(uv run python scripts/path2/run_path2_web.py)+ 前端 dev server
// (playwright.config.ts webServer 自动拉起)+ BTMWW fixture 存在。
// fixture/就绪等待承 subchart-band-zoom.spec.ts 的 setupChart;合成 WheelEvent 技巧
// 承其 C3 注释(真实 wheel 会被 ECharts inside dataZoom 内部消费,合成 dispatchEvent
// 直达 capture 监听;E4 用真实事件验证 capture 先于 ECharts 可达)。
// 断言核心:Ctrl 缩放 end 恒不变(右锚定)、start 按 0.85 公式变化、主副图同步。

const SCAN_TS = '2026-06-30 17:52:56'
const TICKER = 'BTMWW'

async function setupChart(page: import('@playwright/test').Page) {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst(轮询等选项就绪 + 切换生效,消除并发竞态)
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

  // 选股:直接调 view.selectSymbol,绕开 sidebar 虚拟滚动
  await page.evaluate((sym) => {
    ;(window as any).__e2e?.view?.selectSymbol(sym)
  }, TICKER)
  await page.waitForTimeout(1500)

  // 等 chart 完全就绪(chartMain/chartSub 是 getter 函数)
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  })
  await page.waitForTimeout(200)
}

/** 读主/副图 dataZoom[0] 的 {start, end} */
function readZoom(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const e = (window as any).__e2e
    const dzOf = (c: any) => {
      const dz = c.getOption()?.dataZoom?.[0]
      return { start: dz?.start as number, end: dz?.end as number }
    }
    return { main: dzOf(e.chartMain()), sub: dzOf(e.chartSub()) }
  })
}

/** 对 selector 元素派发合成 Ctrl+wheel */
async function dispatchCtrlWheel(page: import('@playwright/test').Page, selector: string, deltaY: number) {
  await page.locator(selector).evaluate((el, dy) => {
    el.dispatchEvent(new WheelEvent('wheel', { deltaY: dy, ctrlKey: true, bubbles: true, cancelable: true }))
  }, deltaY)
  await page.waitForTimeout(200)
}

test.beforeEach(async ({ page }) => {
  await setupChart(page)
})

test('E1: 主图 Ctrl+wheel 放大 → end 不变、start 按 0.85 公式增大、主副同步', async ({ page }) => {
  const before = await readZoom(page)
  await dispatchCtrlWheel(page, '.main-chart', -100)
  const after = await readZoom(page)

  expect(after.main.end).toBeCloseTo(before.main.end, 6)
  const expectedStart = before.main.end - (before.main.end - before.main.start) * 0.85
  expect(after.main.start).toBeCloseTo(expectedStart, 6)
  expect(after.main.start).toBeGreaterThan(before.main.start)
  // 主副同步(relayZoom 链)
  expect(after.sub.start).toBeCloseTo(after.main.start, 6)
  expect(after.sub.end).toBeCloseTo(after.main.end, 6)
})

test('E2: 副图容器 Ctrl+wheel → 同 E1(副图 → chartMain 单入口链路)', async ({ page }) => {
  const before = await readZoom(page)
  await dispatchCtrlWheel(page, '.sub-outer', -100)
  const after = await readZoom(page)

  expect(after.main.end).toBeCloseTo(before.main.end, 6)
  const expectedStart = before.main.end - (before.main.end - before.main.start) * 0.85
  expect(after.main.start).toBeCloseTo(expectedStart, 6)
  expect(after.sub.start).toBeCloseTo(after.main.start, 6)
  expect(after.sub.end).toBeCloseTo(after.main.end, 6)
})

test('E3: 放大后缩小 → start 精确还原(0.85 与 1/0.85 互逆)', async ({ page }) => {
  const before = await readZoom(page)
  await dispatchCtrlWheel(page, '.main-chart', -100)
  await dispatchCtrlWheel(page, '.main-chart', +100)
  const after = await readZoom(page)

  expect(after.main.start).toBeCloseTo(before.main.start, 4)
  expect(after.main.end).toBeCloseTo(before.main.end, 6)
})

test('E4: 真实 Ctrl+wheel → 缩放生效、页面未被浏览器缩放、band zoom 未误触', async ({ page }) => {
  const dprBefore = await page.evaluate(() => window.devicePixelRatio)
  const before = await readZoom(page)

  const box = (await page.locator('.main-chart').boundingBox())!
  await page.keyboard.down('Control')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -100)
  await page.keyboard.up('Control')
  await page.waitForTimeout(200)

  const after = await readZoom(page)
  expect(after.main.start).toBeGreaterThan(before.main.start) // 真实事件到达 capture 监听
  expect(after.main.end).toBeCloseTo(before.main.end, 6) // 右锚定:end 不变
  const dprAfter = await page.evaluate(() => window.devicePixelRatio)
  expect(dprAfter).toBe(dprBefore) // preventDefault 挡住浏览器页面缩放
  await expect(page.locator('.band-zoom-readout')).toContainText('1.0×') // 未误入 Shift 分支
})
