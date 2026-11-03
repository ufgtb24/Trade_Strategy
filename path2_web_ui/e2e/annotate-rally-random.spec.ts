import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { execSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'

/**
 * 找图入口:顶栏 rally(大涨段清单)与 random(随机给一段图)。
 *
 * - 从扫描结果的 app 视图出发,点 rally 的一行、点 random,都落在 annotate;
 * - rally:图停在那段涨之前、同时看得见那段涨(图窗两端 = 清单给的 view_start / view_end),最晚到 2025-12-31;
 * - random:图窗不超过默认 250 根、最晚到 2025-12-31;
 * - 看过什么一律不记:清单与缓存先备好,之后连点几行、几次 random,
 *   仓库的 git status --porcelain --ignored(含被忽略的文件,逐个列出)、标注目录、浏览器 localStorage 都不变。
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

/** 打开最近一次扫描,进到 app 视图。 */
async function enterAppView(page: Page) {
  await page.goto('/')
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

async function localStorageSnapshot(page: Page): Promise<string> {
  return page.evaluate(() => JSON.stringify(Object.entries(localStorage).sort()))
}

test.describe('找图入口 · rally / random', () => {
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

  test('rally:从 app 视图点一行 → annotate,图停在那段涨之前、看得见那段涨,止于 2025-12-31', async ({ page }, testInfo) => {
    await enterAppView(page)
    await page.getByTestId('rally-button').click()
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
    await expect(page.getByTestId('rally-list')).toBeHidden()
    await expectAnnotate(page, sym)

    await expect.poll(async () => (await visibleRange(page)).first, { timeout: 30_000 }).toBe(it.view_start)
    const v = await visibleRange(page)
    expect(v.last).toBe(it.view_end)
    expect(v.lastBar <= TRAIN_END).toBe(true)
    expect(v.first < it.date && it.date <= it.peak_date && it.peak_date <= v.last).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('rally-opened.png'), fullPage: true })
  })

  test('random:从 app 视图点一下 → annotate,图窗不超过 250 根、止于 2025-12-31', async ({ page, request }, testInfo) => {
    const pool: string[] = (await (await request.get(`${apiBase}/pool`)).json()).symbols
    await enterAppView(page)
    await page.getByTestId('random-button').click()
    await expectAnnotate(page)
    const sym = (await page.getByTestId('symbol-input').inputValue())
    expect(pool).toContain(sym)
    await expect(page.locator(`.symbol-title-bar [data-symbol="${sym}"]`)).toBeVisible()
    await expect.poll(async () => (await visibleRange(page)).n, { timeout: 30_000 }).toBeGreaterThan(0)
    const v = await visibleRange(page)
    expect(v.n).toBeLessThanOrEqual(RANDOM_BARS)
    expect(v.last <= TRAIN_END && v.lastBar <= TRAIN_END).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('random-opened.png'), fullPage: true })
  })

  test('看过什么一律不记:连点几行 rally、几次 random,文件与 localStorage 都不变', async ({ page, request }) => {
    await request.get(`${apiBase}/random`)                     // 预热:random 的路径也先走一遍
    await page.goto('/')
    await expect(page.getByTestId('top-bar')).toBeVisible()
    const filesBefore = recordsSnapshot()
    const lsBefore = await localStorageSnapshot(page)

    await page.getByTestId('rally-button').click()
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    for (const i of [0, 5, 9]) {
      if (!(await page.getByTestId('rally-list').isVisible())) await page.getByTestId('rally-button').click()
      const row = page.getByTestId('rally-row').nth(i)
      const sym = (await row.getAttribute('data-symbol'))!
      await row.click()
      await expectAnnotate(page, sym)
    }
    for (let k = 0; k < 3; k++) {
      await page.getByTestId('random-button').click()
      await expect(page.getByTestId('random-button')).toBeEnabled()
      await expectAnnotate(page)
    }
    await page.waitForTimeout(1000)
    expect(await localStorageSnapshot(page)).toBe(lsBefore)
    expect(recordsSnapshot()).toBe(filesBefore)
  })
})
