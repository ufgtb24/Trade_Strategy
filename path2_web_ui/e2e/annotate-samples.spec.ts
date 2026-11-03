import { test, expect, type Page } from '@playwright/test'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  annState, barCount, boxesOf, drag, drawOnKline, klineY, laneY, name, openSymbol, routeTo, settled, startBackend,
  stopBackend, xOf, type Backend,
} from './annotateHelpers'

/**
 * 放样本与成员框(annotate):
 * 1. 放样本,它自动收进之前离得近的一串框,刷新后成员框不变;跨过样本日的框收不进,在 others 里变灰、成员链上
 *    留一个注明原因的空槽;拖框边停在样本日,鼠标旁写它是哪个样本的成员框;当前样本期间新画的框并进它,
 *    换掉当前样本以后再补画的框不并进旧样本;手动点进点出(样本页、框页的 member_of);别的 pattern 的样本在
 *    member_of 里只读;不越界地改起止、删样本照常保存。
 * 2. 后端拒绝保存(另一台机器同步来的修改让一个框成了样本的成员框,本页不知道就把它拖过了样本日):
 *    界面写出原因、涉及的框与样本,并重读出后端眼下的状态;框还在,再拖就停在样本日。
 *
 * 标注会写批次文件,绝不能写进用户的标注目录:后端与转发见 ./annotateHelpers.ts。
 */

const e2e = (page: Page, fn: string) => page.evaluate(f => (window as any).__e2e.ann()[f], fn)
const chartOfState = (st: any, symbol: string) => st.charts.find((c: any) => c.symbol === symbol)
const samplesOf = (st: any, symbol: string) => chartOfState(st, symbol)?.samples ?? []

/** 样本日那根 K 线下方三角的中心(页面坐标)。 */
async function trianglePos(page: Page, i: number): Promise<[number, number]> {
  return page.evaluate((i) => {
    const main = (window as any).__e2e.chartMain()
    const low = main.getOption().series.find((s: any) => s.type === 'candlestick').data[i][2]
    const [x, y] = main.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [i, low])
    const r = document.querySelector('.main-chart')!.getBoundingClientRect()
    return [r.left + x, r.top + y + 12] as [number, number]
  }, i)
}

/** 副图某条特征轨上,下标 i 那根 K 线右边沿的页面坐标 x(拖框右边用)。 */
async function rightEdgeX(page: Page, i: number): Promise<number> {
  const a = await xOf(page, i, 'sub'), b = await xOf(page, i + 1, 'sub')
  return a + (b - a) / 2
}

async function placeAt(page: Page, i: number) {
  await page.getByTestId('tool-point').click()
  await page.mouse.click(await xOf(page, i), await klineY(page))
  await expect(page.getByTestId('sample-panel')).toBeVisible()
  await expect(page.getByTestId('tool-box')).toHaveClass(/on/)            // 放完自动回到 box
}

async function newPattern(page: Page, text: string) {
  await page.getByTestId('top-pattern-button').click()
  await page.getByTestId('top-pattern-new').click()
  await page.getByTestId('top-pattern-new-input').fill(text)
  await page.getByTestId('top-pattern-new-input').press('Enter')
  await expect(page.getByTestId('top-pattern-button')).toContainText(text)
}

async function pickPattern(page: Page, text: string | null) {
  await page.getByTestId('top-pattern-button').click()
  if (text === null) await page.getByTestId('top-pattern-unsorted').click()
  else await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
}

