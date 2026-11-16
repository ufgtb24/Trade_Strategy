import { test, expect, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, TRAIN_END, boxOn, boxesOf, annState, drag, klineY, routeTo, startBackend, stopBackend, xOf,
         type Backend } from './annotateHelpers'
import { enterScanTier } from './scanTier'

/**
 * 主图上按住 Shift 复制一天、一段(spec 1.14「复制一天、一段」、第 9 节「端到端」那条;实施票 16):
 * 1. 四档(annotate、compare、app、scan)各一次 Shift+点、一次 Shift+拖:复制出的行对(`股票 pattern day 日期` /
 *    `股票 pattern range 起→止`,剪贴板里也是它);之后选中的路径、当前日、标注上的选中、视窗的起止都和之前一样。
 *    Shift+拖在成交量带上、从右往左拖。
 * 2. 工具亮着照样复制:annotate 的 box 工具亮着时 Shift+拖不画框、point 工具亮着时 Shift+点不放样本,工具都仍亮;
 *    compare 的 feedback 工具亮着时不弹反馈面板、工具仍亮,作答面板开着时不关它;app、scan 的「框选」亮着时
 *    不发框选查询(不按 Shift 拖照常发,作对照)。
 * 3. app 档 Shift+点主图上的 event 记号:照旧是跨图配对查询,两击后发出 scope=pair 查询,复制出的行没变。
 *    从顶栏切进的 app 档(现算)行里的 pattern 是顶栏的当前 pattern,Shift+C 复制选中的东西也是。
 * 4. 回归:不按 Shift 时拖动照旧平移,点 K 线照旧取消选中(annotate 走标注手势,app 走图表的点击)。
 * 截图(元素级)挂在测试结果里:Shift+拖途中的竖带预览(copy-band.png)、复制后的提示条(copy-toast.png)。
 *
 * 后端是 e2e/annotationBackend.py 起的测试后端(标注在临时目录,用 tests/path2_web/fixtures/annotation_grouping_v1 的
 * 例子批次,mapping 手写:pattern W底 → bo_only),scan 档的扫描也跑在它上面(bo_only 扫 AAPL,只读截到训练段末日的副本)。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nfeatures:\n  w-pc-3: bo\n  w-pc-1: pk\n'

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

/** 在测试后端上跑一次 bo_only 小扫描(只扫 AAPL),返回它的名字。 */
async function runScan(b: Backend): Promise<string> {
  const name = `e2e_shift_copy_${Date.now()}`
  const r = await fetch(`${b.base}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern_ids: ['bo_only'], start_date: '2024-01-01', end_date: TRAIN_END, workers: 1,
                           ticker_regex: '^AAPL$', label_horizon: 20, note: name }),
  })
  expect(r.ok).toBe(true)
  await expect.poll(async () => {
    const scans: any[] = await (await fetch(`${b.base}/scans/`)).json()
    return scans.some(x => x.name === name && !x.partial)
  }, { timeout: 240_000 }).toBe(true)
  return name
}

const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
const lastText = (page: Page) => page.evaluate(() => (window as any).__e2e.copyRef().lastText as string | null)
const clipboard = (page: Page) => page.evaluate(() => navigator.clipboard.readText())
const datesOf = (page: Page): Promise<string[]> =>
  page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
/** 视窗的起止(百分比) */
const zoomOf = (page: Page) => page.evaluate(() => {
  const dz = (window as any).__e2e.chartMain().getOption().dataZoom[0]
  return [dz.start, dz.end] as [number, number]
})
/** 复制前后要不变的:选中的路径、当前日、标注上选中的框 / 样本、亮着的工具 */
const stateOf = (page: Page) => page.evaluate(() => {
  const e2e = (window as any).__e2e
  const a = e2e.ann()
  return JSON.stringify({ sel: e2e.view.selPath, day: e2e.view.currentDay, box: a.selectedBoxId,
                          sample: a.selectedSampleId, tool: a.tool })
})
/** 主图成交量带中间一行的页面坐标 y */
const volumeY = (page: Page) => page.evaluate(() => {
  const g = (window as any).__e2e.chartMain().getOption().grid[1]
  return document.querySelector('.main-chart')!.getBoundingClientRect().top + g.top + g.height / 2
})

async function shiftClick(page: Page, x: number, y: number) {
  await page.mouse.move(x, y)
  await page.keyboard.down('Shift')
  await page.mouse.down()
  await page.mouse.up()
  await page.keyboard.up('Shift')
}
async function shiftDrag(page: Page, x0: number, y0: number, x1: number, y1: number) {
  await page.keyboard.down('Shift')
  await drag(page, x0, y0, x1, y1)
  await page.keyboard.up('Shift')
}

/**
 * 一次 Shift+点(K 线区)、一次 Shift+拖(成交量带、从右往左):行对、剪贴板里是它;状态与视窗不变。
 * head 是行首的「股票 pattern」。
 */
async function checkCopy(page: Page, head: string) {
  const ds = await datesOf(page)
  const n = ds.length
  const i = n - 30, j0 = n - 60, j1 = n - 40
  const before = await stateOf(page), zoom = await zoomOf(page)

  await shiftClick(page, await xOf(page, i), await klineY(page))
  await expect.poll(() => lastText(page)).toBe(`${head} day ${ds[i]}`)
  await expect.poll(() => clipboard(page)).toBe(`${head} day ${ds[i]}`)
  expect(await stateOf(page)).toBe(before)
  expect(await zoomOf(page)).toEqual(zoom)

  await shiftDrag(page, await xOf(page, j1), await volumeY(page), await xOf(page, j0), await volumeY(page))
  await expect.poll(() => lastText(page)).toBe(`${head} range ${ds[j0]}→${ds[j1]}`)
  await expect.poll(() => clipboard(page)).toBe(`${head} range ${ds[j0]}→${ds[j1]}`)
  await expect(page.getByTestId('copy-range-band')).toHaveCount(0)
  expect(await stateOf(page)).toBe(before)
  expect(await zoomOf(page)).toEqual(zoom)
}

/** 图窗缩到最后 200 根(K 线够宽,点得准) */
async function zoomLast200(page: Page) {
  await page.evaluate(() => {
    const main = (window as any).__e2e.chartMain()
    const n = main.getOption().xAxis[0].data.length
    main.dispatchAction({ type: 'dataZoom', start: ((n - 200) / n) * 100, end: 100 })
  })
}

async function pickPattern(page: Page, text: string) {
  await page.getByTestId('top-pattern-button').click()
  await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().currentPattern)).toBe(text)
}

async function waitChart(page: Page, symbol: string) {
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
}

/**
 * 主图上一个 event 记号(price-points)的页面坐标:记号画在锚点上方、位置随种类变,所以沿它那根 K 线的竖线
 * 往上逐点移过去,停到鼠标停着的记号就是它为止。返回记号的 instance_id 与坐标。
 */
async function findMainMarker(page: Page, exclude: string | null = null): Promise<{ id: string; x: number; y: number } | null> {
  const cands = await page.evaluate(() => {
    const main = (window as any).__e2e.chartMain()
    const opt = main.getOption()
    const si = opt.series.findIndex((s: any) => s.name === 'price-points')
    const [a, b] = [opt.dataZoom[0].startValue, opt.dataZoom[0].endValue]
    const rect = document.querySelector('.main-chart')!.getBoundingClientRect()
    return (opt.series[si]?.data ?? [])
      .filter((d: any) => d.value[0] >= a + 3 && d.value[0] <= b - 3)
      .map((d: any) => {
        const [x, y] = main.convertToPixel({ seriesIndex: si }, [d.value[0], d.anchorY ?? d.value[1]])
        return { id: String(d.instance_id), x: rect.left + x, y: rect.top + y }
      })
  })
  for (const c of cands.filter((x: { id: string }) => x.id !== exclude).slice(0, 6)) {
    for (let dy = 12; dy >= -60; dy -= 3) {
      await page.mouse.move(c.x, c.y + dy)
      const hit = await page.evaluate(() => (window as any).__e2e.hoverMarker())
      if (hit === c.id) return { id: c.id, x: c.x, y: c.y + dy }
    }
  }
  return null
}

test.use({ viewport: { width: 2560, height: 1440 }, permissions: ['clipboard-read', 'clipboard-write'] })

test.describe('主图上按住 Shift 复制一天、一段(四档)', () => {
  test.setTimeout(600_000)
  let backend: Backend | null = null
  let scanName = ''
  test.beforeAll(async () => {
    test.setTimeout(300_000)
    backend = await startBackend(undefined, { bo_only: MAPPING })
    await putFixture(backend)
    scanName = await runScan(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('annotate、compare:Shift+点 / 拖复制,选中与视窗不变;box、feedback 工具亮着照样复制;不按 Shift 照旧平移、取消选中', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await expect(page.getByTestId('mode-annotate')).toHaveClass(/\bon\b/)
    await pickPattern(page, 'W底')
    await page.evaluate(() => (window as any).__e2e.ann().selectSample('s-pc-11'))
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).toBe('s-pc-11')
    await zoomLast200(page)

    // annotate:选着样本时复制,样本仍选着
    await checkCopy(page, 'AAPL W底')

    // 截图:Shift+拖途中的竖带预览(只盖主图),松手后的提示条
    const ds = await datesOf(page), n = ds.length
    await page.keyboard.down('Shift')
    await page.mouse.move(await xOf(page, n - 80), await klineY(page))
    await page.mouse.down()
    await page.mouse.move(await xOf(page, n - 70), await klineY(page), { steps: 4 })
    await page.mouse.move(await xOf(page, n - 55), await klineY(page), { steps: 4 })
    await expect(page.getByTestId('copy-range-band')).toBeVisible()
    await page.locator('.kline-wrap-v2').screenshot({ path: testInfo.outputPath('copy-band.png'), scale: 'device' })
    await page.mouse.up()
    await page.keyboard.up('Shift')
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 range ${ds[n - 80]}→${ds[n - 55]}`)
    await expect(page.locator('.toast')).toContainText(`copied  AAPL W底 range ${ds[n - 80]}→${ds[n - 55]}`)
    await page.locator('.toast').screenshot({ path: testInfo.outputPath('copy-toast.png'), scale: 'device' })

    // box 工具亮着:Shift+拖复制一段,不画框,工具仍亮
    const boxes = boxesOf(await annState(page), 'AAPL').length
    await boxOn(page)
    await shiftDrag(page, await xOf(page, n - 50), await klineY(page), await xOf(page, n - 45), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 range ${ds[n - 50]}→${ds[n - 45]}`)
    await expect(page.getByTestId('tool-box')).toHaveClass(/\bon\b/)
    expect(boxesOf(await annState(page), 'AAPL').length).toBe(boxes)
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('tool-box')).not.toHaveClass(/\bon\b/)

    // point 工具亮着:Shift+点复制这一天,不放样本,工具仍亮
    const samples = (await annState(page)).charts.find((c: any) => c.symbol === 'AAPL').samples.length
    await page.getByTestId('tool-point').click()
    await expect(page.getByTestId('tool-point')).toHaveClass(/\bon\b/)
    await shiftClick(page, await xOf(page, n - 33), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 day ${ds[n - 33]}`)
    await expect(page.getByTestId('tool-point')).toHaveClass(/\bon\b/)
    expect((await annState(page)).charts.find((c: any) => c.symbol === 'AAPL').samples.length).toBe(samples)
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('tool-point')).not.toHaveClass(/\bon\b/)

    // compare:Shift+点 / 拖照样复制,选中与视窗不变
    await page.getByTestId('mode-compare').click()
    await expect.poll(() => view(page, 'mode')).toBe('compare')
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null), { timeout: 60_000 }).toBe('AAPL')
    await zoomLast200(page)
    await checkCopy(page, 'AAPL W底')

    // feedback 工具亮着:Shift+拖复制一段,不弹反馈面板,工具仍亮
    await page.getByTestId('tool-feedback').click()
    await expect(page.getByTestId('tool-feedback')).toHaveClass(/\bon\b/)
    await shiftDrag(page, await xOf(page, n - 40), await klineY(page), await xOf(page, n - 20), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 range ${ds[n - 40]}→${ds[n - 20]}`)
    expect(await page.evaluate(() => (window as any).__e2e.fb().panel)).toBeNull()
    await expect(page.getByTestId('tool-feedback')).toHaveClass(/\bon\b/)
    await page.keyboard.press('Escape')

    // 作答面板开着(普通点别处会关):Shift+点、Shift+拖照样复制,面板不关
    await page.evaluate(([a, b]) => (window as any).__e2e.fb().open({ symbol: 'AAPL', start: a, end: b, target: 'range' }),
                        [ds[n - 40], ds[n - 20]])
    await expect.poll(() => page.evaluate(() => !!(window as any).__e2e.fb().panel)).toBe(true)
    await shiftClick(page, await xOf(page, n - 150), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 day ${ds[n - 150]}`)
    await shiftDrag(page, await xOf(page, n - 160), await klineY(page), await xOf(page, n - 140), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 range ${ds[n - 160]}→${ds[n - 140]}`)
    await page.waitForTimeout(200)
    expect(await page.evaluate(() => !!(window as any).__e2e.fb().panel)).toBe(true)
    await page.keyboard.press('Escape')
    await expect.poll(() => page.evaluate(() => !!(window as any).__e2e.fb().panel)).toBe(false)

    // 回到 annotate:不按 Shift 时拖动照旧平移,点 K 线照旧取消选中(样本不再选着)
    await page.getByTestId('mode-annotate').click()
    await expect.poll(() => view(page, 'mode')).toBe('annotate')
    await page.evaluate(() => (window as any).__e2e.ann().selectSample('s-pc-11'))
    const zoom = await zoomOf(page)
    await drag(page, await xOf(page, n - 60), await klineY(page), await xOf(page, n - 30), await klineY(page))
    await expect.poll(() => zoomOf(page)).not.toEqual(zoom)
    const before = await lastText(page)
    // 平移后图窗往前挪了约 30 根:点一根看得见、离样本三角远的 K 线
    const smpIdx: number[] = (await annState(page)).charts
      .find((c: any) => c.symbol === 'AAPL').samples.map((x: any) => ds.indexOf(x.date))
    let k = n - 120
    while (smpIdx.some((j: number) => Math.abs(j - k) <= 3)) k -= 5
    await page.mouse.click(await xOf(page, k), await klineY(page))
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).toBeNull()
    expect(await lastText(page)).toBe(before)
  })

  test('app、scan:Shift+点 / 拖复制,选中与视窗不变;「框选」亮着不发查询;Shift+点记号照旧配对查询', async ({ page }) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await pickPattern(page, 'W底')
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null), { timeout: 60_000 }).toBe('AAPL')
    await zoomLast200(page)
    // 从顶栏切进的 app 档(现算):行里的 pattern 同 compare,是顶栏的当前 pattern(app 是它对上的 bo_only)
    expect(await view(page, 'appId')).toBe('bo_only')

    // 先选中一个 event(选中与当前日都有),再复制
    const ev = await page.evaluate(() => {
      const main = (window as any).__e2e.chartMain()
      const pp = main.getOption().series.find((s: any) => s.name === 'price-points')
      return pp?.data?.at(-1)?.instance_id ?? null
    })
    expect(ev).not.toBeNull()
    await page.evaluate((id) => (window as any).__e2e.view.setPath([{ kind: 'event', instanceId: id }]), ev)
    await expect.poll(() => view(page, 'currentDay')).not.toBeNull()
    await checkCopy(page, 'AAPL W底')
    // Shift+C 复制选中的 event,行首同样是顶栏的 pattern(以前这里取不到 pattern)
    await page.keyboard.press('Shift+C')
    await expect.poll(() => lastText(page)).toMatch(/^AAPL W底 event /)

    // 「框选」亮着:Shift+拖照样复制,不发框选(scope=time)查询
    let timeQueries = 0
    page.on('request', r => { if (r.url().includes('scope=time')) timeQueries += 1 })
    await page.getByRole('button', { name: '框选' }).click()
    await expect(page.getByRole('button', { name: '框选' })).toHaveClass(/active/)
    const ds = await datesOf(page), n = ds.length
    await shiftDrag(page, await xOf(page, n - 50), await klineY(page), await xOf(page, n - 35), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL W底 range ${ds[n - 50]}→${ds[n - 35]}`)
    await page.waitForTimeout(500)
    expect(timeQueries).toBe(0)
    // 对照:不按 Shift 拖,框选照常发查询(证明上面的计数接得到)
    await drag(page, await xOf(page, n - 50), await klineY(page), await xOf(page, n - 35), await klineY(page))
    await expect.poll(() => timeQueries).toBeGreaterThan(0)
    await page.getByRole('button', { name: '框选' }).click()
    await expect(page.getByRole('button', { name: '框选' })).not.toHaveClass(/active/)

    // Shift+点主图上的 event 记号:照旧是配对查询——两击后发出 scope=pair 查询;复制出的行没变
    await page.keyboard.press('Escape')
    await page.keyboard.press('Escape')
    let pairQueries = 0
    page.on('request', r => { if (r.url().includes('scope=pair')) pairQueries += 1 })
    const before = await lastText(page)
    const m1 = await findMainMarker(page)
    expect(m1).not.toBeNull()
    await shiftClick(page, m1!.x, m1!.y)
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)).toBe(1)
    expect(await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents[0]))
      .toMatchObject({ instance_id: m1!.id, source: 'main' })
    const m2 = await findMainMarker(page, m1!.id)
    expect(m2).not.toBeNull()
    await shiftClick(page, m2!.x, m2!.y)
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)).toBe(2)
    await expect.poll(() => pairQueries).toBeGreaterThan(0)
    expect(await lastText(page)).toBe(before)
    await page.keyboard.press('Escape')
    await page.keyboard.press('Escape')

    // 回归:不按 Shift 点一根没有记号的 K 线,照旧取消选中
    await page.evaluate((id) => (window as any).__e2e.view.setPath([{ kind: 'event', instanceId: id }]), ev)
    await expect.poll(() => view(page, 'selPath').then((p: any[]) => p.length)).toBeGreaterThan(0)
    let k = n - 120
    for (;; k -= 3) {
      await page.mouse.move(await xOf(page, k), await klineY(page))
      if (!(await page.evaluate(() => (window as any).__e2e.hoverMarker()))) break
    }
    await page.mouse.click(await xOf(page, k), await klineY(page))
    await expect.poll(() => view(page, 'selPath').then((p: any[]) => p.length)).toBe(0)
    expect(await lastText(page)).toBe(before)

    // scan:加载扫描后落在 scan 档,Shift+点 / 拖照样复制
    await enterScanTier(page)
    await page.getByRole('button', { name: /打开历史/ }).click()
    await page.locator(`.file-list tbody tr:has-text("${scanName}")`).click()
    await page.getByRole('button', { name: /^Open$/ }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible({ timeout: 30_000 })
    await page.waitForFunction(() => !!(window as any).__e2e?.view?.scanFile)
    await expect(page.getByTestId('mode-scan')).toHaveClass(/\bon\b/)
    await waitChart(page, 'AAPL')
    await zoomLast200(page)
    expect(await view(page, 'appId')).toBe('bo_only')
    await checkCopy(page, 'AAPL bo_only')
    // scan 档的「框选」亮着:Shift+拖照样复制,不发框选查询
    const tq = timeQueries
    await page.getByRole('button', { name: '框选' }).click()
    await expect(page.getByRole('button', { name: '框选' })).toHaveClass(/active/)
    const ds2 = await datesOf(page), n2 = ds2.length
    await shiftDrag(page, await xOf(page, n2 - 50), await klineY(page), await xOf(page, n2 - 35), await klineY(page))
    await expect.poll(() => lastText(page)).toBe(`AAPL bo_only range ${ds2[n2 - 50]}→${ds2[n2 - 35]}`)
    await page.waitForTimeout(500)
    expect(timeQueries).toBe(tq)
  })
})
