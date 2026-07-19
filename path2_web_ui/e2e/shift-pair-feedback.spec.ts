import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

/**
 * 入口 D shift+click 沉默期反馈 e2e(spec 2026-07-10-shift-pair-feedback-design)。
 *
 * 5 场景:
 *   1. 第 1 击 → banner + marker 描边(shiftPairPending=true)
 *   2. Esc → 全清(shiftSelectedEvents=[])
 *   3. 空白 click → 全清
 *   4. 第 2 击 → banner 消失 + shift 累积器 length=2(pair query 触发)
 *   5. 第 3 击 → 重置回 1/2(banner 再次出现)
 *
 * 数据源:同股(BTMWW)+ pattern(bottom_burst);SCAN_TS 取当前 outputs/path2_web/scans/
 * 下实际存在的扫描文件时戳(与 marker-click-focus-highlight.spec.ts 写入时的时戳不同——该
 * 环境的扫描历史只保留最近一次全量扫描,历史时戳会随重新扫描漂移,故不能硬编旧值)。marker
 * 屏幕坐标计算沿用 sidebar-chart-focus.spec.ts::locateEventPixel 的手法(zebra 装饰 rect 反查
 * band 中心)——renderPointWithGeom 的 y 是从 bandGeom 派生,不是 y 轴数值映射,convertToPixel
 * 对 y 不适用。shift+click 全用 @playwright/test 原生 mouse.click({modifiers:['Shift']}),
 * 不合成事件。
 */

const SCAN_TS = '2026-07-11 15:39:23'
const TICKER = 'BTMWW'
const BANNER_TEXT = '入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消'

