import { test, expect, type Page } from '@playwright/test'
import { deleteSmallScan, openSmallScan, runSmallScan, smallScanName } from './smallScan'

/**
 * 副图族行(真浏览器):
 * 1. 副图按族画:有族底线系列、没有 tier tag 系列;族行数不超过事件数;
 * 2. 选中一次 hit → K 线主图(价格区、成交量区)与副图都出现当前日竖线,bracket 上它那一族是当家行;
 * 3. → 在这一族的买入日之间走(竖线挪到下一个买入日),到头停住;Esc 一层层往外退,退到头再按才清掉当前日与当家行;
 * 4. 经副图的 click 事件点一格:选中的是格里的那个 event,成员所在族行上画选中框、当前日落在格的终点,用到它的 hit 画细框;
 *    点被买入日不同的几次 hit 共用的阶跃格:选中的是这个 event(显示栏 ← / → 键槽写 into buys ×n),哪一次 hit 都不算选中,
 *    竖线落在它的终点,bracket 上用到它的几次是实线细框、不闪;
 * 5. 副图竖直放大:副图变高、主图变矮、读数跟着走;族行数不变,每一行按倍数变高。
 *
 * 夹具:new_step 小扫描(./smallScan.ts),整个文件共用一次,结束删掉。
 */

test.use({ viewport: { width: 2560, height: 1440 } })

const SCAN_NAME = smallScanName('fold_rows')
const LS_KEY_BAND_ZOOM = 'kline-band-zoom-v1'

test.beforeAll(async () => { await runSmallScan(SCAN_NAME) })
test.afterAll(async () => { await deleteSmallScan(SCAN_NAME) })

async function openScan(page: Page): Promise<boolean> {
  await openSmallScan(page, SCAN_NAME)
  // 挑同起点 hit 最多的股票
  const sym = await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const pid = view.activePatternId
    let best: { sym: string; n: number } | null = null
    for (const r of view.scanFile.results) {
      const hits = r.per_pattern?.[pid]?.analysis?.hits ?? []
      const byStart = new Map<number, number>()
      for (const m of hits) byStart.set(m.start_idx, (byStart.get(m.start_idx) ?? 0) + 1)
      const n = Math.max(0, ...byStart.values())
      if (n >= 2 && (!best || n > best.n)) best = { sym: r.symbol, n }
    }
    if (best) view.selectSymbol(best.sym)
    return best?.sym ?? null
  })
  if (!sym) return false
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    const sub = e?.chartSub?.()
    const s = sub?.getOption()?.series?.find((x: any) => x.name === 'family-lines')
    return !!s && s.data.length > 0
  }, null, { timeout: 30_000 })
  return true
}

const seriesData = (page: Page, chart: 'chartMain' | 'chartSub', name: string) =>
  page.evaluate(([c, n]) => {
    const s = (window as any).__e2e[c]().getOption().series.find((x: any) => x.name === n)
    return s ? s.data : null
  }, [chart, name] as const)

