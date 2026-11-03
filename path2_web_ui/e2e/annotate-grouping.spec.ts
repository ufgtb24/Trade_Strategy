import { test, expect, type Locator, type Page } from '@playwright/test'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, annState, lanes, routeTo, settled, startBackend, stopBackend, type Backend } from './annotateHelpers'

/**
 * 归组与 pattern 页(annotate 侧栏的 pattern 页):
 * 1. pattern 页:用一份固定的例子标注(tests/path2_web/fixtures/annotation_grouping_v1,标注存储的批次文件)
 *    核对页头、features 区、属性的计数(决策票 15:一律数样本、pos k/N · neg m/M、0 也显示),点开后就地分排,
 *    各排之和等于分母;写 definition;点样本卡打开那张图并选中它,侧栏留在 pattern 页;
 *    annotate 的轨序按当前 pattern 里各段的先后。
 * 2. unsorted 页:按骨架分行、负样本那一行有灰字 pattern?;整行 move 进已有 pattern、+ new 新起一个,
 *    刷新后归属还在。
 *
 * 标注会写批次文件,绝不能写进用户的标注目录:后端与转发见 ./annotateHelpers.ts。例子批次的指纹换成测试后端
 * 本机副本的指纹,界面就不弹「副本对不上」的提示。
 */

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const FEATURES = ['横盘', '缩量 ⊂ 横盘', '突破', '派发', '回踩']

const ann = (page: Page, f: string) => page.evaluate(k => (window as any).__e2e.ann()[k], f)

async function putFixture(b: Backend) {
  const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
  for (const f of readdirSync(GROUPING)) {
    const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
    writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
  }
}

async function pickPattern(page: Page, text: string | null) {
  await page.getByTestId('top-pattern-button').click()
  if (text === null) await page.getByTestId('top-pattern-unsorted').click()
  else await page.locator(`[data-testid="top-pattern-option"][data-name="${text}"]`).click()
  await expect.poll(() => ann(page, 'currentPattern')).toBe(text)
}

const door = (page: Page, key: string) => page.locator(`[data-testid="count-door"][data-key="${key}"]`)
const parts = (page: Page, key: string) => page.locator(`[data-testid="count-parts"][data-key="${key}"] [data-testid="count-part"]`)

/** 点开一个计数后的各排:排头文字、这一排的卡数。 */
async function readParts(page: Page, key: string): Promise<{ head: string; cards: number }[]> {
  const ps = parts(page, key)
  await expect(ps.first()).toBeVisible()
  const out: { head: string; cards: number }[] = []
  for (const p of await ps.all()) {
    out.push({ head: (await p.getByTestId('part-head').innerText()).trim(), cards: await p.getByTestId('sample-card').count() })
  }
  return out
}

/** 排头里 pos a · neg b 的 a + b。 */
const headSum = (h: string) => [...h.matchAll(/(?:pos|neg) (\d+)/g)].reduce((s, m) => s + Number(m[1]), 0)

/** 副图特征轨的标题,按从上到下(只取特征名,去掉 bracket 与样本字母)。 */
async function laneTitles(page: Page): Promise<string[]> {
  const ls = await lanes(page)
  return ls.filter(l => FEATURES.includes(l.text)).sort((a, b) => a.y - b.y).map(l => l.text)
}

/** 图上某个系列眼下真正画出的项数(经图窗筛过之后)。 */
const drawn = (page: Page, which: 'main' | 'sub', name: string) => page.evaluate(([w, n]) => {
  const e2e = (window as any).__e2e
  const s = (w === 'main' ? e2e.chartMain() : e2e.chartSub()).getModel().getSeriesByName(n)[0]
  return s ? s.getData().count() : -1
}, [which, name] as const)

