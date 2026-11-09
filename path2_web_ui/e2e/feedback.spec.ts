import { test, expect, type Browser, type Page, type TestInfo } from '@playwright/test'
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  REPO, annState, klineY, routeTo, settled, startBackend, stopBackend, xOf, type Backend,
} from './annotateHelpers'

/**
 * 反馈(spec 6.13「检查·界面」)与删样本提示、撤销(spec 6.14 G4)。
 *
 * 用现成的 app new_step 加一份手写的 mapping(pattern W底 → new_step,会话段 tags 给两条反馈挂原因标签;e2e 后端从
 * 临时目录读它,见 e2e/annotationBackend.py),标注用 tests/path2_web/fixtures/annotation_grouping_v1 的例子批次
 * (指纹换成测试后端本机副本的)。状态接口在临时后端上真跑 app。
 *
 * 股票 CRNC。日期不写死:开始前在 compare 里读一遍图上 hits 行的族(族底线那一行带族起点与全部买点日),现挑——
 *   F = 买点最多的一族,G = 次多的一族,K = 拖选用的一族(F、G 以外的,没有就用 G);
 *   red   = F 的第二个买点日上一条 point 反馈 → matched、朱红,会话标签 for_tuning;
 *   plain = F 范围里一个不是买点、但前后一天有买点的日子上一条 point 反馈 → unmatched、常色;
 *   lost  = F 之前一段没有买点的日子上一条 family 反馈,起点那天没有任何事件起步 → lost,会话标签 unhandled;
 *   另放一个 W底 的正样本在 G 的第二个买点日(pos sample inside),一个框在 lost 那段上(先选中框再点族)。
 * 这几条经后端的批次接口写进临时标注目录(同界面的保存,过同一套校验)。
 *
 * 覆盖:
 * 1. 反馈带三种颜色、会话标签(侧栏与悬停)、侧栏排序;annotate、app 模式下没有反馈带、工具与侧栏页,Shift+F 只在
 *    compare 生效。截图 ①(三种状态连同 hits 行)。
 * 2. 点 ▼、点琥珀格弹 point 面板,点族的命中区得到 family 范围与起点;面板不抢焦点、←/→ 仍走 hit、Esc 先关面板、
 *    点别处关、焦点在按钮上按 Enter 也是保存;同范围打开那条、改、删与撤销;先选中框再点族,框的选中取消;
 *    off_pattern 的分段按钮悬停时 band 加亮。截图 ②(分段按钮展开、鼠标停在一个分段上)。
 * 3. feedback 工具:Shift+F / 按钮点亮、Esc 熄灭、点一下不熄;拖出没有买点的范围不弹、提示 no buy in range;
 *    拖出有买点的范围,松手后面板还在、用一次熄灭;redraw 把 family 反馈改成拖出的 range(同编号、去掉 family_start)。
 * 4. 侧栏点行跳到 compare(竖线停在范围起点、选中那条);落在 compare 的链接;落不成时提示;行上 delete。
 * 5. 删样本:有只服务它的框时先问(yes / no / cancel),删除可撤最近一次。
 *
 * 环境变量 PATH2_E2E_SHOTS 给了目录时,两张截图另复制一份到那里(给人过目)。
 */

const SYMBOL = 'CRNC'
const PATTERN = 'W底'
const APP = 'new_step'
const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const RED = 'f-e2e-901'
const PLAIN = 'f-e2e-902'
const LOST = 'f-e2e-903'
const POS_SAMPLE = 's-e2e-900'
const BOX = 'b-e2e-899'
const MAPPING = [
  `pattern: ${PATTERN}`,
  'features:',
  '  w-pc-3: plateau',
  'notes:',
  '  plateau: 站上新平台(旧平台 → 阶跃 → 新平台)',
  '  old_plat: 旧平台',
  '  step: 阶跃',
  '  new_plat: 新平台',
  '  today: 当天(买点)',
  'session:',
  '  tags:',
  `    ${RED}: for_tuning`,
  `    ${LOST}: unhandled`,
  '',
].join('\n')
const VERMILION = '#E8875A'
const ORANGE = '#E69F00'
const EDGE = '#555555'
const HOVER_STROKE = 'rgb(26, 128, 186)'

/** 一族(K 线下标):起点、全部买点日。 */
interface Fam { start: number; buys: number[] }
/** 开始前现挑的日子(见文件头)。 */
interface Plan {
  dates: string[]
  appVer: string
  F: Fam
  G: Fam
  K: Fam
  red: string
  plain: string
  lost: { start: string; end: string }
  pos: string
}

let backend: Backend | null = null
let plan: Plan

// ───────────────────────── 页面上的小工具 ─────────────────────────

const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
const annOf = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.ann()[key], k)
const fbOf = (page: Page, k: string) => page.evaluate(key => JSON.parse(JSON.stringify((window as any).__e2e.fb()[key] ?? null)), k)
const runSymbol = (page: Page) => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null)
const feedbackOf = (st: any, symbol = SYMBOL): any[] => st.charts.find((c: any) => c.symbol === symbol)?.feedback ?? []
const panel = (page: Page) => page.getByTestId('feedback-panel')

async function waitChart(page: Page, symbol: string) {
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
  await expect.poll(() => annOf(page, 'status')).toBe('ready')
}

async function pickPattern(page: Page, text: string) {
  await page.getByTestId('top-pattern-button').click()
  await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => annOf(page, 'currentPattern')).toBe(text)
}

async function enterCompare(page: Page) {
  await page.getByTestId('mode-compare').click()
  await expect.poll(() => view(page, 'mode')).toBe('compare')
  await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartSub().getOption()?.series ?? []).some((s: any) => s.name === 'bracket-lines')))
    .toBe(true)
}

