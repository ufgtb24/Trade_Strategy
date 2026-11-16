import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { execSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'
import { gotoScanTier } from './scanTier'

/**
 * 找图:左栏找图清单(annotate / compare / app 三档的左栏,三页 rally / random / charts)与顶栏 random。
 *
 * - 打开页面落在 rally 页;点 rally 的一行:图停在那段涨之前、同时看得见那段涨(图窗两端 = 清单给的
 *   view_start / view_end),最晚到 2025-12-31;换图不换档(这里是 annotate;compare 下留在 compare 由
 *   e2e/annotate-compare.spec.ts 验);PageDown 换到下一行;
 * - random:从 scan 档点顶栏 random 落在 annotate,图窗不超过默认 250 根、最晚到 2025-12-31;抽到的按先后进左栏
 *   random 页,点回去、PageUp / PageDown 挨个翻;
 * - 看过什么一律不记、random 页不落盘:清单与缓存先备好,之后连点几行、翻页、几次 random,
 *   仓库的 git status --porcelain --ignored(含被忽略的文件,逐个列出)、标注目录、浏览器存储都不变;刷新后 random 页为空、
 *   回到 rally 页;
 * - 切到 scan 档再切回来,找图清单的页签和滚动位置都还在;反过来从前三档回 scan 档,扫描列表的滚动位置也还在。
 *
 * 前提:后端已按 configs/path2_web.yaml 的 backend_port 启动,读真实的训练段副本(只读)。
 * 大涨段清单第一次要整池算一遍(约半分钟)。还没有扫描结果时,先对少数几只股票跑一次小扫描。
 * 整页截图挂在测试结果里(rally-*.png、random-*.png)。
 */

const TRAIN_END = '2025-12-31'
const RANDOM_BARS = 250
const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

type RallyItem = { symbol: string; date: string; peak_date: string; rise: number; rel: number;
                   view_start: string; view_end: string }

async function ensureScan(request: APIRequestContext) {
  const list = async () => (await (await request.get(`${apiBase}/scans/`)).json()) as any[]
  if ((await list()).length > 0) return
  const r = await request.post(`${apiBase}/scan`, { data: {
    pattern_ids: ['bo_only'], start_date: '2025-01-01', end_date: TRAIN_END,
    workers: 2, ticker_regex: '^AA', label_horizon: 20,
  } })
  expect(r.ok()).toBe(true)
  await expect.poll(async () => (await list()).length, { timeout: 240_000 }).toBeGreaterThan(0)
}

/** 打开最近一次扫描,进到 scan 档的扫描视图。 */
async function enterScanView(page: Page) {
  await gotoScanTier(page)
  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.file-list tbody tr').first()).toBeVisible({ timeout: 15_000 })
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('td.sym[data-symbol]').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('level-control')).toBeVisible()
}

/** 主图当前看得见的那段:第一根与最后一根的日期,和图上全部 K 线的最后日期。 */
async function visibleRange(page: Page): Promise<{ first: string; last: string; n: number; lastBar: string }> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartMain().getOption()
    const dates: string[] = opt?.xAxis?.[0]?.data ?? []
    const dz = opt?.dataZoom?.[0]
    if (!dates.length || !dz) return { first: '', last: '', n: 0, lastBar: '' }
    const N = dates.length
    const i0 = Math.round((dz.start / 100) * N)
    const i1 = Math.round((dz.end / 100) * N) - 1
    return { first: dates[i0], last: dates[i1], n: i1 - i0 + 1, lastBar: dates[N - 1] }
  })
}

async function expectAnnotate(page: Page, symbol?: string) {
  await expect(page.getByTestId('annotation-sidebar')).toBeVisible()
  await expect(page.getByTestId('level-control')).toHaveCount(0)
  if (symbol) await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
}

/** 看图记录的快照:仓库里的全部文件状态(含被忽略的,逐个列出)+ 标注目录里的文件。
 *  测试自己、开发服务器与运行环境的产物不算(测试结果、playwright 缓存、vite 预构建、Python 字节码、
 *  .venv 与 pytest 缓存:别的进程同时装依赖、跑测试时它们会变,和看图无关)。 */
