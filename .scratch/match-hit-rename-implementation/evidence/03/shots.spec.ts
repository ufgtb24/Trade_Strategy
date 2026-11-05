import { test, expect, type Page } from '@playwright/test'
import { appendFileSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO, routeTo, startBackend, stopBackend, type Backend } from './annotateHelpers'

/**
 * 票 03 的截图自查（只留作证据，不进 path2_web_ui/e2e）。跑法：临时复制到 path2_web_ui/e2e/，
 *   configs/path2_web.yaml 端口临时改成 8095 / 5195，e2e_backend.py 在 8095、vite 在 5195，
 *   npx playwright test --workers=1 e2e/t03-shots.spec.ts
 * 只读训练段副本：网页扫描与 annotationBackend 都读 datasets/pkls_until_20251231。
 * 第一段用网页扫描对话框扫一份小 scan；第二段起 annotationBackend 走 compare，因为 compare 要手写的 mapping。
 */
const OUT = join(REPO, '.scratch/match-hit-rename-implementation/evidence/03')
const LOG = join(OUT, 'shots.txt')
const note = (s: string) => appendFileSync(LOG, s + '\n')
const view = (page: Page, k: string) => page.evaluate(key => (window as any).__e2e.view[key], k)
const png = (name: string) => join(OUT, name)
const activeLevel = (page: Page) => page.locator('[data-testid="level-control"] .level-btn.active:not(.panel-toggle)')

/** 副图 graphic 里的固定文字。 */
const subTexts = (page: Page) => page.evaluate(() => {
  const opt = (window as any).__e2e.chartSub().getOption()
  return (opt.graphic?.[0]?.elements ?? []).filter((e: any) => e.type === 'text').map((e: any) => e.style?.text)
})

/** 打开扫描对话框，填窗口、股票范围、只勾 bb_v1（默认全选里 try_complex_where 每只都报错，见票 02 完成记录）。 */
async function fillScanDialog(page: Page, regex: string, name: string) {
  await page.getByRole('button', { name: /扫描 ⚙/ }).click()
  await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
  await page.fill('[data-field="start_date"]', '2022-01-01')
  await page.fill('[data-field="end_date"]', '2025-12-01')
  await page.fill('[data-field="workers"]', '2')
  await page.fill('[data-field="note"]', name)
  await page.fill('[data-field="ticker_regex"]', regex)
  await page.locator('.backdrop').getByRole('button', { name: '清空' }).click()
  await page.locator('.pattern-list li[data-pid="bb_v1"] input[type="checkbox"]').click()
}

test.use({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1 })

