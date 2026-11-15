import { test, expect, type Page } from '@playwright/test'
import { deleteSmallScan, openSmallScan, runSmallScan, smallScanName } from './smallScan'

/**
 * 侧栏与图的选中联动(真浏览器):
 * 1. 侧栏 hits 列表点一行 = 选中这次 hit:只这一行黑粗边、左蓝条;图上 hits 行的粗框落在它竖线那天的格位,
 *    外层(它那一族)一行底线;它的 trace 展开;
 * 2. 点 ▼ 选中叠着几次的那一天:这天几行黑粗边(相邻的连成一块),蓝条只挂 ↓ 第一个那行;图上粗框在那个 ▼;
 *    ↓ 进到其中一次后只剩那一行黑粗边、蓝条;
 * 3. 图上点一个格(选中格里那个 event):hits 列表上它牵出的行挂蓝条、没有黑粗边,hits 行上没有粗框;
 *    → 走进它牵出的买点日后,它退到外层(候选表不再当它是选中的),这天的行黑粗边,粗框在那个 ▼。
 *
 * 夹具:new_step 小扫描(./smallScan.ts),整个文件共用一次,结束删掉。
 */

test.use({ viewport: { width: 2560, height: 1440 } })

const SCAN_NAME = smallScanName('sidebar_chart_focus')
test.beforeAll(async () => { await runSmallScan(SCAN_NAME) })
test.afterAll(async () => { await deleteSmallScan(SCAN_NAME) })

/** 打开小扫描,换到同一天叠着几次 hit 最多的那只股票;返回那一族与那一天(没有叠着的为 null)。 */
async function openScan(page: Page): Promise<{ familyKey: string; day: number } | null> {
  await openSmallScan(page, SCAN_NAME)
  await page.waitForFunction(() => !!(window as any).__e2e?.view)
  const sym = await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const pid = view.activePatternId
    let best: { sym: string; n: number } | null = null
    for (const r of view.scanFile.results) {
      const hits = r.per_pattern?.[pid]?.analysis?.hits ?? []
      const byDay = new Map<string, number>()
      for (const m of hits) byDay.set(`${m.start_idx}|${m.end_idx}`, (byDay.get(`${m.start_idx}|${m.end_idx}`) ?? 0) + 1)
      const n = Math.max(0, ...byDay.values())
      if (!best || n > best.n) best = { sym: r.symbol, n }
    }
    if (best) view.selectSymbol(best.sym)
    return best?.sym ?? null
  })
  expect(sym).not.toBeNull()
  // 右侧诊断侧栏默认收着(开关存在 localStorage):打开它
  const toggle = page.getByTestId('panel-toggle-sidebar')
  if (!/\bactive\b/.test((await toggle.getAttribute('class')) ?? '')) await toggle.click()
  await expect(toggle).toHaveClass(/\bactive\b/)
  await page.waitForFunction(() => {
    const s = (window as any).__e2e.chartSub()?.getOption()?.series?.find((x: any) => x.name === 'brackets')
    return !!s && s.data.length > 0
  }, null, { timeout: 30_000 })
  return page.evaluate(() => {
    const s = (window as any).__e2e.chartSub().getOption().series.find((x: any) => x.name === 'brackets')
    const d = s.data.find((x: any) => x.kind === 'buy' && x.hit_ids.length >= 2)
    return d ? { familyKey: d.family_key as string, day: d.buy_day as number } : null
  })
}

const seriesData = (page: Page, name: string) =>
  page.evaluate((n) => (window as any).__e2e.chartSub().getOption().series.find((x: any) => x.name === n)?.data ?? null, name)

/** 侧栏 hits 列表各行:编号、黑粗边、左蓝条 */
const rowLooks = (page: Page) => page.locator('.hit-row').evaluateAll(els => els.map(e => ({
  id: e.getAttribute('data-hit-id'), framed: e.classList.contains('hit-row--current'),
  led: e.classList.contains('hit-row--batch'),
})))
const kinds = (page: Page) => page.evaluate(() => (window as any).__e2e.view.selPath.map((x: any) => x.kind) as string[])
/** 图上 hits 行的粗框:[族, 格位那天] */
const hitFrames = async (page: Page) => ((await seriesData(page, 'selection')) as any[])
  .filter((d) => d.kind === 'frame' && d.target === 'hits').map((d) => [d.family_key, d.buy_day ?? null])

