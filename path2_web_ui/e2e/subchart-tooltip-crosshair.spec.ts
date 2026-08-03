import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/path2/run_path2_web.py)。
//
// S1/S2/S3 反证 + 正证 e2e:
//
// S1 反证:hover 副图 marker → sub-outer 不再溢出、tooltip DOM 挂 document.body
// S2 反证:showTip on chartSub → 全屏只 1 个 tooltip DOM,不再跨图错位
// S3 正证:hover chartMain/chartSub → overlay dashed 竖线可见 + 高度贯穿 kline-wrap-v2
//
// 数据:复用 subchart-scroll-drag.spec.ts 现有 setup pattern(固定 fixture
// 2026-06-30 17:52:56,pattern=bottom_burst,ticker=BTMWW)。

const SCAN_TS = '2026-06-30 17:52:56'
const TICKER = 'BTMWW'

async function setupChart(page: import('@playwright/test').Page) {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst(main select,DOM 元素固定不虚拟化,dispatch change)。
  // 并发跑多 spec 文件时后端/前端负载升高,固定 sleep 可能在 'bottom_burst' 选项渲染出来前
  // 就设值 → 浏览器静默拒绝非法 <option> value、select 停留在默认 'bo_only',下游全错位。
  // 改为轮询等选项就绪、且切换后再轮询确认真正生效,消除该竞态。
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

  // 选股:直接调 view.selectSymbol(与 subchart-scroll-drag.spec.ts 相同做法,绕开
  // sidebar 虚拟滚动导致 BTMWW 不在初始可见窗口的问题)
  await page.evaluate((sym) => {
    ;(window as any).__e2e?.view?.selectSymbol(sym)
  }, TICKER)
  await page.waitForTimeout(1500)

  // 等 chart 完全就绪:window.__e2e.chartMain / chartSub 是 getter 函数(见 KlineChart.vue),
  // 需调用取得实际 echarts 实例后再判空
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  })
  await page.waitForTimeout(200) // 稳定 render 后再交互
}

test.describe('S1 sub-outer 不再溢出 + tooltip 挂 body', () => {
  test('hover 副图 marker → subOuter scrollHeight ≡ clientHeight + tooltip parent = body', async ({ page }) => {
    await setupChart(page)

    // Trigger:dispatchAction showTip 到 chartSub 第 0 系列第 0 项
    await page.evaluate(() => {
      const sub = (window as any).__e2e.chartSub()
      sub.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
    })
    await page.waitForTimeout(200)

    const metrics = await page.evaluate(() => {
      const outer = document.querySelector('.sub-outer') as HTMLElement
      // Tooltip DOM:ECharts 高 z-index 判定(9999999 by default)
      const candidates = Array.from(document.querySelectorAll<HTMLElement>('div[style*="position: absolute"]'))
      const tt = candidates.find((el) => {
        const z = parseInt(el.style.zIndex || '0', 10)
        return z >= 999999 && el.style.display !== 'none' && el.offsetHeight > 0
      })
      return {
        outerScroll: outer.scrollHeight,
        outerClient: outer.clientHeight,
        tooltipParentIsBody: tt?.parentElement === document.body,
        tooltipParentClass: tt?.parentElement?.className || '(no tooltip found)',
      }
    })

    expect(metrics.outerScroll).toBe(metrics.outerClient)
    expect(metrics.tooltipParentIsBody).toBe(true)
  })

  test('zoom in 后 hover 副图 marker → tooltip flip 到 marker 上方,完全在 viewport 内', async ({ page }) => {
    // 双实例架构下,viewportAwareTooltipPosition 若用 querySelector('[_echarts_instance_]')
    // 会返回主图 rect(第一个匹配),导致副图 markerTooltip 的 flip 判定基于错的 cursorPageY
    // (少了副图 top offset),不翻转,tooltip 一路向下超出 viewport 底。
    // Factory pattern(makeViewportAwarePosition + opts.getChartEl)确保源 chart rect 正确,
    // flip 判定 (cursorPageY + tooltipH > viewport-margin) 正确触发,tooltip 翻到 marker 上方。
    await setupChart(page)

    // Zoom in 到 dataIndex 162 附近(marker 中心 = burst_162_163),
    // marker 保持在 sub-inner 底半区靠近 viewport 底,是原 bug 触发条件
    await page.evaluate(() => {
      const main = (window as any).__e2e.chartMain()
      main.dispatchAction({ type: 'dataZoom', start: 40, end: 60 })
    })
    await page.waitForTimeout(200)

    await page.evaluate(() => {
      const sub = (window as any).__e2e.chartSub()
      sub.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
    })
    await page.waitForTimeout(200)

    const metrics = await page.evaluate(() => {
      const candidates = Array.from(document.querySelectorAll<HTMLElement>('div[style*="position: absolute"]'))
      const tt = candidates.find((el) => {
        const z = parseInt(el.style.zIndex || '0', 10)
        return z >= 999999 && el.style.display !== 'none' && el.offsetHeight > 0
      })
      if (!tt) return null
      const rect = tt.getBoundingClientRect()
      const subEl = document.querySelector('.sub-inner') as HTMLElement
      const subRect = subEl.getBoundingClientRect()
      return {
        tooltipTop: rect.top,
        tooltipBottom: rect.bottom,
        tooltipHeight: rect.height,
        viewportH: window.innerHeight,
        subTop: subRect.top,
      }
    })

    expect(metrics).not.toBeNull()
    // tooltip 完全在 viewport 内(修 flip bug 的核心断言)
    expect(metrics!.tooltipBottom).toBeLessThanOrEqual(metrics!.viewportH)
    // tooltip flip 到 marker 上方:tooltip 顶 < sub-inner 顶 = marker 上方
    expect(metrics!.tooltipTop).toBeLessThan(metrics!.subTop)
  })
})

