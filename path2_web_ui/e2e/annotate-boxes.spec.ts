import { test, expect, type Page } from '@playwright/test'
import { spawn, type ChildProcess } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'

/**
 * 画框、起名与词表(annotate):
 * 1. 按代码打开 → 在 K 线区拖框 → 起名 → 刷新,框和名字都还在;在特征轨上拖出的框直接带这个名字;
 *    拖框边改起止;属性 true → 再点一下 → null(存下的是「没有这个键」);框套框的子框轨与 ⊂;
 *    改名后所有用到这个名字的框处处跟着变(两只股票);合并先显示会波及几个框,刷新后照样能拆回,拆回后恢复原样。
 * 2. 用标注存储的例子文件(tests/path2_web/fixtures/annotation_store_v1)造出冲突与指纹不符:
 *    两种提示各出现一次,图照常显示;冲突点 ok 后刷新不再出现。
 *
 * 标注会写批次文件,绝不能写进用户的标注目录:每组测试自己起一个后端(e2e/annotationBackend.py,
 * 标注目录是系统临时目录、机器名 e2e),页面发往 apiBase 的请求全部转给它。所以本文件不需要另开后端,
 * 但要能起 Python:默认 `uv run python`,环境变量 PATH2_E2E_PYTHON 可换成别的解释器。
 */

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../..')
const FIXTURE = join(REPO, 'tests/path2_web/fixtures/annotation_store_v1/batches')
const TRAIN_END = '2025-12-31'
const MACHINE = 'e2e'
const OTHER_FINGERPRINT = '0'.repeat(64)

function freePort(): Promise<number> {
  return new Promise((ok, fail) => {
    const srv = createServer()
    srv.listen(0, '127.0.0.1', () => {
      const port = (srv.address() as any).port
      srv.close(() => ok(port))
    })
    srv.on('error', fail)
  })
}

interface Backend { base: string; proc: ChildProcess; root: string }

/** 起一个标注目录在临时目录里的后端;fill 往标注目录里放初始文件。 */
async function startBackend(fill?: (dir: string) => void): Promise<Backend> {
  const root = mkdtempSync(join(tmpdir(), 'path2-annotate-e2e-'))
  const dir = join(root, 'annotations')
  mkdirSync(dir)
  fill?.(dir)
  const port = await freePort()
  const py = process.env.PATH2_E2E_PYTHON ? [process.env.PATH2_E2E_PYTHON] : ['uv', 'run', 'python']
  const proc = spawn(py[0], [...py.slice(1), join(HERE, 'annotationBackend.py'), String(port), dir, MACHINE],
                     { cwd: REPO, stdio: ['ignore', 'inherit', 'inherit'] })
  const base = `http://127.0.0.1:${port}`
  await expect.poll(async () => {
    try { return (await fetch(`${base}/annotations`)).status } catch { return 0 }
  }, { timeout: 120_000 }).toBe(200)
  return { base, proc, root }
}

function stopBackend(b: Backend | null) {
  if (!b) return
  b.proc.kill()
  rmSync(b.root, { recursive: true, force: true })
}

/** 页面发往 apiBase 的请求全部转给测试后端;转之前核对它的机器名,确认不是用户的标注目录。 */
async function routeTo(page: Page, b: Backend) {
  const machine = (await (await fetch(`${b.base}/annotations`)).json()).state.machine
  expect(machine).toBe(MACHINE)
  await page.route(u => u.href.startsWith(`${apiBase}/`), async route => {
    const resp = await route.fetch({ url: route.request().url().replace(apiBase, b.base) })
    await route.fulfill({ response: resp })
  })
}