test('主视图：扫描、档位、bracket 轨标题、hit 列表与聚焦、tier tag、旧档位值', async ({ page }) => {
  writeFileSync(LOG, '# 票 03 截图自查的文字记录（shots.spec.ts 写入）\n')
  await page.goto('/')

  // 先扫一批大的，中途停，看扫描进度和停止对话框（有 hit 的股票数 > 0 才弹对话框）；这批丢弃
  await fillScanDialog(page, '^[A-C]', 't03-to-discard')
  await page.getByRole('button', { name: /开始扫描/ }).click()
  await expect(page.locator('.prog')).toContainText(/hit_stocks\s+[1-9]/, { timeout: 200_000 })
  await page.locator('.prog').screenshot({ path: png('07-scan-progress.png') })
  note('扫描中 .prog：' + (await page.locator('.prog').innerText()).replace(/\s+/g, ' '))
  await page.locator('.prog').getByRole('button', { name: /停止扫描/ }).click()
  await expect(page.getByTestId('btn-discard')).toBeVisible()
  await page.locator('.card').screenshot({ path: png('08-stop-dialog.png') })
  note('停止对话框：' + (await page.locator('.prompt').innerText()) + '；title=' + await page.locator('.prompt').getAttribute('title'))
  await page.getByTestId('btn-discard').click()
  await expect(page.locator('.done')).toBeVisible({ timeout: 60_000 })

  // 再扫这份小 scan，看完成数，后面的截图都用它
  await fillScanDialog(page, '^(AMC|PLTR|PLUG|SNAP|SOFI|GME|NVDA|AAPL|MSFT|TSLA)$', 't03-hit-names')
  await page.getByRole('button', { name: /开始扫描/ }).click()
  await expect(page.locator('.done')).toContainText('hit_stocks', { timeout: 300_000 })
  await page.locator('.done').screenshot({ path: png('09-scan-done.png') })
  note('扫描完成 .done：' + (await page.locator('.done').innerText()).replace(/\s+/g, ' '))

  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.file-list')).toBeVisible()
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await page.locator('[data-symbol="PLTR"]').first().click()
  await expect.poll(() => view(page, 'symbol')).toBe('PLTR')
  // 新浏览器里诊断侧栏默认收着
  const sb = page.getByTestId('panel-toggle-sidebar')
  if (!(await sb.getAttribute('class'))?.includes('active')) await sb.click()
  await expect(page.locator('.hit-row').first()).toBeVisible({ timeout: 30_000 })
  note('当前 scan：' + await view(page, 'activePatternId') + ' / PLTR，hit 数 '
    + await page.locator('.hit-row').count())

  // 档位按钮：标签、悬停、字体
  const bar = page.locator('[data-testid="level-control"]')
  const labels = await bar.locator('.level-btn:not(.panel-toggle)').allInnerTexts()
  expect(labels).toEqual(['in_hit', 'qualified', 'detected'])
  for (const b of await bar.locator('.level-btn:not(.panel-toggle)').all()) {
    note(`档位按钮 ${await b.innerText()}：title=${await b.getAttribute('title')}；font=${await b.evaluate(e => getComputedStyle(e).fontFamily)}`)
  }
  await expect(activeLevel(page)).toHaveText('in_hit')
  await bar.screenshot({ path: png('01-level-bar.png') })

  // in_hit 档的主视图
  await page.screenshot({ path: png('02-main-view-in_hit.png'), fullPage: true })

  // bracket 轨标题
  const texts = await subTexts(page)
  note('副图轨标题（in_hit 档）：' + JSON.stringify(texts))
  expect(texts).toContain('hits')
  await page.locator('.sub-outer').screenshot({ path: png('03-bracket-lane-title.png') })

  // 诊断侧栏：hit 列表与聚焦
  await page.locator('.hit-row').nth(1).click()
  await expect(page.locator('.hit-row--selected')).toHaveCount(1)
  await expect(page.locator('.hit-trace')).toBeVisible()
  const ids = await page.evaluate(() => (window as any).__e2e.view.effectiveAnalysis.hits.map((h: any) => h.hit_id))
  expect(await view(page, 'focusedHitId')).toBe(ids[1])
  expect(await view(page, 'selected')).toEqual({ kind: 'hit', hitId: ids[1] })
  note('点 hit 列表第 2 行：focusedHitId=' + ids[1] + '；标题 '
    + JSON.stringify(await page.locator('.sidebar .section-title--sym').allInnerTexts()))
  await page.locator('.sidebar').screenshot({ path: png('04-sidebar-hit-list-focus.png') })
  await page.screenshot({ path: png('04b-main-view-focused.png'), fullPage: true })

  // tier tag：detected 档才看得到没进 hit 的 event
  await page.evaluate(() => (window as any).__e2e.view.clearFocus())
  await bar.getByRole('button', { name: 'detected' }).click()
  await expect(activeLevel(page)).toHaveText('detected')
  await page.waitForTimeout(500)
  const tags = await page.evaluate(() => {
    const opt = (window as any).__e2e.chartSub().getOption()
    return opt.series.filter((s: any) => /tier/i.test(s.name ?? '')).map((s: any) => [s.name, (s.data ?? []).map((d: any) => d.text)])
  })
  note('detected 档的 tier tag 系列：' + JSON.stringify(tags).slice(0, 400))
  expect(JSON.stringify(tags)).toMatch(/detected_only|qualified_only/)
  await page.locator('.sub-outer').screenshot({ path: png('05-app-tier-tags.png') })
  await page.screenshot({ path: png('05b-main-view-detected.png'), fullPage: true })

  // 浏览器里存过的旧档位值读不懂 → 默认档
  await page.evaluate(() => localStorage.setItem('path2_web_ui.level', 'matched'))
  await page.reload()
  // 刷新后没载入 scan、落在 annotate，档位按钮不显示，直接读 store
  await expect.poll(() => view(page, 'level')).toBe('in_hit')
  note('localStorage 存旧值 matched 后刷新：level=' + await view(page, 'level'))
})