function recordsSnapshot(): string {
  const skip = [/^.. path2_web_ui\/test-results\//, /^.. path2_web_ui\/playwright-report\//,
                /^.. \.playwright-mcp\//, /^.. path2_web_ui\/node_modules\//, /__pycache__\//,
                /^.. \.venv\//, /^.. \.pytest_cache\//]
  const status = execSync('git status --porcelain --ignored --untracked-files=all', { cwd: REPO, encoding: 'utf8' })
    .split('\n').filter(l => l && !skip.some(r => r.test(l)))
  const ann = execSync('find -L annotations -type f -printf "%p %s %T@\\n" 2>/dev/null || true',
                       { cwd: REPO, encoding: 'utf8' }).split('\n').filter(Boolean)
  return [...status, '--- annotations', ...ann].sort().join('\n')
}

/** 浏览器存储的快照:localStorage、sessionStorage 的全部键值,以及 IndexedDB 的库名。 */
async function browserStorageSnapshot(page: Page): Promise<string> {
  return page.evaluate(async () => JSON.stringify({
    local: Object.entries(localStorage).sort(),
    session: Object.entries(sessionStorage).sort(),
    idb: (await indexedDB.databases()).map(d => d.name).sort(),
  }))
}

/** 当前打开的图:股票与图窗。 */
async function opened(page: Page): Promise<{ symbol: string | null; win: { start: string; end: string } | null }> {
  return page.evaluate(() => {
    const v = (window as any).__e2e.view
    return { symbol: v.symbol, win: v.viewWindow ? { start: v.viewWindow.start, end: v.viewWindow.end } : null }
  })
}

test.describe('找图 · 左栏 rally / random 与顶栏 random', () => {
  test.setTimeout(600_000)
  let rally: RallyItem[] = []

  test.beforeAll(async ({ request }) => {
    // 清单与缓存先备好(首次整池算一遍),之后的点击不再写任何东西
    const r = await request.get(`${apiBase}/rally`, { timeout: 300_000 })
    expect(r.ok()).toBe(true)
    rally = await r.json()
    expect(rally.length).toBeGreaterThan(10)
    for (const it of rally) {
      expect(it.date <= TRAIN_END && it.peak_date <= TRAIN_END && it.view_end <= TRAIN_END).toBe(true)
    }
    await ensureScan(request)
  })

  test('rally:打开页面就在左栏 rally 页;点一行 → 留在 annotate,图停在那段涨之前、看得见那段涨,止于 2025-12-31;PageDown 换到下一行', async ({ page }, testInfo) => {
    await page.goto('/')
    await expect(page.getByTestId('finder-tab-rally')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    await expect(page.getByTestId('rally-row')).toHaveCount(rally.length)
    await page.screenshot({ path: testInfo.outputPath('rally-list.png'), fullPage: true })

    // 按 date 排一次,点第三行
    await page.getByTestId('rally-sort-date').click()
    const row = page.getByTestId('rally-row').nth(2)
    const sym = (await row.getAttribute('data-symbol'))!
    const date = (await row.getAttribute('data-date'))!
    const it = rally.find(x => x.symbol === sym && x.date === date)!
    expect(it).toBeTruthy()
    await row.click()
    await expectAnnotate(page, sym)
    await expect(row).toHaveClass(/\bcurrent\b/)

    await expect.poll(async () => (await visibleRange(page)).first, { timeout: 30_000 }).toBe(it.view_start)
    const v = await visibleRange(page)
    expect(v.last).toBe(it.view_end)
    expect(v.lastBar <= TRAIN_END).toBe(true)
    expect(v.first < it.date && it.date <= it.peak_date && it.peak_date <= v.last).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('rally-opened.png'), fullPage: true })

    // PageDown:换到第四行那张图,仍在 annotate
    const next = page.getByTestId('rally-row').nth(3)
    const nextSym = (await next.getAttribute('data-symbol'))!
    const nextDate = (await next.getAttribute('data-date'))!
    const nextIt = rally.find(x => x.symbol === nextSym && x.date === nextDate)!
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('PageDown')
    await expect.poll(() => opened(page)).toEqual({ symbol: nextSym, win: { start: nextIt.view_start, end: nextIt.view_end } })
    await expectAnnotate(page, nextSym)
    await expect(next).toHaveClass(/\bcurrent\b/)
  })

  test('random:从 scan 档点一下 → annotate,图窗不超过 250 根、止于 2025-12-31;抽到的按先后进左栏 random 页,点回去、翻页留在当前档', async ({ page, request }, testInfo) => {
    const pool: string[] = (await (await request.get(`${apiBase}/pool`)).json()).symbols
    await enterScanView(page)
    await page.getByTestId('random-button').click()
    await expectAnnotate(page)
    const first = await opened(page)
    expect(pool).toContain(first.symbol)
    await expect(page.locator(`.symbol-title-bar [data-symbol="${first.symbol}"]`)).toBeVisible()
    await expect.poll(async () => (await visibleRange(page)).n, { timeout: 30_000 }).toBeGreaterThan(0)
    const v = await visibleRange(page)
    expect(v.n).toBeLessThanOrEqual(RANDOM_BARS)
    expect(v.last <= TRAIN_END && v.lastBar <= TRAIN_END).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('random-opened.png'), fullPage: true })

    // 再抽一张;random 页按抽的先后列出这两张,刚抽的是当前行
    await page.getByTestId('random-button').click()
    await expect(page.getByTestId('random-button')).toBeEnabled()
    await expect.poll(() => opened(page)).not.toEqual(first)
    const second = await opened(page)
    await page.getByTestId('finder-tab-random').click()
    const rows = page.getByTestId('random-row')
    await expect(rows).toHaveCount(2)
    for (const [i, o] of [first, second].entries()) {
      await expect(rows.nth(i)).toHaveAttribute('data-symbol', o.symbol!)
      await expect(rows.nth(i)).toHaveAttribute('data-start', o.win!.start)
    }
    await expect(rows.nth(1)).toHaveClass(/\bcurrent\b/)
    await page.screenshot({ path: testInfo.outputPath('random-page.png'), fullPage: true })

    // 点回第一张、PageDown 翻到第二张:都留在 annotate
    await rows.nth(0).click()
    await expect.poll(() => opened(page)).toEqual(first)
    await expectAnnotate(page, first.symbol!)
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('PageDown')
    await expect.poll(() => opened(page)).toEqual(second)
    await expectAnnotate(page, second.symbol!)
  })

  test('看过什么一律不记、random 页不落盘:连点几行 rally、翻页、几次 random,文件与浏览器存储都不变;刷新后 random 页为空', async ({ page, request }) => {
    await request.get(`${apiBase}/random`)                     // 预热:random 的路径也先走一遍
    await page.goto('/')
    await expect(page.getByTestId('top-bar')).toBeVisible()
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    const filesBefore = recordsSnapshot()
    const storageBefore = await browserStorageSnapshot(page)

    for (const i of [0, 5, 9]) {
      const row = page.getByTestId('rally-row').nth(i)
      const sym = (await row.getAttribute('data-symbol'))!
      await row.click()
      await expectAnnotate(page, sym)
    }
    await page.keyboard.press('PageDown')
    await page.keyboard.press('PageUp')
    for (let k = 0; k < 3; k++) {
      await page.getByTestId('random-button').click()
      await expect(page.getByTestId('random-button')).toBeEnabled()
      await expectAnnotate(page)
    }
    await page.getByTestId('finder-tab-random').click()
    await expect(page.getByTestId('random-row')).toHaveCount(3)
    await page.getByTestId('random-row').nth(0).click()
    await page.waitForTimeout(1000)
    expect(await browserStorageSnapshot(page)).toBe(storageBefore)
    expect(recordsSnapshot()).toBe(filesBefore)

    // 刷新:random 页清空,回到 rally 页
    await page.reload()
    await expect(page.getByTestId('finder-tab-rally')).toHaveAttribute('aria-selected', 'true')
    await page.getByTestId('finder-tab-random').click()
    await expect(page.getByTestId('random-row')).toHaveCount(0)
    await expect(page.getByTestId('random-page-status')).toHaveText('empty')
  })

  test('切到 scan 档再切回来:找图清单的页签和滚动位置都还在', async ({ page }) => {
    await page.goto('/')
    const rallyPage = page.getByTestId('finder-page-rally')
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    const scrollTop = () => rallyPage.evaluate(el => el.scrollTop)
    await rallyPage.evaluate(el => { el.scrollTop = Math.min(600, el.scrollHeight - el.clientHeight) })
    const y = await scrollTop()
    expect(y).toBeGreaterThan(0)

    // rally 页:进 scan(没加载扫描,no_scan)再回 annotate,还在 rally 页、滚动位置不变
    await page.getByTestId('mode-scan').click()
    await expect(page.getByTestId('finder-list')).toBeHidden()
    await expect(page.getByRole('button', { name: /打开历史/ })).toBeVisible()
    await page.getByTestId('mode-annotate').click()
    await expect(page.getByTestId('finder-list')).toBeVisible()
    await expect(page.getByTestId('finder-tab-rally')).toHaveAttribute('aria-selected', 'true')
    expect(await scrollTop()).toBe(y)

    // 换到 charts 页再进出 scan:还在 charts 页;切回 rally 页,滚动位置仍不变
    await page.getByTestId('finder-tab-charts').click()
    await page.getByTestId('mode-scan').click()
    await page.getByTestId('mode-annotate').click()
    await expect(page.getByTestId('finder-tab-charts')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('finder-page-charts')).toBeVisible()
    await page.getByTestId('finder-tab-rally').click()
    expect(await scrollTop()).toBe(y)
  })
  test('切到前三档再回 scan 档:扫描列表的滚动位置还在', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 340 })        // 矮一些,几行扫描结果也要滚动
    await enterScanView(page)
    const wrap = page.getByTestId('scan-side').locator('.table-wrap')
    await expect.poll(() => wrap.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0)
    await wrap.evaluate(el => { el.scrollTop = el.scrollHeight })
    const y = await wrap.evaluate(el => el.scrollTop)
    expect(y).toBeGreaterThan(0)

    await page.getByTestId('mode-annotate').click()
    await expect(page.getByTestId('finder-list')).toBeVisible()
    await expect(wrap).toBeHidden()
    await page.getByTestId('mode-scan').click()
    await expect(wrap).toBeVisible()
    expect(await wrap.evaluate(el => el.scrollTop)).toBe(y)
  })
})
