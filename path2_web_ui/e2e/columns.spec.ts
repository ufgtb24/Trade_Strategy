import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { apiBase } from './ports'
import { REPO, TRAIN_END, boxOn, drawOnKline, laneY, openSymbol, routeTo, startBackend, stopBackend, xOf,
         type Backend } from './annotateHelpers'
import { gotoScanTier } from './scanTier'

/**
 * 左右栏的收起与拖宽(真浏览器里的几何;按法与守卫的细项在 tests/components/columns.spec.ts):
 * 1. 左栏抽屉:rally 页拖窄到某一宽度时 boxes 列被遮、代码列还在;拖到最窄停在固定宽度、不收起;没有横向滚动条;
 *    换到内容窄的 random 页露出宽度跟着缩,换回 rally 页恢复。
 * 2. 右栏拖宽:标注侧栏、诊断侧栏拖窄后内容换行、字段名仍完整可见,拖到最窄就停。
 * 3. 右栏收着时,在图上选中一个框、画一个新框,右栏都不打开,焦点也没掉进看不见的起名框;Shift+R 打开后停在 selection 页、
 *    显示的是那个新框。
 * 4. 只藏不拆:charts 页滚到中间收起再打开,页签和滚动位置都在;样本的 note 打了一半收起再打开,字还在;
 *    左栏收着时 PageUp / PageDown 照样换图(找图清单;扫描列表另一条)。
 * 5. 记忆:收起状态和三份宽度在换股、切档、刷新后都还在,三份宽度互不影响。
 * 6. 图:收起左右栏前后,第一根和最后一根 K 线的日期不变,框和样本三角仍对着各自的 K 线(点上去选得中);
 *    拖边时图不平移、不画框,点亮的 box 工具还亮着。
 * 1~6 用自己起的后端(标注在临时目录,夹具 annotation_grouping_v1,另放 60 只股票各一个框让 charts 页能滚动;
 * app 用 bo_only 加手写 mapping,同 annotate-compare);扫描列表那条用 configs/path2_web.yaml 的后端和历史里的扫描。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nfeatures:\n  w-pc-3: bo\n  w-pc-1: pk\n'
const STORE_KEY = 'path2_web_ui.panels.v1'

/** 夹具,再加一批:60 只股票各画一个没起名的框(charts 页要够长才能滚到中间)。 */
async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
  const symbols = readdirSync(join(REPO, 'datasets/pkls_until_20251231')).filter(f => f.endsWith('.pkl'))
    .map(f => f.slice(0, -4)).filter(s => /^[A-Z]{2,5}$/.test(s) && !['AAPL', 'MSFT', 'NVDA'].includes(s)).slice(0, 60)
  const ts = '20261104T120000.000Z'
  const ops = symbols.map((symbol, i) => ({
    ts, machine: 'pc', kind: 'box', id: `b-pc-${100 + i}`, base: null,
    value: { id: `b-pc-${100 + i}`, symbol, feature: null, start: '2024-02-01', end: '2024-03-01' },
  }))
  writeFileSync(join(b.root, 'annotations', `pc-${ts}-1.json`),
                JSON.stringify({ schema: 'path2_web.annotation/1', data_fingerprint: local, ops }))
}

const rect = (page: Page, tid: string) => page.getByTestId(tid).evaluate(el => {
  const r = el.getBoundingClientRect()
  return { left: r.left, right: r.right, width: r.width }
})
const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
const ann = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.ann()[key], k)

/** 按住某条边的中段,横向拖 dx(分几步走,途中经过图的上方)。 */
async function dragEdge(page: Page, tid: string, dx: number) {
  const b = (await page.getByTestId(tid).boundingBox())!
  const x = b.x + b.width / 2, y = b.y + b.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + dx / 2, y, { steps: 5 })
  await page.mouse.move(x + dx, y + 40, { steps: 5 })
  await page.mouse.up()
}
/** 把左栏拖到露出 w(CSS 像素)。 */
async function dragLeftTo(page: Page, w: number) {
  await dragEdge(page, 'left-edge', w - (await rect(page, 'left-clip')).width)
}

