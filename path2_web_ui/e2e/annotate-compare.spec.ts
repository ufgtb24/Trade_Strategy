import { test, expect, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, TRAIN_END, lanes, routeTo, startBackend, stopBackend, type Backend } from './annotateHelpers'

/**
 * 顶栏 mode 的 compare / app。compare = 主视图那张图(app 的族行、bracket 的 hit 行、K 线区的记号、档位按钮)+ 标注层
 * (spec 5.8,2026-11-05 改)。
 * 规格变更,不是放宽:实施票 11 时这里断言「event 叠在特征轨上、图上没有任何对照 tag、主图不变」;spec 5.8 改为
 * compare 复用主视图那张图、map 了的轨写 ⇣ node、没 map 的挂 unmapped、▲ 字母后挂 ✓ / ✗、selection 页出 diagnose,
 * 所以改成下面的检查;第二段的 link tag、diff tag、chance_high 与档位小字仍一个都不许出现。
 * 1. 用现成的 app bo_only 加一份手写的 mapping(pattern W底:突破 → bo、横盘 → pk;e2e 后端从临时目录读它,
 *    见 e2e/annotationBackend.py):没有 mapping 的 pattern 下 compare、app 是灰的;W底 下切到 compare,
 *    app 的每个 event 都画出来(bo、pk 画在 K 线区)、每个 hit 都在 bracket 的 hit 行上,数目与后端 /preview 给的一致;
 *    用户轨照 annotate 的顺序,map 了的写 ⇣ node、没 map 的挂 unmapped;档位按钮在、和 app 模式同一份状态;
 *    选中的样本 → 当前日落在样本日,selection 页出 diagnose;→ 走到下一个样本;选中框后点 app 的东西,Delete 删不到框;
 *    选中框后点 ▲ 选中样本,Delete 既不删样本、也删不到之前选中的框;
 *    app 的全部输出都落在截到 2025-12-31 的 K 线里;参照层 peaks 在 compare 下照样能开。
 *    再切到 app:按 node 分轨的主视图画法,参照层自动关。
 * 2. compare 下换股票不退出 compare:pattern 页的样本卡、代码输入、random、rally 都留在 compare,app 对新股票重跑;
 *    链接一律落在 annotate。从扫描结果的 app 出发用 rally、random 落在 annotate,由 e2e/annotate-rally-random.spec.ts 验。
 *
 * 标注用 tests/path2_web/fixtures/annotation_grouping_v1 的例子批次(指纹换成测试后端本机副本的),写在临时目录里。
 * 整页截图挂在测试结果里(compare-*.png、app-*.png)。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nfeatures:\n  w-pc-3: bo\n  w-pc-1: pk\n'
const LANE_OF: Record<string, string> = { bo: '突破', pk: '横盘' }
// 第二段才有的对照 tag 与已退役的档位小字:compare 图上一个都不许出现
const TAG_WORDS = ['connected', 'disconnected', 'not_qualified', 'excluded', 'optional', 'must_not', 'chance_high',
                   'remapped', 'detected_only', 'qualified_only']
/** 轨标题去掉富文本标记后的文字。 */
const plain = (t: string) => t.replace(/\{(biz|sym|node|tag|n|bg)\|([^}]*)\}/g, '$2')

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
/** 现算的 app 是对哪只股票跑的(还没跑完为 null)。 */
const runSymbol = (page: Page) => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null)

async function pickPattern(page: Page, text: string | null) {
  await page.getByTestId('top-pattern-button').click()
  if (text === null) await page.getByTestId('top-pattern-unsorted').click()
  else await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().currentPattern)).toBe(text)
}

async function waitChart(page: Page, symbol: string) {
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
}

/** 副图某个系列的数据行。 */
const subRows = (page: Page, name: string) => page.evaluate(n =>
  ((window as any).__e2e.chartSub().getOption().series ?? []).find((s: any) => s.name === n)?.data ?? null, name)

/** 后端对这只股票跑 bo_only 的输出(和页面跑的同一个请求)。 */
async function preview(b: Backend, symbol: string) {
  const r = await fetch(`${b.base}/preview?pattern_id=bo_only&symbol=${symbol}&start=1900-01-01&end=${TRAIN_END}&label_horizon=20`)
  return (await r.json()).analysis as { events: any[]; hits: any[] }
}