test('族行、当前日竖线、←/→ 与 Esc', async ({ page }) => {
  test.setTimeout(420_000)
  test.skip(!(await openScan(page)), '这次小扫描里没有「同起点多次 hit」的股票')

  // 1. 族底线在、tier tag 不在;族行数 ≤ 事件数
  expect(await seriesData(page, 'chartSub', 'tier-tags')).toBeNull()
  const families = new Set(((await seriesData(page, 'chartSub', 'family-lines')) as any[]).map((d) => d.family_key))
  const nEvents = await page.evaluate(() => (window as any).__e2e.view.effectiveAnalysis.events.length)
  expect(families.size).toBeGreaterThan(0)
  expect(families.size).toBeLessThanOrEqual(nEvents)

  // 2. 选中同起点那一族里最早结束的 hit
  const famHits: string[] = await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const hits = view.effectiveAnalysis.hits.map((m: any, i: number) => ({ m, i }))
    const byStart = new Map<number, any[]>()
    for (const x of hits) byStart.set(x.m.start_idx, [...(byStart.get(x.m.start_idx) ?? []), x])
    const fam = [...byStart.values()].sort((a, b) => b.length - a.length)[0]
    return fam.sort((a: any, b: any) => a.m.end_idx - b.m.end_idx || a.i - b.i).map((x: any) => x.m.hit_id)
  })
  await page.evaluate((id) => (window as any).__e2e.view.focusHit(id), famHits[0])
  await page.waitForTimeout(300)
  const day = await page.evaluate(() => (window as any).__e2e.view.currentDay)
  expect(typeof day).toBe('number')
  expect(await seriesData(page, 'chartSub', 'current-day')).toEqual([{ value: [day] }])
  expect(await seriesData(page, 'chartMain', 'current-day')).toEqual([{ value: [day] }])
  expect(await seriesData(page, 'chartMain', 'current-day-volume')).toEqual([{ value: [day] }])
  const activeLines = ((await seriesData(page, 'chartSub', 'bracket-lines')) as any[]).filter((d) => d.active)
  expect(activeLines).toHaveLength(1)

  // 3. → 竖线挪到这一族的下一个买入日(选中那天买的、和刚才最像的一次);走到头停住。按键一直在这一族里走
  const walkAt = () => page.evaluate(() => {
    const v = (window as any).__e2e.view
    const fam = v.selPath[0]
    const slot = v.selInfo.day                          // ← / → 键槽:这一族的第几个买点日
    return { k: slot.k as number | null, n: slot.n as number, noun: slot.noun as string,
             days: v.world.inside([fam], 'day').map((x: any) => x.day) as number[],
             day: v.currentDay, hit: v.focusedHitId, outer: fam.kind as string }
  })
  const w0 = await walkAt()
  expect(w0.outer).toBe('hit_family')
  expect(w0.days).toContain(w0.day)
  const walkable = w0.days.length >= 2                  // 这一族只有一个买点日时 ← / → 是换到旁边一族,不在这里验
  if (walkable) {
    expect(w0.noun).toBe('buys')
    expect(w0.n).toBe(w0.days.length)
    expect(w0.day).toBe(w0.days[w0.k! - 1])
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(200)
    const w1 = await walkAt()
    if (w0.k! < w0.n) {
      expect(w1.k).toBe(w0.k! + 1)
      expect(w1.day).toBe(w0.days[w0.k!])
      expect(famHits).toContain(w1.hit)
    }
    for (let i = 0; i < w0.n + 1; i++) await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(200)
    const w2 = await walkAt()
    expect(w2.k).toBe(w2.n)
    expect(w2.day).toBe(w2.days[w2.n - 1])
    expect(w2.outer).toBe('hit_family')
    expect(famHits).toContain(w2.hit)
  }

  // Esc 往外退一层:选中的还在这一族里,当前日与当家行都留着;退到头再按才清掉
  const depth = () => page.evaluate(() => (window as any).__e2e.view.selPath.length as number)
  const dayBefore = await page.evaluate(() => (window as any).__e2e.view.currentDay)
  const d0 = await depth()
  expect(d0).toBeGreaterThanOrEqual(2)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
  const d1 = await depth()
  expect(d1).toBeGreaterThan(0)
  expect(d1).toBeLessThan(d0)
  expect(await page.evaluate(() => (window as any).__e2e.view.currentDay)).toBe(dayBefore)
  expect(((await seriesData(page, 'chartSub', 'bracket-lines')) as any[]).filter((d) => d.active)).toHaveLength(1)
  for (let i = d1; i > 0; i--) await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
  expect(await depth()).toBe(0)
  expect(await page.evaluate(() => (window as any).__e2e.view.currentDay)).toBeNull()
  expect(await seriesData(page, 'chartSub', 'current-day')).toEqual([])
  expect(((await seriesData(page, 'chartSub', 'bracket-lines')) as any[]).some((d) => d.active)).toBe(false)
})

const clickSub = (page: Page, seriesName: string, data: any) =>
  page.evaluate(([n, d]) => { (window as any).__e2e.chartSub().trigger('click', { seriesName: n, data: d }) },
                [seriesName, data] as const)