const GROUPING = join(REPO, 'tests/path2_web/fixtures/annotation_grouping_v1/batches')
const MAPPING = 'pattern: W底\nfeatures:\n  w-pc-3: bo\n  w-pc-1: pk\n'

test('compare：悬停里的 in_hit', async ({ page }) => {
  test.setTimeout(600_000)
  let b: Backend | null = null
  try {
    b = await startBackend(undefined, { bo_only: MAPPING })
    const local = (await (await fetch(`${b.base}/annotations`)).json()).fingerprint.local
    for (const f of readdirSync(GROUPING)) {
      const doc = JSON.parse(readFileSync(join(GROUPING, f), 'utf8'))
      writeFileSync(join(b.root, 'annotations', f), JSON.stringify({ ...doc, data_fingerprint: local }))
    }
    await routeTo(page, b)
    await page.goto('/#sample=s-pc-11')
    await expect(page.locator('.symbol-title-bar [data-symbol="AAPL"]')).toBeVisible()
    await page.getByTestId('top-pattern-button').click()
    await page.locator('[data-testid="top-pattern-option"][data-name="W底"]').click()
    await page.getByTestId('mode-compare').click()
    await expect.poll(() => page.evaluate(() => (window as any).__e2e.view.linkedRun?.symbol ?? null), { timeout: 60_000 }).toBe('AAPL')

    // 找一个 in_hit 的 event，图窗拉到它附近
    const target = await page.evaluate(() => {
      const opt = (window as any).__e2e.chartSub().getOption()
      const s = opt.series.find((x: any) => x.name === 'compare-events')
      const i = s.data.findIndex((_: any, k: number) => /in_hit/.test(s.tooltip.formatter({ dataIndex: k })))
      return { i, row: s.data[i], tip: s.tooltip.formatter({ dataIndex: i }), n: opt.xAxis[0].data.length, tiers: Array.from(new Set(s.data.map((_: any, k: number) => /^<span[^>]*>(\w+)<br>/.exec(s.tooltip.formatter({ dataIndex: k }))?.[1]))) }
    })
    note('compare-events 的档位取值：' + JSON.stringify(target.tiers))
    expect(target.i).toBeGreaterThanOrEqual(0)
    await page.evaluate(([i, n]) => (window as any).__e2e.chartMain().dispatchAction(
      { type: 'dataZoom', start: Math.max(0, i - 60) / n * 100, end: Math.min(n, i + 60) / n * 100 }), [target.row[0], target.n])
    await page.waitForTimeout(800)
    const pos = await page.evaluate(([st, en, top]) => {
      const sub = (window as any).__e2e.chartSub()
      const rect = sub.getDom().getBoundingClientRect()
      return { x: rect.left + sub.convertToPixel({ xAxisIndex: 0 }, (st + en) / 2), y: rect.top + top + 2 }
    }, [target.row[0], target.row[1], target.row[2]])
    await page.mouse.move(pos.x - 40, pos.y - 40)
    await page.mouse.move(pos.x, pos.y, { steps: 5 })
    const tip = page.locator('body > div').filter({ hasText: /^in_hit/ }).first()
    await expect(tip).toBeVisible({ timeout: 5_000 })
    note('compare 悬停文字：' + (await tip.innerText()).replace(/\s+/g, ' '))
    await page.screenshot({ path: png('06-compare-tooltip-in_hit.png'), fullPage: true })
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  } finally {
    stopBackend(b)
  }
})