/** 副图上全部文字标题(轨标题、band 表头、user / hits),从上到下。 */
const subTitles = async (page: Page) => (await page.evaluate(() => {
  const opt = (window as any).__e2e.chartSub().getOption()
  return (opt.graphic?.[0]?.elements ?? []).filter((e: any) => e.type === 'text')
    .map((e: any) => ({ text: String(e.style?.text ?? ''), top: e.top as number }))
})).sort((a, b) => a.top - b.top).map(t => plain(t.text))
/** 图上画出来的 app event(副图的族行成员 + K 线区的记号)。 */
const drawnEvents = (page: Page) => page.evaluate(() => {
  const ids = new Set<string>()
  const sub = (window as any).__e2e.chartSub().getOption().series ?? []
  for (const s of sub) if (s.name === 'intervals' || s.name === 'points') for (const d of s.data ?? []) for (const id of d.member_ids ?? [d.instance_id]) ids.add(id)
  const main = (window as any).__e2e.chartMain().getOption().series ?? []
  for (const d of main.find((s: any) => s.name === 'price-points')?.data ?? []) ids.add(d.instance_id)
  return [...ids].sort()
})
/** bracket 的 hit 行上的 hit。 */
const drawnHits = async (page: Page) => ((await subRows(page, 'brackets')) ?? [])
  .filter((d: any) => d.kind === 'mark').flatMap((d: any) => d.hit_ids ?? [d.hit_id]).sort()
async function setLevel(page: Page, l: string) {
  await page.getByTestId('level-control').getByRole('button', { name: l, exact: true }).click()
  await expect.poll(() => view(page, 'level')).toBe(l)
}