/** 用真实挂载的 renderItem 画一条数据,取它的图元(fakeApi 只给坐标换算) */
const renderOf = (page: Page, seriesName: string, pick: (d: any) => boolean) =>
  page.evaluate(([n, src]) => {
    const s = (window as any).__e2e.chartSub().getOption().series.find((x: any) => x.name === n)
    const f = new Function('d', `return (${src})(d)`) as (d: any) => boolean
    const out: any[] = []
    s.data.forEach((d: any, i: number) => {
      if (!f(d)) return
      const api = { value: (k: number) => d.value[k], coord: ([x]: number[]) => [x * 10, 0], size: () => [10, 0] }
      out.push({ d, g: s.renderItem({ dataIndex: i }, api) })
    })
    return out
  }, [seriesName, pick.toString()] as const)

test('点一格:选中那个 event、选中框、当前日;点共用的阶跃格:选中的是这个 event、用到它的几次画实线细框', async ({ page }) => {
  test.setTimeout(300_000)
  test.skip(!(await openScan(page)), '这次小扫描里没有「同起点多次 hit」的股票')

  // 只属于一次 hit 的 plateau 格
  const one = await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const sub = (window as any).__e2e.chartSub()
    const recs = sub.getOption().series.find((x: any) => x.name === 'intervals').data
    const owners = (id: string) => view.effectiveAnalysis.hits.filter((m: any) => Object.values(m.node_index).includes(id))
    return recs.find((d: any) => d.family_key.startsWith('plateau@') && d.member_ids.length === 1
                                 && owners(d.member_ids[0]).length === 1) ?? null
  })
  expect(one).not.toBeNull()
  await clickSub(page, 'intervals', one)
  await page.waitForTimeout(300)
  const st = await page.evaluate(() => {
    const v = (window as any).__e2e.view
    return { hit: v.focusedHitId, inst: v.selectedInstanceId, day: v.currentDay, fam: v.activeFamilyKey,
             kinds: v.selPath.map((x: any) => x.kind), framed: [...v.candidateHitIds] }
  })
  // 点格选中的是格里的那个 event(它属于它那条 band);用到它的那一次 hit 不算选中,只画细框
  expect(st.kinds).toEqual(['node', 'event'])
  expect(st.hit).toBeNull()
  expect(st.inst).toBe(one.member_ids[0])
  expect(st.framed).toHaveLength(1)
  expect(st.day).toBe(one.value[1])
  // 选中 event 时哪一行的族底线都不加粗
  expect(st.fam).toBeNull()
  expect(((await seriesData(page, 'chartSub', 'family-lines')) as any[]).filter((d) => d.active)).toEqual([])
  const focusMarks = await renderOf(page, 'highlight',
    ((d: any) => d.kind === 'focus' && d.shape === 'mark') as any)
  expect(focusMarks.length).toBe(1)
  expect(focusMarks[0].d.instance_id).toBe(one.member_ids[0])
  const box = focusMarks[0].g.children?.at?.(-1) ?? focusMarks[0].g
  expect(box.style.fill).toBe('none')
  expect(box.style.stroke).toBe('#1e293b')

  // 被买入日不同的几次 hit 共用的阶跃格 → 选中的是这个 event,它牵出好几个买点日。先清掉选中(竖线也清掉),逐格点到这样的一格
  const steps: any[] = ((await seriesData(page, 'chartSub', 'intervals')) as any[])
    .filter((d) => d.family_key.startsWith('step@'))
  let cand: string[] = []
  let shared: any = null
  for (const rec of steps) {
    await page.evaluate(() => (window as any).__e2e.view.clearFocus())
    await clickSub(page, 'intervals', rec)
    cand = await page.evaluate(() => [...(window as any).__e2e.view.candidateHitIds] as string[])
    const slot = await page.evaluate(() => (window as any).__e2e.view.selInfo.day)
    if (cand.length >= 2 && slot.mode === 'into' && slot.n >= 2) { shared = rec; break }
  }
  expect(cand.length).toBeGreaterThanOrEqual(2)
  expect(shared).not.toBeNull()
  await page.waitForTimeout(300)
  // 选中的是这个 event:用到它的哪一次 hit 都不算选中;竖线落在它的终点;显示栏写它是什么、← / → 会进到几个买点日
  const cellVal = (id: string) => page.getByTestId(id).locator(':scope > :last-child')
  expect(await page.evaluate(() => (window as any).__e2e.view.selPath.map((x: any) => x.kind))).toEqual(['node', 'event'])
  expect(await page.evaluate(() => (window as any).__e2e.view.focusedHitId)).toBeNull()
  expect(await page.evaluate(() => (window as any).__e2e.view.currentDay)).toBe(shared.value[1])
  await expect(cellVal('sel-kind')).toHaveText('event')
  await expect(cellVal('sel-node')).toHaveText('step')
  await expect(cellVal('sel-day')).toHaveText(/^into buys ×\d+$/)
  // 竖线在别的日子上时点它:竖线照样落到它的终点,仍然哪一次 hit 都不选
  const off = shared.value[1] + 1
  await page.evaluate((d) => (window as any).__e2e.view.setCurrentDay(d), off)
  await clickSub(page, 'intervals', shared)
  await page.waitForTimeout(200)
  expect(await page.evaluate(() => (window as any).__e2e.view.currentDay)).toBe(shared.value[1])
  expect(await page.evaluate(() => (window as any).__e2e.view.focusedHitId)).toBeNull()
  await expect(cellVal('sel-day')).toHaveText(/^into buys ×\d+$/)
  const candMarks = await renderOf(page, 'brackets',
    ((d: any) => d.kind === 'mark') as any)
  const candBoxes = candMarks.filter((x: any) => x.d.hit_ids.some((id: string) => cand.includes(id)))
  expect(candBoxes.length).toBeGreaterThan(0)
  for (const { g } of candBoxes) {
    const last = g.children.at(-1)
    expect(last.style.lineDash).toBeUndefined()
    expect(last.style.fill).toBe('none')
    expect(g.children.some((c: any) => c.keyframeAnimation)).toBe(false)
  }
})

