import { test, expect, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, TRAIN_END, routeTo, startBackend, stopBackend, type Backend } from './annotateHelpers'

/**
 * 直达链接(格式见 src/annotate/directLinks.ts):
 * 1. 股票 + 日期 #symbol=…&date=…:新开的页带着它,打开那只股票、图窗停在那天附近、落在 annotate;页面在 app 下时
 *    地址的 # 部分换成另一个,同样落在 annotate;日期写 2026-03-01 的,看得见的和图上的最后一根 K 线都不晚于 2025-12-31。
 * 2. 样本编号 #sample=…:新开的页带着它,等标注读完,打开样本所在的图并选中它;换一个编号照样跳过去;
 *    编号不存在、写法认不出时,提示条写明,点 ok 收起。
 *
 * 标注用一份固定的例子(tests/path2_web/fixtures/annotation_grouping_v1,标注存储的批次文件),由测试自己起的
 * 后端读(标注目录在系统临时目录,见 ./annotateHelpers.ts),不碰用户的标注目录。整页截图挂在测试结果里。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

const e2e = (page: Page, f: string) => page.evaluate(k => (window as any).__e2e.ann()[k], f)
const viewOf = (page: Page, f: string) => page.evaluate(k => (window as any).__e2e.view[k], f)

/** 主图当前看得见的那段:第一根与最后一根的日期,和图上全部 K 线的最后日期。 */
async function visibleRange(page: Page): Promise<{ first: string; last: string; lastBar: string }> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartMain().getOption()
    const dates: string[] = opt?.xAxis?.[0]?.data ?? []
    const dz = opt?.dataZoom?.[0]
    if (!dates.length || !dz) return { first: '', last: '', lastBar: '' }
    const N = dates.length
    return { first: dates[Math.round((dz.start / 100) * N)], last: dates[Math.round((dz.end / 100) * N) - 1],
             lastBar: dates[N - 1] }
  })
}

/** 落在 annotate、打开的是这只股票、K 线已画上。 */
async function expectOpened(page: Page, symbol: string) {
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect(page.getByTestId('annotation-sidebar')).toBeVisible()
  expect(await viewOf(page, 'mode')).toBe('annotate')
  await expect.poll(async () => (await visibleRange(page)).first).not.toBe('')
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('直达链接', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    backend = await startBackend()
    await putFixture(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('股票 + 日期:打开对的股票、图窗停在那天附近、落在 annotate;晚于 2025-12-31 的截到 2025-12-31', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    // 新开的页带着链接(代码写成小写也认)
    await page.goto('/#symbol=msft&date=2024-05-10')
    await expectOpened(page, 'MSFT')
    const r = await visibleRange(page)
    expect(r.first <= '2024-05-10' && '2024-05-10' <= r.last, JSON.stringify(r)).toBe(true)
    expect(r.first >= '2023-11-12' && r.last <= '2024-07-09', JSON.stringify(r)).toBe(true)   // 往前约半年、往后约两个月
    expect(await page.evaluate(() => location.hash)).toBe('')                                  // 跟完把 # 部分去掉
    await page.screenshot({ path: testInfo.outputPath('01-chart-link.png'), fullPage: true })

    // 页面在 app 下,地址的 # 部分换成另一个:同样落在 annotate;2026-03-01 截到 2025-12-31
    await page.evaluate(() => { (window as any).__e2e.view.mode = 'app' })
    await expect(page.getByTestId('annotation-sidebar')).toHaveCount(0)
    await page.evaluate(() => { location.hash = '#symbol=AAPL&date=2026-03-01' })
    await expectOpened(page, 'AAPL')
    const late = await visibleRange(page)
    expect(late.lastBar <= TRAIN_END, JSON.stringify(late)).toBe(true)
    expect(late.last).toBe(late.lastBar)                                                       // 图窗一直到最后一根
    expect(late.first >= '2025-07-04', JSON.stringify(late)).toBe(true)                       // 按 2025-12-31 往前约半年
    await page.screenshot({ path: testInfo.outputPath('02-chart-link-after-train-end.png'), fullPage: true })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('样本编号:打开样本所在的图并选中它;不存在的编号、认不出的写法有明确提示', async ({ page }, testInfo) => {
    const st = (await (await fetch(`${backend!.base}/annotations`)).json()).state
    const sid = (symbol: string, date: string) =>
      st.charts.find((c: any) => c.symbol === symbol).samples.find((s: any) => s.date === date).id as string
    const msft = sid('MSFT', '2024-02-08'), nvda = sid('NVDA', '2024-04-15')

    // 新开的页带着链接:等标注读完再找
    await routeTo(page, backend!)
    await page.goto(`/#sample=${msft}`)
    await expectOpened(page, 'MSFT')
    await expect.poll(() => e2e(page, 'selectedSampleId')).toBe(msft)
    expect(await e2e(page, 'currentSampleId')).toBe(msft)
    expect(await e2e(page, 'currentPattern')).toBe('W底')                                    // 当前 pattern 换成样本所在的
    await expect(page.getByTestId('sample-panel')).toBeVisible()
    const r = await visibleRange(page)
    expect(r.first <= '2024-02-08' && '2024-02-08' <= r.last, JSON.stringify(r)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('03-sample-link.png'), fullPage: true })

    // 地址的 # 部分换成另一个编号:换到那张图并选中它
    await page.evaluate(id => { location.hash = `#sample=${id}` }, nvda)
    await expectOpened(page, 'NVDA')
    await expect.poll(() => e2e(page, 'selectedSampleId')).toBe(nvda)

    // 不存在的编号:不换图,提示条写明编号与 not_found,点 ok 收起
    await page.evaluate(() => { location.hash = '#sample=s-pc-999' })
    const notice = page.getByTestId('notice-url')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText('sample')
    await expect(notice).toContainText('s-pc-999')
    await expect(notice).toContainText('not_found')
    await expect(page.locator('.symbol-title-bar [data-symbol="NVDA"]')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('04-sample-not-found.png'), fullPage: true })
    await page.getByTestId('notice-url-ok').click()
    await expect(notice).toHaveCount(0)

    // 认不出的写法
    await page.evaluate(() => { location.hash = '#symbol=AAPL' })
    await expect(notice).toContainText('bad_url')
    await expect(notice).toHaveAttribute('title', /#symbol=AAPL/)

    // 另开一页带着不存在的编号:同样提示
    const tab = await page.context().newPage()
    await routeTo(tab, backend!)
    await tab.goto('/#sample=s-pc-999')
    await expect(tab.getByTestId('notice-url')).toContainText('not_found')
    for (const p of [page, tab]) await p.unrouteAll({ behavior: 'ignoreErrors' })
  })
})
