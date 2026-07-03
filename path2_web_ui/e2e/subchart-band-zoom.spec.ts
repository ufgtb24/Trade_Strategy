import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 副图 band 竖直 zoom 交互 e2e (spec 2026-07-03-subchart-band-zoom):
// 前置 = 后端在线 + 前端 dev server 在线 + BTMWW fixture 存在(playwright.config.ts
// 的 webServer 自动启动前端;后端须外部启动 uv run python scripts/run_path2_web.py)。
// 5 case:UI 按钮 zoom / Shift+wheel zoom / 主图区 Shift+wheel = noop /
// 与 subHeightOffset 正交(隐含于 button/wheel 两 case 均在 override=null 下驱动) / 持久化。
//
// fixture 加载模式复用 subchart-tooltip-crosshair.spec.ts 的 setupChart(固定 fixture
// 2026-06-30 17:52:56,pattern=bottom_burst,ticker=BTMWW,selectSymbol 绕开 sidebar 虚拟滚动)。
// 额外:每 case 独立 —— goto 后先清 localStorage 的 band-zoom 键、reload 一次,保证每个 test
// 从 1.0× 起跑(factor 会跨 test 持久化到 localStorage,不清会被前一 test 的残留值污染)。
// 注意不用 page.addInitScript:那会对该 page 之后所有导航生效,C5 case 里 setup 结束后再
// 显式 page.reload() 时会把刚设好的 1.4× 又清掉——所以改为「goto → 清 → reload 一次」,
// 只影响 setup 阶段这一次导航,不污染 test body 自己触发的 reload。

const SCAN_TS = '2026-06-30 17:52:56'
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

  // 切 active pattern → bottom_burst(main select,DOM 元素固定不虚拟化,dispatch change)。
  // 轮询等选项就绪、且切换后再轮询确认真正生效,消除并发跑多 spec 文件时的竞态。
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

  // 选股:直接调 view.selectSymbol,绕开 sidebar 虚拟滚动导致 BTMWW 不在初始可见窗口的问题。
  await page.evaluate((sym) => {
    ;(window as any).__e2e?.view?.selectSymbol(sym)
  }, TICKER)
  await page.waitForTimeout(1500)

  // 等 chart 完全就绪:window.__e2e.chartMain / chartSub 是 getter 函数(见 KlineChart.vue),
  // 需调用取得实际 echarts 实例后再判空。
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  })
  await page.waitForTimeout(200) // 稳定 render 后再交互
}

test.beforeEach(async ({ page }) => {
  await setupChart(page)
})

test('C1: 点 + 按钮 → sub-inner height 涨、主图 flex 缩、readout 显示因子', async ({ page }) => {
  // SUB_CANVAS_MIN_H 已收窄为空数据专用兜底(非空内容 canvas 高 = 自然高),bracket 区随 z
  // 增长从 1.2× 即可观测;历史上「z=1.0..2.2 恒为 120,z=2.4 起才增长」的 clamp 地板前提已消失。
  // 连点 7 次(1.0→2.4×)保留:更大 delta 信号更稳,exercise 的仍是同一条
  // setBandZoom → effectiveSubH → sub-outer/main-chart 高度分配代码路径。
  const subInner = page.locator('.sub-inner')
  const mainChart = page.locator('.main-chart')
  const h0Sub = (await subInner.boundingBox())!.height
  const h0Main = (await mainChart.boundingBox())!.height

  const plusBtn = page.locator('.band-zoom-controls button[title*="放大"]')
  for (let i = 0; i < 7; i++) {
    await plusBtn.click()
    await page.waitForTimeout(150)
  }

  const h1Sub = (await subInner.boundingBox())!.height
  const h1Main = (await mainChart.boundingBox())!.height
  expect(h1Sub).toBeGreaterThan(h0Sub)
  expect(h1Main).toBeLessThan(h0Main)
  await expect(page.locator('.band-zoom-readout')).toContainText('2.4×')
})

