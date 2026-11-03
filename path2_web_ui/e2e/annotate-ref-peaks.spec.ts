import { test, expect, type Page } from '@playwright/test'
import {
  barCount, drawOnKline, name, openSymbol, routeTo, startBackend, stopBackend, TRAIN_END, type Backend,
} from './annotateHelpers'

/**
 * 参照层 peaks(顶栏 ref 组的复选框):
 *
 * - 默认关;勾上后主图画出峰线,条数、起止和高度都和后端 /peaks 给的一样,最晚都到 2025-12-31;
 * - 换股票自动关(复选框取消勾选、峰线不画);
 * - app 下不能用:复选框变灰、不能勾(从扫描列表选股走的就是 view store 的 selectSymbol)。
 *
 * 只用截到 2025-12-31 的数据算峰,由后端测试 tests/path2_web/test_peaks.py 用合成例子验:图上画的就是 /peaks 给的。
 * 后端是测试自己起的(标注目录在临时目录里,读真实的训练段副本,只读)。股票从 /symbols 里现找有峰的,不写死。
 * 整页截图与峰线附近的元素截图挂在测试结果里(ref-peaks-*.png),用来自查峰线和 K 线、用户的框分不分得开。
 */

type PeakLine = { date: string; price: number; end: string }

let backend: Backend | null = null
test.beforeAll(async () => { backend = await startBackend() })
test.afterAll(() => stopBackend(backend))

const getJson = async (path: string) => (await fetch(`${backend!.base}${path}`)).json()

/** 从股票列表中间往后找两只峰不少于 min 条的股票。 */
async function stocksWithPeaks(min: number): Promise<[string, PeakLine[]][]> {
  const symbols: string[] = await getJson('/symbols')
  const found: [string, PeakLine[]][] = []
  for (const s of symbols.slice(Math.floor(symbols.length / 2))) {
    const lines: PeakLine[] = await getJson(`/peaks?symbol=${encodeURIComponent(s)}`)
    if (lines.length >= min) found.push([s, lines])
    if (found.length === 2) return found
  }
  throw new Error(`股票列表里找不到两只峰不少于 ${min} 条的股票`)
}

/** 主图上峰线系列的数据 [起点下标, 终点下标, 峰价],连同图上的日期。 */
async function drawnPeaks(page: Page): Promise<{ dates: string[]; data: number[][] }> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartMain().getOption()
    return { dates: opt.xAxis[0].data, data: opt.series.find((s: any) => s.name === 'ref-peaks')?.data ?? [] }
  })
}

test.describe('参照层 peaks', () => {
  test('默认关;勾上画出峰线(同 /peaks、止于 2025-12-31);换股票自动关', async ({ page }) => {
    test.setTimeout(180_000)
    const [[a, linesA], [b]] = await stocksWithPeaks(5)
    await routeTo(page, backend!)
    await page.setViewportSize({ width: 2560, height: 1440 })
    await page.goto('/')
    await openSymbol(page, a)

    const box = page.getByTestId('ref-peaks')
    await expect(box).not.toBeChecked()
    await expect(box).toBeEnabled()
    expect((await drawnPeaks(page)).data).toEqual([])

    await box.check()
    await expect.poll(async () => (await drawnPeaks(page)).data.length).toBe(linesA.length)
    const { dates, data } = await drawnPeaks(page)
    expect(data.map(([i, j, p]) => ({ date: dates[i], price: p, end: dates[j] }))).toEqual(linesA)
    expect(linesA.every(l => l.date <= TRAIN_END && l.end <= TRAIN_END)).toBe(true)

    // 截图自查:图窗停在最后一条峰线前后,在它上面画一个框并选中(主图上画出框的范围)
    const last = data.at(-1)!
    const n = await barCount(page)
    const i0 = Math.max(0, last[0] - 40)
    const i1 = Math.min(n - 1, Math.max(last[1], last[0] + 40) + 20)
    await page.evaluate(([s, e, n]) => (window as any).__e2e.chartMain()
      .dispatchAction({ type: 'dataZoom', start: (s / n) * 100, end: ((e + 1) / n) * 100 }), [i0, i1, n])
    await drawOnKline(page, last[0] - 5, last[0] + 10)
    await name(page, '突破前横盘')
    await page.mouse.move(5, 5, { steps: 10 })                     // 鼠标移到顶栏:图上不留十字线、价格线和提示框
    await page.evaluate(() => (window as any).__e2e.chartMain().dispatchAction({ type: 'hideTip' }))
    await page.screenshot({ path: test.info().outputPath('ref-peaks-page.png'), fullPage: true, scale: 'device' })
    await page.locator('.main-chart').screenshot({ path: test.info().outputPath('ref-peaks-main.png'), scale: 'device' })

    await openSymbol(page, b)
    await expect(box).not.toBeChecked()
    await expect.poll(async () => (await drawnPeaks(page)).data).toEqual([])
  })

  test('app 下不能用:复选框变灰、不能勾', async ({ page }) => {
    const [[a]] = await stocksWithPeaks(1)
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, a)
    const box = page.getByTestId('ref-peaks')
    await box.check()
    await expect(box).toBeChecked()
    await page.evaluate((s) => (window as any).__e2e.view.selectSymbol(s), a)
    await expect(box).not.toBeChecked()
    await expect(box).toBeDisabled()
    await expect(page.getByTestId('ref-group').locator('label')).toHaveClass(/\boff\b/)
    // 勾上时发出的 /peaks 可能还在路上(结果已不用):测试结束前撤掉转发,免得页面关掉时转发报错
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})