/** 打开一只股票,图窗缩到最后 200 根(K 线够宽,拖框、点框边才准)。 */
async function openSymbol(page: Page, code: string) {
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

const annState = (page: Page) =>
  page.evaluate(() => JSON.parse(JSON.stringify((window as any).__e2e.ann().state)))
const settled = (page: Page) => page.evaluate(() => (window as any).__e2e.ann().flushed())

/** K 线下标 → 页面坐标 x;which 选主图或副图(两者 x 轴对齐)。 */
async function xOf(page: Page, i: number, which: 'main' | 'sub' = 'main'): Promise<number> {
  return page.evaluate(([i, which]) => {
    const e2e = (window as any).__e2e
    const chart = which === 'main' ? e2e.chartMain() : e2e.chartSub()
    const el = document.querySelector(which === 'main' ? '.main-chart' : '.sub-inner')!
    return el.getBoundingClientRect().left + chart.convertToPixel({ xAxisIndex: 0 }, i)
  }, [i, which] as const)
}

/** 主图 K 线区中间一行的页面坐标 y。 */
async function klineY(page: Page): Promise<number> {
  return page.evaluate(() => {
    const g = (window as any).__e2e.chartMain().getOption().grid[0]
    return document.querySelector('.main-chart')!.getBoundingClientRect().top + g.top + g.height / 2
  })
}

/** 副图上各条轨的标题文字与轨中线的页面坐标 y(轨标题在轨顶内侧)。 */
async function lanes(page: Page): Promise<{ text: string; y: number }[]> {
  return page.evaluate(() => {
    const opt = (window as any).__e2e.chartSub().getOption()
    const top = document.querySelector('.sub-inner')!.getBoundingClientRect().top
    const els = (opt.graphic?.[0]?.elements ?? []).filter((e: any) => e.type === 'text')
    return els.map((e: any) => ({ text: String(e.style?.text ?? '').replace(/\{(biz|sym)\|([^}]*)\}/g, '$2'), y: top + e.top + 8 }))
  })
}

async function laneY(page: Page, text: string): Promise<number> {
  await expect.poll(async () => (await lanes(page)).map(l => l.text)).toContain(text)
  return (await lanes(page)).find(l => l.text === text)!.y
}

async function drag(page: Page, x0: number, y0: number, x1: number, y1: number) {
  await page.mouse.move(x0, y0)
  await page.mouse.down()
  await page.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, { steps: 4 })
  await page.mouse.move(x1, y1, { steps: 4 })
  await page.mouse.up()
}

async function barCount(page: Page): Promise<number> {
  return page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data.length)
}

/** 在 K 线区从下标 i0 拖到 i1,画一个还没起名的框,返回它的编号。 */
async function drawOnKline(page: Page, i0: number, i1: number): Promise<string> {
  const before = await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)
  await drag(page, await xOf(page, i0), await klineY(page), await xOf(page, i1), await klineY(page))
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).not.toBe(before)
  return page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)
}

async function name(page: Page, text: string) {
  await page.getByTestId('feature-input').fill(text)
  await page.getByTestId('feature-input').press('Enter')
  await expect(page.getByTestId('box-feature')).toHaveText(text)
}