/** 在 K 线区空白处点一下(不拖):什么都不选,当前样本清掉。 */
async function clickBlank(page: Page, i: number) {
  await page.mouse.click(await xOf(page, i), await klineY(page))
  await expect.poll(() => e2e(page, 'currentSampleId')).toBeNull()
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('放样本与成员框', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => { backend = await startBackend() })
  test.afterAll(() => stopBackend(backend))

  test('自动收进之前的框、刷新不变;跨过样本日收不进;拖框边停在样本日;换掉当前样本后冻结;手动点进点出', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const A = symbols[Math.floor(symbols.length / 3)]
    await page.goto('/')
    await openSymbol(page, A)
    const n = await barCount(page)
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)

    // ── 先画三个框:横盘、突破在样本日之前;第二个横盘跨过样本日 ──
    const b1 = await drawOnKline(page, n - 80, n - 60)
    await name(page, '横盘')
    const b2 = await drawOnKline(page, n - 50, n - 45)
    await name(page, '突破')
    const b3 = await drawOnKline(page, n - 35, n - 25)
    await page.getByTestId('suggest-横盘').click()
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')

    // ── 新起一个 pattern,point 点在 n-30 放样本 ──
    await newPattern(page, 'W底')
    await placeAt(page, n - 30)
    await expect(page.getByTestId('sample-head')).toHaveText(`a · ${dates[n - 30]}`)
    await settled(page)
    let st = await annState(page)
    const [smp] = samplesOf(st, A)
    expect(smp).toMatchObject({ date: dates[n - 30], pattern: 'W底', judgment: 'pos', members: [b1, b2] })
    // 跨过样本日的框收不进:others 里变灰,成员链上留一个注明原因的空槽
    await expect(page.locator(`[data-testid="other-chip"][data-box="${b3}"]`)).toHaveAttribute('data-cross', '1')
    await expect(page.locator(`[data-testid="other-chip"][data-box="${b3}"]`)).toHaveAttribute('title', /crosses sample date/)
    const slot = page.locator(`[data-testid="member-slot"][data-box="${b3}"]`)
    await expect(slot).toHaveAttribute('data-reason', 'crosses_sample_date')
    await expect(slot).toHaveAttribute('title', /crosses sample date/)
    await page.locator(`[data-testid="other-chip"][data-box="${b3}"]`).click({ force: true })
    await settled(page)
    expect(samplesOf(await annState(page), A)[0].members).toEqual([b1, b2])     // 点了也收不进
    // 图上:三角、暗一档、bracket 轨
    const mainSeries = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().series
      .filter((s: any) => s.type === 'custom').map((s: any) => ({ name: s.name, data: s.data })))
    expect(mainSeries.find((s: any) => s.name === 'annotation-samples').data).toEqual([[n - 30, expect.any(Number)]])
    expect(mainSeries.find((s: any) => s.name === 'annotation-after-dim').data).toEqual([[n - 29, n - 1]])
    await laneY(page, 'bracket')
    await page.screenshot({ path: testInfo.outputPath('01-sample-placed.png'), fullPage: true })

    // ── 刷新:样本和它的成员框不变 ──
    await page.reload()
    await openSymbol(page, A)
    expect(samplesOf(await annState(page), A)).toEqual(samplesOf(st, A))
    await expect(page.getByTestId('top-pattern-button')).toContainText('W底')    // 当前 pattern 记在浏览器里
    const [tx, ty] = await trianglePos(page, n - 30)
    await page.mouse.click(tx, ty)                                             // 点三角 → 选中样本
    await expect(page.getByTestId('sample-panel')).toBeVisible()
    await expect(page.locator('[data-testid="member-chip"]')).toHaveCount(2)

    // ── 拖「突破」的右边越过样本日:停在样本日,鼠标旁写它是哪个样本的成员框 ──
    const yBreak = await laneY(page, '突破')
    await page.mouse.move(await rightEdgeX(page, n - 45), yBreak)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, n - 35, 'sub'), yBreak, { steps: 4 })
    await page.mouse.move(await xOf(page, n - 20, 'sub'), yBreak, { steps: 4 })
    await expect(page.getByTestId('resize-stop')).toHaveText(`member box of a ▲ ${dates[n - 30]}`)
    await page.screenshot({ path: testInfo.outputPath('02-resize-stops.png'), fullPage: true })
    await page.mouse.up()
    await expect(page.getByTestId('resize-stop')).toHaveCount(0)
    await settled(page)
    expect(boxesOf(await annState(page), A).find((b: any) => b.id === b2).end).toBe(dates[n - 30])
    // 不越界地改起止照常保存
    await drag(page, await rightEdgeX(page, n - 30), yBreak, await xOf(page, n - 40, 'sub'), yBreak)
    await settled(page)
    expect(boxesOf(await annState(page), A).find((b: any) => b.id === b2).end).toBe(dates[n - 40])
    expect(await e2e(page, 'saveError')).toBeNull()

    // ── 当前样本期间新画的框并进它;选中框时顶上一条当前样本的成员链 ──
    await page.mouse.click(tx, ty)
    const b4 = await drawOnKline(page, n - 33, n - 32)
    await expect(page.getByTestId('current-sample')).toBeVisible()
    await settled(page)
    expect(samplesOf(await annState(page), A)[0].members).toEqual([b1, b2, b4])

    // ── 换掉当前样本(点空白处)后冻结:再补画的框不并进旧样本 ──
    await clickBlank(page, n - 5)
    const b5 = await drawOnKline(page, n - 37, n - 36)
    await settled(page)
    expect(samplesOf(await annState(page), A)[0].members).toEqual([b1, b2, b4])
    await expect(page.getByTestId('current-sample')).toHaveCount(0)

    // ── 手动点进点出:样本页 others 点进、成员链点出(记 members_edited)──
    await page.mouse.click(tx, ty)
    await page.locator(`[data-testid="other-chip"][data-box="${b5}"]`).click()
    await settled(page)
    expect(samplesOf(await annState(page), A)[0]).toMatchObject({ members: [b1, b2, b5, b4], members_edited: true })
    await page.locator(`[data-testid="member-chip"][data-box="${b5}"]`).click()
    await settled(page)
    expect(samplesOf(await annState(page), A)[0].members).toEqual([b1, b2, b4])
    await page.screenshot({ path: testInfo.outputPath('03-sample-panel.png'), fullPage: true })

    // ── 框页的 member_of:点掉、点上;别的 pattern 的样本只读 ──
    const sid = samplesOf(await annState(page), A)[0].id
    await pickPattern(page, null)                         // unsorted
    await placeAt(page, n - 10)                           // 这个 unsorted 样本会收进 b3
    await settled(page)
    const other = samplesOf(await annState(page), A).find((s: any) => s.pattern === null)
    expect(other.members).toContain(b3)
    await pickPattern(page, 'W底')
    await page.mouse.click(await xOf(page, n - 70, 'sub'), await laneY(page, '横盘'))
    await expect(page.getByTestId('box-panel')).toBeVisible()
    const row = page.getByTestId(`member-of-${sid}`)
    await expect(row).toHaveAttribute('data-state', 'member')
    await row.click()
    await expect(row).toHaveAttribute('data-state', 'open')
    await settled(page)
    expect(samplesOf(await annState(page), A).find((s: any) => s.id === sid).members).toEqual([b2, b4])
    await row.click()
    await settled(page)
    expect(samplesOf(await annState(page), A).find((s: any) => s.id === sid).members).toEqual([b1, b2, b4])
    // b3:跨过 W底 样本的样本日(灰、点不了);被 unsorted 样本收进(只读)
    await page.mouse.click(await xOf(page, n - 30, 'sub'), await laneY(page, '横盘'))
    await expect(page.getByTestId('box-span')).toHaveText(`${dates[n - 35]} – ${dates[n - 25]}`)
    await expect(page.getByTestId(`member-of-${sid}`)).toHaveAttribute('data-state', 'crosses')
    await expect(page.getByTestId(`member-of-${sid}`)).toBeDisabled()
    await expect(page.getByTestId(`member-of-${other.id}`)).toHaveAttribute('data-state', 'member')
    await expect(page.getByTestId(`member-of-${other.id}`)).toBeDisabled()
    await page.screenshot({ path: testInfo.outputPath('04-member-of.png'), fullPage: true })

    // ── 负样本:空心三角;删样本照常保存 ──
    const [ox, oy] = await trianglePos(page, n - 10)
    await page.mouse.click(ox, oy)
    await page.getByTestId('sample-judgment-neg').click()
    await expect(page.getByTestId('sample-pattern-button')).toContainText('pattern?')   // 负样本挂在 unsorted:待选
    await settled(page)
    await pickPattern(page, null)                         // 当前 pattern 换成 unsorted:空心三角不画淡,实心的画淡
    await page.screenshot({ path: testInfo.outputPath('05-neg-sample.png'), fullPage: true })
    await page.getByTestId('sample-delete').click()
    await settled(page)
    st = await annState(page)
    expect(samplesOf(st, A).map((s: any) => s.id)).toEqual([sid])
    expect(await e2e(page, 'saveError')).toBeNull()
  })
})