/** 打开 CRNC、当前 pattern 设为 W底、进 compare,等反馈状态取到。 */
async function openCompare(page: Page, day: string) {
  await routeTo(page, backend!)
  await page.goto(`/#symbol=${SYMBOL}&date=${day}`)
  await waitChart(page, SYMBOL)
  await pickPattern(page, PATTERN)
  await enterCompare(page)
  await expect.poll(() => fbOf(page, 'loading')).toBe(false)
}

/** 图窗缩到 K 线下标 [i0, i1](主副图联动)。缩放会收起反馈面板,所以只在开面板之前调。 */
async function zoomTo(page: Page, i0: number, i1: number) {
  await page.evaluate(([a, b]) => {
    const main = (window as any).__e2e.chartMain()
    const n = main.getOption().xAxis[0].data.length
    main.dispatchAction({ type: 'dataZoom', start: Math.max(0, a) / n * 100, end: Math.min(n, b + 1) / n * 100 })
  }, [i0, i1] as const)
  await page.waitForTimeout(300)
}

interface ItemBox { i: number; d: any; x: number; y: number; w: number; h: number }

/** 副图某个系列各数据项画出来的范围(页面坐标);child 给了就只取组里第几个子元素(格的琥珀底、反馈记号的底)。 */
async function itemBoxes(page: Page, series: string, child: number | null = null): Promise<ItemBox[]> {
  return page.evaluate(([name, child]) => {
    const chart = (window as any).__e2e.chartSub()
    const s = chart.getModel().getSeriesByName(name)[0]
    if (!s) return []
    const data = s.getData()
    const base = document.querySelector('.sub-inner')!.getBoundingClientRect()
    const out: any[] = []
    for (let i = 0; i < data.count(); i++) {
      let el = data.getItemGraphicEl(i)
      if (el && child !== null) el = el.childAt?.(child)
      if (!el) continue
      const r = el.getBoundingRect().clone()
      const m = el.getComputedTransform ? el.getComputedTransform() : el.transform
      if (m) r.applyTransform(m)
      out.push({ i, d: JSON.parse(JSON.stringify(data.getRawDataItem(i) ?? null)),
                 x: base.left + r.x, y: base.top + r.y, w: r.width, h: r.height })
    }
    return out
  }, [series, child] as const)
}

/** 反馈带上各条记号的样子:编号、底色、描边、描边宽。 */
async function stripMarks(page: Page): Promise<{ id: string; fill: string; stroke: string; lineWidth: number }[]> {
  return page.evaluate(() => {
    const s = (window as any).__e2e.chartSub().getModel().getSeriesByName('feedback-strip')[0]
    if (!s) return []
    const data = s.getData()
    const out: any[] = []
    for (let i = 0; i < data.count(); i++) {
      const rect = data.getItemGraphicEl(i)?.childAt?.(0)
      if (!rect) continue
      out.push({ id: data.getRawDataItem(i).feedback_id, fill: String(rect.style.fill), stroke: String(rect.style.stroke),
                 lineWidth: rect.style.lineWidth })
    }
    return out
  })
}

/** 让副图里 [top, bottom] 这一段露在可见区里(副图外框能上下滚)。滚动会收起反馈面板,只在开面板之前调。
 *  返回滚了没有(滚了要重取坐标)。 */
async function reveal(page: Page, top: number, bottom: number): Promise<boolean> {
  const d = await page.evaluate(([t, b]) => {
    const o = document.querySelector('.sub-outer') as HTMLElement
    const r = o.getBoundingClientRect()
    const shift = t < r.top + 4 ? t - r.top - 20 : b > r.bottom - 4 ? b - r.bottom + 20 : 0
    if (shift) o.scrollTop += shift
    return shift
  }, [top, bottom] as const)
  if (d) await page.waitForTimeout(200)
  return d !== 0
}

/** 找到某个系列里满足条件的那一项,滚到看得见,返回它的范围。 */
async function findItem(page: Page, series: string, pred: (b: ItemBox) => boolean, child: number | null = null): Promise<ItemBox> {
  for (let k = 0; k < 2; k++) {
    const hit = (await itemBoxes(page, series, child)).find(pred)
    expect(hit, `${series} 里没有要找的那一项`).toBeTruthy()
    if (!(await reveal(page, hit!.y, hit!.y + hit!.h))) return hit!
  }
  return (await itemBoxes(page, series, child)).find(pred)!
}

const inside = (b: ItemBox, x: number, y: number, pad = 1) =>
  x >= b.x - pad && x <= b.x + b.w + pad && y >= b.y - pad && y <= b.y + b.h + pad

/** 点 ▼(买在 day 那天)。 */
async function clickBuy(page: Page, day: number) {
  const b = await findItem(page, 'brackets', x => x.d?.kind === 'buy' && x.d.buy_day === day)
  await page.mouse.click(b.x + b.w / 2, b.y + b.h * 0.35)
}

/** 点一个格:那一列有 ▼ 的格,点它下半截(▼ 只占格的上半截)。返回格那一列的买点日下标。 */
async function clickMark(page: Page, pred: (d: any) => boolean): Promise<number> {
  const b = await findItem(page, 'brackets', x => x.d?.kind === 'mark' && typeof x.d.buy_day === 'number' && pred(x.d), 0)
  await page.mouse.click(b.x + Math.min(b.w / 2, 3), b.y + b.h * 0.85)
  return b.d.buy_day
}