test('侧栏 hits 列表点一行:选中这次 hit,只这一行黑粗边、蓝条;图上粗框在它那一格位,一族一行底线', async ({ page }) => {
  test.setTimeout(300_000)
  await openScan(page)
  const rows = page.locator('.hit-row')
  await expect(rows.first()).toBeVisible({ timeout: 15_000 })
  const target = await rows.last().getAttribute('data-hit-id')
  await rows.last().click()
  await expect.poll(() => kinds(page)).toEqual(['hit_family', 'buy', 'hit'])
  expect(await page.evaluate(() => (window as any).__e2e.view.focusedHitId)).toBe(target)
  await expect(page.locator('.hit-trace')).toBeVisible()
  const looks = await rowLooks(page)
  expect(looks.filter(r => r.framed).map(r => r.id)).toEqual([target])
  expect(looks.filter(r => r.led).map(r => r.id)).toEqual([target])
  const st = await page.evaluate(() => {
    const v = (window as any).__e2e.view
    return { fam: v.selPath[0].familyKey as string, day: v.currentDay as number }
  })
  expect(await hitFrames(page)).toEqual([[st.fam, st.day]])
  const unders = ((await seriesData(page, 'selection')) as any[])
    .filter((d) => d.kind === 'under' && d.target === 'hits' && d.buy_day === undefined).map((d) => d.family_key)
  expect(unders).toEqual([st.fam])
})

test('点 ▼ 选中叠着几次的那一天:这天几行黑粗边、蓝条只挂 ↓ 第一个;↓ 进到其中一次只剩那一行', async ({ page }) => {
  test.setTimeout(300_000)
  const stacked = await openScan(page)
  test.skip(!stacked, '这次小扫描里没有同一天叠着几次 hit 的股票')
  await page.evaluate(([f, d]) => (window as any).__e2e.view.clickBuyDay(f, d), [stacked!.familyKey, stacked!.day] as const)
  await expect.poll(() => kinds(page)).toEqual(['hit_family', 'buy'])
  const dayHits: string[] = await page.evaluate(() => (window as any).__e2e.view.selDayHitIds)
  expect(dayHits.length).toBeGreaterThanOrEqual(2)
  let looks = await rowLooks(page)
  expect(looks.filter(r => r.framed).map(r => r.id).sort()).toEqual([...dayHits].sort())
  expect(looks.filter(r => r.led).map(r => r.id)).toEqual([dayHits[0]])
  expect(await hitFrames(page)).toEqual([[stacked!.familyKey, stacked!.day]])

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('ArrowDown')
  await expect.poll(() => kinds(page)).toEqual(['hit_family', 'buy', 'hit'])
  looks = await rowLooks(page)
  expect(looks.filter(r => r.framed).map(r => r.id)).toEqual([dayHits[0]])
  expect(looks.filter(r => r.led).map(r => r.id)).toEqual([dayHits[0]])
})

test('图上点一格:hits 列表上它牵出的行挂蓝条、没有黑粗边;→ 走进买点日后这天的行黑粗边', async ({ page }) => {
  test.setTimeout(300_000)
  await openScan(page)
  // 一个格,选中它以后 ← / → 会进到它牵出的买点日(没进 hit、或只牵出一天而 band 上又有别的格时 → 是换到旁边一格):
  // 逐格点到这样的一格。(new_step 的 node 全是孤立轨,节点漏斗不给它们展开候选表,候选表的选中行由 vitest 覆盖)
  const cands: any[] = await page.evaluate(() =>
    (window as any).__e2e.chartSub().getOption().series.find((x: any) => x.name === 'intervals').data)
  let rec: any = null
  for (const d of cands) {
    await page.evaluate(() => (window as any).__e2e.view.clearFocus())
    await page.evaluate((x) => (window as any).__e2e.chartSub().trigger('click', { seriesName: 'intervals', data: x }), d)
    if (await page.evaluate(() => {
      const v = (window as any).__e2e.view
      return v.selInfo?.day?.mode === 'into' && v.selInfo?.day?.noun === 'buys'
    })) { rec = d; break }
  }
  expect(rec).not.toBeNull()
  await expect.poll(() => kinds(page)).toEqual(['event'])
  expect(await page.evaluate(() => (window as any).__e2e.view.selectedInstanceId)).toBe(rec.member_ids[0])
  const led: string[] = await page.evaluate(() => [...(window as any).__e2e.view.highlight.ledHits])
  expect(led.length).toBeGreaterThan(0)
  const looks = await rowLooks(page)
  expect(looks.filter(r => r.framed)).toEqual([])                       // event 不由 hit 组成:没有黑粗边
  expect(looks.filter(r => r.led).map(r => r.id).sort()).toEqual([...led].sort())
  expect(await hitFrames(page)).toEqual([])                              // 粗框在 band 上它那一格,不在 hits 行

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => kinds(page)).toEqual(['event', 'buy'])
  expect(await page.evaluate(() => (window as any).__e2e.view.markedEventIds.size)).toBe(0)   // 它退到外层
  // 这天的几次(只有一次时这天就是那次 hit)黑粗边
  const dayHits: string[] = await page.evaluate(() => {
    const v = (window as any).__e2e.view
    return v.world.members(v.selPath).map((x: any) => x.sel.hitId)
  })
  expect(dayHits.length).toBeGreaterThan(0)
  expect((await rowLooks(page)).filter(r => r.framed).map(r => r.id).sort()).toEqual([...dayHits].sort())
  const day = await page.evaluate(() => (window as any).__e2e.view.currentDay)
  expect((await hitFrames(page)).map(([, d]) => d)).toEqual([day])
})
