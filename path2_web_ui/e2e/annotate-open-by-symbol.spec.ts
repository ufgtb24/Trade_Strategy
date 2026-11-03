import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { apiBase } from './ports'

/**
 * 按代码打开:不经扫描,在顶栏 symbol 输入代码回车,打开训练段副本里的任一只股票,落在 annotate。
 *
 * - 图最晚画到 2025-12-31;
 * - 训练段副本里没有的代码(2026 年才上市的不在副本里)不在列表里,回车后报 not_found,当前的图不动;
 * - annotate 下图上没有 app 的产物(主图 app 系列全空、副图只有用户的框、没有 band/bracket),不显示档位与诊断侧栏;
 * - 成交量画在 K 线区下方。
 *
 * 前提:后端已按 configs/path2_web.yaml 的 backend_port 启动,读真实的训练段副本(只读)。
 * 代码从 /symbols 现取,不写死某只股票。还没有扫描结果时,先对少数几只股票跑一次小扫描。
 * 两张整页截图挂在测试结果里(annotate-*.png)。
 */

const TRAIN_END = '2025-12-31'
const ABSENT = 'ZZZQ26'     // 副本里没有的代码,代表「2026 年才上市」的那一类

async function openSymbol(page: Page, code: string) {
  const input = page.getByTestId('symbol-input')
  await input.fill(code)
  await input.press('Enter')
}

async function mainOption(page: Page): Promise<any> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartMain().getOption()
    if (!opt?.xAxis) return { grid: [], dates: [], series: [] }       // 还没出图
    return {
      grid: opt.grid,
      dates: opt.xAxis[0].data,
      series: opt.series.map((s: any) => ({ name: s.name, xAxisIndex: s.xAxisIndex, n: (s.data ?? []).length })),
    }
  })
}

/** 本环境还没有扫描结果时,对少数几只股票跑一次小扫描(bo_only),等它落盘。 */
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

/** 副图上 app 的系列个数。annotate 下副图是用户的特征轨,只有用户的框(annotation-boxes),它不算 app 的产物。 */
async function subSeriesCount(page: Page): Promise<number> {
  return page.evaluate(() => ((window as any).__e2e.chartSub().getOption()?.series ?? [])
    .filter((s: any) => s.name !== 'annotation-boxes').length)
}

test.describe('按代码打开 · annotate', () => {
  test('副本里的代码回车打开:K 线止于 2025-12-31、只有 K 线和成交量;副本里没有的代码报 not_found', async ({ page, request }) => {
    const symbols: string[] = await (await request.get(`${apiBase}/symbols`)).json()
    expect(symbols.length).toBeGreaterThan(100)
    expect(symbols).not.toContain(ABSENT)
    const code = symbols[Math.floor(symbols.length / 2)]

    await page.goto('/')
    await expect(page.getByTestId('top-bar')).toBeVisible()
    await openSymbol(page, code.toLowerCase())                      // 小写也认
    await expect(page.locator(`.symbol-title-bar [data-symbol="${code}"]`)).toBeVisible()

    await expect.poll(async () => (await mainOption(page)).dates.length).toBeGreaterThan(0)
    const opt = await mainOption(page)
    expect(opt.dates.at(-1) <= TRAIN_END).toBe(true)
    await page.screenshot({ path: test.info().outputPath('annotate-open-by-symbol.png'), fullPage: true })

    // 只有 K 线和成交量:app 的系列(价格点、高亮、遮罩)全空,副图没有 app 的系列
    const byName = Object.fromEntries(opt.series.map((s: any) => [s.name, s]))
    expect(byName.kline.n).toBe(opt.dates.length)
    expect(byName.volume.n).toBe(opt.dates.length)
    for (const n of ['price-points', 'highlight-price', 'shift-veil-price']) expect(byName[n].n).toBe(0)
    expect(await subSeriesCount(page)).toBe(0)
    // 成交量带在 K 线区下方
    expect(byName.volume.xAxisIndex).toBe(1)
    expect(opt.grid[1].top).toBeGreaterThan(opt.grid[0].top + opt.grid[0].height)

    // 外壳:没有档位控件、诊断侧栏、框选;右侧是三页
    await expect(page.getByTestId('level-control')).toHaveCount(0)
    await expect(page.locator('.brush-toggle-wrap')).toHaveCount(0)
    await expect(page.getByRole('tab')).toHaveText(['selection', 'features', 'pattern'])

    // 副本里没有的代码:not_found,图不动
    await openSymbol(page, ABSENT)
    await expect(page.getByTestId('symbol-status')).toHaveText('not_found')
    await expect(page.locator(`.symbol-title-bar [data-symbol="${code}"]`)).toBeVisible()
  })

  test('现有扫描入口照旧能用:扫描结果是 app 视图;按代码打开切到 annotate;再从扫描列表选股回到 app', async ({ page, request }, testInfo) => {
    test.setTimeout(300_000)
    await ensureScan(request)

    await page.goto('/')
    await page.getByRole('button', { name: /打开历史/ }).click()
    await expect(page.locator('.file-list tbody tr').first()).toBeVisible({ timeout: 15_000 })
    await page.locator('.file-list tbody tr').first().click()
    await page.getByRole('button', { name: /^Open$/ }).click()
    const firstRow = page.locator('td.sym[data-symbol]').first()
    await expect(firstRow).toBeVisible({ timeout: 30_000 })
    const scanSym = await firstRow.getAttribute('data-symbol')

    // app:档位控件在,副图画出 app 的产物
    await expect(page.getByTestId('level-control')).toBeVisible()
    await expect.poll(() => subSeriesCount(page)).toBeGreaterThan(0)

    // 按代码打开 → annotate:同一只股票也不画 app 的产物
    await openSymbol(page, scanSym!)
    await expect(page.getByTestId('level-control')).toHaveCount(0)
    await expect(page.getByTestId('annotation-sidebar')).toBeVisible()
    await expect.poll(() => subSeriesCount(page)).toBe(0)
    await expect.poll(async () => {
      const o = await mainOption(page)
      return o.series.find((s: any) => s.name === 'price-points')?.n
    }).toBe(0)
    await page.screenshot({ path: testInfo.outputPath('annotate-after-scan.png'), fullPage: true })

    // 从扫描列表选股 → 回到 app
    await firstRow.click()
    await expect(page.getByTestId('level-control')).toBeVisible()
    await expect.poll(() => subSeriesCount(page)).toBeGreaterThan(0)
  })

  test('后端:非法代码 400,不存在 404', async ({ request }) => {
    expect((await request.get(`${apiBase}/ohlc?symbol=${encodeURIComponent('../x')}`)).status()).toBe(400)
    expect((await request.get(`${apiBase}/ohlc?symbol=${ABSENT}`)).status()).toBe(404)
  })
})
