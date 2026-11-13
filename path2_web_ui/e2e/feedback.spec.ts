import { test, expect, type Browser, type Locator, type Page, type TestInfo } from '@playwright/test'
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
 * 预置的这三条故意用以前存下的形状(带 answer):red 是 neg + note,plain 是 off_pattern + node、没写 note,
 * lost 是 off_pattern + dag + note。界面现在写出的反馈不带 answer、不带 dag;以前存下的照样显示(answer 与 dag
 * 不显示)、能编辑(保存后改写成不带这两个键的)、能被挑去共享。
 *
 * 覆盖:
 * 1. 反馈带三种颜色、会话标签(侧栏与悬停)、侧栏排序;以前存下的三种形状在记号悬停、侧栏组头里都不出 answer / dag;
 *    点记号只选中,按住 Enter 打开那条、自动重复不保存;
 *    annotate、app 模式下没有反馈带、工具与侧栏页,Shift+F 只在 compare 生效。截图 ①(三种状态连同 hits 行)。
 * 2. 点 ▼、点琥珀格、点族、点记号都只选中、不弹面板;选中后按 Enter 或点显示栏的 feedback 按钮才弹:▼ / 琥珀格得
 *    point 面板,族的命中区得 family 范围与起点;焦点停在别处的按钮上时 Enter 照样开、不「点」那个按钮;
 *    面板开着时它管的那段日期有贯穿主副图的竖带,面板默认靠在竖带旁、
 *    底边贴住显示栏上沿,按住页头能拖走;面板开着时点另一个 ▼:面板关掉、选中换过去、不开新的;
 *    面板一打开就是 issues / nodes / note 三行
 *    (没有答案按钮、没有 dag);不抢焦点、←/→ 仍走 hit、Esc 先关面板、点别处关、焦点在按钮上按 Enter 也是保存;
 *    只点 node 不写 note 存不了,点 node 后光标进 note;只写 note 就能存;同范围打开那条、改、删与撤销;
 *    先选中框再点族,框的选中取消;node 按钮悬停时 band 加亮。截图 ②(鼠标停在一个 node 按钮上)。
 * 3. feedback 工具:Shift+F / 按钮点亮、Esc 熄灭、点一下不熄;拖出没有买点的范围不弹、提示 no buy in range;
 *    拖出有买点的范围,松手后面板还在、用一次熄灭;拖选中那条反馈竖带的边改起止:新范围里没有买点不改、提示
 *    no buy in range;有就直接存,以前存下的 family 反馈(带 dag)改成同编号的 range(去掉 family_start,不带 answer、dag)。
 * 4. 侧栏点行跳到 compare(竖线停在范围起点、选中那条);落在 compare 的链接;落不成时提示;行上 delete。
 * 5. 删样本:有只服务它的框时先问(yes / no / cancel),删除可撤最近一次。
 * 6. 长 note 与 node、记号上的字、卡片的 edit、选中的竖带:note 是多行文本区,长文字换行长高、面板不变宽,
 *    Shift+Enter 换行;记号够宽时写点出的 node 名、窄了不写;卡片的 edit 落过去后打开预填的面板(落点同上);
 *    选中卡片后记号描黑粗边、图上一条贯穿主副图的实线边竖带,删掉后消失。截图 panel-long-note.png、selected-band.png。
 * 7. issue 复用(几处反馈共享同一份内容:note 与 node):第二只股票(现找一只 new_step 有一族三个以上买点的)上点 ▼、按 Enter →
 *    列表一打开就有(不用先选答案,以前存下的也在)→ 挑 CRNC 上的一条 → Enter,两处带同一个 issue 值(原来不带的
 *    那条同批补上,并改写成不带 answer 的);挑了又改字出现 shared by n places 与 all / only this,Enter 不存,
 *    all 后各处一起变、only this 后这一处不带 issue 值、别处不变;以前存下的带 dag 的也能复用;挑一个以前存下的、
 *    没写 note 的 issue:不补存不了,补了以后问 all / only this;再点一次已连着的那条 = 不再共享;侧栏按 issue
 *    分组、组头写处数与 matched 数;记号悬停写 shared: n places。
 *    截图 issue-panel.png、unified-panel.png(面板)、unified-sidebar.png(侧栏分组)。
 * 8. 以前存下的记录:经卡片的 edit 改一条 neg + note(保存后不带 answer);没写 note 的那种不补存不了;
 *    撤销删除——单独一处照原值写回;同一个 issue 还有别的处(点了 node、没写 note)时照那一处写回,后端收下。
 *
 * 环境变量 PATH2_E2E_SHOTS 给了目录时,截图另复制一份到那里(给人过目)。
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
const EDGE = '#555555'
const SELECTED_EDGE = '#000000'       // 选中的记号:黑色粗边
const SELECTED_W = 3.5
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
/** 侧栏里某条反馈所在的那一组(一个 issue:组头写点出的 node 与理由,下面每处一行)。 */
const groupOf = (page: Page, id: string) => page.locator('[data-testid="feedback-group"]',
  { has: page.locator(`[data-testid="feedback-row"][data-id="${id}"]`) })

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