const boxesOf = (st: any, symbol: string) => st.charts.find((c: any) => c.symbol === symbol)?.boxes ?? []
const featureId = (st: any, n: string) => st.features.find((f: any) => f.name === n)?.id

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('画框、起名与词表', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => { backend = await startBackend() })
  test.afterAll(() => stopBackend(backend))

  test('拖框起名刷新后还在;轨上拖出带名字的框;改起止;属性回到 null;子框轨;改名处处生效;合并预览与拆回', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const [A, B] = [symbols[Math.floor(symbols.length / 2)], symbols[Math.floor(symbols.length / 2) + 1]]
    await page.goto('/')
    await openSymbol(page, A)
    const n = await barCount(page)

    // ── 在 K 线区拖框 → 起名 ──
    const b1 = await drawOnKline(page, n - 80, n - 40)
    await expect(page.getByTestId('feature-input')).toBeFocused()
    await name(page, '横盘')
    await expect(page.getByTestId('definition-input')).toBeVisible()      // 新特征第一次用,留一格写定义
    await page.getByTestId('definition-input').fill('窄幅震荡、量缩')
    await page.getByTestId('definition-input').press('Enter')
    await expect(page.getByTestId('definition-text')).toHaveText('窄幅震荡、量缩')
    await settled(page)
    let st = await annState(page)
    const [box1] = boxesOf(st, A)
    expect(box1.id).toBe(b1)
    expect(box1.feature).toBe(featureId(st, '横盘'))
    expect(box1.end <= TRAIN_END).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('01-drawn-named.png'), fullPage: true })

    // ── 刷新:框和名字都还在 ──
    await page.reload()
    await openSymbol(page, A)
    expect(boxesOf(await annState(page), A)).toEqual([box1])
    const yLane = await laneY(page, '横盘')
    await page.mouse.click((await xOf(page, n - 60, 'sub')), yLane)                 // 点框中间 → 选中
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')
    await expect(page.getByTestId('definition-text')).toHaveText('窄幅震荡、量缩')

    // ── 在特征轨上拖 → 新框直接带这个名字 ──
    await drag(page, await xOf(page, n - 30, 'sub'), yLane, await xOf(page, n - 20, 'sub'), yLane)
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')
    await settled(page)
    expect(boxesOf(await annState(page), A).map((b: any) => b.feature)).toEqual([box1.feature, box1.feature])

    // ── 拖框的右边改终点 ──
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    const halfBar = ((await xOf(page, n - 39, 'sub')) - (await xOf(page, n - 40, 'sub'))) / 2
    await drag(page, (await xOf(page, n - 40, 'sub')) + halfBar, yLane, await xOf(page, n - 50, 'sub'), yLane)
    await settled(page)
    expect(boxesOf(await annState(page), A).find((b: any) => b.id === b1).end).toBe(dates[n - 50])
    expect(boxesOf(await annState(page), A)).toHaveLength(2)

    // ── 子框:在大框里画一个小框,默认属于大框;子框轨写成「缩量 ⊂ 横盘」;⊂ 点掉 = detach ──
    await drawOnKline(page, n - 70, n - 60)
    await name(page, '缩量')
    await expect(page.getByTestId('parent-toggle').first()).toHaveClass(/on/)
    await laneY(page, '缩量 ⊂ 横盘')
    await page.screenshot({ path: testInfo.outputPath('02-child-lane.png'), fullPage: true })
    await page.getByTestId('parent-toggle').first().click()
    await expect(page.getByTestId('parent-toggle').first()).not.toHaveClass(/on/)
    await laneY(page, '缩量')
    await page.getByTestId('parent-toggle').first().click()
    await laneY(page, '缩量 ⊂ 横盘')

    // ── 属性三态:true → 再点一下 → null(存下的是没有这个键,不是 false)──
    await page.getByTestId('attr-input').fill('放量')
    await page.getByTestId('attr-input').press('Enter')
    await expect(page.getByTestId('attr-true-放量')).toHaveClass(/on/)
    await page.getByTestId('attr-true-放量').click()
    await expect(page.getByTestId('attr-null-放量')).toBeVisible()
    await settled(page)
    st = await annState(page)
    const shrink = boxesOf(st, A).find((b: any) => b.feature === featureId(st, '缩量'))
    expect(shrink.attrs ?? {}).not.toHaveProperty(featureId(st, '放量'))

    // ── 另一只股票上也用「横盘」(从候选里点选)──
    await openSymbol(page, B)
    await expect(page.getByTestId('box-panel')).toHaveCount(0)            // 换了图,选中的框跟着清掉
    const m = await barCount(page)
    await drawOnKline(page, m - 100, m - 70)
    await page.getByTestId('suggest-横盘').click()
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')

    // ── 改名:改一处,两只股票上处处跟着变 ──
    await page.getByTestId('annotation-tab-features').click()
    await page.getByTestId('feature-横盘').getByTestId('rename').click()
    await page.getByTestId('rename-input').fill('盘整')
    await page.getByTestId('rename-input').press('Enter')
    await expect(page.getByTestId('feature-盘整')).toBeVisible()
    await expect(page.getByTestId('feature-盘整').getByTestId('usage')).toHaveText('box×3 · attr×0')
    await laneY(page, '盘整')
    await openSymbol(page, A)
    await laneY(page, '盘整')
    await laneY(page, '缩量 ⊂ 盘整')

    // ── 合并:先显示会波及几个框,合并后被并的词不见;拆回后恢复原样 ──
    await openSymbol(page, B)
    await drawOnKline(page, m - 50, m - 30)
    await name(page, '整理')
    await settled(page)
    const beforeMerge = await annState(page)
    await page.getByTestId('annotation-tab-features').click()
    await page.getByTestId('feature-整理').getByTestId('merge-select').selectOption({ label: '盘整' })
    await expect(page.getByTestId('merge-preview')).toContainText('box×1 · attr×0')
    await page.screenshot({ path: testInfo.outputPath('03-merge-preview.png'), fullPage: true })
    await page.getByTestId('merge-apply').click()
    await expect(page.getByTestId('feature-整理')).toHaveCount(0)
    await expect(page.getByTestId('merged-整理')).toBeVisible()
    await settled(page)
    const merged = await annState(page)
    expect(boxesOf(merged, B).every((b: any) => b.feature === featureId(merged, '盘整'))).toBe(true)
    await expect(page.getByTestId('feature-盘整').getByTestId('usage')).toHaveText('box×4 · attr×0')
    // 合并记在标注文件里:刷新之后照样能拆回
    await page.reload()
    await openSymbol(page, B)
    await page.getByTestId('annotation-tab-features').click()
    await expect(page.getByTestId('merged-整理')).toContainText('box×1 · attr×0')
    await page.getByTestId('unmerge').click()
    await expect(page.getByTestId('feature-整理')).toBeVisible()
    await settled(page)
    const sortF = (s: any) => ({ ...s, features: [...s.features].sort((a: any, b: any) => (a.id < b.id ? -1 : 1)) })
    expect(sortF(await annState(page))).toEqual(sortF(beforeMerge))
    await laneY(page, '整理')
    await page.screenshot({ path: testInfo.outputPath('04-unmerged.png'), fullPage: true })

    // 全部图止于训练段末日
    for (const c of (await annState(page)).charts) for (const b of c.boxes) expect(b.end <= TRAIN_END).toBe(true)
  })
})

