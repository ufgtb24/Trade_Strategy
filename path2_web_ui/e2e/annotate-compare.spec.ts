import { test, expect, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, TRAIN_END, lanes, routeTo, startBackend, stopBackend, type Backend } from './annotateHelpers'

/**
 * 顶栏 mode 的 compare / app(第一段:只叠画、不挂对照 tag):
 * 1. 用现成的 app bo_only 加一份手写的 mapping(pattern W底:突破 → bo、横盘 → pk;e2e 后端从临时目录读它,
 *    见 e2e/annotationBackend.py):没有 mapping 的 pattern 下 compare、app 是灰的;W底 下切到 compare,
 *    app 的每个 event 出现在它对的那个特征的轨上、每个 hit 出现在 bracket 轨上,数目与后端 /preview 给的一致;
 *    图上没有任何对照 tag;app 的全部输出都落在截到 2025-12-31 的 K 线里;参照层 peaks 在 compare 下照样能开。
 *    再切到 app:按 node 分轨的主视图画法,参照层自动关。
 * 2. compare 下换股票不退出 compare:pattern 页的样本卡、代码输入、random、rally 都留在 compare,app 对新股票重跑;
 *    链接一律落在 annotate。从扫描结果的 app 出发用 rally、random 落在 annotate,由 e2e/annotate-rally-random.spec.ts 验。
 *
 * 标注用 tests/path2_web/fixtures/annotation_grouping_v1 的例子批次(指纹换成测试后端本机副本的),写在临时目录里。
 * 整页截图挂在测试结果里(compare-*.png、app-*.png)。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nfeatures:\n  w-pc-3: bo\n  w-pc-1: pk\n'
const LANE_OF: Record<string, string> = { bo: '突破', pk: '横盘' }
const NAMES = ['annotation-boxes', 'annotation-brackets', 'compare-events', 'compare-tier-tags', 'compare-hits']
const TAG_WORDS = ['missing', 'matched', 'unmatched', 'connected', 'disconnected', 'not_qualified',
                   'unmapped', 'excluded', 'optional', 'must_not', 'chance_high', 'remapped']

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
/** 现算的 app 是对哪只股票跑的(还没跑完为 null)。 */
const runSymbol = (page: Page) => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null)

async function pickPattern(page: Page, text: string | null) {
  await page.getByTestId('top-pattern-button').click()
  if (text === null) await page.getByTestId('top-pattern-unsorted').click()
  else await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().currentPattern)).toBe(text)
}

async function waitChart(page: Page, symbol: string) {
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
}

/** 副图某个系列的数据行。 */
const subRows = (page: Page, name: string) => page.evaluate(n =>
  ((window as any).__e2e.chartSub().getOption().series ?? []).find((s: any) => s.name === n)?.data ?? null, name)

/** 后端对这只股票跑 bo_only 的输出(和页面跑的同一个请求)。 */
async function preview(b: Backend, symbol: string) {
  const r = await fetch(`${b.base}/preview?pattern_id=bo_only&symbol=${symbol}&start=1900-01-01&end=${TRAIN_END}&label_horizon=20`)
  return (await r.json()).analysis as { events: any[]; matches: any[] }
}

/** 副图轨的上沿(按轨标题),从上到下:{ text, top }。轨标题在轨顶内侧 4 像素处。 */
const laneTops = (page: Page) => page.evaluate(() => {
  const opt = (window as any).__e2e.chartSub().getOption()
  return (opt.graphic?.[0]?.elements ?? []).filter((e: any) => e.type === 'text')
    .map((e: any) => ({ text: String(e.style?.text ?? '').replace(/\{(biz|sym)\|([^}]*)\}/g, '$2'), top: e.top - 4 }))
    .sort((a: any, b: any) => a.top - b.top)
})
const laneAtY = (tops: { text: string; top: number }[], y: number) => [...tops].reverse().find(t => t.top <= y)?.text ?? null