/** 反馈带上各条记号上写的字(按编号;没写字为 null)。 */
async function stripLabels(page: Page): Promise<Record<string, string | null>> {
  return page.evaluate(() => {
    const s = (window as any).__e2e.chartSub().getModel().getSeriesByName('feedback-strip')[0]
    const out: Record<string, string | null> = {}
    if (!s) return out
    const data = s.getData()
    for (let i = 0; i < data.count(); i++) {
      const text = data.getItemGraphicEl(i)?.childAt?.(1)
      out[data.getRawDataItem(i).feedback_id] = text ? String(text.style.text) : null
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

/** 对选中的那一个打开作答面板:按 Enter。点图上的东西只选中,所以先确认点击本身没有弹面板。 */
async function openFb(page: Page) {
  await expect(panel(page)).toHaveCount(0)
  await page.keyboard.press('Enter')
  await expect(panel(page)).toBeVisible()
}

/** 对选中的那一个打开作答面板:点显示栏最右的 feedback 按钮。 */
async function openFbByButton(page: Page) {
  await expect(panel(page)).toHaveCount(0)
  await page.getByTestId('sel-feedback').click()
  await expect(panel(page)).toBeVisible()
}

/**
 * 面板在默认落点:底边贴住显示栏上沿(留 4 像素;主图太矮时贴住视口上沿,底边仍在显示栏之上),左右不出图表区;
 * 竖带旁边放得下时不压竖带。
 */
async function expectDefaultPlace(page: Page) {
  const pb = (await panel(page).boundingBox())!
  const bar = (await page.getByTestId('walk-bar').boundingBox())!
  const wrap = (await page.locator('.kline-wrap-v2').boundingBox())!
  expect(pb.y + pb.height).toBeLessThanOrEqual(bar.y + 0.5)
  if (pb.y > 0.5) expect(Math.abs(pb.y + pb.height - (bar.y - 4))).toBeLessThan(1.5)
  expect(pb.x).toBeGreaterThanOrEqual(wrap.x - 0.5)
  expect(pb.x + pb.width).toBeLessThanOrEqual(wrap.x + wrap.width + 0.5)
  const band = await page.getByTestId('feedback-selected-band').boundingBox()
  if (band && (wrap.x + wrap.width - (band.x + band.width) >= pb.width + 10 || band.x - wrap.x >= pb.width + 10)) {
    expect(pb.x >= band.x + band.width - 0.5 || pb.x + pb.width <= band.x + 0.5,
           `面板 ${JSON.stringify(pb)} 不该压住竖带 ${JSON.stringify(band)}`).toBe(true)
  }
}

/** 焦点在不在反馈面板里。 */
const focusInPanel = (page: Page) => page.evaluate(() =>
  !!document.querySelector('[data-testid="feedback-panel"]')?.contains(document.activeElement))
const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())

/** 截图:挂在测试结果里;PATH2_E2E_SHOTS 给了目录时另复制一份。around 给了就只截它周围的一块(四边各多留 pad)。 */
async function shot(page: Page, testInfo: TestInfo, name: string, around?: Locator, pad = 40) {
  const path = testInfo.outputPath(name)
  const box = around ? await around.boundingBox() : null
  if (box) {
    const vp = page.viewportSize()!
    const x = Math.max(0, box.x - pad), y = Math.max(0, box.y - pad)
    await page.screenshot({ path, scale: 'device', clip: {
      x, y, width: Math.min(vp.width, box.x + box.width + pad) - x, height: Math.min(vp.height, box.y + box.height + pad) - y } })
  } else {
    await page.screenshot({ path, scale: 'device', fullPage: true })
  }
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
  // 三条反馈故意用以前存下的形状(带 answer;lost 那条还带 dag),见文件头
  await postOps(b, [
    { kind: 'sample', id: POS_SAMPLE, base: null,
      value: { id: POS_SAMPLE, symbol: SYMBOL, date: pl.pos, pattern: PATTERN, judgment: 'pos', members: [] } },
    { kind: 'box', id: BOX, base: null, value: { id: BOX, symbol: SYMBOL, feature: 'w-pc-1', start: pl.lost.start, end: box } },
    fb(RED, { start: pl.red, end: pl.red, target: 'point', answer: 'neg', note: '追在阶跃之后太远' }),
    fb(PLAIN, { start: pl.plain, end: pl.plain, target: 'point', answer: 'off_pattern', nodes: ['plateau'] }),
    fb(LOST, { start: pl.lost.start, end: pl.lost.end, target: 'family', family_start: pl.lost.start,
               answer: 'off_pattern', note: '这一段不是平台', dag: true }),
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
    // 状态接口真跑 app:三条各是 matched(朱红)、unmatched、起点认不出(页面上并进 unmatched,会话给它挂了标签,
    // 说明毛病还在,所以标签照带);会话标签照 mapping 的会话段
    await expect.poll(async () => {
      const s = await fbOf(page, 'statusById')
      return [RED, PLAIN, LOST].map(id => `${s?.[id]?.status}:${s?.[id]?.red}:${s?.[id]?.tag}`)
    }, { timeout: 60_000 }).toEqual(['matched:true:for_tuning', 'unmatched:false:null', 'unmatched:false:unhandled'])

    // 反馈带:每条一个记号,朱红 / 白底深灰描边(起点认不出的那条也是常色)
    const li = dates.indexOf(plan.lost.start)
    await zoomTo(page, li - 6, F.buys[F.buys.length - 1] + 6)
    await expect.poll(async () => (await stripMarks(page)).map(m => m.id).sort()).toEqual([RED, PLAIN, LOST].sort())
    const marks = Object.fromEntries((await stripMarks(page)).map(m => [m.id, m]))
    expect([marks[RED].fill.toUpperCase(), marks[RED].stroke.toUpperCase()]).toEqual([VERMILION, EDGE.toUpperCase()])
    expect([marks[LOST].fill.toLowerCase(), marks[LOST].stroke.toLowerCase()]).toEqual(['#ffffff', EDGE])
    expect([marks[PLAIN].fill.toLowerCase(), marks[PLAIN].stroke.toLowerCase()]).toEqual(['#ffffff', EDGE])
    // 反馈带在 hit 行下面
    const strip = await itemBoxes(page, 'feedback-strip', 0)
    const hitRows = await itemBoxes(page, 'brackets')
    expect(Math.min(...strip.map(b => b.y))).toBeGreaterThan(Math.max(...hitRows.map(b => b.y + b.h)) - 1)

    // 记号上的字是点出的 node 名:没点 node 的两条不写字;点了 plateau 的那条只占一根 K 线,放得下才写
    const labels = await stripLabels(page)
    expect(labels[RED]).toBeNull()
    expect(labels[LOST]).toBeNull()
    expect([null, 'plateau']).toContain(labels[PLAIN])

    // 悬停朱红那条(以前存下的 neg + note):写全理由、状态、会话标签;不写答案
    const red = strip.find(b => b.d.feedback_id === RED)!
    await page.mouse.move(red.x + red.w / 2, red.y + red.h / 2)
    const tip = page.locator('body > div').filter({ hasText: 'tag: for_tuning' })
    await expect(tip.first()).toBeVisible()
    await expect(tip.first()).toContainText('status: matched')
    await expect(tip.first()).toContainText('note: 追在阶跃之后太远')
    await expect(tip.first()).not.toContainText(/answer|nodes:|undefined/)
    // 就地点它只选中那条;按住 Enter 打开面板(第一下开,后面的自动重复不会顺手把它存了——它的理由写着,按一下就能存):
    // 悬停提示收起、开着期间不再弹(鼠标仍停在记号上);状态与会话标签改在面板里看
    await page.mouse.click(red.x + red.w / 2, red.y + red.h / 2)
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(RED)
    await expect(panel(page)).toHaveCount(0)
    for (let i = 0; i < 5; i++) await page.keyboard.down('Enter')
    await page.keyboard.up('Enter')
    await expect(panel(page)).toHaveAttribute('data-editing', RED)
    await settled(page)
    expect(feedbackOf(await annState(page)).find(f => f.id === RED)).toHaveProperty('answer')   // 没存:还是预置的样子
    await expect(tip.first()).toBeHidden()
    await page.mouse.move(red.x + red.w / 2 + 1, red.y + red.h / 2)
    await expect(tip.first()).toBeHidden()
    await expect(page.getByTestId('feedback-status')).toHaveText('matched')
    await expect(page.getByTestId('feedback-tag')).toHaveText('for_tuning')
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)
    // 面板关了,悬停照常
    await page.mouse.move(10, 10)
    await page.mouse.move(red.x + red.w / 2, red.y + red.h / 2)
    await expect(tip.first()).toBeVisible()
    await page.mouse.move(10, 10)
    // 悬停 lost 那条(以前存下的 off_pattern + dag + note):没点 node 就没有 nodes 行,dag 不写
    const lostMark = strip.find(b => b.d.feedback_id === LOST)!
    await page.mouse.move(lostMark.x + lostMark.w / 2, lostMark.y + lostMark.h / 2)
    const tipLost = page.locator('body > div').filter({ hasText: 'tag: unhandled' })
    await expect(tipLost.first()).toBeVisible()
    await expect(tipLost.first()).toContainText('status: unmatched')
    await expect(tipLost.first()).not.toContainText('id:')
    await expect(tipLost.first()).toContainText('note: 这一段不是平台')
    await expect(tipLost.first()).not.toContainText(/answer|off_pattern|nodes:|dag|undefined/)
    await page.mouse.move(10, 10)
    // 悬停常色那条(以前存下的 off_pattern + node、没写 note):有 nodes 行,没有 note 行
    const plainMark = strip.find(b => b.d.feedback_id === PLAIN)!
    await page.mouse.move(plainMark.x + plainMark.w / 2, plainMark.y + plainMark.h / 2)
    const tipPlain = page.locator('body > div').filter({ hasText: 'nodes: plateau' })
    await expect(tipPlain.first()).toBeVisible()
    await expect(tipPlain.first()).toContainText('nodes: plateau')
    await expect(tipPlain.first()).not.toContainText(/answer|off_pattern|note:|undefined/)
    await page.mouse.move(10, 10)

    // 侧栏 feedback 页:朱红在前、不买了却挂着标签的其次、其余在后;接口给了标签的行照挂
    await page.getByTestId('annotation-tab-feedback').click()
    await expect(page.getByTestId('feedback-page')).toBeVisible()
    await expect(page.getByTestId('feedback-loading')).toHaveCount(0)
    const rows = page.getByTestId('feedback-row')
    await expect(rows).toHaveCount(3)
    expect(await rows.evaluateAll(els => els.map(e => [e.getAttribute('data-id'), e.getAttribute('data-tone')])))
      .toEqual([[RED, 'red'], [LOST, 'plain'], [PLAIN, 'plain']])
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${RED}"] [data-testid="feedback-row-tag"]`)).toHaveText('for_tuning')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${LOST}"] [data-testid="feedback-row-tag"]`)).toHaveText('unhandled')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"] [data-testid="feedback-row-tag"]`)).toHaveCount(0)
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${RED}"] [data-testid="feedback-row-status"]`)).toHaveText('matched')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${LOST}"] [data-testid="feedback-row-status"]`)).toHaveText('unmatched')
    await expect(page.locator(`[data-testid="feedback-row"][data-id="${PLAIN}"] [data-testid="feedback-row-status"]`)).toHaveText('unmatched')
    // 组头:点出的 node 小标签,一个都没点的写灰字 none;理由在第二行;以前存下的 answer、dag 不留痕
    await expect(groupOf(page, LOST).getByTestId('feedback-row-nodes-none')).toHaveText('none')
    await expect(groupOf(page, LOST).getByTestId('feedback-row-nodes-none')).toHaveAttribute('title', 'not on any one node, or not said')
    await expect(groupOf(page, LOST).getByTestId('feedback-row-node')).toHaveCount(0)
    await expect(groupOf(page, LOST).getByTestId('feedback-row-note')).toHaveText('这一段不是平台')
    await expect(groupOf(page, RED).getByTestId('feedback-row-nodes-none')).toHaveText('none')
    await expect(groupOf(page, RED).getByTestId('feedback-row-note')).toHaveText('追在阶跃之后太远')
    await expect(groupOf(page, PLAIN).getByTestId('feedback-row-node')).toHaveText(['plateau'])
    await expect(groupOf(page, PLAIN).getByTestId('feedback-row-nodes-none')).toHaveCount(0)
    await expect(groupOf(page, PLAIN).getByTestId('feedback-row-note')).toHaveCount(0)
    await expect(page.getByTestId('feedback-row-answer')).toHaveCount(0)
    await expect(page.getByTestId('feedback-row-dag')).toHaveCount(0)
    await expect(page.getByTestId('feedback-page')).not.toContainText(/off_pattern|\bneg\b|answer|dag|undefined/)
    // 都不和谁共享:一处一组
    await expect(page.getByTestId('feedback-group')).toHaveCount(3)
    await expect(groupOf(page, LOST).getByTestId('feedback-group-places')).toHaveText('places 1')
    expect(await rows.first().locator('button').evaluateAll(els => els.map(e => e.getAttribute('data-testid'))))
      .toEqual(['feedback-row-edit', 'feedback-row-delete'])
    await shot(page, testInfo, 'feedback-strip-three-states.png')

    // Shift+F 在 compare 下点亮 / 熄灭
    await blur(page)
    await page.keyboard.press('Shift+F')
    await expect.poll(() => annOf(page, 'tool')).toBe('feedback')
    await expect(page.getByTestId('tool-feedback')).toHaveClass(/\bon\b/)
    await page.keyboard.press('Shift+F')
    await expect.poll(() => annOf(page, 'tool')).toBeNull()

    // app 模式:不画反馈带,没有 feedback 工具与侧栏页,Shift+F 不点亮;族那一行照样可点(点它选中这一族)
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await expect.poll(() => page.evaluate(() =>
      ((window as any).__e2e.chartSub().getOption()?.series ?? []).some((s: any) => s.name === 'bracket-lines'))).toBe(true)
    const series = await page.evaluate(() => ((window as any).__e2e.chartSub().getOption().series ?? [])
      .map((s: any) => ({ name: s.name, silent: !!s.silent })))
    expect(series.map(s => s.name)).not.toContain('feedback-strip')
    expect(series.find(s => s.name === 'bracket-lines')!.silent).toBe(false)
    await expect(page.getByTestId('tool-feedback')).toHaveCount(0)
    await expect(page.getByTestId('annotation-tab-feedback')).toHaveCount(0)
    await expect(page.getByTestId('feedback-page')).toHaveCount(0)
    await blur(page)
    await page.keyboard.press('Shift+F')
    await page.waitForTimeout(200)
    expect(await annOf(page, 'tool')).toBeNull()
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('点 ▼ / 格 / 族 / 记号只选中,Enter 或显示栏 feedback 弹面板(竖带、默认落点、拖页头;一打开就是 issues / nodes / note);不抢焦点、Esc 先关面板、点别处关、按钮上 Enter 也保存;只点 node 不写 note 存不了;同范围打开那条、改、删与撤销;选中的框被取消;node 按钮悬停 band 加亮', async ({ page }, testInfo) => {
    const { dates, F, G } = plan
    await openCompare(page, plan.pos)
    await zoomTo(page, Math.min(F.start, G.start) - 3, Math.max(F.buys.at(-1)!, G.buys.at(-1)!) + 4)
    const g0 = G.buys[0], g0Date = dates[g0]

    // ── 点 ▼ 只选中:不弹面板,显示栏的 feedback 按钮亮起来;按 Enter 才弹 point 面板,范围是那一天;不抢焦点 ──
    await expect(page.getByTestId('sel-feedback')).toBeDisabled()               // 还没选中:不能作答
    await clickBuy(page, g0)
    await page.waitForTimeout(300)
    await expect(panel(page)).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.selPath.map((x: any) => x.kind)))
      .toEqual(['hit_family', 'buy'])
    await expect(page.getByTestId('sel-feedback')).toBeEnabled()
    await expect(page.getByTestId('feedback-selected-band')).toHaveCount(0)    // 没开面板、没选中反馈:没有竖带
    await openFb(page)
    await expect(page.getByTestId('sel-feedback')).toHaveAttribute('aria-pressed', 'true')
    // 面板开着:它管的那一天画成贯穿主副图的竖带;面板靠在竖带旁、底边贴住显示栏上沿,显示栏露着
    const selBand = page.getByTestId('feedback-selected-band')
    await expect(selBand).toBeVisible()
    await expect.poll(async () => {
      const bb = (await selBand.boundingBox())!
      const bw = (await xOf(page, g0 + 1)) - (await xOf(page, g0))
      return Math.abs(bb.x + bb.width / 2 - (await xOf(page, g0))) < bw
    }).toBe(true)
    await expect.poll(async () => {
      const pb = (await panel(page).boundingBox())!, bar = (await page.getByTestId('walk-bar').boundingBox())!
      return pb.y + pb.height <= bar.y + 0.5
    }).toBe(true)
    await expectDefaultPlace(page)
    await expect(page.getByTestId('walk-bar')).toBeVisible()
    // 按住页头拖走:面板跟着挪、不关、不夺焦点;拖到哪只管这一次
    const at0 = (await panel(page).boundingBox())!
    const hdr = (await page.getByTestId('feedback-drag').boundingBox())!
    const hx = hdr.x + Math.min(30, hdr.width / 4), hy = hdr.y + hdr.height / 2
    await page.mouse.move(hx, hy)
    await page.mouse.down()
    await page.mouse.move(hx - 120, hy - 60, { steps: 5 })
    await page.mouse.up()
    const at1 = (await panel(page).boundingBox())!
    expect(Math.abs(at1.x - (at0.x - 120))).toBeLessThan(2)
    expect(Math.abs(at1.y - (at0.y - 60))).toBeLessThan(2)
    await expect(panel(page)).toBeVisible()
    expect(await focusInPanel(page)).toBe(false)
    await expect(panel(page)).toHaveAttribute('data-target', 'point')
    await expect(panel(page)).toHaveAttribute('data-editing', '')
    await expect(page.getByTestId('feedback-symbol')).toHaveText(SYMBOL)
    await expect(page.getByTestId('feedback-span')).toHaveText(g0Date)
    // 一打开就是完整的面板:issues(预置的三条,以前存下的也列)、nodes、note、save;没有答案按钮、没有 dag
    await expect(panel(page).locator('.fb-kv > .ann-k')).toHaveText(['issues', 'nodes', 'note'])
    for (const t of ['feedback-answer-neg', 'feedback-answer-off_pattern', 'feedback-dag']) {
      await expect(page.getByTestId(t)).toHaveCount(0)
    }
    await expect(page.getByTestId('feedback-issue')).toHaveCount(3)
    await expect(page.getByTestId('feedback-node').first()).toBeVisible()
    await expect(page.getByTestId('feedback-note')).toHaveAttribute('placeholder', 'required')
    await expect(page.getByTestId('feedback-save')).toBeVisible()
    await expect(panel(page)).not.toContainText(/answer|off_pattern|\bneg\b|dag/)
    await expect(page.getByTestId('feedback-pos-inside')).toHaveCount(0)
    expect(await focusInPanel(page)).toBe(false)
    expect(await view(page, 'currentDay')).toBe(g0)
    // 点 ▼ 选中的是这一天整体(这天只有一次 hit 时就是那次 hit)。按键不归面板:↑ / ↓ 进到这天叠着的几次、
    // 在它们之间换,竖线不动,point 面板留着;← / → 竖线挪到这一族的下一个买入日,走出了面板的那一天,面板关掉(没存)
    expect(await page.evaluate(() => (window as any).__e2e.view.selPath.map((x: any) => x.kind))).toEqual(['hit_family', 'buy'])
    const dayHits: string[] = await page.evaluate(() => [...(window as any).__e2e.view.selDayHitIds])
    if (dayHits.length >= 2) {
      expect(await view(page, 'selectedHitId')).toBeNull()
      await page.keyboard.press('ArrowDown')
      await expect.poll(() => view(page, 'selectedHitId')).toBe(dayHits[0])
      await page.keyboard.press('ArrowDown')
      await expect.poll(() => view(page, 'selectedHitId')).toBe(dayHits[1])
      expect(await view(page, 'currentDay')).toBe(g0)
      await expect(panel(page)).toBeVisible()
    } else {
      expect(await view(page, 'selectedHitId')).not.toBeNull()
    }
    await page.keyboard.press('ArrowRight')
    await expect.poll(() => view(page, 'currentDay')).toBe(G.buys[1])
    await expect(panel(page)).toHaveCount(0)

    // ── 显示栏的 feedback 按钮:点了打开(拖过的位置不留,回到默认落点),再点关掉、不存 ──
    await openFbByButton(page)
    await expect(page.getByTestId('feedback-span')).toHaveText(dates[G.buys[1]])
    await expectDefaultPlace(page)
    await page.getByTestId('sel-feedback').click()
    await expect(panel(page)).toHaveCount(0)
    // ── 面板开着时点另一个 ▼:面板关掉、选中换过去,不开新的 ──
    await openFb(page)
    await clickBuy(page, g0)
    await page.waitForTimeout(300)
    await expect(panel(page)).toHaveCount(0)
    expect(await view(page, 'currentDay')).toBe(g0)

    // ── 焦点停在别处的按钮上(像刚用鼠标点过它):能作答时 Enter 照样开面板,不「点」那个按钮,焦点放掉 ──
    await page.getByTestId('tool-box').focus()
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    expect(await annOf(page, 'tool')).toBeNull()                             // box 工具没被点亮
    expect(await page.evaluate(() => document.activeElement?.getAttribute('data-testid') ?? null)).not.toBe('tool-box')
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)

    // ── Esc 第一下只关面板:当前日、当家行都不动 ──
    await openFb(page)
    const before = [await view(page, 'currentDay'), await view(page, 'activeFamilyKey')]
    expect(before[1]).not.toBeNull()
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)
    expect([await view(page, 'currentDay'), await view(page, 'activeFamilyKey')]).toEqual(before)

    // ── 点别处(主图 K 线区)关,不存 ──
    await clickBuy(page, g0)
    await openFb(page)
    await page.getByTestId('feedback-note').fill('写了一半')
    await page.mouse.click(await xOf(page, g0 - 2), await klineY(page))
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)).toEqual([])

    // ── 只点 node、不写 note:存不了(点 node 后光标进 note);点掉 node、只写 note:Enter 保存,记号出现 ──
    await clickBuy(page, g0)
    await openFb(page)
    const firstNode = page.getByTestId('feedback-node').first()
    await firstNode.click()
    await expect(firstNode).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['note'])
    await settled(page)
    expect(feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)).toEqual([])
    await firstNode.click()                                                  // 点掉:一个 node 都不点
    await expect(firstNode).not.toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toBeFocused()            // 点掉之后光标也在 note 里
    await page.keyboard.insertText('放量不够')
    await expect(page.getByTestId('feedback-note')).toHaveValue('放量不够')
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const saved = feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)
    expect(saved).toHaveLength(1)
    const pid: string = saved[0].id
    expect(pid).toMatch(/^f-e2e-\d+$/)
    // 存下的是不带 answer 的形状:没有 answer、没有 dag、没点 node 就没有 nodes
    expect(saved[0]).toEqual({ id: pid, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: g0Date, end: g0Date,
                               target: 'point', source: 'picked', note: '放量不够' })
    await expect.poll(async () => (await stripMarks(page)).map(m => m.id)).toContain(pid)
    await expect.poll(async () => (await fbOf(page, 'statusById'))?.[pid]?.status).toBe('matched')

    // ── 同范围不重复:再选中那个 ▼、按 Enter 打开这一条(预填、多 delete、没有 redraw);焦点在按钮上按 Enter 也是保存 ──
    await clickBuy(page, g0)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-editing', pid)
    await expect(page.getByTestId('feedback-note')).toHaveValue('放量不够')
    await expect(page.locator('[data-testid="feedback-node"].on')).toHaveCount(0)
    await expect(page.getByTestId('feedback-delete')).toBeVisible()
    await expect(page.getByTestId('feedback-redraw')).toHaveCount(0)
    expect(await focusInPanel(page)).toBe(false)                             // 打开已有的一条也不抢焦点
    await page.getByTestId('feedback-note').fill('放量不够,而且离阶跃太远')
    await page.getByTestId('feedback-node').first().focus()
    await page.keyboard.press('Enter')                                       // 浏览器默认会「点按钮」;归面板就是保存
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const edited = feedbackOf(await annState(page)).filter(f => f.start === g0Date && f.end === g0Date)
    expect(edited.map(f => [f.id, f.note, 'nodes' in f, 'answer' in f])).toEqual([[pid, '放量不够,而且离阶跃太远', false, false]])

    // ── 缺东西时 Enter 不存,标出缺什么 ──
    await clickBuy(page, plan.dates.indexOf(plan.pos))
    await openFb(page)
    await expect(page.getByTestId('feedback-pos-inside')).toBeVisible()      // 那天放着当前 pattern 的正样本
    await page.getByTestId('feedback-note').click()
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem="note"]')).toBeVisible()
    await page.keyboard.press('Escape')                                      // 焦点在 note 里也是先关面板
    await expect(panel(page)).toHaveCount(0)

    // ── 点格(那一列有 ▼ 的琥珀格)只选中;按 Enter:point 面板,范围是那一列的买点日 ──
    const redI = dates.indexOf(plan.red)
    const day = await clickMark(page, d => d.family_start === F.start && d.buy_day !== redI)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-target', 'point')
    await expect(page.getByTestId('feedback-span')).toHaveText(dates[day])
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)

    // ── 先选中一个框,再点族的命中区:框的选中取消、Delete 删不到它;选中整族,按 Enter:family 面板,
    //    范围 = 全部 ▼ 的最早到最晚 ──
    await page.evaluate(id => (window as any).__e2e.ann().selectBox(id), BOX)
    await expect.poll(() => annOf(page, 'selectedBoxId')).toBe(BOX)
    await clickFamily(page, G.start)
    await expect.poll(() => annOf(page, 'selectedBoxId')).toBeNull()
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.selPath.map((x: any) => x.kind)))
      .toEqual(['hit_family'])
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await expect(page.getByTestId('feedback-span')).toHaveText(`${dates[G.buys[0]]} – ${dates[G.buys.at(-1)!]}`)
    await expect(page.getByTestId('feedback-pos-inside')).toBeVisible()
    await page.keyboard.press('Delete')
    await settled(page)
    expect((await annState(page)).charts.find((c: any) => c.symbol === SYMBOL).boxes.map((b: any) => b.id)).toContain(BOX)

    // ── node 按钮(根 node 保留),悬停时那条 band 加亮;截图 ② ──
    await expect(panel(page)).toBeVisible()
    const btns = page.getByTestId('feedback-node')
    await expect(btns.first()).toBeVisible()
    const nodes = await btns.evaluateAll(els => els.map(e => e.getAttribute('data-node')))
    expect(nodes).toContain('plateau')
    const hoverRect = () => page.evaluate(stroke => JSON.stringify((window as any).__e2e.chartSub().getOption().graphic ?? [])
      .includes(stroke), HOVER_STROKE)
    let lit: string | null = null
    // 先试子 node(截图里加亮的那条 band 和根 node 那条分得开),最后试根 node
    for (const n of [...nodes.filter(x => x !== 'plateau'), 'plateau']) {
      await page.locator(`[data-testid="feedback-node"][data-node="${n}"]`).hover()
      await page.waitForTimeout(150)
      if (await hoverRect()) { lit = n; break }
    }
    expect(lit, '悬停某个 node 按钮时,它所在的 band 要加亮').not.toBeNull()
    await expect(page.locator(`[data-testid="feedback-node"][data-node="${lit}"]`)).toHaveAttribute('title', /\S/)
    await shot(page, testInfo, 'feedback-panel-nodes-hover.png')
    await page.getByTestId('feedback-target').hover()
    await expect.poll(hoverRect).toBe(false)
    await page.locator(`[data-testid="feedback-node"][data-node="${lit}"]`).click()
    await expect(page.locator(`[data-testid="feedback-node"][data-node="${lit}"]`)).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toBeFocused()            // 点 node 后光标进 note(按钮自己不夺焦点)
    await page.keyboard.insertText('这一族的平台太窄')
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const fam = feedbackOf(await annState(page)).filter(f => f.target === 'family' && f.family_start === dates[G.start])
    expect(fam.map(f => [f.start, f.end, f.nodes, f.note, 'answer' in f, 'dag' in f]))
      .toEqual([[dates[G.buys[0]], dates[G.buys.at(-1)!], [lit], '这一族的平台太窄', false, false]])

    // ── 点记号选中它(描边加粗),按 Enter 打开那条;delete 删掉,提示条 undo 放回 ──
    await clickStrip(page, pid)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-editing', pid)
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(pid)
    await expect.poll(async () => {
      const m = (await stripMarks(page)).find(x => x.id === pid)
      return [m?.stroke.toLowerCase(), m?.lineWidth]
    }).toEqual([SELECTED_EDGE, SELECTED_W])
    await expect(page.getByTestId('feedback-selected-band')).toBeVisible()     // 选中的那条:图上一条竖带
    await page.getByTestId('feedback-delete').click()
    await expect(panel(page)).toHaveCount(0)
    await expect(page.getByTestId('feedback-selected-band')).toHaveCount(0)    // 删掉即取消选中,竖带消失
    await settled(page)
    expect(feedbackOf(await annState(page)).map(f => f.id)).not.toContain(pid)
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'feedback')
    await page.getByTestId('notice-undo-btn').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    expect(feedbackOf(await annState(page)).find(f => f.id === pid)).toEqual(
      { id: pid, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: g0Date, end: g0Date, target: 'point',
        source: 'picked', note: '放量不够,而且离阶跃太远' })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('feedback 工具:点亮与熄灭;没有买点的范围不弹、提示 no buy in range;拖完松手面板还在;拖竖带的边把以前存下的带 dag 的那条改成 range', async ({ page }) => {
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
    const firstNode = page.getByTestId('feedback-node').first()
    const picked = await firstNode.getAttribute('data-node')
    await firstNode.click()
    await page.getByTestId('feedback-save').click()                          // 只点 node、不写 note:存不了
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['note'])
    await expect(panel(page)).toBeVisible()
    await page.getByTestId('feedback-note').fill('阶跃那根太弱')
    await expect(page.getByTestId('feedback-problems')).toHaveCount(0)
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const rg = feedbackOf(await annState(page)).filter(f => f.target === 'range')
    expect(rg.map(f => [f.start, f.end, f.note, f.nodes, 'dag' in f, 'answer' in f]))
      .toEqual([[dates[b0 - 1], dates[b0 + 1], '阶跃那根太弱', [picked], false, false]])

    // 改起止:点 lost 那条(family;以前存下的 off_pattern + dag + note)的记号选中它、按 Enter 打开(贯穿主副图的竖带);
    // 面板上没有 redraw,日期范围的悬停写怎么改。点亮 feedback(点按钮 = 点在面板外,面板关上、选中留着),拖竖带的边
    const nb = Math.min(...[...plan.F.buys, ...plan.G.buys, ...K.buys].filter(b => b > le))   // lost 之后最近的买点日
    await zoomTo(page, li - 6, nb + 4)
    await clickStrip(page, LOST)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-editing', LOST)
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await expect(page.getByTestId('feedback-note')).toHaveValue('这一段不是平台')   // 以前存下的那条:预填理由
    await expect(page.getByTestId('feedback-dag')).toHaveCount(0)                   // 面板上没有 dag、没有答案
    await expect(panel(page)).not.toContainText(/answer|off_pattern|dag|undefined/)
    await expect(page.getByTestId('feedback-redraw')).toHaveCount(0)
    await expect(page.getByTestId('feedback-span')).toHaveAttribute('title', /drag the left or right edge/)
    await expect(page.getByTestId('feedback-selected-band')).toBeVisible()
    await feedbackOn(page)
    await expect(panel(page)).toHaveCount(0)
    await expect(page.getByTestId('feedback-selected-band')).toBeVisible()
    const half = ((await xOf(page, li + 1)) - (await xOf(page, li))) / 2
    const edgeL = (await xOf(page, li)) - half, edgeR = (await xOf(page, le)) + half
    // 左边往里拖到第 3 天:新范围里没有买点 → 不改,在松开处提示 no buy in range,工具熄灭
    await page.mouse.move(edgeL + 1, y)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, li + 1), y, { steps: 4 })
    await page.mouse.move(await xOf(page, li + 3), y, { steps: 4 })
    await expect(page.getByTestId('feedback-range-band')).toBeVisible()             // 拖动中:新范围的虚线竖带
    await page.mouse.up()
    await expect(page.getByTestId('feedback-no-buy')).toHaveText('no buy in range')
    expect(await annOf(page, 'tool')).toBeNull()
    await settled(page)
    expect(feedbackOf(await annState(page)).find(f => f.id === LOST)).toMatchObject({ start: dates[li], end: dates[le],
                                                                                    target: 'family' })
    // 右边往外拖到 lost 之后最近的买点日:直接存成同编号的 range,不弹面板;存下的不带 family_start、answer、dag
    await feedbackOn(page)
    await page.mouse.move(edgeR - 1, y)
    await page.mouse.down()
    await page.mouse.move(await xOf(page, le + 1), y, { steps: 4 })
    await page.mouse.move(await xOf(page, nb), y, { steps: 4 })
    await page.mouse.up()
    expect(await annOf(page, 'tool')).toBeNull()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const re = feedbackOf(await annState(page)).find(f => f.id === LOST)
    expect(re).toEqual({ id: LOST, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: dates[li],
                         end: dates[nb], target: 'range', source: 'picked', note: '这一段不是平台' })
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
    await expect.poll(async () => (await stripMarks(page)).find(m => m.id === PLAIN)?.lineWidth).toBe(SELECTED_W)
    await expect(page.getByTestId('feedback-selected-band')).toBeVisible()
    await expect(panel(page)).toHaveCount(0)                                 // 点卡片只跳过去并选中,不开面板
    // Esc 取消选中:竖带消失、卡片的框去掉;再点一次卡片选回来
    await page.keyboard.press('Escape')
    await expect.poll(() => fbOf(page, 'selectedId')).toBeNull()
    await expect(page.getByTestId('feedback-selected-band')).toHaveCount(0)
    await expect(row).not.toHaveClass(/\bon\b/)
    await row.click()
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(PLAIN)
    await expect(page.getByTestId('feedback-selected-band')).toBeVisible()
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

  test('长 note 与 node:只点 node 不写 note 存不了;note 换行长高;记号上写 node 名;卡片 edit 打开预填面板;选中的竖带', async ({ page }, testInfo) => {
    const { dates, F, G } = plan
    const f0 = F.buys[0], f1 = F.buys.at(-1)!
    await openCompare(page, dates[f0])
    await zoomTo(page, F.start - 6, f1 + 8)

    // ── 选中 F 这一族、按 Enter:family 面板;nodes 一行只有 node 按钮(没有 dag),note 必填 ──
    await clickFamily(page, F.start)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await expect(panel(page)).toHaveAttribute('data-editing', '')
    const rowBtns = await page.getByTestId('feedback-nodes').locator('button')
      .evaluateAll(els => els.map(e => e.getAttribute('data-testid')))
    expect(rowBtns.length).toBeGreaterThanOrEqual(2)
    expect([...new Set(rowBtns)]).toEqual(['feedback-node'])
    const note = page.getByTestId('feedback-note')
    await expect(note).toHaveAttribute('placeholder', 'required')
    expect(await note.evaluate(e => e.tagName)).toBe('TEXTAREA')
    expect(await focusInPanel(page)).toBe(false)

    // ── 只点 node、不写 note:存不了,标出缺 note;点 node 后光标在 note 里,接着多选不受妨碍 ──
    const node = page.getByTestId('feedback-node').first()
    const nodeName = (await node.getAttribute('data-node'))!
    await node.click()
    await expect(node).toHaveClass(/\bon\b/)
    await expect(note).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['note'])
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem="note"]')).toHaveAttribute('title', 'write a note first')
    const node2 = page.getByTestId('feedback-node').nth(1)
    const nodeName2 = (await node2.getAttribute('data-node'))!
    await node2.click()
    await expect(node2).toHaveClass(/\bon\b/)
    await expect(node).toHaveClass(/\bon\b/)
    await expect(note).toBeFocused()
    await settled(page)
    expect(feedbackOf(await annState(page)).filter(f => f.target === 'family' && f.family_start === dates[F.start])).toEqual([])

    // ── 长 note:自动换行、文本区长高(三行以上),面板不变宽;Shift+Enter 换行、不保存 ──
    const box0 = (await note.boundingBox())!
    const panelW0 = (await panel(page).boundingBox())!.width
    const LONG = '几个 node 单看都认得出,毛病在它们之间:旧平台到阶跃隔得太久,中间其实又走出了一段下跌,'
      + '新平台是从那段下跌的低点重新起来的,和旧平台已经不是一回事;再加上阶跃那天的量并不比前面几次反弹大,整体更像一次超跌反弹。'
    await note.fill(LONG)
    await expect.poll(async () => (await note.boundingBox())!.height).toBeGreaterThan(box0.height * 2.6)
    const box1 = (await note.boundingBox())!
    expect(Math.abs(box1.width - box0.width)).toBeLessThan(1)
    expect(Math.abs((await panel(page).boundingBox())!.width - panelW0)).toBeLessThan(1)
    expect(await note.evaluate((e: HTMLTextAreaElement) => e.scrollHeight <= e.clientHeight + 1)).toBe(true)   // 全露出来,没滚
    await note.press('End')
    await note.press('Shift+Enter')
    await note.pressSequentially('second line')
    await expect(note).toHaveValue(`${LONG}\nsecond line`)
    await expect(panel(page)).toBeVisible()
    await expect.poll(async () => (await note.boundingBox())!.height).toBeGreaterThan(box1.height + 8)
    // 面板长高后往上长:底边仍贴住显示栏上沿,整个在视口里
    const pb = (await panel(page).boundingBox())!
    expect(pb.y).toBeGreaterThanOrEqual(0)
    expect(pb.y + pb.height).toBeLessThanOrEqual(page.viewportSize()!.height)
    await expectDefaultPlace(page)
    await expect(page.getByTestId('feedback-problems')).toHaveCount(0)       // 缺的都补齐了
    await expect(page.getByTestId('feedback-blocked')).toHaveCount(0)        // 也不挂 not saved
    await shot(page, testInfo, 'panel-long-note.png')

    // ── Enter 保存:记录只有 note 与 nodes(没有 answer、dag);记号悬停、卡片都写点出的 node ──
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const saved = feedbackOf(await annState(page)).filter(f => f.target === 'family' && f.family_start === dates[F.start])
    expect(saved).toHaveLength(1)
    const id: string = saved[0].id
    expect(saved[0]).toEqual({ id, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, start: dates[f0], end: dates[f1],
                               target: 'family', family_start: dates[F.start], source: 'picked',
                               note: `${LONG}\nsecond line`, nodes: [nodeName, nodeName2] })
    await expect.poll(async () => (await stripMarks(page)).map(m => m.id)).toContain(id)
    const mark = await findItem(page, 'feedback-strip', x => x.d?.feedback_id === id, 0)
    await page.mouse.move(mark.x + mark.w / 2, mark.y + mark.h / 2)
    const tipSaved = page.locator('body > div').filter({ hasText: 'target: ' })
    await expect(tipSaved.first()).toContainText(`nodes: ${nodeName}, ${nodeName2}`)
    await expect(tipSaved.first()).not.toContainText(/answer|dag|undefined/)
    await page.mouse.move(10, 10)
    // 记号上的字:够宽时写点出的 node 名(逗号连起来);图窗拉到最宽、记号只剩几像素时不写
    await zoomTo(page, f0 - 2, f1 + 2)
    await expect.poll(async () => (await stripLabels(page))[id]).toBe(`${nodeName}, ${nodeName2}`)
    await zoomTo(page, 0, dates.length - 1)
    const narrow = (await itemBoxes(page, 'feedback-strip', 0)).find(b => b.d.feedback_id === id)!
    if (narrow.w < 30) expect((await stripLabels(page))[id]).toBeNull()
    await zoomTo(page, F.start - 6, f1 + 8)
    await page.getByTestId('annotation-tab-feedback').click()
    const card = page.locator(`[data-testid="feedback-row"][data-id="${id}"]`)
    await expect(groupOf(page, id).getByTestId('feedback-row-node')).toHaveText([nodeName, nodeName2])
    await expect(groupOf(page, id).getByTestId('feedback-row-nodes-none')).toHaveCount(0)

    // ── 点卡片:落过去并选中;记号描黑粗边,图上一条贯穿主副图的竖带(淡底、两侧深色实线边)标出那段日期 ──
    await zoomTo(page, G.start - 4, G.buys.at(-1)! + 4)
    await expect(page.getByTestId('feedback-selected-band')).toHaveCount(0)
    await card.click()
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(id)
    await expect.poll(() => view(page, 'currentDay')).toBe(f0)
    await expect(card).toHaveClass(/\bon\b/)
    await expect(panel(page)).toHaveCount(0)
    await expect.poll(async () => {
      const m = (await stripMarks(page)).find(x => x.id === id)
      return [m?.stroke.toLowerCase(), m?.lineWidth]
    }).toEqual([SELECTED_EDGE, SELECTED_W])
    const band = page.getByTestId('feedback-selected-band')
    await expect(band).toBeVisible()
    // 竖带的内侧正好盖住 [start, end] 这几根 K 线(整根对齐),上下贯穿主图和副图
    const want = async () => {
      const bw = (await xOf(page, f0 + 1)) - (await xOf(page, f0))
      return { left: (await xOf(page, f0)) - bw / 2, right: (await xOf(page, f1)) + bw / 2 }
    }
    const got = () => band.evaluate(e => {
      const r = e.getBoundingClientRect(), cs = getComputedStyle(e)
      const bl = parseFloat(cs.borderLeftWidth), br = parseFloat(cs.borderRightWidth)
      const wrap = document.querySelector('.kline-wrap-v2')!.getBoundingClientRect()
      return { left: r.left + bl, right: r.right - br, top: r.top - wrap.top, bottom: wrap.bottom - r.bottom,
               style: [cs.borderLeftStyle, cs.borderRightStyle], color: [cs.borderLeftColor, cs.borderRightColor], bl, br,
               bg: cs.backgroundColor }
    })
    await expect.poll(async () => Math.abs((await got()).left - (await want()).left)).toBeLessThan(1.5)
    const g = await got(), w = await want()
    expect(Math.abs(g.right - w.right)).toBeLessThan(1.5)
    expect([g.top, g.bottom].every(v => Math.abs(v) < 1)).toBe(true)
    expect(g.style).toEqual(['solid', 'solid'])                              // 拖选草稿是虚线,选中是实线
    expect(g.color).toEqual(['rgb(17, 17, 17)', 'rgb(17, 17, 17)'])
    expect(g.bl).toBeGreaterThanOrEqual(2)
    const sub = (await page.locator('.sub-outer').boundingBox())!, main = (await page.locator('.main-chart').boundingBox())!
    const bb = (await band.boundingBox())!
    expect(bb.y).toBeLessThanOrEqual(main.y + 1)
    expect(bb.y + bb.height).toBeGreaterThanOrEqual(sub.y + sub.height - 1)
    await page.mouse.move(10, 10)
    await shot(page, testInfo, 'selected-band.png')
    // 平移 / 缩放后竖带跟着走
    await zoomTo(page, F.start - 20, f1 + 30)
    await expect.poll(async () => Math.abs((await got()).left - (await want()).left)).toBeLessThan(1.5)
    expect(Math.abs((await got()).right - (await want()).right)).toBeLessThan(1.5)

    // ── 卡片的 edit:从别处落过去,落定后打开那条的面板并预填(等同选中记号再按 Enter) ──
    await zoomTo(page, G.start - 4, G.buys.at(-1)! + 4)
    await card.getByTestId('feedback-row-edit').click()
    await expect(panel(page)).toBeVisible()
    await expect(panel(page)).toHaveAttribute('data-editing', id)
    await expect(panel(page)).toHaveAttribute('data-target', 'family')
    await expect(page.locator('[data-testid="feedback-node"].on')).toHaveCount(2)
    await expect(page.locator(`[data-testid="feedback-node"][data-node="${nodeName}"]`)).toHaveClass(/\bon\b/)
    await expect(page.locator(`[data-testid="feedback-node"][data-node="${nodeName2}"]`)).toHaveClass(/\bon\b/)
    await expect(note).toHaveValue(`${LONG}\nsecond line`)
    expect((await note.boundingBox())!.height).toBeGreaterThan(box0.height * 2.6)      // 预填的长 note 一打开就是多行
    expect(await focusInPanel(page)).toBe(false)
    await expect.poll(() => fbOf(page, 'selectedId')).toBe(id)
    await expect.poll(() => view(page, 'currentDay')).toBe(f0)
    await page.waitForTimeout(400)
    await expect(panel(page)).toBeVisible()                                  // 落定后的重画不把它关掉
    // 面板在默认落点:靠在那条的竖带旁、底边贴住显示栏上沿,整个在视口里
    await expect(band).toBeVisible()
    await expectDefaultPlace(page)
    expect((await panel(page).boundingBox())!.y).toBeGreaterThanOrEqual(0)
    await shot(page, testInfo, 'card-edit-panel.png')
    // 在面板里把两个 node 都点掉、保存:记录不再带 nodes,卡片的组头写灰字 none
    await page.locator(`[data-testid="feedback-node"][data-node="${nodeName}"]`).click()
    await page.locator(`[data-testid="feedback-node"][data-node="${nodeName2}"]`).click()
    await expect(page.locator('[data-testid="feedback-node"].on')).toHaveCount(0)
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const after = feedbackOf(await annState(page)).find(f => f.id === id)
    expect('nodes' in after).toBe(false)
    expect(after.note).toBe(`${LONG}\nsecond line`)
    await expect(groupOf(page, id).getByTestId('feedback-row-node')).toHaveCount(0)
    await expect(groupOf(page, id).getByTestId('feedback-row-nodes-none')).toHaveText('none')

    // ── 从别的股票点卡片的 edit:换到 CRNC、app 重跑,落定后同样打开那条(默认落点) ──
    await page.evaluate(() => (window as any).__e2e.view.openSymbol('AAPL'))
    await waitChart(page, 'AAPL')
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe('AAPL')
    await expect(band).toHaveCount(0)                                        // 选中的那条不在这只股票上:没有竖带
    await card.getByTestId('feedback-row-edit').click()
    await waitChart(page, SYMBOL)
    await expect(panel(page)).toBeVisible({ timeout: 60_000 })
    await expect(panel(page)).toHaveAttribute('data-editing', id)
    await expect(page.getByTestId('feedback-symbol')).toHaveText(SYMBOL)
    await expect.poll(() => view(page, 'currentDay')).toBe(f0)
    await page.waitForTimeout(600)
    await expect(panel(page)).toBeVisible()
    await expectDefaultPlace(page)
    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)

    // ── 删掉选中的那条:取消选中,竖带消失 ──
    await expect(band).toBeVisible()
    await card.getByTestId('feedback-row-delete').click()
    await expect(card).toHaveCount(0)
    await expect(band).toHaveCount(0)
    expect(await fbOf(page, 'selectedId')).toBeNull()
    await settled(page)
    expect(feedbackOf(await annState(page)).map(f => f.id)).not.toContain(id)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('issue 复用:跨股票挑一条共享(以前存下的也能挑);改字后 all / only this;没写 note 的要先补;再点一次不再共享;侧栏分组', async ({ page }, testInfo) => {
    const { dates, F } = plan
    const ISS_NEG = 'f-e2e-911', ISS_DAG = 'f-e2e-912', ISS_BARE = 'f-e2e-913'
    const NOTE = '买在新平台末端,离阶跃太远', NOTE_ALL = '买在新平台末端,离阶跃已经隔了一整段', NOTE_ONLY = '这一处是量能跟不上'
    const NOTE_DAG = '旧平台和新平台之间隔了一段下跌', NOTE_BARE = '平台里的波动太大,不算平台'
    const seedOf = (id: string, v: Record<string, unknown>) =>
      ({ id, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, source: 'picked', target: 'point', ...v })
    const negSeed = seedOf(ISS_NEG, { start: dates[F.buys[2]], end: dates[F.buys[2]], answer: 'neg', note: NOTE })
    const dagSeed = seedOf(ISS_DAG, { start: dates[F.buys[0]], end: dates[F.buys[0]], answer: 'off_pattern', note: NOTE_DAG,
                                      nodes: ['plateau'], dag: true })
    const bareSeed = seedOf(ISS_BARE, { start: dates[F.buys[0]], end: dates[F.buys[1]], target: 'range', answer: 'off_pattern',
                                        nodes: ['plateau'] })
    // 三条都是以前存下的形状:neg + note;off_pattern + node + dag + note;off_pattern + node、没写 note
    await postOps(backend!, [negSeed, dagSeed, bareSeed].map(v => ({ kind: 'feedback', id: v.id, base: null, value: { ...v, symbol: SYMBOL } })))
    /** 一条以前存下的记录被界面改写之后的样子:拿掉 answer、dag,换上 extra。 */
    const rewritten = (seed: Record<string, unknown>, extra: Record<string, unknown>) => {
      const { answer: _a, dag: _d, ...rest } = seed
      return { ...rest, ...extra }
    }
    await openCompare(page, dates[F.buys[2]])

    // ── 现找第二只股票:new_step 在它上面有一族三个以上的买点 ──
    const all: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const at = all.indexOf(SYMBOL)
    const candidates = ['AAPL', ...all.slice(at + 1), ...all.slice(0, Math.max(0, at))].filter(s => s !== SYMBOL).slice(0, 60)
    let S2 = '', fam: Fam | null = null, d2: string[] = []
    for (const sym of candidates) {
      await page.evaluate(s => (window as any).__e2e.view.openSymbol(s), sym)
      await waitChart(page, sym)
      await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe(sym)
      await page.waitForTimeout(400)
      const got = await page.evaluate(() => {
        const e2e = (window as any).__e2e
        const fams = (e2e.chartSub().getOption()?.series?.find((s: any) => s.name === 'bracket-lines')?.data ?? [])
          .map((d: any) => ({ start: d.family_start as number, buys: [...(d.buy_days ?? [])].sort((a: number, b: number) => a - b) }))
        return { fams, dates: e2e.chartMain().getOption().xAxis[0].data as string[] }
      })
      const ok = (got.fams as Fam[]).filter(f => f.buys.length >= 3 && f.buys.at(-1)! - f.buys[0] <= 40)
        .sort((a, b) => b.buys.length - a.buys.length)[0]
      if (ok) { S2 = sym; fam = ok; d2 = got.dates; break }
    }
    expect(fam, `前 ${candidates.length} 只候选股票里要有一只:${APP} 有一族三个以上买点`).not.toBeNull()
    const [b0, b1, b2] = fam!.buys
    await zoomTo(page, Math.min(fam!.start, b0 - 12) - 3, fam!.buys.at(-1)! + 8)
    const fbAt = async (symbol: string, start: string, end = start) =>
      feedbackOf(await annState(page), symbol).find(f => f.start === start && f.end === end) ?? null
    const byId = async (id: string, symbol = SYMBOL) => feedbackOf(await annState(page), symbol).find(f => f.id === id)
    const issueItem = (note: string) => page.locator('[data-testid="feedback-issue"]', { hasText: note })
    const bareItem = page.locator(`[data-testid="feedback-issue"][data-key="${ISS_BARE}"]`)

    // ── 第二只股票上点 ▼、按 Enter:issues 一打开就列出来(不用先选答案;跨股票,以前存下的两种答案都在) ──
    await clickBuy(page, b0)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-target', 'point')
    await expect(page.getByTestId('feedback-symbol')).toHaveText(S2)
    await expect(page.getByTestId('feedback-issues')).toBeVisible()
    await expect(issueItem(NOTE)).toHaveCount(1)
    await expect(issueItem(NOTE)).toHaveAttribute('data-key', ISS_NEG)        // 还不带 issue 值:组键是它自己的编号
    await expect(issueItem(NOTE)).toHaveAttribute('data-places', '1')
    await expect(issueItem(NOTE_DAG)).toHaveCount(1)
    await expect(issueItem(NOTE_DAG).locator('.fb-chip')).toHaveText(['plateau'])   // node 小标签;以前点的 dag 不显示
    await expect(bareItem).toHaveText('plateauplaces 1')                      // 没写理由的:只有 node 与处数
    await expect(page.getByTestId('feedback-issues')).not.toContainText(/off_pattern|\bneg\b|dag/)
    expect(await focusInPanel(page)).toBe(false)
    // 挑一条:note 填好、那条加黑边,不动焦点;Enter 保存
    await issueItem(NOTE).click()
    await expect(issueItem(NOTE)).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue(NOTE)
    expect(await focusInPanel(page)).toBe(false)
    await expect(page.getByTestId('feedback-share')).toHaveCount(0)
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const p0 = (await fbAt(S2, d2[b0]))!
    const V: string = p0.issue
    expect(V).toMatch(/^i-e2e-\d+$/)
    expect(p0).toMatchObject({ note: NOTE, target: 'point', issue: V })
    expect('answer' in p0).toBe(false)
    // 原来那条同批补上 issue 值,并改写成不带 answer 的;其余原样
    expect(await byId(ISS_NEG)).toEqual(rewritten(negSeed, { issue: V }))

    // ── 再标一处,挑同一条又改了字:save 换成 shared by n places + all / only this;Enter 不存 ──
    await clickBuy(page, b1)
    await openFbByButton(page)
    await expect(issueItem(NOTE)).toHaveAttribute('data-key', V)
    await expect(issueItem(NOTE)).toHaveAttribute('data-places', '2')
    await issueItem(NOTE).click()
    await expect(page.getByTestId('feedback-save')).toBeVisible()
    await page.getByTestId('feedback-note').fill(NOTE_ALL)
    await expect(page.getByTestId('feedback-share-count')).toHaveText('shared by 3 places')
    await expect(page.getByTestId('feedback-share').locator('button')).toHaveText(['all', 'only this'])
    await expect(page.getByTestId('feedback-save')).toHaveCount(0)
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['all | only this'])
    await expect(page.getByTestId('feedback-blocked')).toHaveCount(0)
    await settled(page)
    expect(await fbAt(S2, d2[b1])).toBeNull()
    const pb = (await panel(page).boundingBox())!
    expect(pb.y + pb.height).toBeLessThanOrEqual(page.viewportSize()!.height)
    await shot(page, testInfo, 'issue-panel.png')
    // all:各处一起改(一批),都还带同一个 issue 值
    await page.getByTestId('feedback-share-all').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const p1 = (await fbAt(S2, d2[b1]))!
    expect([p1.note, p1.issue]).toEqual([NOTE_ALL, V])
    expect([(await fbAt(S2, d2[b0]))!.note, (await fbAt(S2, d2[b0]))!.issue]).toEqual([NOTE_ALL, V])
    expect(await byId(ISS_NEG)).toEqual(rewritten(negSeed, { note: NOTE_ALL, issue: V }))   // 别的股票上的那处也改了,日期、app_ver 不动

    // ── 第三处,挑同一条又改字,选 only this:这一处不带 issue 值、另立;别的处不变 ──
    await clickBuy(page, b2)
    await openFb(page)
    await expect(issueItem(NOTE_ALL)).toHaveAttribute('data-places', '3')
    await issueItem(NOTE_ALL).click()
    await page.getByTestId('feedback-note').fill(NOTE_ONLY)
    await expect(page.getByTestId('feedback-share-count')).toHaveText('shared by 4 places')
    await page.getByTestId('feedback-share-only').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const p2 = (await fbAt(S2, d2[b2]))!
    expect(p2.note).toBe(NOTE_ONLY)
    expect('issue' in p2).toBe(false)
    expect([(await fbAt(S2, d2[b0]))!.note, (await fbAt(S2, d2[b1]))!.note, (await byId(ISS_NEG)).note])
      .toEqual([NOTE_ALL, NOTE_ALL, NOTE_ALL])

    // ── 以前存下的带 dag 的 issue 也能复用:拖一段(头两个买点)→ 挑它,node 与 note 填好;存下的两处都不带 answer、dag ──
    await feedbackOn(page)
    const ky = await klineY(page)
    await page.mouse.move(await xOf(page, b0), ky)
    await page.mouse.down()
    await page.mouse.move((await xOf(page, b0) + await xOf(page, b1)) / 2, ky, { steps: 4 })
    await page.mouse.move(await xOf(page, b1), ky, { steps: 4 })
    await page.mouse.up()
    await expect(panel(page)).toHaveAttribute('data-target', 'range')
    await expect(page.getByTestId('feedback-span')).toHaveText(`${d2[b0]} – ${d2[b1]}`)
    await expect(issueItem(NOTE_ALL)).toHaveCount(1)                           // 列表不按答案分:两种都在
    await issueItem(NOTE_DAG).click()
    await expect(issueItem(NOTE_DAG)).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-dag')).toHaveCount(0)
    await expect(page.locator('[data-testid="feedback-node"][data-node="plateau"]')).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue(NOTE_DAG)
    await expect(page.getByTestId('feedback-share')).toHaveCount(0)
    // 截图前把鼠标挪到面板上、收起 K 线的悬停提示(否则它压在面板左边)
    await page.getByTestId('feedback-target').hover()
    await page.evaluate(() => {
      const e2e = (window as any).__e2e
      for (const c of [e2e.chartMain(), e2e.chartSub()]) c.dispatchAction({ type: 'hideTip' })
    })
    await page.waitForTimeout(300)
    await shot(page, testInfo, 'unified-panel.png', panel(page), 120)
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const pf = (await fbAt(S2, d2[b0], d2[b1]))!
    const V2: string = pf.issue
    expect(V2).toMatch(/^i-e2e-\d+$/)
    expect(V2).not.toBe(V)
    expect(pf).toMatchObject({ target: 'range', note: NOTE_DAG, nodes: ['plateau'] })
    expect(['answer' in pf, 'dag' in pf]).toEqual([false, false])
    expect(await byId(ISS_DAG)).toEqual(rewritten(dagSeed, { issue: V2 }))

    // ── 记号悬停:和几处共享(两处以上才写) ──
    await expect.poll(async () => (await fbOf(page, 'statusById'))?.[p1.id]?.status, { timeout: 60_000 }).toBe('matched')
    const m1 = await findItem(page, 'feedback-strip', x => x.d?.feedback_id === p1.id, 0)
    await page.mouse.move(m1.x + m1.w / 2, m1.y + m1.h / 2)
    await expect(page.locator('body > div').filter({ hasText: 'shared: 3 places' }).first()).toBeVisible()
    await page.mouse.move(10, 10)
    const m2 = await findItem(page, 'feedback-strip', x => x.d?.feedback_id === p2.id, 0)
    await page.mouse.move(m2.x + m2.w / 2, m2.y + m2.h / 2)
    const tip2 = page.locator('body > div').filter({ hasText: 'target: ' })
    await expect(tip2.first()).toBeVisible()
    await expect(tip2.first()).not.toContainText('shared:')
    await page.mouse.move(10, 10)

    // ── 侧栏按 issue 分组:组头写一次 node 与理由、处数、其中 app 还在买的处数;组里每处一行(跨股票) ──
    await page.getByTestId('annotation-tab-feedback').click()
    await expect(page.getByTestId('feedback-loading')).toHaveCount(0)
    const gNeg = page.locator(`[data-testid="feedback-group"][data-key="${V}"]`)
    await expect(gNeg).toHaveAttribute('data-places', '3')
    await expect(gNeg.getByTestId('feedback-row-nodes-none')).toHaveText('none')
    await expect(gNeg.getByTestId('feedback-row-note')).toHaveText([NOTE_ALL])
    await expect(gNeg.getByTestId('feedback-group-places')).toHaveText('places 3')
    await expect(gNeg.getByTestId('feedback-group-places')).toHaveAttribute('title', 'places sharing this issue (same note and nodes)')
    await expect(gNeg.getByTestId('feedback-group-matched')).toHaveText('matched 3')
    expect((await gNeg.getByTestId('feedback-row').evaluateAll(els => els.map(e => e.getAttribute('data-id')))).sort())
      .toEqual([ISS_NEG, p0.id, p1.id].sort())
    expect((await gNeg.getByTestId('feedback-row-symbol').allTextContents()).sort()).toEqual([SYMBOL, S2, S2].sort())
    await expect(gNeg.getByTestId('feedback-row-edit')).toHaveCount(3)
    const gDag = page.locator(`[data-testid="feedback-group"][data-key="${V2}"]`)
    await expect(gDag).toHaveAttribute('data-places', '2')
    await expect(gDag.getByTestId('feedback-row-node')).toHaveText(['plateau'])
    await expect(gDag.getByTestId('feedback-row-note')).toHaveText([NOTE_DAG])
    await expect(groupOf(page, p2.id)).toHaveAttribute('data-places', '1')    // only this 的那一处:自己一组
    await expect(groupOf(page, p2.id).getByTestId('feedback-row-note')).toHaveText([NOTE_ONLY])
    // 以前存下的、还没被改写的两条照常成组:只点了 node 没写理由的(组头只有一行)、neg + note 的(none + 理由)
    await expect(groupOf(page, ISS_BARE).getByTestId('feedback-row-node')).toHaveText(['plateau'])
    await expect(groupOf(page, ISS_BARE).getByTestId('feedback-row-note')).toHaveCount(0)
    expect((await byId(RED)).answer).toBe('neg')
    await expect(groupOf(page, RED).getByTestId('feedback-row-nodes-none')).toHaveText('none')
    await expect(page.getByTestId('feedback-row-answer')).toHaveCount(0)
    await expect(page.getByTestId('feedback-row-dag')).toHaveCount(0)
    await expect(page.getByTestId('feedback-page')).not.toContainText(/off_pattern|\bneg\b|answer|dag|undefined/)
    // 每条反馈恰在一组里
    const total = feedbackOf(await annState(page)).length + feedbackOf(await annState(page), S2).length
    await expect(page.getByTestId('feedback-row')).toHaveCount(total)
    await gNeg.scrollIntoViewIfNeeded()
    await shot(page, testInfo, 'issue-sidebar.png')
    await page.locator('[data-testid="feedback-page"]').evaluate(e => e.scrollIntoView({ block: 'start' }))
    await shot(page, testInfo, 'unified-sidebar.png', page.getByTestId('feedback-page'), 24)

    // ── 挑一个以前存下的、没写 note 的 issue:不补存不了;补了以后问 all / only this;all 把原来那处也补上并改写 ──
    await feedbackOn(page)
    const ky2 = await klineY(page)
    await page.mouse.move(await xOf(page, b1), ky2)
    await page.mouse.down()
    await page.mouse.move((await xOf(page, b1) + await xOf(page, b2)) / 2, ky2, { steps: 4 })
    await page.mouse.move(await xOf(page, b2), ky2, { steps: 4 })
    await page.mouse.up()
    await expect(panel(page)).toHaveAttribute('data-target', 'range')
    await expect(panel(page)).toHaveAttribute('data-editing', '')
    await expect(page.getByTestId('feedback-span')).toHaveText(`${d2[b1]} – ${d2[b2]}`)
    await bareItem.click()
    await expect(bareItem).toHaveClass(/\bon\b/)
    await expect(page.locator('[data-testid="feedback-node"][data-node="plateau"]')).toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue('')
    await expect(page.getByTestId('feedback-share')).toHaveCount(0)            // 内容还和它一样:先缺的是 note
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['note'])
    await page.getByTestId('feedback-note').fill(NOTE_BARE)
    await expect(page.getByTestId('feedback-share-count')).toHaveText('shared by 2 places')
    await expect(page.getByTestId('feedback-save')).toHaveCount(0)
    await page.getByTestId('feedback-share-all').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    expect(await annOf(page, 'saveError')).toBeNull()
    const pBare = (await fbAt(S2, d2[b1], d2[b2]))!
    const V3: string = pBare.issue
    expect(V3).toMatch(/^i-e2e-\d+$/)
    expect(pBare).toMatchObject({ target: 'range', note: NOTE_BARE, nodes: ['plateau'] })
    expect('answer' in pBare).toBe(false)
    expect(await byId(ISS_BARE)).toEqual(rewritten(bareSeed, { note: NOTE_BARE, issue: V3 }))
    await expect(groupOf(page, ISS_BARE)).toHaveAttribute('data-places', '2')
    await expect(groupOf(page, ISS_BARE).getByTestId('feedback-row-note')).toHaveText([NOTE_BARE])

    // ── 再点一次已连着的那条 = 不再共享:不问 all / only this;内容留着,这一处不再带 issue 值,其余各处不动 ──
    await clickBuy(page, b0)
    await openFb(page)
    await expect(panel(page)).toHaveAttribute('data-editing', p0.id)
    await expect(issueItem(NOTE_ALL)).toHaveClass(/\bon\b/)                   // 打开已有的一处:连着的那条标着
    await issueItem(NOTE_ALL).click()
    await expect(issueItem(NOTE_ALL)).not.toHaveClass(/\bon\b/)
    await expect(page.getByTestId('feedback-note')).toHaveValue(NOTE_ALL)
    await expect(page.getByTestId('feedback-share')).toHaveCount(0)
    await page.getByTestId('feedback-save').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const left = (await fbAt(S2, d2[b0]))!
    expect(left.id).toBe(p0.id)
    expect(left.note).toBe(NOTE_ALL)
    expect('issue' in left).toBe(false)
    expect([(await fbAt(S2, d2[b1]))!.issue, (await fbAt(S2, d2[b1]))!.note]).toEqual([V, NOTE_ALL])
    expect(await byId(ISS_NEG)).toEqual(rewritten(negSeed, { note: NOTE_ALL, issue: V }))
    await expect(gNeg).toHaveAttribute('data-places', '2')

    // ── 行上 delete 只删这一处:组还在 ──
    await gNeg.locator(`[data-testid="feedback-row"][data-id="${p1.id}"] [data-testid="feedback-row-delete"]`).click()
    await expect(gNeg).toHaveAttribute('data-places', '1')
    await settled(page)
    expect(await fbAt(S2, d2[b1])).toBeNull()
    expect(await byId(ISS_NEG)).toEqual(rewritten(negSeed, { note: NOTE_ALL, issue: V }))
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('以前存下的记录:卡片 edit 改一条(保存后不带 answer);没写 note 的不补存不了;撤销删除照原值或照同一个 issue 的别处写回', async ({ page }) => {
    const U1 = 'f-e2e-921', U2 = 'f-e2e-922', ISSUE = 'i-seed-1'
    // 同一个 issue 的两处,都是以前存下的「off_pattern + node、没写 note」
    const old = (id: string, day: string) => ({ id, pattern: PATTERN, app_id: APP, app_ver: plan.appVer, source: 'picked',
      target: 'point', start: day, end: day, answer: 'off_pattern', nodes: ['plateau'], issue: ISSUE })
    const u1 = old(U1, plan.plain), u2 = old(U2, plan.lost.start)
    await postOps(backend!, [u1, u2].map(v => ({ kind: 'feedback', id: v.id, base: null, value: { ...v, symbol: SYMBOL } })))
    await openCompare(page, plan.red)
    const byId = async (id: string) => feedbackOf(await annState(page)).find(f => f.id === id)
    const onServer = async (id: string) =>
      feedbackOf((await (await fetch(`${backend!.base}/annotations`)).json()).state).find(f => f.id === id)
    const rowOf = (id: string) => page.locator(`[data-testid="feedback-row"][data-id="${id}"]`)
    await page.getByTestId('annotation-tab-feedback').click()
    await expect(page.getByTestId('feedback-loading')).toHaveCount(0)
    const g = page.locator(`[data-testid="feedback-group"][data-key="${ISSUE}"]`)
    await expect(g).toHaveAttribute('data-places', '2')
    await expect(g.getByTestId('feedback-row-node')).toHaveText(['plateau'])
    await expect(g.getByTestId('feedback-row-note')).toHaveCount(0)

    // ── 撤销删除:这个 issue 还有别的处(点了 node、没写 note)→ 写回的照那一处(带 answer、node,没有 note),后端收下 ──
    await rowOf(U2).getByTestId('feedback-row-delete').click()
    await expect(g).toHaveAttribute('data-places', '1')
    await settled(page)
    expect(await onServer(U2)).toBeUndefined()
    await expect(page.getByTestId('notice-undo')).toHaveAttribute('data-kind', 'feedback')
    await page.getByTestId('notice-undo-btn').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    expect(await annOf(page, 'saveError')).toBeNull()
    expect(await byId(U2)).toEqual(u2)
    expect(await onServer(U2)).toEqual(u2)                                    // 真存进了后端,不只是页面上有
    await expect(g).toHaveAttribute('data-places', '2')

    // ── 撤销删除:单独一处、以前存下的 neg + note → 照原值写回(仍带 answer) ──
    const red0 = await byId(RED)
    expect(red0).toMatchObject({ answer: 'neg', note: '追在阶跃之后太远' })
    await rowOf(RED).getByTestId('feedback-row-delete').click()
    await expect(rowOf(RED)).toHaveCount(0)
    await settled(page)
    await page.getByTestId('notice-undo-btn').click()
    await expect(page.getByTestId('notice-undo')).toHaveCount(0)
    await settled(page)
    expect(await annOf(page, 'saveError')).toBeNull()
    expect(await onServer(RED)).toEqual(red0)

    // ── 卡片 edit 打开以前存下的 neg + note:预填理由、没有答案按钮;改几个字保存 → 不再带 answer ──
    await rowOf(RED).getByTestId('feedback-row-edit').click()
    await expect(panel(page)).toHaveAttribute('data-editing', RED)
    await expect(page.getByTestId('feedback-note')).toHaveValue('追在阶跃之后太远')
    await expect(page.locator('[data-testid="feedback-node"].on')).toHaveCount(0)
    await expect(panel(page)).not.toContainText(/answer|off_pattern|\bneg\b|dag|undefined/)
    await page.getByTestId('feedback-note').fill('追在阶跃之后太远,已经隔了三周')
    await page.keyboard.press('Enter')
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    const { answer: _a, ...redPlain } = red0
    expect(await onServer(RED)).toEqual({ ...redPlain, app_ver: plan.appVer, note: '追在阶跃之后太远,已经隔了三周' })
    await expect(groupOf(page, RED).getByTestId('feedback-row-note')).toHaveText('追在阶跃之后太远,已经隔了三周')

    // ── 卡片 edit 打开以前存下的「点了 node、没写 note」:node 预填点上;不补 note 存不了;补了(和同 issue 的另一处不同了)
    //    选 only this → 这一处不带 answer、不带 issue 值,另一处原样 ──
    await rowOf(U1).getByTestId('feedback-row-edit').click()
    await expect(panel(page)).toHaveAttribute('data-editing', U1)
    await expect(page.locator('[data-testid="feedback-node"].on')).toHaveText(/plateau/)
    await expect(page.getByTestId('feedback-note')).toHaveValue('')
    await page.keyboard.press('Enter')
    await expect(panel(page)).toBeVisible()
    await expect(page.locator('[data-testid="feedback-problems"] [data-problem]')).toHaveText(['note'])
    await settled(page)
    expect(await onServer(U1)).toEqual(u1)
    await page.getByTestId('feedback-note').fill('这里的平台是斜的')
    await expect(page.getByTestId('feedback-share-count')).toHaveText('shared by 2 places')
    await page.getByTestId('feedback-share-only').click()
    await expect(panel(page)).toHaveCount(0)
    await settled(page)
    expect(await annOf(page, 'saveError')).toBeNull()
    const { answer: _b, issue: _i, ...u1Plain } = u1
    expect(await onServer(U1)).toEqual({ ...u1Plain, note: '这里的平台是斜的' })
    expect(await onServer(U2)).toEqual(u2)
    await expect(g).toHaveAttribute('data-places', '1')
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})

/** 点亮 feedback 工具(已亮不动)。 */
async function feedbackOn(page: Page) {
  const btn = page.getByTestId('tool-feedback')
  if (!/\bon\b/.test((await btn.getAttribute('class')) ?? '')) await btn.click()
  await expect(btn).toHaveClass(/\bon\b/)
}
