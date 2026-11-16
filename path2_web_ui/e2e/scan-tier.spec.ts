import { test, expect, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, TRAIN_END, openSymbol, routeTo, startBackend, stopBackend, type Backend } from './annotateHelpers'
import { enterScanTier } from './scanTier'

/**
 * 顶栏 mode 四档 annotate / compare / app │ scan(spec 5.2、第 9 节「端到端」最后两条):
 * 1. 没加载扫描时点 scan 落在 no_scan(图区写 no_scan、股票不带过去),回 annotate 还是原来那只;
 *    加载扫描后落在 scan;进出 scan 时股票照 5.2 的规矩带——进:当前股票在扫描文件里就留着,不在就回扫描列表上次停的
 *    那只;出:在 scan 里点过扫描列表的行就带着那只,没点过回到进 scan 前那只。
 * 2. 扫描专用的按键和控件只在 scan 档:敲字母搜股票、PageUp / PageDown 切扫描股、Shift+P 参数抽屉在前三档不起作用、
 *    在 scan 档照旧;扫描的休眠草稿横幅在 scan 档出现、不出现在 compare。
 *
 * 后端是 e2e/annotationBackend.py 起的测试后端(标注在临时目录,用 tests/path2_web/fixtures/annotation_grouping_v1 的
 * 例子批次,mapping 手写:pattern W底 → bo_only),扫描也跑在它上面:bo_only 扫三只股票,只读截到训练段末日的副本。
 * 扫描里没有的股票用 KO(不在扫描的代码范围里)。整页截图挂在测试结果里(scan-tier-*.png)。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nreference: bo\nfeatures:\n  w-pc-3: bo\n'
const OUTSIDE = 'KO'

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

/** 在测试后端上跑一次小扫描(bo_only、三只股票),返回它的名字与 scan_ts。 */
async function runScan(b: Backend): Promise<{ name: string; ts: string }> {
  const name = `e2e_scan_tier_${Date.now()}`
  const r = await fetch(`${b.base}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern_ids: ['bo_only'], start_date: '2024-01-01', end_date: TRAIN_END, workers: 2,
                           ticker_regex: '^(AAPL|NVDA|AMD)$', label_horizon: 20, note: name }),
  })
  expect(r.ok).toBe(true)
  let ts = ''
  await expect.poll(async () => {
    const scans: any[] = await (await fetch(`${b.base}/scans/`)).json()
    const s = scans.find(x => x.name === name && !x.partial)
    ts = s?.scan_ts ?? ''
    return ts
  }, { timeout: 240_000 }).not.toBe('')
  return { name, ts }
}

/** 进 scan 档(扫描面板只在 scan 档的左栏)→ 打开历史 → 选这个扫描 → Open,等扫描文件进 store。 */
async function openScan(page: Page, name: string) {
  await enterScanTier(page)
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator(`.file-list tbody tr:has-text("${name}")`).click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).not.toBeVisible({ timeout: 30_000 })
  await page.waitForFunction(() => !!(window as any).__e2e?.view?.scanFile)
}

const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
/** 扫描列表从上到下的股票。 */
const scanSymbols = (page: Page): Promise<string[]> =>
  page.evaluate(() => (window as any).__e2e.view.filteredSortedRows.map((r: any) => r.symbol))
/** 加载扫描时落下的那只(扫描文件里的第一只)。 */
const firstResult = (page: Page): Promise<string> =>
  page.evaluate(() => (window as any).__e2e.view.scanFile.results[0].symbol)
async function expectTier(page: Page, tier: 'annotate' | 'compare' | 'app' | 'scan', symbol: string | null) {
  await expect(page.getByTestId(`mode-${tier}`)).toHaveClass(/\bon\b/)
  await expect.poll(() => view(page, 'symbol')).toBe(symbol)
  if (symbol) await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  else await expect(page.locator('.symbol-title-bar')).toHaveCount(0)
}
async function pickPattern(page: Page, text: string) {
  await page.getByTestId('top-pattern-button').click()
  await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().currentPattern)).toBe(text)
}
/** 焦点放回页面空白处(按代码打开后焦点还在代码输入框里)。 */
const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('顶栏 mode 四档与 scan 档', () => {
  let b: Backend | null = null
  let scan: { name: string; ts: string }
  test.beforeAll(async () => {
    test.setTimeout(300_000)
    b = await startBackend(undefined, { bo_only: MAPPING })
    await putFixture(b)
    scan = await runScan(b)
  })
  test.afterAll(() => stopBackend(b))

  test('没加载扫描时 scan 落在 no_scan;进出 scan 时股票照规矩带', async ({ page }, testInfo) => {
    test.setTimeout(300_000)
    await routeTo(page, b!)
    await page.goto('/')
    await openSymbol(page, OUTSIDE)

    // no_scan:图区写 no_scan,股票不带过去;回 annotate 还是原来那只
    await page.getByTestId('mode-scan').click()
    await expect(page.getByTestId('no-scan')).toHaveText('no_scan')
    await expectTier(page, 'scan', null)
    await page.screenshot({ path: testInfo.outputPath('scan-tier-no-scan.png'), fullPage: true })
    await page.getByTestId('mode-annotate').click()
    await expectTier(page, 'annotate', OUTSIDE)

    // 加载扫描:落在 scan,当前股票不在扫描里 → 扫描文件里的第一只;没点过行,回去是进 scan 前那只
    await openScan(page, scan.name)
    const first = await firstResult(page)
    const other = (await scanSymbols(page)).find(s => s !== first)!
    expect(other).toBeTruthy()
    await expectTier(page, 'scan', first)
    await expect(page.getByTestId('no-scan')).toHaveCount(0)
    await page.getByTestId('mode-annotate').click()
    await expectTier(page, 'annotate', OUTSIDE)

    // 当前股票在扫描文件里:进 scan 还是它,回去也是它
    await openSymbol(page, other)
    await page.getByTestId('mode-scan').click()
    await expectTier(page, 'scan', other)
    await page.getByTestId('mode-annotate').click()
    await expectTier(page, 'annotate', other)

    // 不在:落到扫描列表上次停的那只(上一步停在 other)
    await openSymbol(page, OUTSIDE)
    await page.getByTestId('mode-scan').click()
    await expectTier(page, 'scan', other)

    // 在 scan 里点过扫描列表的行:回前三档带着那只
    await page.locator(`td.sym[data-symbol="${first}"]`).click()
    await expectTier(page, 'scan', first)
    await page.getByTestId('mode-annotate').click()
    await expectTier(page, 'annotate', first)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('扫描专用的按键与控件在前三档不起作用、scan 档照旧;休眠草稿横幅不出现在 compare', async ({ page }, testInfo) => {
    test.setTimeout(300_000)
    await routeTo(page, b!)
    await page.goto('/')
    // 上次会话遗留的一份休眠草稿(Working Copy):打开扫描时扫出来
    await page.evaluate(([ts]) => localStorage.setItem(`p2wc:${ts}:bo_only`,
      JSON.stringify({ dict: {}, baseline: {}, savedAt: 1 })), [scan.ts])
    await openScan(page, scan.name)
    const rows = await scanSymbols(page)
    expect(rows.length).toBeGreaterThanOrEqual(2)
    await page.locator(`td.sym[data-symbol="${rows[0]}"]`).click()     // 停在扫描列表第一行
    await expectTier(page, 'scan', rows[0])
    const search = page.getByTestId('symbol-search')

    // scan 档:横幅在;敲字母进搜索框;PageDown 切到下一只;Shift+P 开关抽屉
    await expect(page.getByTestId('dormant-banner')).toBeVisible()
    await blur(page)
    await page.keyboard.press('x')
    await expect(search).toHaveValue('x')
    await expect(search).toBeFocused()
    await page.keyboard.press('Escape')                     // 搜索框里 Esc:清掉 query
    await expect(search).toHaveValue('')
    await blur(page)
    await page.keyboard.press('PageDown')
    await expectTier(page, 'scan', rows[1])
    await page.keyboard.press('Shift+P')
    await expect(page.getByTestId('wc-drawer')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('scan-tier-scan-drawer.png'), fullPage: true })
    await page.keyboard.press('Shift+P')
    await expect(page.getByTestId('wc-drawer')).toHaveCount(0)

    // annotate:敲字母不进搜索框,PageUp / PageDown 不切扫描股、不离开 annotate,Shift+P 不开抽屉。
    // 前三档的翻页键归左栏找图清单:切到这次还空着的 random 页,清单没有行可翻,扫描列表也不接,图不换
    await openSymbol(page, OUTSIDE)
    await pickPattern(page, 'W底')
    await page.getByTestId('finder-tab-random').click()
    await blur(page)
    await page.keyboard.press('x')
    await expect(search).toHaveValue('')
    await expect(search).not.toBeFocused()
    for (const key of ['PageDown', 'PageUp']) {
      await page.keyboard.press(key)
      await expectTier(page, 'annotate', OUTSIDE)
    }
    await page.keyboard.press('Shift+P')
    await expect(page.getByTestId('wc-drawer')).toHaveCount(0)

    // compare:没有休眠草稿横幅;PageDown 不切股、不离开 compare
    await page.getByTestId('mode-compare').click()
    await expect.poll(() => view(page, 'mode')).toBe('compare')
    await expect(page.getByTestId('level-control')).toBeVisible()
    await expect(page.getByTestId('dormant-banner')).toHaveCount(0)
    await blur(page)
    await page.keyboard.press('PageDown')
    await expectTier(page, 'compare', OUTSIDE)
    await page.keyboard.press('Shift+P')
    await expect(page.getByTestId('wc-drawer')).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('scan-tier-compare.png'), fullPage: true })

    // 回 scan:横幅又出现
    await page.getByTestId('mode-scan').click()
    await expect(page.getByTestId('dormant-banner')).toBeVisible()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})