/** 点一族的透明命中区:在族底线那一行里找一个不压在格和 ▼ 上、又在图区里的点。 */
async function clickFamily(page: Page, start: number) {
  const fam = await findItem(page, 'bracket-lines', x => x.d?.family_start === start, 0)
  const marks = await itemBoxes(page, 'brackets')
  const plot = await page.evaluate(() => {
    const r = document.querySelector('.sub-inner')!.getBoundingClientRect()
    const g = (window as any).__e2e.chartSub().getOption().grid[0]
    return { left: r.left + g.left, right: r.right - g.right }
  })
  const y = fam.y + fam.h * 0.4
  for (let x = Math.max(fam.x + 2, plot.left + 2); x < Math.min(fam.x + fam.w - 2, plot.right - 2); x += 2) {
    if (!marks.some(m => inside(m, x, y, 2))) {
      await page.mouse.click(x, y)
      return
    }
  }
  throw new Error(`族 ${start} 的那一行上找不到不压在格上的空处`)
}

/** 点反馈带上某条反馈的记号。 */
async function clickStrip(page: Page, id: string) {
  const b = await findItem(page, 'feedback-strip', x => x.d?.feedback_id === id, 0)
  await page.mouse.click(b.x + b.w / 2, b.y + b.h / 2)
}

/** 焦点在不在反馈面板里。 */
const focusInPanel = (page: Page) => page.evaluate(() =>
  !!document.querySelector('[data-testid="feedback-panel"]')?.contains(document.activeElement))
const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())

/** 截图:挂在测试结果里;PATH2_E2E_SHOTS 给了目录时另复制一份。 */
async function shot(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(name)
  await page.screenshot({ path, scale: 'device', fullPage: true })
  const dir = process.env.PATH2_E2E_SHOTS
  if (dir) {
    mkdirSync(dir, { recursive: true })
    copyFileSync(path, join(dir, name))
  }
}

// ───────────────────────── 准备:临时后端、现挑日子、写进几条反馈 ─────────────────────────

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

async function postOps(b: Backend, ops: any[]) {
  const r = await fetch(`${b.base}/annotations/batch`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ops }),
  })
  expect(r.status, await r.clone().text()).toBe(200)
}

/** 在 compare 里读一遍 CRNC 上的族与事件起点,挑出要用的日子(见文件头)。 */
async function makePlan(browser: Browser): Promise<Plan> {
  const page = await browser.newPage({ viewport: { width: 2560, height: 1440 } })
  await openCompare(page, '2025-01-02')
  const got = await page.evaluate(() => {
    const e2e = (window as any).__e2e
    const fams = (e2e.chartSub().getOption().series.find((s: any) => s.name === 'bracket-lines')?.data ?? [])
      .map((d: any) => ({ start: d.family_start as number, buys: [...(d.buy_days ?? [])].sort((a: number, b: number) => a - b) }))
    const starts = (e2e.view.effectiveAnalysis?.events ?? []).map((e: any) => e.start_idx as number)
    return { fams, starts, dates: e2e.chartMain().getOption().xAxis[0].data as string[],
             appVer: e2e.view.linkedRun?.scan?.app_ver ?? null }
  })
  await page.close()
  const { dates, appVer } = got
  expect(appVer, '单股预览要带回 app_ver').toBeTruthy()
  const fams: Fam[] = got.fams.filter((f: Fam) => f.buys.length > 0).sort((a: Fam, b: Fam) => b.buys.length - a.buys.length)
  expect(fams.length, `${SYMBOL} 上 ${APP} 至少要有两族买点`).toBeGreaterThanOrEqual(2)
  const [F, G] = fams
  expect(F.buys.length, '买点最多的一族至少 3 天').toBeGreaterThanOrEqual(3)
  expect(G.buys.length, '次多的一族至少 2 天').toBeGreaterThanOrEqual(2)
  const K = fams.slice(2).sort((a, b) => b.start - a.start)[0] ?? G
  const buys = new Set(fams.flatMap(f => f.buys))
  const starts = new Set<number>(got.starts)
  // plain:F 范围里不是买点、前后一天有买点的日子
  let p = -1
  for (let i = F.buys[0] + 1; i < F.buys[F.buys.length - 1]; i++) {
    if (!buys.has(i) && (buys.has(i - 1) || buys.has(i + 1))) { p = i; break }
  }
  expect(p, 'F 的范围里要有一天不是买点').toBeGreaterThan(0)
  // lost:F 之前一段 6 天,没有买点、起点那天没有任何事件起步
  let d = -1
  for (let i = F.buys[0] - 8; i > 10; i--) {
    let ok = !starts.has(i)
    for (let j = i; j <= i + 5 && ok; j++) ok = !buys.has(j)
    if (ok) { d = i; break }
  }
  expect(d, 'F 之前要有一段没有买点的日子').toBeGreaterThan(0)
  return { dates, appVer, F, G, K, red: dates[F.buys[1]], plain: dates[p],
           lost: { start: dates[d], end: dates[d + 5] }, pos: dates[G.buys[1]] }
}

