import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//        后端须外部启动 uv run python scripts/run_path2_web.py)。
// 策略:用 window.__e2e.view.setCandidateMatches(realIds) 模拟进入 candidate 态,
//       绕开"在真实 K 线上精确 click multi-match marker"的坐标依赖,专注验证
//       banner 可见性 / Esc 清空 / 切股清空。

// ─── 辅助:确保至少有一次扫描历史并加载,选中第一只 ticker ───────────────────

/**
 * 确保至少有一次扫描并加载到 UI,选中第一只 ticker。
 * 若无历史则触发全量扫描(最长 3 分钟)再加载。
 * 返回已选中的 ticker symbol。
 */
async function ensureScanLoaded(page: any): Promise<string> {
  await page.goto(baseURL + '/')

  // 等 app 初始化完成:「打开历史…」按钮出现
  const openHistBtn = page.getByRole('button', { name: /打开历史/ })
  await expect(openHistBtn).toBeVisible({ timeout: 15_000 })

  // 检查是否已有历史记录
  await openHistBtn.click()
  await expect(page.locator('.backdrop')).toBeVisible({ timeout: 5_000 })
  // 等 loading 完成
  await expect(page.locator('.state')).not.toContainText('Loading', { timeout: 5_000 }).catch(() => {})

  const hasRows = (await page.locator('.file-list tbody tr').count()) > 0
  if (!hasRows) {
    // 无历史 → 关历史 dialog → 开扫描配置 dialog(顶部工具条「扫描 ⚙」) → 全选 pattern → 扫描 → 重开
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible()

    await page.getByRole('button', { name: /扫描 ⚙/ }).click()
    // 等 patterns 加载完成(pattern-list 渲染出行)后全选
    await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
    await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()

    // 等「开始扫描」启用后触发
    const scanBtn = page.getByRole('button', { name: /开始扫描/ })
    await expect(scanBtn).toBeEnabled({ timeout: 10_000 })
    await scanBtn.click()

    // 等扫描完成(最长 4 分钟)
    await expect(page.locator('.done')).toBeVisible({ timeout: 240_000 })

    // 重新打开历史 dialog
    await openHistBtn.click()
    await expect(page.locator('.backdrop')).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('.file-list')).toBeVisible({ timeout: 5_000 })
  }

  // 选第一行 → Open
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).not.toBeVisible()

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

/** 等 effectiveAnalysis.matches 至少有 1 条(后端数据到达) */
async function waitForMatches(page: any): Promise<void> {
  await page.waitForFunction(
    () => ((window as any).__e2e?.view?.effectiveAnalysis?.matches?.length ?? 0) > 0,
    { timeout: 15_000 },
  )
}

/**
 * 用第一只 ticker 的真实 match event_id(最多 n 条)调用 setCandidateMatches。
 * 返回实际设置的 id 数量(≥1 时 banner 才能出现)。
 * 注意:banner 的 v-if 条件是 ordinalChars.length>0,ordinalChars 依赖
 * candidateMatchIds 中 id 同时存在于 props.matches,因此必须用真实 event_id。
 */
async function setRealCandidateMatches(page: any, n = 2): Promise<number> {
  return page.evaluate((count: number) => {
    const view = (window as any).__e2e?.view
    const matches: Array<{ event_id: string }> = view?.effectiveAnalysis?.matches ?? []
    const ids = matches.slice(0, count).map((m) => m.event_id)
    if (ids.length > 0) view?.setCandidateMatches(ids)
    return ids.length
  }, n)
}

// ─────────────────────────────────────────────────────────────────────────────
// Test 1: 进入 candidate 态 → banner 出现
// ─────────────────────────────────────────────────────────────────────────────
test('multi-match: setCandidateMatches → candidate banner appears', async ({ page }) => {
  test.setTimeout(300_000) // 含可能的扫描等待
  await ensureScanLoaded(page)
  await waitForE2E(page)
  await waitForMatches(page)

  // banner 初始隐藏
  await expect(page.locator('.candidate-banner')).toBeHidden()

  // 模拟进入 candidate 态(使用真实 match event_id)
  const idsSet = await setRealCandidateMatches(page, 2)
  expect(idsSet).toBeGreaterThanOrEqual(1)

  // banner 应变可见并包含"候选"
  await expect(page.locator('.candidate-banner')).toBeVisible()
  await expect(page.locator('.candidate-banner')).toContainText('候选')
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 2: Esc 清空 candidate 态 → banner 消失
// ─────────────────────────────────────────────────────────────────────────────
test('Esc clears candidate: banner disappears', async ({ page }) => {
  test.setTimeout(300_000)
  await ensureScanLoaded(page)
  await waitForE2E(page)
  await waitForMatches(page)

  const idsSet = await setRealCandidateMatches(page, 2)
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
  await waitForMatches(page)

  const idsSet = await setRealCandidateMatches(page, 2)
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

  // view.selectSymbol 同步清空 candidateMatchIds → banner 应消失
  await expect(page.locator('.candidate-banner')).toBeHidden()
})
