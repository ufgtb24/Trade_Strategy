import { expect, type Page } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'

/**
 * 标注 e2e 共用的小工具:起一个标注目录在临时目录里的后端、把页面的请求转给它、打开股票、在图上拖框起名、
 * 读页面里的标注状态与图上的坐标。
 *
 * 标注会写批次文件,绝不能写进用户的标注目录:每组测试自己起一个后端(e2e/annotationBackend.py,
 * 标注目录是系统临时目录、机器名 e2e),页面发往 apiBase 的请求全部转给它。要能起 Python:默认
 * `uv run python`,环境变量 PATH2_E2E_PYTHON 可换成别的解释器。
 */

export const HERE = dirname(fileURLToPath(import.meta.url))
export const REPO = resolve(HERE, '../..')
export const FIXTURE = join(REPO, 'tests/path2_web/fixtures/annotation_store_v1/batches')
export const TRAIN_END = '2025-12-31'
export const MACHINE = 'e2e'
export const OTHER_FINGERPRINT = '0'.repeat(64)

export function freePort(): Promise<number> {
  return new Promise((ok, fail) => {
    const srv = createServer()
    srv.listen(0, '127.0.0.1', () => {
      const port = (srv.address() as any).port
      srv.close(() => ok(port))
    })
    srv.on('error', fail)
  })
}

export interface Backend { base: string; proc: ChildProcess; root: string }

/** 起一个标注目录在临时目录里的后端;fill 往标注目录里放初始文件。
 *  mappings 给了就让后端从临时目录读 app 的 mapping 文件({app: 文件内容},见 e2e/annotationBackend.py),
 *  不读 path2_apps/ 里的。 */
export async function startBackend(fill?: (dir: string) => void, mappings?: Record<string, string>): Promise<Backend> {
  const root = mkdtempSync(join(tmpdir(), 'path2-annotate-e2e-'))
  const dir = join(root, 'annotations')
  mkdirSync(dir)
  fill?.(dir)
  const extra: string[] = []
  if (mappings) {
    const mdir = join(root, 'mappings')
    mkdirSync(mdir)
    for (const [app, text] of Object.entries(mappings)) writeFileSync(join(mdir, `${app}.yaml`), text)
    extra.push(mdir)
  }
  const port = await freePort()
  const py = process.env.PATH2_E2E_PYTHON ? [process.env.PATH2_E2E_PYTHON] : ['uv', 'run', 'python']
  const proc = spawn(py[0], [...py.slice(1), join(HERE, 'annotationBackend.py'), String(port), dir, MACHINE, ...extra],
                     { cwd: REPO, stdio: ['ignore', 'inherit', 'inherit'] })
  const base = `http://127.0.0.1:${port}`
  await expect.poll(async () => {
    try { return (await fetch(`${base}/annotations`)).status } catch { return 0 }
  }, { timeout: 120_000 }).toBe(200)
  return { base, proc, root }
}

export function stopBackend(b: Backend | null) {
  if (!b) return
  b.proc.kill()
  rmSync(b.root, { recursive: true, force: true })
}

/** 页面发往 apiBase 的请求全部转给测试后端;转之前核对它的机器名,确认不是用户的标注目录。 */
export async function routeTo(page: Page, b: Backend) {
  const machine = (await (await fetch(`${b.base}/annotations`)).json()).state.machine
  expect(machine).toBe(MACHINE)
  await page.route(u => u.href.startsWith(`${apiBase}/`), async route => {
    const resp = await route.fetch({ url: route.request().url().replace(apiBase, b.base) })
    await route.fulfill({ response: resp })
  })
}

/** 打开一只股票,图窗缩到最后 200 根(K 线够宽,拖框、点框边才准)。 */
export async function openSymbol(page: Page, code: string) {
  const input = page.getByTestId('symbol-input')
  await input.fill(code)
  await input.press('Enter')
  await expect(page.locator(`.symbol-title-bar [data-symbol="${code}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().status)).toBe('ready')
  await page.evaluate(() => {
    const main = (window as any).__e2e.chartMain()
    const n = main.getOption().xAxis[0].data.length
    main.dispatchAction({ type: 'dataZoom', start: ((n - 200) / n) * 100, end: 100 })
  })
}

export const annState = (page: Page) =>
  page.evaluate(() => JSON.parse(JSON.stringify((window as any).__e2e.ann().state)))
export const settled = (page: Page) => page.evaluate(() => (window as any).__e2e.ann().flushed())

/** K 线下标 → 页面坐标 x;which 选主图或副图(两者 x 轴对齐)。 */
export async function xOf(page: Page, i: number, which: 'main' | 'sub' = 'main'): Promise<number> {
  return page.evaluate(([i, which]) => {
    const e2e = (window as any).__e2e
    const chart = which === 'main' ? e2e.chartMain() : e2e.chartSub()
    const el = document.querySelector(which === 'main' ? '.main-chart' : '.sub-inner')!
    return el.getBoundingClientRect().left + chart.convertToPixel({ xAxisIndex: 0 }, i)
  }, [i, which] as const)
}

/** 主图 K 线区中间一行的页面坐标 y。 */
export async function klineY(page: Page): Promise<number> {
  return page.evaluate(() => {
    const g = (window as any).__e2e.chartMain().getOption().grid[0]
    return document.querySelector('.main-chart')!.getBoundingClientRect().top + g.top + g.height / 2
  })
}

/** 副图上各条轨的标题文字与轨中线的页面坐标 y(轨标题在轨顶内侧)。 */
export async function lanes(page: Page): Promise<{ text: string; y: number }[]> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartSub().getOption()
    const top = document.querySelector('.sub-inner')!.getBoundingClientRect().top
    const els = (opt.graphic?.[0]?.elements ?? []).filter((e: any) => e.type === 'text')
    return els.map((e: any) => ({ text: String(e.style?.text ?? '').replace(/\{(biz|sym)\|([^}]*)\}/g, '$2'), y: top + e.top + 8 }))
  })
}

export async function laneY(page: Page, text: string): Promise<number> {
  await expect.poll(async () => (await lanes(page)).map(l => l.text)).toContain(text)
  return (await lanes(page)).find(l => l.text === text)!.y
}

export async function drag(page: Page, x0: number, y0: number, x1: number, y1: number) {
  await page.mouse.move(x0, y0)
  await page.mouse.down()
  await page.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, { steps: 4 })
  await page.mouse.move(x1, y1, { steps: 4 })
  await page.mouse.up()
}

export async function barCount(page: Page): Promise<number> {
  return page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data.length)
}

/** 在 K 线区从下标 i0 拖到 i1,画一个还没起名的框,返回它的编号。 */
export async function drawOnKline(page: Page, i0: number, i1: number): Promise<string> {
  const before = await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)
  await drag(page, await xOf(page, i0), await klineY(page), await xOf(page, i1), await klineY(page))
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).not.toBe(before)
  return page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)
}

export async function name(page: Page, text: string) {
  await page.getByTestId('feature-input').fill(text)
  await page.getByTestId('feature-input').press('Enter')
  await expect(page.getByTestId('box-feature')).toHaveText(text)
}

export const boxesOf = (st: any, symbol: string) => st.charts.find((c: any) => c.symbol === symbol)?.boxes ?? []
export const featureId = (st: any, n: string) => st.features.find((f: any) => f.name === n)?.id