test.describe('冲突与指纹不符', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    // 例子文件原样带着一处冲突(两台同步前都改了「回踩」);把每批记的指纹换成另一份副本的,造出指纹不符
    backend = await startBackend((dir) => {
      for (const f of readdirSync(FIXTURE)) {
        const src = join(FIXTURE, f)
        if (!/^[A-Za-z0-9_]+-\d{8}T/.test(f)) { copyFileSync(src, join(dir, f)); continue }
        const doc = JSON.parse(readFileSync(src, 'utf8'))
        writeFileSync(join(dir, f), JSON.stringify({ ...doc, data_fingerprint: OTHER_FINGERPRINT }))
      }
    })
  })
  test.afterAll(() => stopBackend(backend))

  test('两种提示各出现一次,图照常显示;冲突看过后不再出现', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')
    await expect(page.getByTestId('notice-fingerprint')).toHaveCount(1)
    await expect(page.getByTestId('notice-fingerprint')).toContainText('mismatched')
    await expect(page.getByTestId('notice-conflict')).toHaveCount(1)
    await expect(page.getByTestId('notice-conflict')).toContainText('×1')
    await expect(page.getByTestId('notice-conflict')).toContainText('回踩')
    // 图照常显示:K 线与例子里的框都在
    expect(await barCount(page)).toBeGreaterThan(100)
    await laneY(page, '放量突破')
    await page.screenshot({ path: testInfo.outputPath('05-conflict-fingerprint.png'), fullPage: true })

    await page.getByTestId('notice-conflict-ok').click()
    await expect(page.getByTestId('notice-conflict')).toHaveCount(0)
    await page.reload()
    await openSymbol(page, 'AAPL')
    await expect(page.getByTestId('notice-fingerprint')).toHaveCount(1)
    await expect(page.getByTestId('notice-conflict')).toHaveCount(0)
  })
})
