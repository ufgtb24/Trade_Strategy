import { test, expect } from '@playwright/test'
import { deleteSmallScan, openSmallScan, runSmallScan, smallScanName } from './smallScan'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/path2/run_path2_web.py)。
// 策略:用 window.__e2e.view.focusMark([实例]) 模拟「点 band 上的一个 event」,
//       绕开在真实 K 线上精确点中记号的坐标依赖,专注验证显示栏(kind 那格、← / → 键槽)/ → 进去 / Esc 往外退 / 切股清空。
//       被几次买在不同日子的 hit 共用的 event:选中它时 ← / → 键槽写 into buys ×n;找不到这样的 event 时退到选中一次 hit。

// 夹具:new_step 小扫描(./smallScan.ts),整个文件共用一次,结束删掉。
const SCAN_NAME = smallScanName('hit_event_disambig')
test.beforeAll(async () => { await runSmallScan(SCAN_NAME) })
test.afterAll(async () => { await deleteSmallScan(SCAN_NAME) })

/** 打开小扫描,选中第一只 ticker,返回它的 symbol。 */
async function ensureScanLoaded(page: any): Promise<string> {
  await openSmallScan(page, SCAN_NAME)
  await expect(page.locator('td.sym').first()).toBeVisible({ timeout: 30_000 })
  const firstSymCell = page.locator('td.sym').first()
  const symbol = (await firstSymCell.textContent())?.trim() ?? ''
  await firstSymCell.click()
  return symbol
}

/** 等 KlineChart onMounted 后 window.__e2e.view 可用,且 hit 已到 */
async function waitForHits(page: any): Promise<void> {
  await page.waitForFunction(() => !!(window as any).__e2e?.view, { timeout: 10_000 })
  await page.waitForFunction(
    () => ((window as any).__e2e?.view?.effectiveAnalysis?.hits?.length ?? 0) > 0,
    { timeout: 15_000 },
  )
}

/**
 * 清掉选中(竖线也清掉)后选一个东西:优先找被两次以上 hit 用到、牵出两个以上买点日的 event(点它);
 * 找不到就选第一次 hit。返回选中的是哪一种(显示栏 kind 那格写的词)。
 */
async function selectSomething(page: any): Promise<string> {
  return page.evaluate(() => {
    const view = (window as any).__e2e.view
    const events: Array<{ instance_id: string }> = view.effectiveAnalysis?.events ?? []
    for (const e of events) {
      view.clearFocus()
      view.focusMark([e.instance_id])
      const s = view.selInfo
      if (s?.kind === 'event' && s.day.mode === 'into' && s.day.noun === 'buys' && s.day.n >= 2
          && view.candidateHitIds.size >= 2) return 'event'
    }
    view.clearFocus()
    view.focusHit(view.effectiveAnalysis.hits[0].hit_id)
    return view.selInfo?.kind ?? 'none'
  })
}

/** 显示栏一格里的值(标签 / 键帽后面那一段) */
const cellVal = (page: any, id: string) => page.getByTestId(id).locator(':scope > :last-child')

test('选中一个东西 → 显示栏写它是什么;选中的是共用的 event 时 ← / → 键槽写 into buys ×n,→ 进到其中一天', async ({ page }) => {
  test.setTimeout(300_000)
  await ensureScanLoaded(page)
  await waitForHits(page)

  // 显示栏常驻(app 下),没有选中时九格都在、kind 那格写 —
  await expect(page.getByTestId('walk-bar')).toBeVisible()
  await expect(cellVal(page, 'sel-kind')).toHaveText('—')

  const kind = await selectSomething(page)
  expect(['event', 'hit']).toContain(kind)
  await expect(cellVal(page, 'sel-kind')).toHaveText(kind)
  await expect(page.getByTestId('sel-esc')).toBeVisible()

  if (kind === 'event') {
    // 选中的是这个 event:用到它的哪一次 hit 都不算选中,只画细框;← / → 会进到它牵出的买点日
    await expect(cellVal(page, 'sel-day')).toHaveText(/^into buys ×\d+$/)
    expect(await page.evaluate(() => (window as any).__e2e.view.focusedHitId)).toBeNull()
    expect(await page.evaluate(() => (window as any).__e2e.view.candidateHitIds.size)).toBeGreaterThanOrEqual(2)
    const line0: number = await page.evaluate(() => (window as any).__e2e.view.currentDay)
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('ArrowRight')
    await expect(cellVal(page, 'sel-day')).toHaveText(/^buys \d+\/\d+$/)
    // 进到一个买点日:竖线那天本身是买点日就落它,否则落右边最近的(右边没有取左边最近的);仍在这个 event 里面
    const st = await page.evaluate(() => {
      const v = (window as any).__e2e.view
      const path = v.selPath
      return { kinds: path.map((x: any) => x.kind), buy: path[2]?.day, day: v.currentDay, hit: v.focusedHitId,
               days: v.world.inside(path.slice(0, 2), 'day').map((x: any) => x.day),
               framed: v.focusedHitId ? v.candidateHitIds.has(v.focusedHitId) : null }
    })
    expect(st.kinds.slice(0, 3)).toEqual(['node', 'event', 'buy'])
    const want = st.days.includes(line0) ? line0
      : (st.days.find((d: number) => d > line0) ?? [...st.days].reverse().find((d: number) => d < line0))
    expect(st.day).toBe(want)
    expect(st.buy).toBe(st.day)
    if (st.hit !== null) expect(st.framed).toBe(true)     // 那天只有一次时就是那次 hit,它是用到这个 event 的
  }
})

test('Esc 往外退一层,退到头再按才清空:显示栏九格写回 —,条本身留着', async ({ page }) => {
  test.setTimeout(300_000)
  await ensureScanLoaded(page)
  await waitForHits(page)

  await selectSomething(page)
  await expect(cellVal(page, 'sel-kind')).not.toHaveText('—')
  const depth = () => page.evaluate(() => (window as any).__e2e.view.selPath.length as number)
  const d0 = await depth()
  expect(d0).toBeGreaterThanOrEqual(2)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  // 第一下只退一层:还有选中
  await page.keyboard.press('Escape')
  const d1 = await depth()
  expect(d1).toBeGreaterThan(0)
  expect(d1).toBeLessThan(d0)
  await expect(cellVal(page, 'sel-kind')).not.toHaveText('—')
  // 一层层退到最外一层,再按一下才清空
  for (let i = d1; i > 1; i--) {
    await page.keyboard.press('Escape')
    expect(await depth()).toBeLessThan(i)
  }
  expect(await depth()).toBe(1)
  await page.keyboard.press('Escape')
  expect(await depth()).toBe(0)
  await expect(cellVal(page, 'sel-kind')).toHaveText('—')
  await expect(page.getByTestId('walk-bar')).toBeVisible()
})

test('切股清空选中', async ({ page }) => {
  test.setTimeout(300_000)
  const firstSym = await ensureScanLoaded(page)
  await waitForHits(page)

  await selectSomething(page)
  await expect(cellVal(page, 'sel-kind')).not.toHaveText('—')

  const allSymCells = page.locator('td.sym')
  if ((await allSymCells.count()) < 2) {
    console.warn(`Only 1 ticker (${firstSym}) in scan; skipping switch-ticker sub-assertion`)
    return
  }
  const otherCell = allSymCells.filter({ hasNot: page.locator(`:text-is("${firstSym}")`) }).first()
  await otherCell.click()
  await expect(cellVal(page, 'sel-kind')).toHaveText('—')
  expect(await page.evaluate(() => (window as any).__e2e.view.selPath.length)).toBe(0)
})
