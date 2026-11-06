import { test, expect } from '@playwright/test'
import { deleteSmallScan, openSmallScan, runSmallScan, smallScanName } from './smallScan'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/path2/run_path2_web.py)。
// 策略:用 window.__e2e.view.setCandidateHits(realIds) 模拟进入 candidate 态,
//       绕开"在真实 K 线上精确 click multi-hit marker"的坐标依赖,专注验证
//       banner 可见性 / Esc 清空 / 切股清空。

// ─── 辅助:确保至少有一次扫描历史并加载,选中第一只 ticker ───────────────────

// 夹具:new_step 小扫描(./smallScan.ts),整个文件共用一次,结束删掉。
// (原先打开历史里第一个扫描、没有就全量扫描;现存扫描或是 bo_only 大文件、或越过数据墙打不开,改用小扫描。)
const SCAN_NAME = smallScanName('hit_event_disambig')
test.beforeAll(async () => { await runSmallScan(SCAN_NAME) })
test.afterAll(async () => { await deleteSmallScan(SCAN_NAME) })

/** 打开小扫描,选中第一只 ticker,返回它的 symbol。 */
async function ensureScanLoaded(page: any): Promise<string> {
  await openSmallScan(page, SCAN_NAME)

  // 等 ticker 列表出现:SidebarResultList 渲染 td.sym
  await expect(page.locator('td.sym').first()).toBeVisible({ timeout: 30_000 })
  const firstSymCell = page.locator('td.sym').first()
  const symbol = (await firstSymCell.textContent())?.trim() ?? ''
  await firstSymCell.click()
  return symbol
}

/** 等 KlineChart onMounted 后 window.__e2e.view 可用 */
async function waitForE2E(page: any): Promise<void> {
  await page.waitForFunction(() => !!(window as any).__e2e?.view, { timeout: 10_000 })
}

/** 等 effectiveAnalysis.hits 至少有 1 条(后端数据到达) */
async function waitForHits(page: any): Promise<void> {
  await page.waitForFunction(
    () => ((window as any).__e2e?.view?.effectiveAnalysis?.hits?.length ?? 0) > 0,
    { timeout: 15_000 },
  )
}

/**
 * 用第一只 ticker 的真实 hit_id(最多 n 条)调用 setCandidateHits。
 * 返回实际设置的 id 数量(≥1 时 banner 才能出现)。
 */
async function setRealCandidateHits(page: any, n = 2): Promise<number> {
  return page.evaluate((count: number) => {
    const view = (window as any).__e2e?.view
    const hits: Array<{ hit_id: string }> = view?.effectiveAnalysis?.hits ?? []
    const ids = hits.slice(0, count).map((m) => m.hit_id)
    if (ids.length > 0) view?.setCandidateHits(ids)
    return ids.length
  }, n)
}

// ─────────────────────────────────────────────────────────────────────────────
// Test 1: 进入 candidate 态 → banner 出现
// ─────────────────────────────────────────────────────────────────────────────
test('multi-hit: setCandidateHits → candidate banner appears', async ({ page }) => {
  test.setTimeout(300_000) // 含可能的扫描等待
  await ensureScanLoaded(page)
  await waitForE2E(page)
  await waitForHits(page)

  // banner 初始隐藏
  await expect(page.locator('.candidate-banner')).toBeHidden()

  // 模拟进入 candidate 态(使用真实 hit_id)
  const idsSet = await setRealCandidateHits(page, 2)
  expect(idsSet).toBeGreaterThanOrEqual(1)

  // banner 应变可见:`candidates n` `←/→` `Esc`
  await expect(page.locator('.candidate-banner')).toBeVisible()
  await expect(page.locator('.candidate-banner')).toContainText('candidates')
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 2: Esc 清空 candidate 态 → banner 消失
// ─────────────────────────────────────────────────────────────────────────────
test('Esc clears candidate: banner disappears', async ({ page }) => {
  test.setTimeout(300_000)
  await ensureScanLoaded(page)
  await waitForE2E(page)
  await waitForHits(page)

  const idsSet = await setRealCandidateHits(page, 2)
  expect(idsSet).toBeGreaterThanOrEqual(1)
  await expect(page.locator('.candidate-banner')).toBeVisible()

  // Esc → KlineChart.onKeyDown 调用 clearCandidates
  await page.keyboard.press('Escape')
  await expect(page.locator('.candidate-banner')).toBeHidden()
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 3: 切股 → candidate 态被清空 → banner 消失
// ─────────────────────────────────────────────────────────────────────────────
test('switch ticker clears candidate: banner disappears', async ({ page }) => {
  test.setTimeout(300_000)
  const firstSym = await ensureScanLoaded(page)
  await waitForE2E(page)
  await waitForHits(page)

  const idsSet = await setRealCandidateHits(page, 2)
  expect(idsSet).toBeGreaterThanOrEqual(1)
  await expect(page.locator('.candidate-banner')).toBeVisible()

  // 选另一只 ticker(过滤掉当前 firstSym)
  const allSymCells = page.locator('td.sym')
  const count = await allSymCells.count()
  if (count < 2) {
    console.warn(`Only 1 ticker (${firstSym}) in scan; skipping switch-ticker sub-assertion`)
    return
  }
  // 点与 firstSym 不同的首个 td.sym
  const otherCell = allSymCells.filter({ hasNot: page.locator(`:text-is("${firstSym}")`) }).first()
  await otherCell.click()

  // view.selectSymbol 同步清空 candidateHitIds → banner 应消失
  await expect(page.locator('.candidate-banner')).toBeHidden()
})