/** 主图看得见的那段:第一根与最后一根的日期。 */
const visibleRange = (page: Page) => page.evaluate(() => {
  const opt = (window as any).__e2e.chartMain().getOption()
  const dates: string[] = opt.xAxis[0].data
  const dz = opt.dataZoom[0]
  const N = dates.length
  return { first: dates[Math.round((dz.start / 100) * N)], last: dates[Math.round((dz.end / 100) * N) - 1] }
})
/** 主图宽度(栏收起、变宽变窄后跟着变)。 */
const chartWidth = (page: Page) => page.evaluate(() => document.querySelector('.main-chart')!.getBoundingClientRect().width)
/** 图窗缩到 [d0, d1]。 */
async function zoomTo(page: Page, d0: string, d1: string) {
  await page.evaluate(([a, b]) => {
    const main = (window as any).__e2e.chartMain()
    const dates: string[] = main.getOption().xAxis[0].data
    const n = dates.length
    const i0 = dates.findIndex(d => d >= a), i1 = dates.findIndex(d => d > b)
    main.dispatchAction({ type: 'dataZoom', start: (i0 / n) * 100, end: ((i1 < 0 ? n : i1) / n) * 100 })
  }, [d0, d1])
}
const indexOf = (page: Page, date: string) => page.evaluate(d =>
  ((window as any).__e2e.chartMain().getOption().xAxis[0].data as string[]).indexOf(d), date)