test('副图竖直放大:副图变高、主图变矮;族行数不变、行高按倍数变', async ({ page }) => {
  test.setTimeout(300_000)
  test.skip(!(await openScan(page)), '这次小扫描里没有「同起点多次 hit」的股票')
  await page.evaluate((key) => { try { localStorage.removeItem(key) } catch { /* noop */ } }, LS_KEY_BAND_ZOOM)
  // 放大倍数会存进 localStorage:先复位到 1.0×
  const reset = page.locator('.band-zoom-controls button[title*="复位"]')
  if (await reset.isEnabled()) await reset.click()
  await expect(page.locator('.band-zoom-readout')).toContainText('1.0×')

  const rows = async () => {
    const d = (await seriesData(page, 'chartSub', 'family-lines')) as any[]
    return { n: new Set(d.map((x) => `${x.value[3]}:${x.value[2]}`)).size, keys: new Set(d.map((x) => x.family_key)).size }
  }
  const laneH = async () => {
    const r = await renderOf(page, 'family-lines', ((d: any) => true) as any)
    return r[0].g.children[0].shape.height as number            // 透明命中区 = 一整行的高
  }
  const subInner = page.locator('.sub-inner')
  const mainChart = page.locator('.main-chart')
  const h0Sub = (await subInner.boundingBox())!.height
  const h0Main = (await mainChart.boundingBox())!.height
  const rows0 = await rows()
  const lane0 = await laneH()

  const plus = page.locator('.band-zoom-controls button[title*="放大"]')
  for (let i = 0; i < 5; i++) { await plus.click(); await page.waitForTimeout(150) }
  await expect(page.locator('.band-zoom-readout')).toContainText('2.0×')
  const h1Sub = (await subInner.boundingBox())!.height
  const h1Main = (await mainChart.boundingBox())!.height
  expect(h1Sub).toBeGreaterThan(h0Sub)
  expect(h1Main).toBeLessThan(h0Main)
  expect(await rows()).toEqual(rows0)
  expect(await laneH()).toBeCloseTo(lane0 * 2, 5)

  await reset.click()
  await expect(page.locator('.band-zoom-readout')).toContainText('1.0×')
})