async function openCard(page: Page, symbol: string, date: string, card?: Locator) {
  const c = card ?? page.locator('[data-testid="sample-card"]', { hasText: `${symbol}` }).filter({ hasText: date }).first()
  await c.click()
  await expect(page.locator(`.symbol-title-bar [data-symbol="${symbol}"]`)).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    ((window as any).__e2e.chartMain().getOption()?.xAxis?.[0]?.data ?? []).length)).toBeGreaterThan(100)
}

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('归组与 pattern 页', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    backend = await startBackend()
    await putFixture(backend)
  })
  test.afterAll(() => stopBackend(backend))

  test('pattern 页的计数与点开分排、definition、打开样本、轨序;unsorted 页按骨架分行、整行 move、刷新后还在', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await expect.poll(() => page.evaluate(() => (window as any).__e2e?.ann().status)).toBe('ready')
    const st = await annState(page)
    const fid = (n: string) => st.features.find((f: any) => f.name === n).id
    const sid = (symbol: string, date: string) =>
      st.charts.find((c: any) => c.symbol === symbol).samples.find((s: any) => s.date === date).id
    await expect(page.getByTestId('notice-fingerprint')).toHaveCount(0)

    // ── pattern 页(W底):页头、features 区、属性的计数 ──
    await pickPattern(page, 'W底')
    await page.getByTestId('annotation-tab-pattern').click()
    const pg = page.getByTestId('pattern-page')
    await expect(pg.getByTestId('pattern-name')).toHaveText('W底')
    await expect(pg.getByTestId('pattern-definition')).toHaveValue('')
    await expect(door(page, 'samples|pos')).toHaveText('pos 3')
    await expect(door(page, 'samples|neg')).toHaveText('neg 1')
    await expect(pg.locator('[data-testid="feature-block"] > .ann-row [data-testid="feature-name"]'))
      .toHaveText(['横盘', '缩量', '突破', '派发'])
    await expect(pg.getByTestId('feature-arrow')).toHaveCount(2)                         // 顶层三块之间
    await expect(pg.locator('[data-testid="feature-block"][data-feature="横盘"] [data-testid="feature-block"][data-feature="缩量"] > .ann-row').first())
      .toContainText('横盘⊃缩量')                                                          // 写成「横盘 ⊃ 缩量」
    await expect(door(page, `in|${fid('横盘')}`)).toHaveText('in pos 3/3 · neg 1/1')
    await expect(door(page, `in|${fid('缩量')}`)).toHaveText('in pos 1/3 · neg 0/1')
    await expect(door(page, `in|${fid('突破')}`)).toHaveText('in pos 3/3 · neg 0/1')
    await expect(door(page, `in|${fid('派发')}`)).toHaveText('in pos 0/3 · neg 1/1')        // 只在负样本里出现的也列
    await expect(door(page, `attr|${fid('横盘')}|${fid('窄幅')}`)).toHaveText('true pos 1/3 · neg 0/1')
    await expect(door(page, `attr|${fid('突破')}|${fid('放量')}`)).toHaveText('true pos 2/3 · neg 0/0')   // 0/0 也显示
    await expect(door(page, `in|${fid('横盘')}`)).toHaveAttribute('title', /has a “横盘” box \/ all samples/)
    const rowCards = (j: string) => page.locator(`[data-testid="samples-row"][data-judgment="${j}"] [data-testid="sample-card"]`)
    await expect(rowCards('pos')).toHaveCount(3)
    await expect(rowCards('neg')).toHaveCount(1)

    // ── 点开分排:各排之和等于分母,空的排也写排头 ──
    const narrow = `attr|${fid('横盘')}|${fid('窄幅')}`
    await door(page, narrow).click()
    expect(await readParts(page, narrow)).toEqual([
      { head: 'true pos 1 · neg 0', cards: 1 }, { head: 'false pos 0 · neg 1', cards: 1 }, { head: 'null pos 2 · neg 0', cards: 2 }])
    await page.getByTestId('annotation-sidebar').screenshot({ path: testInfo.outputPath('01-pattern-page-attr-open.png') })
    const vol = `attr|${fid('突破')}|${fid('放量')}`
    await door(page, vol).click()                                                         // 换一个:前一个收起
    await expect(parts(page, narrow)).toHaveCount(0)
    const vp = await readParts(page, vol)
    expect(vp).toEqual([
      { head: 'true pos 2 · neg 0', cards: 2 }, { head: 'false pos 1 · neg 0', cards: 1 }, { head: 'null pos 0 · neg 0', cards: 0 }])
    expect(vp.reduce((s, p) => s + headSum(p.head), 0)).toBe(3)                          // 分母:有突破框的样本
    for (const key of [`in|${fid('派发')}`, 'samples|pos', 'samples|neg']) {
      await door(page, key).click()
      const ps = await readParts(page, key)
      expect(ps.reduce((s, p) => s + headSum(p.head), 0), key).toBe(key === 'samples|neg' ? 1 : key === 'samples|pos' ? 3 : 4)
      expect(ps.reduce((s, p) => s + p.cards, 0), key).toBe(ps.reduce((s, p) => s + headSum(p.head), 0))
    }
    await door(page, 'samples|neg').click()                                               // 再点一下收起
    await expect(page.getByTestId('count-parts')).toHaveCount(0)

    // ── definition 写进这个 pattern ──
    await pg.getByTestId('pattern-definition').fill('两个低点,第二个不破第一个')
    await pg.getByTestId('pattern-definition').press('Enter')
    await settled(page)
    expect((await annState(page)).patterns.find((p: any) => p.name === 'W底').definition).toBe('两个低点,第二个不破第一个')

    // ── 点样本卡:打开那张图、选中那个样本,侧栏留在 pattern 页;轨序按 W底 里各段的先后 ──
    await openCard(page, 'MSFT', '2024-02-08')
    await expect.poll(() => ann(page, 'selectedSampleId')).toBe(sid('MSFT', '2024-02-08'))
    await expect(page.getByTestId('pattern-page')).toBeVisible()
    await expect(page.locator(`[data-testid="sample-card"][data-sample="${sid('MSFT', '2024-02-08')}"]`).first()).toHaveClass(/cur/)
    await expect.poll(() => laneTitles(page)).toEqual(['横盘', '缩量 ⊂ 横盘', '突破', '派发', '回踩'])
    // 图上也选中了它:样本日之后暗一档
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.chartMain().getOption().series
      .find((x: any) => x.name === 'annotation-after-dim')?.data?.length ?? 0)).toBe(1)
    await page.screenshot({ path: testInfo.outputPath('02-pattern-page-open-sample.png'), fullPage: true })

    // ── unsorted 页:按骨架分行,负样本那一行有 pattern? ──
    await pickPattern(page, null)
    await expect.poll(() => laneTitles(page)).toEqual(['横盘', '缩量 ⊂ 横盘', '回踩', '突破', '派发'])   // 轨序跟着当前 pattern 变
    const up = page.getByTestId('unsorted-page')
    await expect(up.getByTestId('pattern-name')).toHaveText('unsorted')
    await expect(door(page, 'samples|pos')).toHaveText('pos 4')
    await expect(door(page, 'samples|neg')).toHaveText('neg 1')
    const rows = up.getByTestId('unsorted-row')
    const rowKeys = async () => (await rows.all()).length
      ? Promise.all((await rows.all()).map(async r => `${await r.getAttribute('data-judgment')}|${await r.getAttribute('data-skeleton')}|${await r.getByTestId('sample-card').count()}`))
      : []
    await expect.poll(rowKeys).toEqual(['pos|回踩|1', 'pos|横盘 → 突破|2', 'neg|横盘 → 突破|1', 'pos||1'])
    const negRow = rows.filter({ has: page.getByTestId('row-pending') })
    await expect(negRow).toHaveCount(1)
    await expect(negRow.getByTestId('row-pending')).toHaveText('pattern?')
    await expect(negRow.getByTestId('row-pending')).toHaveAttribute('title', 'pick the pattern it looks like')
    // 打开这一行的样本:当前 pattern 是 unsorted,W底 的样本、它的 bracket、只被它收进的框画淡
    await openCard(page, 'AAPL', '2024-09-09', negRow.getByTestId('sample-card'))
    // 图窗左边切过 W底 那个负样本的跨度(2024-05-01 – 06-17):它的 bracket 照样画(画淡),不因起点在图窗外整条消失;
    // 图窗右边没到最后一根:样本日之后暗一档照样画
    await expect.poll(() => drawn(page, 'sub', 'annotation-brackets')).toBe(2)
    await expect.poll(() => drawn(page, 'main', 'annotation-after-dim')).toBe(1)
    await page.screenshot({ path: testInfo.outputPath('03-unsorted-page.png'), fullPage: true })
    await page.getByTestId('annotation-sidebar').screenshot({ path: testInfo.outputPath('03b-unsorted-sidebar.png') })

    // ── 整行 move:pos 的「横盘 → 突破」进 W底;neg 那行 + new 新起一个 ──
    const moved = ['MSFT|2024-05-08', 'NVDA|2024-07-09'].map(k => sid(...(k.split('|') as [string, string])))
    const posRowEl = up.locator('[data-testid="unsorted-row"][data-judgment="pos"][data-skeleton="横盘 → 突破"]')
    await posRowEl.getByTestId('row-move-button').click()
    await expect(posRowEl.getByTestId('row-move-unsorted')).toHaveCount(0)              // move 里不列 unsorted
    await posRowEl.locator('[data-testid="row-move-option"][data-name="W底"]').click()
    await settled(page)
    await expect.poll(rowKeys).toEqual(['pos|回踩|1', 'neg|横盘 → 突破|1', 'pos||1'])
    const negRowEl = up.locator('[data-testid="unsorted-row"][data-judgment="neg"]')
    await negRowEl.getByTestId('row-move-button').click()
    await negRowEl.getByTestId('row-move-new').click()
    await negRowEl.getByTestId('row-move-new-input').fill('头肩底')
    await negRowEl.getByTestId('row-move-new-input').press('Enter')
    await settled(page)
    await expect.poll(rowKeys).toEqual(['pos|回踩|1', 'pos||1'])
    await expect(up.getByTestId('row-pending')).toHaveCount(0)
    await expect(door(page, 'samples|neg')).toHaveText('neg 0')                           // 0 也显示

    // ── 刷新:归属还在 ──
    await page.reload()
    await expect.poll(() => page.evaluate(() => (window as any).__e2e?.ann().status)).toBe('ready')
    const after = await annState(page)
    const patternOf = (id: string) => after.charts.flatMap((c: any) => c.samples).find((s: any) => s.id === id).pattern
    expect(moved.map(patternOf)).toEqual(['W底', 'W底'])
    expect(patternOf(sid('AAPL', '2024-09-09'))).toBe('头肩底')
    expect(after.patterns.map((p: any) => p.name)).toEqual(['W底', '旗形', '头肩底'])
    await page.getByTestId('annotation-tab-pattern').click()
    await expect.poll(rowKeys).toEqual(['pos|回踩|1', 'pos||1'])
    await pickPattern(page, 'W底')
    await expect(door(page, 'samples|pos')).toHaveText('pos 5')
    await expect(door(page, 'samples|neg')).toHaveText('neg 1')
    await expect(page.getByTestId('pattern-definition')).toHaveValue('两个低点,第二个不破第一个')

    // ── 一个样本都没有的 pattern:计数全是 0,也照写 ──
    await pickPattern(page, '旗形')
    await expect(door(page, 'samples|pos')).toHaveText('pos 0')
    await expect(door(page, 'samples|neg')).toHaveText('neg 0')
    await expect(page.getByTestId('samples-row')).toHaveText(['pos', 'neg'])                 // 没有样本的行也在
    await expect(page.locator('[data-testid="samples-row"] [data-testid="sample-card"]')).toHaveCount(0)
    await expect(page.getByTestId('pattern-definition')).toHaveValue('上升途中的小平台')
    await page.getByTestId('annotation-sidebar').screenshot({ path: testInfo.outputPath('04-empty-pattern.png') })
  })
})
