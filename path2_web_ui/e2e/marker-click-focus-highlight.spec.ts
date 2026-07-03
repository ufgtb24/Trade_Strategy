import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/run_path2_web.py)。
//
// 被点 event marker 的高亮(放大+阴影悬浮方案,spec 2026-07-02-marker-highlight-elevation):
//
// 描边框方案历经白(浅底不可见)/蓝(撞蓝色角色色)/琥珀+呼吸(被推翻)三轮,
// 根本矛盾 = 角色色由 pattern 任意定义,任何固定描边色都有撞车场景。现方案改用
// 形态维度:组员 = 本色放大+投影(悬浮),被点者 = 同轮廓+琥珀边缘,bundle 层
// focus 条目独占(防双阴影叠深);放大实心版 silent:true 让交互穿透到本体。
//
// 步骤(按用户验收路径):读扫描文件 → active pattern=bottom_burst → 列表按
// bottom_burst 降序 → 选第一只(fixture 固定为 BTMWW)→ 以副图 marker 为中心
// zoom in → 真实鼠标点击 marker → 断言链路状态 + focus 条目独占 + renderItem 放大实心产物。

const SCAN_TS = '2026-06-30 17:52:56'
const TICKER = 'BTMWW'

async function setupChart(page: import('@playwright/test').Page) {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 active pattern → bottom_burst(轮询等选项就绪,消除负载竞态;同 subchart-tooltip spec)
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

  // 选股:直接调 view.selectSymbol(绕开 sidebar 虚拟滚动;BTMWW 即 bottom_burst 降序第一)
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

test.describe('marker 点击 focus 高亮', () => {
  test('点击副图 event marker → 放大实心+琥珀边+阴影,focus 条目独占(链路 + 条目 + renderItem)', async ({ page }) => {
    await setupChart(page)

    // 副图第一个 point marker(x=start_idx, band 从 value[2] 取)
    const marker = await page.evaluate(() => {
      const sub = (window as any).__e2e.chartSub()
      const pts = sub.getOption().series.find((s: any) => s.name === 'points')
      const d = pts?.data?.[0]
      if (!d) return null
      return { eventId: d.event_id as string, x: d.value[0] as number, band: d.value[2] as number }
    })
    expect(marker).not.toBeNull()

    // 以 marker 为中心 zoom in
    await page.evaluate((x) => {
      const main = (window as any).__e2e.chartMain()
      const n = (main.getOption().xAxis?.[0]?.data || []).length
      const c = (x / n) * 100
      main.dispatchAction({ type: 'dataZoom', start: Math.max(0, c - 8), end: Math.min(100, c + 8) })
    }, marker!.x)
    await page.waitForTimeout(300)

    // marker 屏幕坐标:x 由 convertToPixel;y 取 band 中心(zebra 装饰 rect z===1,
    // 第 band 个的 top + height/2 即 renderPointWithGeom 的三角中心)
    const pos = await page.evaluate(({ x, band }) => {
      const sub = (window as any).__e2e.chartSub()
      const rect = (document.querySelector('.sub-inner canvas') as HTMLElement).getBoundingClientRect()
      const px = sub.convertToPixel({ seriesIndex: 1 }, [x, 0])
      const g = sub.getOption().graphic
      const els = Array.isArray(g) ? (g[0]?.elements ?? g) : (g?.elements ?? [])
      const zebra = els.filter((e: any) => e.type === 'rect' && e.z === 1)
      const zb = zebra[band]
      if (!zb) return null
      const innerY = zb.top + zb.shape.height / 2
      return { clientX: rect.left + px[0], clientY: rect.top + innerY, innerX: px[0], innerY }
    }, marker!)
    expect(pos).not.toBeNull()

    // 真实鼠标点击 marker
    await page.mouse.click(pos!.clientX, pos!.clientY)
    await page.waitForTimeout(500)

    // 断言 1:点击链路状态 — 被点 event 被选中且进 highlight 集合
    const state = await page.evaluate(() => {
      const v = (window as any).__e2e.view
      return { sel: v.selectedEventId, hl: Array.from(v.highlightedEventIds ?? []) }
    })
    expect(state.sel).toBe(marker!.eventId)
    expect(state.hl).toContain(marker!.eventId)

    const kinds = await page.evaluate((eid) => {
      const sub = (window as any).__e2e.chartSub()
      const s = sub.getOption().series.find((x: any) => x.name === 'highlight')
      return (s?.data ?? []).filter((d: any) => d.event_id === eid).map((d: any) => d.kind)
    }, marker!.eventId)
    // 断言 2:被点 marker 由 focus 条目独家表达(无 group 条目——双条目=双阴影叠深)
    expect(kinds).toEqual(['focus'])

    // 断言 3(锁琥珀词汇,spec 2026-07-03-group-amber-focus-edge):真实挂载 renderItem 的
    // 产物 — focus = 琥珀实心放大 + 深灰蓝边 + 阴影 + silent 穿透;group(组内另一 marker)
    // = 琥珀实心 + 阴影、无描边;且 highlight 系列显式 animation:true(pending 闪烁的前提)。
    // 旧本色方案下此断言失败:fill=本色、focus stroke='#fbbf24'。
    const probe = await page.evaluate((eid) => {
      const sub = (window as any).__e2e.chartSub()
      const s = sub.getOption().series.find((x: any) => x.name === 'highlight')
      if (!s) return null
      const fakeApi = { value: () => 0, coord: () => [100, 200], size: () => [10, 0] }
      const out: Record<string, any> = { animation: s.animation }
      s.data.forEach((d: any, i: number) => {
        const shape = s.renderItem({ dataIndex: i }, fakeApi)
        const slot = d.event_id === eid ? 'focus' : 'group'
        out[slot] = { kind: d.kind, style: shape?.style, silent: shape?.silent }
      })
      return out
    }, marker!.eventId)
    expect(probe).not.toBeNull()
    expect(probe!.animation).toBe(true)
    expect(probe!.focus.kind).toBe('focus')
    expect(probe!.focus.style.stroke).toBe('#1e293b')
    expect(probe!.focus.style.fill).toBe('#fbbf24')
    expect(probe!.focus.style.shadowBlur).toBeGreaterThan(0)
    expect(probe!.focus.silent).toBe(true)
    expect(probe!.group.kind).toBe('group')
    expect(probe!.group.style.stroke).toBeUndefined()
    expect(probe!.group.style.fill).toBe('#fbbf24')
    expect(probe!.group.style.shadowBlur).toBeGreaterThan(0)
  })
})