/** 样本日那根 K 线下方三角的中心(页面坐标;同 annotate-samples)。 */
async function trianglePos(page: Page, i: number): Promise<[number, number]> {
  return page.evaluate((i) => {
    const main = (window as any).__e2e.chartMain()
    const low = main.getOption().series.find((s: any) => s.type === 'candlestick').data[i][2]
    const [x, y] = main.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [i, low])
    const r = document.querySelector('.main-chart')!.getBoundingClientRect()
    return [r.left + x, r.top + y + 12] as [number, number]
  }, i)
}
/** 点框所在轨上框的中间,点样本三角:都要选得中(框和三角对着各自的 K 线)。 */
async function expectMarksAligned(page: Page) {
  const [b0, b1] = [await indexOf(page, '2024-02-01'), await indexOf(page, '2024-03-01')]
  await page.mouse.click((await xOf(page, b0, 'sub') + await xOf(page, b1, 'sub')) / 2, await laneY(page, '横盘'))
  await expect.poll(() => ann(page, 'selectedBoxId')).toBe('b-pc-8')
  const [tx, ty] = await trianglePos(page, await indexOf(page, '2024-03-11'))
  await page.mouse.click(tx, ty)
  await expect.poll(() => ann(page, 'selectedSampleId')).toBe('s-pc-11')
}
/** 页面上没有横向滚动条:整页不横滚,左栏里没有出了横向滚动条的盒子。 */
const horizontalScrollers = (page: Page) => page.evaluate(() => {
  const out: string[] = []
  if (document.documentElement.scrollWidth > window.innerWidth) out.push('page')
  for (const el of document.querySelectorAll('[data-testid="left-panel"] *')) {
    const s = getComputedStyle(el)
    if ((s.overflowX === 'auto' || s.overflowX === 'scroll') && el.scrollWidth > el.clientWidth + 1
        && (el as HTMLElement).offsetParent !== null) out.push((el as HTMLElement).className || el.tagName)
  }
  return out
})

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('左右栏的收起与拖宽', () => {
  test.setTimeout(600_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    backend = await startBackend(undefined, { bo_only: MAPPING })
    await putFixture(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('左栏抽屉:拖窄从靠图一侧遮列、代码列最后遮,拖到最窄停住不收起,没有横向滚动条;换到窄页跟着缩、换回来恢复',
       async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    const th = (name: string) => page.getByTestId('finder-page-rally').locator('th', { hasText: name }).first()
      .evaluate(el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right } })
    const full = (await rect(page, 'left-drawer')).width
    expect((await rect(page, 'left-clip')).width).toBeCloseTo(full, 0)        // 没拖过:全开
    expect(await horizontalScrollers(page)).toEqual([])

    // 拖到 boxes 列左沿往里 4px:boxes 列整个被遮,symbol、date 列还在;内容不重排(列的位置不变)
    const boxes0 = await th('boxes'), sym0 = await th('symbol')
    await dragLeftTo(page, boxes0.left - 4)
    const clip = await rect(page, 'left-clip')
    expect(clip.width).toBeCloseTo(boxes0.left - 4, 0)
    expect(await th('boxes')).toEqual(boxes0)
    expect(await th('symbol')).toEqual(sym0)
    expect((await th('date')).right).toBeLessThanOrEqual(clip.right)
    const hidden = await page.getByTestId('finder-page-rally').locator('[data-testid="row-boxes"]').first().evaluate(el => {
      const r = el.getBoundingClientRect()
      return !el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2))
    })
    expect(hidden).toBe(true)
    expect(await horizontalScrollers(page)).toEqual([])

    // 拖过最窄:停在固定宽度、不收起;代码列还在
    await dragEdge(page, 'left-edge', -800)
    const min = await rect(page, 'left-clip')
    expect(min.width).toBe(70)
    expect(await page.evaluate(k => JSON.parse(localStorage.getItem(k)!).leftCollapsed, STORE_KEY)).toBe(false)
    await expect(page.getByTestId('left-clip')).toBeVisible()
    expect((await th('symbol')).right).toBeLessThanOrEqual(min.right)
    expect(await horizontalScrollers(page)).toEqual([])

    // 拖到 290(在 rally 内容全宽之内):换到内容窄的 random 页(空页,按 220 算)露出跟着缩;换回 rally 恢复 290
    await dragLeftTo(page, 290)
    expect((await rect(page, 'left-clip')).width).toBeCloseTo(290, 0)
    await page.getByTestId('finder-tab-random').click()
    expect((await rect(page, 'left-clip')).width).toBeCloseTo(220, 0)
    await page.getByTestId('finder-tab-rally').click()
    expect((await rect(page, 'left-clip')).width).toBeCloseTo(290, 0)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('右栏拖宽:标注侧栏、诊断侧栏拖窄后内容换行、字段名完整,拖到最窄就停', async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')
    await page.getByTestId('annotation-tab-features').click()
    const def = page.getByTestId('annotation-page-features').locator('[data-testid="definition-text"]', { hasText: '成交量比前一段' })
    await dragEdge(page, 'ann-edge', -300)                                     // 先拉宽:定义一行写得下
    const wide = await rect(page, 'annotation-sidebar')
    expect(wide.width).toBeGreaterThan(560)
    const h1 = (await def.boundingBox())!.height
    await dragEdge(page, 'ann-edge', 2000)                                     // 拖过最窄
    const narrow = await rect(page, 'annotation-sidebar')
    expect(narrow.width).toBe(260)
    expect((await def.boundingBox())!.height).toBeGreaterThan(h1 * 1.5)        // 换行了
    // 字段名(definition、box×n 这些固定词)都完整可见:没被截、没伸出栏外
    const cut = await page.getByTestId('annotation-sidebar').evaluate(side => {
      const r = side.getBoundingClientRect()
      return [...side.querySelectorAll('.ann-k')].filter(k => {
        const b = k.getBoundingClientRect()
        return b.width > 0 && (k.scrollWidth > k.clientWidth + 1 || b.right > r.right || b.left < r.left)
      }).map(k => k.textContent)
    })
    expect(cut).toEqual([])
    expect(await page.getByTestId('annotation-sidebar').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)

    // 诊断侧栏(app 档,Sidebar 按钮打开):同样拖窄停在最窄,块跟着变窄,node 名完整可见
    await page.getByTestId('top-pattern-button').click()
    await page.locator('[data-testid="top-pattern-option"][data-name="W底"]').click()
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await page.getByTestId('panel-toggle-sidebar').click()
    const detail = page.locator('.chart-area > .sidebar')
    await expect(detail.locator('.node-label').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('detail-edge-toggle')).toHaveCount(0)
    await dragEdge(page, 'detail-edge', -300)
    const dWide = (await detail.boundingBox())!.width
    const nameWide = (await detail.locator('.panel-name').boundingBox())!.width
    await dragEdge(page, 'detail-edge', 2000)
    expect((await detail.boundingBox())!.width).toBe(220)
    expect(dWide).toBeGreaterThan(500)
    expect((await detail.locator('.panel-name').boundingBox())!.width).toBeLessThan(nameWide - 200)
    const dCut = await detail.evaluate(side => {
      const r = side.getBoundingClientRect()
      return [...side.querySelectorAll('.node-label, .panel-name, .section-title')].filter(k => {
        const b = k.getBoundingClientRect()
        return b.width > 0 && (k.scrollWidth > k.clientWidth + 1 || b.right > r.right)
      }).map(k => k.textContent)
    })
    expect(dCut).toEqual([])
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('右栏收着时选中框、画新框都不打开,焦点不掉进看不见的起名框;Shift+R 打开后停在 selection 页、显示那个新框',
       async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')
    await zoomTo(page, '2024-01-02', '2024-06-28')
    await page.getByTestId('annotation-tab-pattern').click()
    await page.getByTestId('ann-edge-toggle').click()
    await expect(page.getByTestId('annotation-sidebar')).toBeHidden()

    // 在图上点选一个框:选中了,右栏不打开,页签已翻到 selection
    const [b0, b1] = [await indexOf(page, '2024-02-01'), await indexOf(page, '2024-03-01')]
    await page.mouse.click((await xOf(page, b0, 'sub') + await xOf(page, b1, 'sub')) / 2, await laneY(page, '横盘'))
    await expect.poll(() => ann(page, 'selectedBoxId')).toBe('b-pc-8')
    await expect(page.getByTestId('annotation-sidebar')).toBeHidden()
    expect(await ann(page, 'tab')).toBe('selection')

    // 画一个新框:右栏照样收着;起名框看不见,焦点没掉进去(仍在页面上或刚点过的 box 按钮上)
    const i = await indexOf(page, '2024-05-01')
    const id = await drawOnKline(page, i, i + 10)
    await expect(page.getByTestId('annotation-sidebar')).toBeHidden()
    expect(await page.evaluate(() => {
      const ae = document.activeElement
      return !!ae && !document.querySelector('[data-testid="annotation-sidebar"]')!.contains(ae)
        && !ae.matches('input, textarea, select')
    })).toBe(true)

    // Shift+R:打开,停在 selection 页,显示的是新框
    await page.keyboard.press('Shift+R')
    await expect(page.getByTestId('annotation-sidebar')).toBeVisible()
    await expect(page.getByTestId('annotation-tab-selection')).toHaveAttribute('aria-selected', 'true')
    expect(await ann(page, 'selectedBoxId')).toBe(id)
    await expect(page.getByTestId('box-panel')).toBeVisible()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('只藏不拆:charts 页的滚动位置、note 打了一半的字都留着;左栏收着时 PageUp / PageDown 照样换图', async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')

    // charts 页滚到中间,收起再打开:页签和滚动位置都在
    await page.getByTestId('finder-tab-charts').click()
    const charts = page.getByTestId('finder-page-charts')
    await expect(page.getByTestId('charts-row')).toHaveCount(63)
    await page.setViewportSize({ width: 2560, height: 700 })
    await expect.poll(() => charts.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(200)
    await charts.evaluate(el => { el.scrollTop = Math.round((el.scrollHeight - el.clientHeight) / 2) })
    const y = await charts.evaluate(el => el.scrollTop)
    await page.getByTestId('left-edge-toggle').click()
    await expect(charts).toBeHidden()
    await page.getByTestId('left-edge').click()
    await expect(charts).toBeVisible()
    await expect(page.getByTestId('finder-tab-charts')).toHaveAttribute('aria-selected', 'true')
    expect(await charts.evaluate(el => el.scrollTop)).toBe(y)

    // 样本的 note 打了一半,点箭头收起再打开:字还在
    await page.evaluate(() => (window as any).__e2e.ann().selectSample('s-pc-11'))
    const note = page.getByTestId('sample-note')
    await note.click()
    await note.pressSequentially('half wri')
    await page.getByTestId('ann-edge-toggle').click()
    await expect(page.getByTestId('annotation-sidebar')).toBeHidden()
    await page.getByTestId('ann-edge').click()
    await expect(note).toHaveValue('half wri')

    // 左栏收着(Shift+L)时 PageDown / PageUp 在 charts 页上照样挨个换图
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    const rowsSyms = await page.getByTestId('charts-row').evaluateAll(rs => rs.map(r => r.getAttribute('data-symbol')))
    const at = rowsSyms.indexOf(await view(page, 'symbol'))
    await page.keyboard.press('Shift+L')
    await expect(charts).toBeHidden()
    await page.keyboard.press('PageDown')
    await expect.poll(() => view(page, 'symbol')).toBe(rowsSyms[at + 1])
    await page.keyboard.press('PageUp')
    await expect.poll(() => view(page, 'symbol')).toBe(rowsSyms[at])
    await expect(charts).toBeHidden()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('记忆:收起状态和三份宽度在换股、切档、刷新后都还在,三份宽度互不影响', async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    await openSymbol(page, 'AAPL')
    await dragLeftTo(page, 250)
    await dragEdge(page, 'ann-edge', -80)                                      // 320 → 400
    expect((await rect(page, 'annotation-sidebar')).width).toBe(400)
    await page.getByTestId('ann-edge-toggle').click()
    await page.getByTestId('top-pattern-button').click()
    await page.locator('[data-testid="top-pattern-option"][data-name="W底"]').click()
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await page.getByTestId('panel-toggle-sidebar').click()
    await dragEdge(page, 'detail-edge', -50)                                   // 280 → 330
    const check = async (where: string) => {
      expect((await rect(page, 'left-clip')).width, where).toBeCloseTo(250, 0)
      if (await view(page, 'annotating')) {
        await expect(page.getByTestId('annotation-sidebar'), where).toBeHidden()
      } else {
        expect((await page.locator('.chart-area > .sidebar').boundingBox())!.width, where).toBe(330)
      }
    }
    await check('app 档')
    const sym0 = await view(page, 'symbol')
    await page.getByTestId('rally-row').nth(1).click()                         // 换股(左栏换图不换档,留在 app)
    await expect.poll(() => view(page, 'symbol')).not.toBe(sym0)
    expect(await view(page, 'mode')).toBe('app')
    await check('app 档换股后')
    await page.getByTestId('mode-annotate').click()
    await check('切回 annotate')
    await openSymbol(page, 'MSFT')                                             // annotate 里用代码换股
    await check('annotate 换股后')
    await page.getByTestId('ann-edge').click()
    expect((await rect(page, 'annotation-sidebar')).width).toBe(400)
    await page.getByTestId('ann-edge-toggle').click()
    await page.getByTestId('left-edge-toggle').click()
    await page.reload()
    await expect(page.getByTestId('left-clip')).toBeHidden()                    // 刷新后左栏还收着
    await expect(page.getByTestId('annotation-sidebar')).toBeHidden()
    await page.getByTestId('left-edge').click()
    await page.getByTestId('ann-edge').click()
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    expect((await rect(page, 'left-clip')).width).toBeCloseTo(250, 0)
    expect((await rect(page, 'annotation-sidebar')).width).toBe(400)
    const stored = await page.evaluate(k => JSON.parse(localStorage.getItem(k)!), STORE_KEY)
    expect([stored.leftWidth, stored.annWidth, stored.detailWidth]).toEqual([250, 400, 330])
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('图:收起左右栏前后日期范围不变、框和三角仍对着 K 线;拖边不平移、不画框,点亮的 box 还亮着', async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')
    await zoomTo(page, '2024-01-02', '2024-06-28')
    const r0 = await visibleRange(page)
    const w0 = await chartWidth(page)
    await expectMarksAligned(page)

    await page.getByTestId('left-edge-toggle').click()
    await page.getByTestId('ann-edge-toggle').click()
    await expect.poll(() => chartWidth(page)).toBeGreaterThan(w0 + 300)
    expect(await visibleRange(page)).toEqual(r0)
    await expectMarksAligned(page)

    await page.getByTestId('left-edge').click()
    await page.getByTestId('ann-edge').click()
    await expect.poll(() => chartWidth(page)).toBeCloseTo(w0, 0)
    expect(await visibleRange(page)).toEqual(r0)
    await expectMarksAligned(page)

    // 点亮 box 后拖两条边(途中经过图的上方):图不平移、不多出框,box 还亮着
    const nBoxes = async () => (await page.evaluate(() =>
      (window as any).__e2e.ann().state.charts.find((c: any) => c.symbol === 'AAPL').boxes.length)) as number
    const n0 = await nBoxes()
    await boxOn(page)
    await dragEdge(page, 'left-edge', 120)
    await dragEdge(page, 'ann-edge', -150)
    expect(await visibleRange(page)).toEqual(r0)
    expect(await nBoxes()).toBe(n0)
    await expect(page.getByTestId('tool-box')).toHaveClass(/\bon\b/)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})

async function ensureScan(request: APIRequestContext) {
  const list = async () => (await (await request.get(`${apiBase}/scans/`)).json()) as any[]
  if ((await list()).length > 0) return
  const r = await request.post(`${apiBase}/scan`, { data: {
    pattern_ids: ['bo_only'], start_date: '2025-01-01', end_date: TRAIN_END, workers: 2, ticker_regex: '^AA', label_horizon: 20,
  } })
  expect(r.ok()).toBe(true)
  await expect.poll(async () => (await list()).length, { timeout: 240_000 }).toBeGreaterThan(0)
}

test('左栏收着时,scan 档扫描列表的 PageUp / PageDown 照样换图', async ({ page, request }) => {
  test.setTimeout(600_000)
  await ensureScan(request)
  await gotoScanTier(page)
  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.file-list tbody tr').first()).toBeVisible({ timeout: 15_000 })
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  const rows = page.getByTestId('scan-side').locator('td.sym[data-symbol]')
  await expect(rows.first()).toBeVisible({ timeout: 30_000 })
  const syms = await rows.evaluateAll(rs => rs.map(r => r.getAttribute('data-symbol')))
  expect(syms.length).toBeGreaterThan(1)
  await rows.first().click()
  await expect.poll(() => view(page, 'symbol')).toBe(syms[0])
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('Shift+L')
  await expect(page.getByTestId('scan-side')).toBeHidden()
  await page.keyboard.press('PageDown')
  await expect.poll(() => view(page, 'symbol')).toBe(syms[1])
  await page.keyboard.press('PageUp')
  await expect.poll(() => view(page, 'symbol')).toBe(syms[0])
  await expect(page.getByTestId('scan-side')).toBeHidden()
})