async function seed(b: Backend, pl: Plan) {
  const fb = (id: string, v: Record<string, unknown>) => ({
    kind: 'feedback', id, base: null,
    value: { id, symbol: SYMBOL, pattern: PATTERN, app_id: APP, app_ver: pl.appVer, source: 'picked', ...v },
  })
  const box = pl.dates[pl.dates.indexOf(pl.lost.start) + 3]
  await postOps(b, [
    { kind: 'sample', id: POS_SAMPLE, base: null,
      value: { id: POS_SAMPLE, symbol: SYMBOL, date: pl.pos, pattern: PATTERN, judgment: 'pos', members: [] } },
    { kind: 'box', id: BOX, base: null, value: { id: BOX, symbol: SYMBOL, feature: 'w-pc-1', start: pl.lost.start, end: box } },
    fb(RED, { start: pl.red, end: pl.red, target: 'point', answer: 'neg', note: '追在阶跃之后太远' }),
    fb(PLAIN, { start: pl.plain, end: pl.plain, target: 'point', answer: 'off_pattern', segments: ['plateau'] }),
    fb(LOST, { start: pl.lost.start, end: pl.lost.end, target: 'family', family_start: pl.lost.start,
               answer: 'off_pattern', note: '这一段不是平台' }),
  ])
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('反馈(new_step + 手写 mapping,CRNC)', () => {
  test.setTimeout(600_000)
  test.beforeAll(async ({ browser }) => {
    test.setTimeout(300_000)
    backend = await startBackend(undefined, { [APP]: MAPPING })
    await putFixture(backend)
    plan = await makePlan(browser)
    await seed(backend, plan)
  })
  test.afterAll(() => stopBackend(backend))

  test('反馈带三种颜色、会话标签、侧栏排序;annotate 与 app 下没有反馈;Shift+F 只在 compare 生效', async ({ page }, testInfo) => {
    const { dates, F } = plan
    await routeTo(page, backend!)
    await page.goto(`/#symbol=${SYMBOL}&date=${plan.red}`)
    await waitChart(page, SYMBOL)
    await pickPattern(page, PATTERN)

    // annotate:没有 feedback 工具、侧栏没有 feedback 页,Shift+F 不点亮
    await expect(page.getByTestId('tool-box')).toBeVisible()
    await expect(page.getByTestId('tool-feedback')).toHaveCount(0)
    await expect(page.getByTestId('annotation-tab-feedback')).toHaveCount(0)
    await blur(page)
    await page.keyboard.press('Shift+F')
    await page.waitForTimeout(200)
    expect(await annOf(page, 'tool')).toBeNull()

    await enterCompare(page)
    await expect(page.getByTestId('tool-feedback')).toBeVisible()
    // 状态接口真跑 app:三条各是 matched(朱红)、unmatched、lost;会话标签照 mapping 的会话段
    await expect.poll(async () => {
      const s = await fbOf(page, 'statusById')
      return [RED, PLAIN, LOST].map(id => `${s?.[id]?.status}:${s?.[id]?.red}:${s?.[id]?.tag}`)
    }, { timeout: 60_000 }).toEqual(['matched:true:for_tuning', 'unmatched:false:null', 'lost:false:unhandled'])

    // 反馈带:每条一个记号,朱红 / 白底橙描边 / 白底深灰描边
    const li = dates.indexOf(plan.lost.start)
    await zoomTo(page, li - 6, F.buys[F.buys.length - 1] + 6)
    await expect.poll(async () => (await stripMarks(page)).map(m => m.id).sort()).toEqual([RED, PLAIN, LOST].sort())
    const marks = Object.fromEntries((await stripMarks(page)).map(m => [m.id, m]))
    expect([marks[RED].fill.toUpperCase(), marks[RED].stroke.toUpperCase()]).toEqual([VERMILION, EDGE.toUpperCase()])
    expect([marks[LOST].fill.toLowerCase(), marks[LOST].stroke.toUpperCase()]).toEqual(['#ffffff', ORANGE])
    expect([marks[PLAIN].fill.toLowerCase(), marks[PLAIN].stroke.toLowerCase()]).toEqual(['#ffffff', EDGE])
    // 反馈带在 hit 行下面
    const strip = await itemBoxes(page, 'feedback-strip', 0)
    const hitRows = await itemBoxes(page, 'brackets')
    expect(Math.min(...strip.map(b => b.y))).toBeGreaterThan(Math.max(...hitRows.map(b => b.y + b.h)) - 1)

    // 悬停朱红那条:写全答案、理由、状态、会话标签
    const red = strip.find(b => b.d.feedback_id === RED)!
    await page.mouse.move(red.x + red.w / 2, red.y + red.h / 2)
    const tip = page.locator('body > div').filter({ hasText: 'tag: for_tuning' })
    await expect(tip.first()).toBeVisible()
    await expect(tip.first()).toContainText('status: matched')
    await expect(tip.first()).toContainText('answer: neg')
    await page.mouse.move(10, 10)

    // 侧栏 feedback 页:朱红在前、lost 其次、常色在后;朱红与 lost 挂会话标签,常色不挂
    await page.getByTestId('annotation-tab-feedback').click()
    await expect(page.getByTestId('feedback-page')).toBeVisible()
    await expect(page.getByTestId('feedback-loading')).toHaveCount(0)
    const rows = page.getByTestId('feedback-row')
    await expect(rows).toHaveCount(3)
    expect(await rows.evaluateAll(els => els.map(e => [e.getAttribute('data-id'), e.getAttribute('data-tone')])))
      .toEqual([[RED, 'red'], [LOST, 'lost'], [PLAIN, 'plain']])
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${RED}"] [data-testid="feedback-row-tag"]`)).toHaveText('for_tuning')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${LOST}"] [data-testid="feedback-row-tag"]`)).toHaveText('unhandled')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"] [data-testid="feedback-row-tag"]`)).toHaveCount(0)
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${RED}"] [data-testid="feedback-row-status"]`)).toHaveText('matched')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${LOST}"] [data-testid="feedback-row-status"]`)).toHaveText('lost')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"] [data-testid="feedback-row-status"]`)).toHaveText('unmatched')
    await shot(page, testInfo, 'feedback-strip-three-states.png')

    // Shift+F 在 compare 下点亮 / 熄灭
    await blur(page)
    await page.keyboard.press('Shift+F')
    await expect.poll(() => annOf(page, 'tool')).toBe('feedback')
    await expect(page.getByTestId('tool-feedback')).toHaveClass(/\bon\b/)
    await page.keyboard.press('Shift+F')
    await expect.poll(() => annOf(page, 'tool')).toBeNull()

    // app 模式:不画反馈带,族那一行不可点,没有 feedback 工具与侧栏页,Shift+F 不点亮
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await expect.poll(() => page.evaluate(() =>
      ((window as any).__e2e.chartSub().getOption()?.series ?? []).some((s: any) => s.name === 'bracket-lines'))).toBe(true)
    const series = await page.evaluate(() => ((window as any).__e2e.chartSub().getOption().series ?? [])
      .map((s: any) => ({ name: s.name, silent: !!s.silent })))
    expect(series.map(s => s.name)).not.toContain('feedback-strip')
    expect(series.find(s => s.name === 'bracket-lines')!.silent).toBe(true)
    await expect(page.getByTestId('tool-feedback')).toHaveCount(0)
    await expect(page.getByTestId('annotation-tab-feedback')).toHaveCount(0)
    await expect(page.getByTestId('feedback-page')).toHaveCount(0)
    await blur(page)
    await page.keyboard.press('Shift+F')
    await page.waitForTimeout(200)
    expect(await annOf(page, 'tool')).toBeNull()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('点 ▼ / 格 / 族弹面板;不抢焦点、Esc 先关面板、点别处关、按钮上 Enter 也保存;同范围打开那条、改、删与撤销;选中的框被取消;分段悬停 band 加亮', async ({ page }, testInfo) => {
    const { dates, F, G } = plan
    await openCompare(page, plan.pos)
    await zoomTo(page, Math.min(F.start, G.start) - 3, Math.max(F.buys.at(-1)!, G.buys.at(-1)!) + 4)
    const g0 = G.buys[0], g0Date = dates[g0]

    // ── 点 ▼:point 面板,范围是那一天;不抢焦点 ──
    await clickBuy(page, g0)
    await expect(panel(page)).toBeVisible()
    await expect(panel(page)).toHaveAttribute('data-target', 'point')
    await expect(panel(page)).toHaveAttribute('data-editing', '')
    await expect(page.getByTestId('feedback-symbol')).toHaveText(SYMBOL)
    await expect(page.getByTestId('feedback-span')).toHaveText(g0Date)
    await expect(page.getByTestId('feedback-answer-neg')).toBeVisible()
    await expect(page.getByTestId('feedback-answer-off_pattern')).toBeVisible()
    await expect(page.getByTestId('feedback-note')).toHaveCount(0)              // 初始只有两个按钮
    await expect(page.getByTestId('feedback-pos-inside')).toHaveCount(0)
    expect(await focusInPanel(page)).toBe(false)
    expect(await view(page, 'currentDay')).toBe(g0)
    // ←/→ 照旧在族里走(按键不归面板)
    const hit0 = await view(page, 'selectedHitId')
    expect(hit0).not.toBeNull()
    await page.keyboard.press('ArrowRight')
    await expect.poll(() => view(page, 'selectedHitId')).not.toBe(hit0)

    // ── Esc 第一下只关面板:当前日、当家行都不动 ──
    await clickBuy(page, g0)
    await expect(panel(page)).toBeVisible()
    const before = [await view(page, 'currentDay'), await view(page, 'activeFamilyKey')]
    expect(before[1]).not.toBeNull()
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)
    expect([await view(page, 'currentDay'), await view(page, 'activeFamilyKey')]).toEqual(before)

    // ── 点别处(主图 K 线区)关,不存 ──
    await clickBuy(page, g0)
    await expect(panel(page)).toBeVisible()
    await page.getByTestId('feedback-answer-neg').click()
    await page.mouse.click(await xOf(page, g0 - 2), await klineY(page))
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)).toEqual([])

    // ── 作答 neg:光标进 note;Enter 保存;记号出现 ──
    await clickBuy(page, g0)
    await page.getByTestId('feedback-answer-neg').click()
    await expect(page.getByTestId('feedback-note')).toBeFocused()
    await page.getByTestId('feedback-note').fill('放量不够')
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const saved = feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)
    expect(saved).toHaveLength(1)
    const pid: string = saved[0].id
    expect(pid).toMatch(/^f-e2e-\d+$/)
    expect(saved[0]).toEqual({ id: pid, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: g0Date, end: g0Date,
                               target: 'point', source: 'picked', answer: 'neg', note: '放量不够' })
    await expect.poll(async () => (await stripMarks(page)).map(m => m.id)).toContain(pid)
    await expect.poll(async () => (await fbOf(page, 'statusById'))?.[pid]?.status).toBe('matched')

    // ── 同范围不重复:再点那个 ▼ 打开这一条(预填、多 delete / redraw);焦点在按钮上按 Enter 也是保存 ──
    await clickBuy(page, g0)
    await expect(panel(page)).toHaveAttribute('data-editing', pid)
    await expect(page.getByTestId('feedback-answer-neg')).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue('放量不够')
    await expect(page.getByTestId('feedback-delete')).toBeVisible()
    await expect(page.getByTestId('feedback-redraw')).toBeVisible()
    await page.getByTestId('feedback-note').fill('放量不够,而且离阶跃太远')
    await page.getByTestId('feedback-answer-off_pattern').focus()
    await page.keyboard.press('Enter')                                       // 浏览器默认会「点按钮」;归面板就是保存
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const edited = feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)
    expect(edited.map(f => [f.id, f.answer, f.note])).toEqual([[pid, 'neg', '放量不够,而且离阶跃太远']])

    // ── 缺东西时 Enter 不存,标出缺什么 ──
    await clickBuy(page, plan.dates.indexOf(plan.pos))
    await expect(page.getByTestId('feedback-pos-inside')).toBeVisible()      // 那天放着当前 pattern 的正样本
    await page.getByTestId('feedback-answer-neg').click()
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem="note"]')).toBeVisible()
    await page.keyboard.press('Escape')                                      // 焦点在 note 里也是先关面板
    await expect(panel(page)).toHaveCount(0)

    // ── 点格(那一列有 ▼ 的琥珀格):point 面板,范围是那一列的买点日 ──
    const redI = dates.indexOf(plan.red)
    const day = await clickMark(page, d => d.family_start === F.start && d.buy_day !== redI)
    await expect(panel(page)).toHaveAttribute('data-target', 'point')
    await expect(page.getByTestId('feedback-span')).toHaveText(dates[day])
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)

    // ── 先选中一个框,再点族的命中区:框的选中取消、Delete 删不到它;family 面板,范围 = 全部 ▼ 的最早到最晚 ──
    await page.evaluate(id => (window as any).__e2e.ann().selectBox(id), BOX)
    await expect.poll(() => annOf(page, 'selectedBoxId')).toBe(BOX)
    await clickFamily(page, G.start)
    await expect(panel(page)).toBeVisible()
    await expect.poll(() => annOf(page, 'selectedBoxId')).toBeNull()
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await expect(page.getByTestId('feedback-span')).toHaveText(`${dates[G.buys[0]]} – ${dates[G.buys.at(-1)!]}`)
    await expect(page.getByTestId('feedback-pos-inside')).toBeVisible()
    await page.keyboard.press('Delete')
    await settled(page)
    expect((await annState(page)).charts.find((c: any) => c.symbol === SYMBOL).boxes.map((b: any) => b.id)).toContain(BOX)

    // ── off_pattern:分段按钮(根 node 保留),悬停时那条 band 加亮;截图 ② ──
    await expect(panel(page)).toBeVisible()
    await page.getByTestId('feedback-answer-off_pattern').click()
    const segs = page.getByTestId('feedback-segment')
    await expect(segs.first()).toBeVisible()
    const nodes = await segs.evaluateAll(els => els.map(e => e.getAttribute('data-node')))
    expect(nodes).toContain('plateau')
    const hoverRect = () => page.evaluate(stroke => JSON.stringify((window as any).__e2e.chartSub().getOption().graphic ?? [])
      .includes(stroke), HOVER_STROKE)
    let lit: string | null = null
    // 先试子 node(截图里加亮的那条 band 和根 node 那条分得开),最后试根 node
    for (const n of [...nodes.filter(x => x !== 'plateau'), 'plateau']) {
      await page.locator(`[data-testid="feedback-segment"][data-node="${n}"]`).hover()
      await page.waitForTimeout(150)
      if (await hoverRect()) { lit = n; break }
    }
    expect(lit, '悬停某个分段按钮时,它所在的 band 要加亮').not.toBeNull()
    await expect(page.locator(`[data-testid="feedback-segment"][data-node="${lit}"]`)).toHaveAttribute('title', /\S/)
    await shot(page, testInfo, 'feedback-panel-segments-hover.png')
    await page.getByTestId('feedback-target').hover()
    await expect.poll(hoverRect).toBe(false)
    await page.locator(`[data-testid="feedback-segment"][data-node="${lit}"]`).click()
    await expect(page.locator(`[data-testid="feedback-segment"][data-node="${lit}"]`)).toHaveClass(/\bon\b/)
    expect(await focusInPanel(page)).toBe(false)                             // 点按钮不夺焦点
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const fam = feedbackOf(await annState(page)).filter(f => f.target === 'family' && f.family_start === dates[G.start])
    expect(fam.map(f => [f.start, f.end, f.answer, f.segments])).toEqual([[dates[G.buys[0]], dates[G.buys.at(-1)!], 'off_pattern', [lit]]])

    // ── 点记号打开那条、选中它(描边加粗);delete 删掉,提示条 undo 放回 ──
    await clickStrip(page, pid)
    await expect(panel(page)).toHaveAttribute('data-editing', pid)
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(pid)
    await expect.poll(async () => (await stripMarks(page)).find(m => m.id === pid)?.lineWidth).toBe(3)
    await page.getByTestId('feedback-delete').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).map(f => f.id)).not.toContain(pid)
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'feedback')
    await page.getByTestId('notice-undo-btn').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).find(f => f.id === pid)).toMatchObject(
      { start: g0Date, end: g0Date, answer: 'neg', note: '放量不够,而且离阶跃太远' })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('feedback 工具:点亮与熄灭;没有买点的范围不弹、提示 no buy in range;拖完松手面板还在;redraw 改成拖出的 range', async ({ page }) => {
    const { dates, K } = plan
    await openCompare(page, plan.lost.start)
    const tool = page.getByTestId('tool-feedback')

    // 按钮点亮,Esc 熄灭;点一下不拖,工具不熄
    await tool.click()
    await expect.poll(() => annOf(page, 'tool')).toBe('feedback')
    await blur(page)
    await page.keyboard.press('Escape')
    await expect.poll(() => annOf(page, 'tool')).toBeNull()
    const li = dates.indexOf(plan.lost.start), le = dates.indexOf(plan.lost.end)
    await zoomTo(page, li - 20, le + 20)
    await tool.click()
    await page.mouse.click(await xOf(page, li - 4), await klineY(page))
    await page.waitForTimeout(200)
    expect(await annOf(page, 'tool')).toBe('feedback')
    await expect(panel(page)).toHaveCount(0)

    // 拖出一段没有买点的范围:拖动中有贯穿主副图的竖带;松手工具熄灭,不弹面板,在松开处提示 no buy in range
    const y = await klineY(page)
    await page.mouse.move(await xOf(page, li), y)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, li + 2), y, { steps: 4 })
    await page.mouse.move(await xOf(page, le), y, { steps: 4 })
    await expect(page.getByTestId('feedback-range-band')).toBeVisible()
    await page.mouse.up()
    await expect(page.getByTestId('feedback-range-band')).toHaveCount(0)
    await expect(page.getByTestId('feedback-no-buy')).toHaveText('no buy in range')
    await expect(panel(page)).toHaveCount(0)
    expect(await annOf(page, 'tool')).toBeNull()
    await expect(page.getByTestId('feedback-no-buy')).toHaveCount(0, { timeout: 5_000 })

    // 在副图 app 区(hit 行)拖出有买点的范围:松手后面板还在(浏览器补派的 click 不把它关掉),工具熄灭
    const b0 = K.buys[0]
    await zoomTo(page, b0 - 25, b0 + 15)
    const row = await findItem(page, 'bracket-lines', x => x.d?.family_start === K.start, 0)
    const ry = row.y + row.h / 2
    await feedbackOn(page)
    await page.mouse.move(await xOf(page, b0 - 1, 'sub'), ry)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, b0, 'sub'), ry, { steps: 4 })
    await page.mouse.move(await xOf(page, b0 + 1, 'sub'), ry, { steps: 4 })
    await page.mouse.up()
    await expect(panel(page)).toBeVisible()
    await page.waitForTimeout(500)
    await expect(panel(page)).toBeVisible()
    await expect(panel(page)).toHaveAttribute('data-target', 'range')
    await expect(page.getByTestId('feedback-span')).toHaveText(`${dates[b0 - 1]} – ${dates[b0 + 1]}`)
    expect(await annOf(page, 'tool')).toBeNull()
    expect(await focusInPanel(page)).toBe(false)
    await page.getByTestId('feedback-answer-off_pattern').click()
    await page.getByTestId('feedback-note').fill('阶跃那根太弱')
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const rg = feedbackOf(await annState(page)).filter(f => f.target === 'range')
    expect(rg.map(f => [f.start, f.end, f.answer, f.note])).toEqual([[dates[b0 - 1], dates[b0 + 1], 'off_pattern', '阶跃那根太弱']])

    // redraw:点 lost 那条(family)的记号 → redraw → 工具亮;拖出新范围,面板带着原答案;Enter 存成同编号的 range
    await zoomTo(page, li - 6, le + 6)
    await clickStrip(page, LOST)
    await expect(panel(page)).toHaveAttribute('data-editing', LOST)
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await page.getByTestId('feedback-redraw').click()
    await expect(panel(page)).toHaveCount(0)
    await expect.poll(() => annOf(page, 'tool')).toBe('feedback')
    await zoomTo(page, b0 - 25, b0 + 15)
    await page.mouse.move(await xOf(page, b0 - 3), y)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, b0), y, { steps: 4 })
    await page.mouse.move(await xOf(page, b0 + 3), y, { steps: 4 })
    await page.mouse.up()
    await expect(panel(page)).toHaveAttribute('data-editing', LOST)
    await expect(panel(page)).toHaveAttribute('data-target', 'range')
    await expect(page.getByTestId('feedback-answer-off_pattern')).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue('这一段不是平台')
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const re = feedbackOf(await annState(page)).find(f => f.id === LOST)
    expect(re).toEqual({ id: LOST, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: dates[b0 - 3],
                         end: dates[b0 + 3], target: 'range', source: 'picked', answer: 'off_pattern', note: '这一段不是平台' })
    await expect.poll(async () => (await fbOf(page, 'statusById'))?.[LOST]?.status).toBe('matched')
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('侧栏点行跳到 compare、竖线停在范围起点并选中那条;落在 compare 的链接;落不成时提示;行上 delete', async ({ page }) => {
    const { dates } = plan
    // 从 AAPL 的 compare 出发
    await routeTo(page, backend!)
    await page.goto('/#symbol=AAPL&date=2024-03-11')
    await waitChart(page, 'AAPL')
    await pickPattern(page, PATTERN)
    await enterCompare(page)
    await page.getByTestId('annotation-tab-feedback').click()
    const row = page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"]`)
    await expect(row).toBeVisible()
    await expect.poll(async () => (await fbOf(page, 'statusById'))?.[PLAIN]?.status).toBe('unmatched')

    // 点 plain 那一行:换到 CRNC、仍在 compare;当前日竖线停在范围起点;选中那条(行加框、记号描边加粗)
    await row.click()
    await waitChart(page, SYMBOL)
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe(SYMBOL)
    expect(await view(page, 'mode')).toBe('compare')
    const crnc: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    await expect.poll(() => view(page, 'currentDay')).toBe(crnc.indexOf(plan.plain))
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(PLAIN)
    await expect(row).toHaveClass(/\bon\b/)
    await expect.poll(async () => (await stripMarks(page)).find(m => m.id === PLAIN)?.lineWidth).toBe(3)
    // 图窗包住那段日期
    const win = await page.evaluate(() => {
      const m = (window as any).__e2e.chartMain(), dz = m.getOption().dataZoom[0], n = m.getOption().xAxis[0].data.length
      return [Math.floor(dz.start / 100 * n), Math.ceil(dz.end / 100 * n)]
    })
    expect(win[0]).toBeLessThanOrEqual(crnc.indexOf(plan.plain))
    expect(win[1]).toBeGreaterThanOrEqual(crnc.indexOf(plan.plain))
    expect(crnc).toEqual(dates)

    // 落在 compare 的链接:从 annotate 的 AAPL 进来,落到 CRNC 的 compare、竖线停在那天
    await page.getByTestId('mode-annotate').click()
    await page.evaluate(() => { location.hash = '#symbol=AAPL&date=2024-03-11' })
    await waitChart(page, 'AAPL')
    await page.evaluate(([s, d, p]) => { location.hash = `#symbol=${s}&date=${d}&pattern=${encodeURIComponent(p)}&mode=compare` },
                        [SYMBOL, plan.red, PATTERN] as const)
    await waitChart(page, SYMBOL)
    await expect.poll(() => view(page, 'mode')).toBe('compare')
    await expect.poll(() => view(page, 'currentDay')).toBe(dates.indexOf(plan.red))
    await expect(page.getByTestId('notice-url')).toHaveCount(0)
    // 链接里的 pattern 没有 mapping:落在 annotate,提示 compare_unavailable
    await page.evaluate(([s, d]) => { location.hash = `#symbol=${s}&date=${d}&pattern=${encodeURIComponent('旗形')}&mode=compare` },
                        [SYMBOL, plan.plain] as const)
    await expect(page.getByTestId('notice-url')).toContainText('compare_unavailable')
    await expect.poll(() => view(page, 'mode')).toBe('annotate')
    await page.getByTestId('notice-url-ok').click()

    // 行上 delete
    await pickPattern(page, PATTERN)
    await enterCompare(page)
    await page.getByTestId('annotation-tab-feedback').click()
    await page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"] [data-testid="feedback-row-delete"]`).click()
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"]`)).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).map(f => f.id)).not.toContain(PLAIN)
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'feedback')
    await page.getByTestId('notice-undo-ok').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('删样本:有只服务它的框时先问 yes / no / cancel;删除可撤最近一次', async ({ page }) => {
    await routeTo(page, backend!)
    const smp = (st: any, id: string) => st.charts.flatMap((c: any) => c.samples).find((s: any) => s.id === id) ?? null
    const boxIds = (st: any) => st.charts.flatMap((c: any) => c.boxes).map((b: any) => b.id)

    // s-pc-11(W底 正样本)的三个成员框只服务它
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await expect.poll(() => annOf(page, 'selectedSampleId')).toBe('s-pc-11')
    await page.getByTestId('sample-delete').click()
    await expect(page.getByTestId('sample-delete-ask')).toHaveAttribute('data-count', '3')
    await page.getByTestId('sample-delete-cancel').click()                   // cancel:不删
    await expect(page.getByTestId('sample-delete-ask')).toHaveCount(0)
    await settled(page)
    expect(smp(await annState(page), 's-pc-11')).not.toBeNull()
    await page.getByTestId('sample-delete').click()
    await page.getByTestId('sample-delete-yes').click()                      // yes:样本连同三个框一批删掉
    await settled(page)
    let st = await annState(page)
    expect(smp(st, 's-pc-11')).toBeNull()
    for (const b of ['b-pc-8', 'b-pc-9', 'b-pc-10']) expect(boxIds(st)).not.toContain(b)
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'sample')
    await expect(page.getByTestId('notice-undo')).toContainText('+3 boxes')
    await page.getByTestId('notice-undo-btn').click()                        // undo:原编号写回
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    st = await annState(page)
    expect(smp(st, 's-pc-11')).toMatchObject({ date: '2024-03-11', pattern: PATTERN, judgment: 'pos',
                                               members: ['b-pc-8', 'b-pc-9', 'b-pc-10'] })
    for (const b of ['b-pc-8', 'b-pc-9', 'b-pc-10']) expect(boxIds(st)).toContain(b)

    // s-pc-14(负样本)的两个成员框只服务它:no = 只删样本,框留着;提示条 ok 放弃撤销
    await page.evaluate(() => { location.hash = '#sample=s-pc-14' })
    await expect.poll(() => annOf(page, 'selectedSampleId')).toBe('s-pc-14')
    await page.getByTestId('sample-delete').click()
    await expect(page.getByTestId('sample-delete-ask')).toHaveAttribute('data-count', '2')
    await page.getByTestId('sample-delete-no').click()
    await settled(page)
    st = await annState(page)
    expect(smp(st, 's-pc-14')).toBeNull()
    for (const b of ['b-pc-12', 'b-pc-13']) expect(boxIds(st)).toContain(b)
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'sample')
    await page.getByTestId('notice-undo-ok').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    expect(smp(await annState(page), 's-pc-14')).toBeNull()

    // 没有只服务它的框(s-pc-35 一个成员框都没有):直接删,不问
    await page.evaluate(() => { location.hash = '#sample=s-pc-35' })
    await expect.poll(() => annOf(page, 'selectedSampleId')).toBe('s-pc-35')
    await page.getByTestId('sample-delete').click()
    await settled(page)
    await expect(page.getByTestId('sample-delete-ask')).toHaveCount(0)
    expect(smp(await annState(page), 's-pc-35')).toBeNull()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})

/** 点亮 feedback 工具(已亮不动)。 */
async function feedbackOn(page: Page) {
  const btn = page.getByTestId('tool-feedback')
  if (!/\bon\b/.test((await btn.getAttribute('class')) ?? '')) await btn.click()
  await expect(btn).toHaveClass(/\bon\b/)
}