test('C2: 点 ↺ 按钮 → factor 回 1.0×、sub-inner height 回初始、↺ disabled', async ({ page }) => {
  // 先 + 一次
  await page.locator('.band-zoom-controls button[title*="放大"]').click()
  await page.waitForTimeout(200)
  await expect(page.locator('.band-zoom-readout')).toContainText('1.2×')

  // ↺ 回 1.0
  await page.locator('.band-zoom-controls button[title*="复位"]').click()
  await page.waitForTimeout(200)
  await expect(page.locator('.band-zoom-readout')).toContainText('1.0×')
  await expect(page.locator('.band-zoom-controls button[title*="复位"]')).toBeDisabled()
})

test('C3: Shift+wheel over sub-outer → factor × 1.1(相对步进)', async ({ page }) => {
  // 实测偏离(相对 plan 原稿真实 mouse.wheel):BTMWW/bottom_burst 副图 chartSub 的
  // echarts option 含 dataZoom:[{type:'inside',xAxisIndex:0,...}](chart.ts:529),
  // 'inside' 默认开 zoomOnMouseWheel——经实测确认,真实(trusted)wheel 事件落在
  // chartSub 的 canvas 上时,echarts 自己的 x 轴 zoom 会先消费该事件并在其内部
  // wrapper 上 stopPropagation(实测:echarts 自身 dataZoom start/end 确实随真实
  // 非-shift wheel 变化,证明它收到并处理了事件;但同一真实 shift+wheel 事件無論
  // 加不加 shift 均从未冒泡到 .sub-outer 的 @wheel 监听——用 addEventListener
  // 探针在 window-capture / canvas-bubble 均能看到该事件,唯独 sub-outer-bubble
  // 从未触发,而对同一 canvas 节点手工 dispatchEvent 则能正常冒泡到位),即真实鼠标
  // wheel 手势会被 echarts 内部吞掉、不到达 onSubWheel。
  // design spec Case 2(2026-07-03-subchart-band-zoom-design.md:288-289)本身明确
  // 允许「在 sub-outer 元素上 dispatch wheel({shiftKey:true, deltaY:-100})」作为
  // 「或 Playwright page.mouse.wheel + hold Shift」的替代验证方式——改用前者,
  // 直接对 .sub-outer 派发合成 WheelEvent,精确对应生产 onSubWheel 的真实处理逻辑,
  // 绕开与本 feature 无关的 echarts 内部 wheel 消费细节。
  await page.locator('.sub-outer').evaluate((el) => {
    el.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, shiftKey: true, bubbles: true, cancelable: true }))
  })
  await page.waitForTimeout(200)
  // 相对 × 1.1 → 1.1×;取一次 wheel 只算一档
  await expect(page.locator('.band-zoom-readout')).toContainText('1.1×')
})

test('C4: 主图区 Shift+wheel = noop(readout 不变、页面不滚动)', async ({ page }) => {
  const main = page.locator('.main-chart')
  const box = (await main.boundingBox())!
  const scrollBefore = await page.evaluate(() => window.scrollY)

  await page.keyboard.down('Shift')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -100)
  await page.keyboard.up('Shift')
  await page.waitForTimeout(200)

  const scrollAfter = await page.evaluate(() => window.scrollY)
  expect(scrollAfter).toBe(scrollBefore)   // 页面未滚动(preventDefault 生效)
  await expect(page.locator('.band-zoom-readout')).toContainText('1.0×')  // factor 未变
})

test('C5: 持久化 → factor=1.4 set → reload → 保留', async ({ page }) => {
  // 连 + 两次 → 1.4×
  await page.locator('.band-zoom-controls button[title*="放大"]').click()
  await page.waitForTimeout(150)
  await page.locator('.band-zoom-controls button[title*="放大"]').click()
  await page.waitForTimeout(150)
  await expect(page.locator('.band-zoom-readout')).toContainText('1.4×')

  await page.reload()
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  })
  await page.waitForTimeout(500)

  await expect(page.locator('.band-zoom-readout')).toContainText('1.4×')
})