async function enterCompare(page: Page) {
  await page.getByTestId('mode-compare').click()
  await expect.poll(() => view(page, 'mode')).toBe('compare')
  await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('compare / app 叠画(bo_only + 手写 mapping)', () => {
  test.setTimeout(600_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    backend = await startBackend(undefined, { bo_only: MAPPING })
    await putFixture(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('compare 是主视图那张图 + 标注层:event、hit 都画出来,⇣ / unmapped / diagnose,聚焦样本与 →,Delete 删不到框,不越过 2025-12-31;没有 mapping 的 pattern 下 compare 是灰的', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await expect(page.getByTestId('mode-annotate')).toHaveClass(/\bon\b/)

    // 没有 mapping 的 pattern(unsorted、旗形):compare、app 变灰
    for (const p of [null, '旗形']) {
      await pickPattern(page, p)
      await expect(page.getByTestId('mode-compare')).toBeDisabled()
      await expect(page.getByTestId('mode-app')).toBeDisabled()
    }
    await pickPattern(page, 'W底')
    await expect(page.getByTestId('mode-compare')).toBeEnabled()
    await enterCompare(page)
    await expect(page.getByTestId('linked-app')).toHaveText('bo_only')

    const out = await preview(backend!, 'AAPL')
    expect(out.events.length).toBeGreaterThan(0)
    expect(out.hits.length).toBeGreaterThan(0)
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    expect(dates.at(-1)).toBe(TRAIN_END)

    // 档位按钮在 compare 下也有,和 app 模式同一份状态;调到 detected,每个 event 都画出来
    await expect(page.getByTestId('level-control')).toBeVisible()
    await setLevel(page, 'detected')
    await expect.poll(() => drawnEvents(page)).toEqual(out.events.map(e => e.instance_id).sort())
    await expect.poll(() => drawnHits(page)).toEqual(out.hits.map(m => m.hit_id).sort())
    // 数据墙:全部输出都在截到训练段末日的 K 线里
    for (const r of [...out.events, ...out.hits]) {
      expect(r.end_idx).toBeLessThan(dates.length)
      expect(dates[r.end_idx] <= TRAIN_END).toBe(true)
    }
    // K 线主图不被副图挤掉
    expect(await page.evaluate(() => (window as any).__e2e.chartMain().getHeight())).toBeGreaterThanOrEqual(300)

    // 上区(用户):特征轨照 annotate 的顺序,map 了的写 ⇣ node,没 map 的挂 unmapped,user 行在这一区最后;
    // 粗深线下面是 app 区,hits 行在第一行
    const titles = await subTitles(page)
    expect(titles).toEqual(['横盘  ⇣ pk', '缩量 ⊂ 横盘  unmapped', '突破  ⇣ bo', '派发  unmapped', 'user', 'hits'])
    const graphic = await page.evaluate(() => JSON.stringify((window as any).__e2e.chartSub().getOption().graphic ?? []))
    for (const w of TAG_WORDS) expect(graphic).not.toContain(w)

    // 选中的样本:当前日落在样本日,当家行是样本;selection 页出 diagnose(配对 node 是 eval_meta 的买点 node)
    const smp = await page.evaluate(() => {
      const a = (window as any).__e2e.ann()
      const c = a.state.charts.find((x: any) => x.symbol === 'AAPL')
      return { sel: a.selectedSampleId, list: c.samples.filter((s: any) => s.pattern === a.currentPattern).map((s: any) => [s.id, s.date]) }
    })
    const selDate = smp.list.find(([id]: string[]) => id === smp.sel)![1]
    await expect.poll(() => view(page, 'currentDay')).toBe(dates.indexOf(selDate))
    expect(await view(page, 'activeFamilyKey')).toBe('samples')
    await expect(page.getByTestId('sample-diagnose')).toBeVisible()
    await expect(page.getByTestId('diagnose-node')).toHaveText('bo')
    await expect(page.getByTestId('diagnose-date')).toHaveText(selDate)
    // events 一行:总数加三档各几个;每个 event 一块,键值排
    await expect(page.getByTestId('diagnose-count')).toContainText(/^\d+/)
    const nRows = await page.getByTestId('diagnose-row').count()
    if (nRows) {   // 那天有 event 才有分档计数和 event 块
      await expect(page.getByTestId('diagnose-count')).toContainText(/in_hit \d+/)
      await expect(page.getByTestId('diagnose-row').first().getByTestId('diagnose-level')).toHaveText(/^(in_hit|qualified|detected)$/)
    }
    await expect(page.getByTestId('diagnose-mark')).toHaveText(/^[✓✗]$/)
    // → 走到样本日更晚的下一个样本(当前 pattern 的,这张图上)
    const order = [...smp.list].sort((a: string[], b: string[]) => (a[1] < b[1] ? -1 : 1)).map((x: string[]) => x[0])
    const k = order.indexOf(smp.sel)
    if (k + 1 < order.length) {
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
      await page.keyboard.press('ArrowRight')
      await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).toBe(order[k + 1])
    }

    // 选中一个框后点 app 的记号(同 KlineChart 的点击入口):框的选中取消,按 Delete 不会删掉它
    const boxId: string = await page.evaluate(() =>
      (window as any).__e2e.ann().state.charts.find((x: any) => x.symbol === 'AAPL').boxes[0].id)
    await page.evaluate(id => (window as any).__e2e.ann().selectBox(id), boxId)
    await page.evaluate(() => {
      const m = (window as any).__e2e.chartMain()
      const s = m.getOption().series.find((x: any) => x.name === 'price-points')
      m.trigger('click', { componentType: 'series', seriesName: 'price-points', dataIndex: 0, data: s.data[0],
                          event: { event: new MouseEvent('click') } })
    })
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBeNull()
    await page.keyboard.press('Delete')
    expect(await page.evaluate(id => !!(window as any).__e2e.ann().state.charts.find((x: any) => x.symbol === 'AAPL')
      .boxes.find((b: any) => b.id === id), boxId)).toBe(true)

    // 选中一个框后在副图 user 行上点 ▲(选中样本,只是为了看):框的选中取消;按 Delete 什么都不删——
    // Delete 只删选中的框,样本不归它管,之前选中的框也删不到
    await page.evaluate(id => (window as any).__e2e.ann().selectBox(id), boxId)
    const counts = () => page.evaluate(() => {
      const c = (window as any).__e2e.ann().state.charts.find((x: any) => x.symbol === 'AAPL')
      return [c.boxes.length, c.samples.length]
    })
    const before = await counts()
    const tri = await page.evaluate(() => {
      const e = (window as any).__e2e, main = e.chartMain()
      const r = e.chartSub().getOption().series.find((s: any) => s.name === 'annotation-brackets').data[0]
      const n = main.getOption().xAxis[0].data.length
      main.dispatchAction({ type: 'dataZoom', start: Math.max(0, r[1] - 60) / n * 100, end: Math.min(n, r[1] + 20) / n * 100 })
      return { end: r[1] as number, y: (r[2] + r[3]) / 2 }
    })
    await page.waitForTimeout(300)
    const pt = await page.evaluate(({ end, y }) => {
      const [x] = (window as any).__e2e.chartSub().convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [end, 0])
      const rc = document.querySelector('.sub-inner')!.getBoundingClientRect()
      return { x: rc.left + x, y: rc.top + y }
    }, tri)
    await page.mouse.click(pt.x, pt.y)
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).not.toBeNull()
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBeNull()
    const picked = await page.evaluate(() => {
      const a = (window as any).__e2e.ann()
      return a.state.charts.find((x: any) => x.symbol === 'AAPL').samples.find((x: any) => x.id === a.selectedSampleId).date
    })
    expect(picked).toBe(dates[tri.end])                                   // 点中的就是那个 ▲ 的样本
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('Delete')
    await page.waitForTimeout(300)
    expect(await counts()).toEqual(before)
    expect(await page.evaluate(id => !!(window as any).__e2e.ann().state.charts.find((x: any) => x.symbol === 'AAPL')
      .boxes.find((b: any) => b.id === id), boxId)).toBe(true)

    // 什么都没选中时进 compare:默认聚焦离图窗中心最近的样本,selection 页显示它(只读,不选中);Esc 后不再显示
    await page.keyboard.press('Escape')
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).toBeNull()
    await expect(page.getByTestId('focused-sample')).toHaveCount(0)
    await page.getByTestId('mode-annotate').click()
    await enterCompare(page)
    await expect(page.getByTestId('focused-sample')).toBeVisible()
    await expect(page.getByTestId('focused-sample').getByTestId('sample-diagnose')).toBeVisible()
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedSampleId)).toBeNull()
    expect(await view(page, 'activeFamilyKey')).toBe('samples')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('focused-sample')).toHaveCount(0)

    // 参照层 peaks 在 compare 下可用:勾上画出峰线(同 /peaks)
    const box = page.getByTestId('ref-peaks')
    await expect(box).toBeEnabled()
    await box.check()
    const peaks = await (await fetch(`${backend!.base}/peaks?symbol=AAPL`)).json()
    expect(peaks.length).toBeGreaterThan(0)
    await expect.poll(() => page.evaluate(() => ((window as any).__e2e.chartMain().getOption().series
      .find((s: any) => s.name === 'ref-peaks')?.data ?? []).length)).toBe(peaks.length)

    // 图窗拉到第一个 hit 附近截图
    const h0 = Math.min(...out.hits.map(m => m.start_idx))
    await page.evaluate(([i, n]) => (window as any).__e2e.chartMain().dispatchAction(
      { type: 'dataZoom', start: Math.max(0, i - 90) / n * 100, end: Math.min(n, i + 40) / n * 100 }), [h0, dates.length])
    await page.screenshot({ path: testInfo.outputPath('compare-AAPL.png'), fullPage: true })

    // app:按 node 分轨的主视图画法,app 名、档位都在;hit 画成主视图的 bracket
    await page.getByTestId('mode-app').click()
    await expect.poll(() => view(page, 'mode')).toBe('app')
    await expect(page.getByTestId('linked-app')).toHaveText('bo_only')
    await expect(page.getByTestId('level-control')).toBeVisible()
    expect(await view(page, 'level')).toBe('detected')                     // 档位和 compare 同一份状态
    await expect(box).not.toBeChecked()                                    // 参照层切到 app 自动关、不能勾
    await expect(box).toBeDisabled()
    // bracket 系列里除了 hit 的记号还有买入日 ▼(kind 'buy');按记号上的 hit 数,每次 hit 恰好落在一个记号上
    await expect.poll(async () => (await drawnHits(page)).length).toBe(out.hits.length)
    await page.screenshot({ path: testInfo.outputPath('app-AAPL.png'), fullPage: true })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('compare 下用样本卡、代码输入、random、rally 换股票不退出 compare;链接进来落在 annotate', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/#sample=s-pc-11')
    await waitChart(page, 'AAPL')
    await pickPattern(page, 'W底')
    await enterCompare(page)

    // pattern 页点 MSFT 的样本卡:留在 compare,app 对 MSFT 重跑
    await page.getByTestId('annotation-tab-pattern').click()
    await page.locator('[data-testid="sample-card"][data-sample="s-pc-21"]').first().click()
    await waitChart(page, 'MSFT')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe('MSFT')
    const out = await preview(backend!, 'MSFT')
    await setLevel(page, 'detected')
    await expect.poll(() => drawnEvents(page)).toEqual(out.events.map(e => e.instance_id).sort())
    await page.screenshot({ path: testInfo.outputPath('compare-MSFT-from-sample-card.png'), fullPage: true })

    // 代码输入、random、rally:换了股票,仍在 compare,app 对新股票重跑
    await page.getByTestId('symbol-input').fill('NVDA')
    await page.getByTestId('symbol-input').press('Enter')
    await waitChart(page, 'NVDA')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(() => runSymbol(page), { timeout: 60_000 }).toBe('NVDA')
    await page.getByTestId('random-button').click()
    await expect.poll(() => view(page, 'symbol'), { timeout: 120_000 }).not.toBe('NVDA')
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(async () => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
    await page.getByTestId('rally-button').click()
    await expect(page.getByTestId('rally-row').first()).toBeVisible({ timeout: 300_000 })
    const before = await view(page, 'symbol')
    const row = page.locator(`[data-testid="rally-row"]:not([data-symbol="${before}"])`).first()
    await row.click()
    await expect.poll(() => view(page, 'symbol')).not.toBe(before)
    expect(await view(page, 'mode')).toBe('compare')
    await expect.poll(async () => runSymbol(page), { timeout: 60_000 }).toBe(await view(page, 'symbol'))
    // 两种链接:落在 annotate
    for (const link of ['#symbol=AAPL&date=2024-03-11', '#sample=s-pc-21']) {
      await enterCompare(page)
      await page.evaluate(h => { location.hash = h }, link)
      await expect.poll(() => view(page, 'mode')).toBe('annotate')
      await waitChart(page, link.includes('AAPL') ? 'AAPL' : 'MSFT')
    }
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })
})