async function setupChart(page: import('@playwright/test').Page) {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst(轮询等选项就绪,消除负载竞态;同 marker-click spec)
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

async function zoomAroundBar(page: import('@playwright/test').Page, centerIdx: number, halfWindowPct = 8): Promise<void> {
  await page.evaluate(({ centerIdx, halfWindowPct }) => {
    const main = (window as any).__e2e.chartMain()
    const n = (main.getOption().xAxis?.[0]?.data || []).length
    const c = (centerIdx / n) * 100
    main.dispatchAction({ type: 'dataZoom', start: Math.max(0, c - halfWindowPct), end: Math.min(100, c + halfWindowPct) })
  }, { centerIdx, halfWindowPct })
  await page.waitForTimeout(300)
}

/** 取副图 'points' series 第 index 个 marker 的 event_id + start_idx(用于 zoom 定位)。 */
async function nthPointMarker(page: import('@playwright/test').Page, index: number) {
  return page.evaluate((i) => {
    const sub = (window as any).__e2e.chartSub()
    const pts = sub.getOption().series.find((s: any) => s.name === 'points')
    const d = pts?.data?.[i]
    if (!d) return null
    return { event_id: d.event_id as string, startIdx: d.value[0] as number }
  }, index)
}

/** 定位副图 points marker 真实屏幕坐标(x=convertToPixel,y=zebra 装饰 rect band 中心)。 */
async function locatePointPixel(page: import('@playwright/test').Page, eventId: string) {
  return page.evaluate((eid) => {
    const sub = (window as any).__e2e.chartSub()
    const subCanvas = document.querySelector('.sub-inner canvas') as HTMLElement | null
    if (!subCanvas) return null
    const idx = sub.getOption().series.findIndex((s: any) => s.name === 'points')
    const d = idx >= 0 ? sub.getOption().series[idx].data.find((x: any) => x.event_id === eid) : null
    if (!d) return null
    const graphicArr = sub.getOption().graphic
    const els = Array.isArray(graphicArr) ? (graphicArr[0]?.elements ?? graphicArr) : (graphicArr?.elements ?? [])
    const zebra = els.filter((e: any) => e.type === 'rect' && e.z === 1)
    const zb = zebra[d.value[2]]
    if (!zb) return null
    const rect = subCanvas.getBoundingClientRect()
    const px = sub.convertToPixel({ seriesIndex: idx }, [d.value[0], 0])
    return { x: rect.left + px[0], y: rect.top + zb.top + zb.shape.height / 2 }
  }, eventId)
}

/** page.mouse.click(...,{modifiers:['Shift']}) 对 Mouse.click 无效(Playwright 只在
 * locator.click()/elementHandle.click() 支持 modifiers 选项;e2e 走 esbuild 免类型检查,
 * 无效字段被静默吞掉,实测 shiftKey 恒为 false)——改用 keyboard.down/up 包裹真实按住。 */
async function shiftClickMarker(page: import('@playwright/test').Page, eventId: string): Promise<void> {
  const pos = await locatePointPixel(page, eventId)
  if (!pos) throw new Error(`marker pixel not found for event_id=${eventId}`)
  await page.keyboard.down('Shift')
  await page.mouse.click(pos.x, pos.y)
  await page.keyboard.up('Shift')
}

test.describe('入口 D shift+click 沉默期反馈', () => {
  // 串行跑:多场景共用同一后端 :8000 与前端 :5170 的 __e2e 全局 store,
  // 并行时会互相污染扫描历史加载/图表实例(与 subchart-scroll-drag 等 e2e 同类)。
  test.describe.configure({ mode: 'serial' })

  test('场景 1: 第 1 击 → banner + marker 描边', async ({ page }) => {
    await setupChart(page)
    const m = await nthPointMarker(page, 0)
    expect(m).not.toBeNull()
    await zoomAroundBar(page, m!.startIdx)
    await shiftClickMarker(page, m!.event_id)

    await expect(page.locator('.shift-pair-banner')).toHaveText(BANNER_TEXT)
    // shift-veil 数据(spec 2026-07-11):副图 shift-veil / 主图 shift-veil-price series
    // 之一含此 event_id;不再断言本体 marker itemStyle.borderColor(Task 4 mutate 路径已回滚)。
    const veilHit = await page.evaluate((eid) => {
      const readVeilData = (chart: any, name: string) => {
        const s = chart.getOption().series.find((x: any) => x.name === name)
        return s?.data ?? []
      }
      const sub = (window as any).__e2e.chartSub()
      const main = (window as any).__e2e.chartMain()
      const combined = [...readVeilData(sub, 'shift-veil'), ...readVeilData(main, 'shift-veil-price')]
      return combined.some((d: any) => d.event_id === eid)
    }, m!.event_id)
    expect(veilHit).toBe(true)
  })

  test('场景 2: Esc 取消 → banner 消失 + shift 累积器空', async ({ page }) => {
    await setupChart(page)
    const m = await nthPointMarker(page, 0)
    expect(m).not.toBeNull()
    await zoomAroundBar(page, m!.startIdx)
    await shiftClickMarker(page, m!.event_id)
    await expect(page.locator('.shift-pair-banner')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(0)
  })

  test('场景 3: 空白 click 取消 → banner 消失 + shift 累积器空', async ({ page }) => {
    await setupChart(page)
    const m = await nthPointMarker(page, 0)
    expect(m).not.toBeNull()
    await zoomAroundBar(page, m!.startIdx)
    await shiftClickMarker(page, m!.event_id)
    await expect(page.locator('.shift-pair-banner')).toBeVisible()

    // 空白 click:主图左上角(grid.left=56/grid.top=40 之外,保证脱靶任何 series)
    const mainBox = await page.locator('.main-chart canvas').first().boundingBox()
    if (!mainBox) throw new Error('main-chart canvas not found')
    await page.mouse.click(mainBox.x + 20, mainBox.y + 20)

    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(0)
  })

  test('场景 4: 第 2 击 → banner 消失 + shift 累积器 length=2(pair query 触发)', async ({ page }) => {
    await setupChart(page)
    const m1 = await nthPointMarker(page, 0)
    expect(m1).not.toBeNull()
    const m2 = await nthPointMarker(page, 1)
    if (!m2) {
      test.skip(true, 'fixture 副图 points 不足 2 个 marker,场景 4 无法真实驱动第 2 击')
    }

    await zoomAroundBar(page, m1!.startIdx)
    await shiftClickMarker(page, m1!.event_id)
    await expect(page.locator('.shift-pair-banner')).toBeVisible()

    await zoomAroundBar(page, m2!.startIdx)
    await shiftClickMarker(page, m2!.event_id)

    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(2)
  })

  test('场景 5: 第 3 击重置 → banner 再次出现', async ({ page }) => {
    await setupChart(page)
    const m1 = await nthPointMarker(page, 0)
    expect(m1).not.toBeNull()
    await zoomAroundBar(page, m1!.startIdx)

    // 直接注入 shift 累积器 length=2 前置态,绕开场景 4 的 fixture 依赖(brief 约定手法)
    await page.evaluate(() => {
      const view = (window as any).__e2e.view
      view.setShiftSelectedEvents([
        { event_id: 'fake1', class_id: 'BO', source: 'main' },
        { event_id: 'fake2', class_id: 'BO', source: 'main' },
      ])
    })
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()

    // 第 3 击:handleShiftClick 累积器 length===2 分支 → 重置为 [新点击 event]
    await shiftClickMarker(page, m1!.event_id)
    await expect(page.locator('.shift-pair-banner')).toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(1)
  })
})