test.describe('保存被拒', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => { backend = await startBackend() })
  test.afterAll(() => stopBackend(backend))

  test('另一台机器同步来的修改让本页的改动越界:界面写出原因,重读后框还在,再拖就停在样本日', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const A = symbols[Math.floor(symbols.length / 3) + 1]
    await page.goto('/')
    await openSymbol(page, A)
    const n = await barCount(page)
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)

    const bx = await drawOnKline(page, n - 60, n - 50)
    await name(page, '横盘')
    await placeAt(page, n - 30)
    await clickBlank(page, n - 5)
    const by = await drawOnKline(page, n - 45, n - 40)
    await name(page, '回踩')
    await settled(page)
    const read = await (await fetch(`${backend!.base}/annotations`)).json()
    const smp = samplesOf(read.state, A)[0]
    expect(smp.members).toEqual([bx])

    // 另一台机器(upc)把 by 也收进了这个样本,文件同步到标注目录;本页还不知道
    const dir = join(backend!.root, 'annotations')
    const anyBatch = JSON.parse(readFileSync(join(dir, readdirSync(dir).find(f => f.endsWith('.json'))!), 'utf8'))
    const ts = new Date(Date.now() + 1000).toISOString().replace(/[-:]/g, '').replace(/(\d{8}T\d{6})\.(\d{3})Z/, '$1.$2Z')
    writeFileSync(join(dir, `upc-${ts}-1.json`), JSON.stringify({
      schema: anyBatch.schema, data_fingerprint: anyBatch.data_fingerprint,
      ops: [{ ts, machine: 'upc', kind: 'sample', id: smp.id, base: read.revs.sample[smp.id],
              value: { ...smp, symbol: A, members: [bx, by] } }],
    }))

    // 本页把 by 的右边拖过样本日(本页以为它不是成员框,不拦)→ 后端拒绝
    const yLane = await laneY(page, '回踩')
    await drag(page, await rightEdgeX(page, n - 40), yLane, await xOf(page, n - 20, 'sub'), yLane)
    await settled(page)
    const notice = page.getByTestId('notice-save')
    await expect(notice).toContainText('rejected')
    const reason = page.getByTestId('notice-save-reason')
    await expect(reason).toContainText('box_crosses_sample_date')
    await expect(reason).toContainText('回踩')
    await expect(reason).toContainText(`${dates[n - 45]} – ${dates[n - 40]}`)
    await expect(reason).toContainText(`a ▲ ${dates[n - 30]}`)
    await page.screenshot({ path: testInfo.outputPath('06-save-rejected.png'), fullPage: true })
    // 重读后:本页显示的是后端眼下的状态,框还在、没被改
    const st = await annState(page)
    expect(boxesOf(st, A).find((b: any) => b.id === by)).toMatchObject({ start: dates[n - 45], end: dates[n - 40] })
    expect(samplesOf(st, A)[0].members).toEqual([bx, by])
    // 提示点 ok 收起;再拖就停在样本日
    await notice.getByRole('button', { name: 'ok' }).click()
    await expect(notice).toHaveCount(0)
    await page.mouse.move(await rightEdgeX(page, n - 40), yLane)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, n - 20, 'sub'), yLane, { steps: 6 })
    await expect(page.getByTestId('resize-stop')).toContainText(dates[n - 30])
    await page.mouse.up()
    await settled(page)
    expect(boxesOf(await annState(page), A).find((b: any) => b.id === by).end).toBe(dates[n - 30])
    await expect(notice).toHaveCount(0)
  })
})