async function enterCompare(page: Page) {
  await page.getByTestId('mode-compare').click()
  await expect.poll(() => view(page, 'mode')).toBe('compare')
  await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('compare / app 叠画(bo_only + 手写 mapping)', () => {
  test.setTimeout(600_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    backend = await startBackend(undefined, { bo_only: MAPPING })
    await putFixture(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('event 在对应特征的轨上、hit 在 bracket 轨上,没有对照 tag,不越过 2025-12-31;没有 mapping 的 pattern 下 compare 是灰的', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await expect(page.getByTestId('mode-annotate')).toHaveClass(/\bon\b/)

    // 没有 mapping 的 pattern(unsorted、旗形):compare、app 变灰
    for (const p of [null, '旗形']) {
      await pickPattern(page, p)
      await expect(page.getByTestId('mode-compare')).toBeDisabled()
      await expect(page.getByTestId('mode-app')).toBeDisabled()
    }
    await pickPattern(page, 'W底')
    await expect(page.getByTestId('mode-compare')).toBeEnabled()
    const mainNamesBefore = await page.evaluate(() =>
      (window as any).__e2e.chartMain().getOption().series.map((s: any) => s.name))
    await enterCompare(page)
    await expect(page.getByTestId('linked-app')).toHaveText('bo_only')

    const out = await preview(backend!, 'AAPL')
    expect(out.events.length).toBeGreaterThan(0)
    expect(out.matches.length).toBeGreaterThan(0)
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    expect(dates.at(-1)).toBe(TRAIN_END)

    // event:每个都在它的 node 对的那个特征的轨上
    const evRows: number[][] = await subRows(page, 'compare-events')
    const tops = await laneTops(page)
    const got = evRows.map(r => `${r[0]}-${r[1]}@${laneAtY(tops, r[2])}`).sort()
    const want = out.events.map(e => `${e.start_idx}-${e.end_idx}@${LANE_OF[e.node_id]}`).sort()
    expect(got).toEqual(want)
    // hit:都在 bracket 轨上(第一条特征轨之上)
    const hitRows: number[][] = await subRows(page, 'compare-hits')
    expect(hitRows.map(r => `${r[0]}-${r[1]}`).sort()).toEqual(out.matches.map(m => `${m.start_idx}-${m.end_idx}`).sort())
    for (const r of hitRows) expect(laneAtY(tops, r[2])).toBe('bracket')
    // 数据墙:全部输出都在截到训练段末日的 K 线里
    for (const r of [...evRows, ...hitRows]) {
      expect(r[1]).toBeLessThan(dates.length)
      expect(dates[r[1]] <= TRAIN_END).toBe(true)
    }

    // 没有对照 tag:副图只多出 event、tier tag、hit 三个系列;轨标题、bracket 外没有别的字;主图不变
    const sub = await page.evaluate(() => {
      const o = (window as any).__e2e.chartSub().getOption()
      return { names: o.series.map((s: any) => s.name), graphic: JSON.stringify(o.graphic ?? []) }
    })
    expect(sub.names).toEqual(NAMES)
    for (const w of TAG_WORDS) expect(sub.graphic).not.toContain(w)
    expect(await page.evaluate(() => (window as any).__e2e.chartMain().getOption().series.map((s: any) => s.name)))
      .toEqual(mainNamesBefore)
    expect((await lanes(page)).map(l => l.text)).toEqual(['bracket', '横盘', '缩量 ⊂ 横盘', '突破', '派发'])

    // 参照层 peaks 在 compare 下可用:勾上画出峰线(同 /peaks)
    const box = page.getByTestId('ref-peaks')
    await expect(box).toBeEnabled()
    await box.check()
    const peaks = await (await fetch(`${backend!.base}/peaks?symbol=AAPL`)).json()
    expect(peaks.length).toBeGreaterThan(0)
    await expect.poll(() => page.evaluate(() => ((window as any).__e2e.chartMain().getOption().series
      .find((s: any) => s.name === 'ref-peaks')?.data ?? []).length)).toBe(peaks.length)

    // 图窗拉到第一个 hit 附近截图
    const h0 = Math.min(...hitRows.map(r => r[0]))
    await page.evaluate(([i, n]) => (window as any).__e2e.chartMain().dispatchAction(
      { type: 'dataZoom', start: Math.max(0, i - 90) / n * 100, end: Math.min(n, i + 40) / n * 100 }), [h0, dates.length])
    await page.screenshot({ path: testInfo.outputPath('compare-AAPL.png'), fullPage: true })

    // app:按 node 分轨的主视图画法,app 名、档位与 tiers 都在;hit 画成主视图的 bracket
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await expect(page.getByTestId('linked-app')).toHaveText('bo_only')
    await expect(page.getByTestId('level-control')).toBeVisible()
    await expect(page.getByTestId('tiers')).toBeEnabled()
    await expect(box).not.toBeChecked()                                    // 参照层切到 app 自动关、不能勾
    await expect(box).toBeDisabled()
    await expect.poll(async () => (await subRows(page, 'brackets'))?.length ?? -1).toBe(out.matches.length)
    await page.screenshot({ path: testInfo.outputPath('app-AAPL.png'), fullPage: true })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('compare 下用样本卡、代码输入、random、rally 换股票不退出 compare;链接进来落在 annotate', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await pickPattern(page, 'W底')
    await enterCompare(page)

    // pattern 页点 MSFT 的样本卡:留在 compare,app 对 MSFT 重跑
    await page.getByTestId('annotation-tab-pattern').click()
    await page.locator('[data-testid="sample-card"][data-sample="s-pc-21"]').first().click()
    await waitChart(page, 'MSFT')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe('MSFT')
    const out = await preview(backend!, 'MSFT')
    await expect.poll(async () => (await subRows(page, 'compare-events'))?.length ?? -1).toBe(out.events.length)
    await page.screenshot({ path: testInfo.outputPath('compare-MSFT-from-sample-card.png'), fullPage: true })

    // 代码输入、random、rally:换了股票,仍在 compare,app 对新股票重跑
    await page.getByTestId('symbol-input').fill('NVDA')
    await page.getByTestId('symbol-input').press('Enter')
    await waitChart(page, 'NVDA')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe('NVDA')
    await page.getByTestId('random-button').click()
    await expect.poll(() => view(page, 'symbol'), { timeout: 120_000 }).not.toBe('NVDA')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(async () => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
    await page.getByTestId('rally-button').click()
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    const before = await view(page, 'symbol')
    const row = page.locator(`[data-testid="rally-row"]:not([data-symbol="${before}"])`).first()
    await row.click()
    await expect.poll(() => view(page, 'symbol')).not.toBe(before)
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(async () => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
    // 两种链接:落在 annotate
    for (const link of ['#symbol=AAPL&date=2024-03-11', '#sample=s-pc-21']) {
      await enterCompare(page)
      await page.evaluate(h => { location.hash = h }, link)
      await expect.poll(() => view(page, 'mode')).toBe('annotate')
      await waitChart(page, link.includes('AAPL') ? 'AAPL' : 'MSFT')
    }
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})