test.describe('S2 单 tooltip(无跨图错位)', () => {
  test('dispatchAction showTip on chartSub → DOM 仅 1 个可见 tooltip', async ({ page }) => {
    await setupChart(page)

    await page.evaluate(() => {
      const sub = (window as any).__e2e.chartSub()
      sub.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: 0 })
    })
    await page.waitForTimeout(200)

    const tooltipCount = await page.evaluate(() => {
      const candidates = Array.from(document.querySelectorAll<HTMLElement>('div[style*="position: absolute"]'))
      return candidates.filter((el) => {
        const z = parseInt(el.style.zIndex || '0', 10)
        return z >= 999999 && el.style.display !== 'none' && el.offsetHeight > 0
      }).length
    })

    expect(tooltipCount).toBe(1)
  })
})

test.describe('S3 overlay 贯穿', () => {
  test('hover chartMain 中部 → overlay 可见 + 高度覆盖 kline-wrap-v2', async ({ page }) => {
    await setupChart(page)

    const mainBox = await page.locator('.main-chart canvas').first().boundingBox()
    if (!mainBox) throw new Error('main-chart canvas 未渲染')
    await page.mouse.move(
      mainBox.x + mainBox.width / 2,
      mainBox.y + mainBox.height / 2,
    )
    await page.waitForTimeout(200)

    const overlay = await page.evaluate(() => {
      const el = document.querySelector('.crosshair-overlay') as HTMLElement | null
      if (!el) return null
      const rect = el.getBoundingClientRect()
      return { left: rect.left, top: rect.top, height: rect.height }
    })

    expect(overlay).not.toBeNull()
    const wrapBox = await page.locator('.kline-wrap-v2').boundingBox()
    if (!wrapBox) throw new Error('.kline-wrap-v2 not found')
    // overlay 高度 ≥ wrap 90%(允许 <=10% padding 差)
    expect(overlay!.height).toBeGreaterThan(wrapBox.height * 0.9)
  })

  test('hover chartSub 中部 → overlay 对称可见', async ({ page }) => {
    await setupChart(page)

    const subBox = await page.locator('.sub-inner').boundingBox()
    if (!subBox) throw new Error('.sub-inner 未渲染')
    await page.mouse.move(
      subBox.x + subBox.width / 2,
      subBox.y + subBox.height / 2,
    )
    await page.waitForTimeout(200)

    const overlayVisible = await page.evaluate(() => {
      return document.querySelector('.crosshair-overlay') != null
    })
    expect(overlayVisible).toBe(true)
  })

  test('鼠标移出图 → overlay 消失', async ({ page }) => {
    await setupChart(page)

    const mainBox = await page.locator('.main-chart canvas').first().boundingBox()
    if (!mainBox) throw new Error('main-chart canvas 未渲染')
    await page.mouse.move(mainBox.x + mainBox.width / 2, mainBox.y + mainBox.height / 2)
    await page.waitForTimeout(200)
    // 移到 viewport 角落触发 chart 的 mouseout
    await page.mouse.move(1, 1)
    await page.waitForTimeout(200)

    const overlayExists = await page.evaluate(() => {
      return document.querySelector('.crosshair-overlay') != null
    })
    expect(overlayExists).toBe(false)
  })
})
