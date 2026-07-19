import { test, expect } from '@playwright/test'

// 前提:B 在 localhost:8000 在线;已有一次命中扫描(或本测试触发扫描)。

// 扫描参数已搬进 ScanConfigDialog(点顶部工具条「扫描 ⚙」打开);
// dialog 打开时 pattern 选择默认清空,需先全选才能启用「开始扫描」。
async function openScanDialogAndSelectAll(page: any) {
  await page.getByRole('button', { name: /扫描 ⚙/ }).click()
  await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
  await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()
}

/**
 * 辅助:等待扫描并返回首只命中股的 symbol。
 * 若已有历史记录则直接复用首条,否则触发新扫描。
 */
async function ensureScanLoaded(page: any) {
  await page.goto('/')
  // pattern 已自动加载
  await expect(page.locator('select')).toContainText('底部反转突破爆发')

  // 检查是否已有历史记录(若有则直接复用)
  await page.getByRole('button', { name: /打开历史/ }).click()
  // wait for dialog to open
  await expect(page.locator('.file-list, .state')).toBeVisible({ timeout: 5_000 })
  let rowCount = await page.locator('.file-list tbody tr').count()
  if (rowCount === 0) {
    // 关 dialog(点 Cancel),开扫描配置 dialog 全选 pattern 后触发扫描,再开
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible()
    await openScanDialogAndSelectAll(page)
    await page.getByRole('button', { name: /开始扫描/ }).click()
    await expect(page.locator('.done')).toBeVisible({ timeout: 180_000 })
    await page.getByRole('button', { name: /打开历史/ }).click()
    await expect(page.locator('.file-list')).toBeVisible({ timeout: 5_000 })
  }
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()

  // 等命中列表出现
  await expect(page.locator('[data-symbol]').first()).toBeVisible({ timeout: 30_000 })
  // 选第一只股票
  const firstSym = page.locator('[data-symbol]').first()
  const symbol = await firstSym.getAttribute('data-symbol')
  await firstSym.click()
  return symbol
}

// ─────────────────────────────────────────────────────────────────────────────
// Test 1: 基础流程 + 5-node 拓扑校验
// ─────────────────────────────────────────────────────────────────────────────
test('scan → load → 5-node topology → sidebar funnel visible', async ({ page }) => {
  await ensureScanLoaded(page)

  // 拓扑控制器 5 节点(down / side / bo / burst / tb)
  await expect(page.locator('[data-node-id]')).toHaveCount(5)

  // 每个节点都存在
  for (const nodeId of ['down', 'side', 'bo', 'burst', 'tb']) {
    await expect(page.locator(`[data-node-id="${nodeId}"]`)).toBeVisible()
  }

  // level-control 出现
  await expect(page.locator('[data-testid="level-control"]')).toBeVisible()

  // sidebar 漏斗总览:pattern nodes(有边)渲染 ▸ 行;bo 渲染"原始检测"密度行
  // 等 diag 加载完成(sidebar 出现漏斗行)
  await expect(page.locator('.funnel-row').first()).toBeVisible({ timeout: 15_000 })

  // 共 5 行(对应 5 nodes)
  await expect(page.locator('.funnel-row')).toHaveCount(5)

  // pattern nodes(down/side/burst/tb,有边): 含 ▸
  for (const nodeId of ['down', 'side', 'burst', 'tb']) {
    // funnel-row 按 v-for nodes 顺序渲染,找含 ▸ 的行(funnel-arrow span)
  }
  // 至少存在一个 funnel-arrow 元素(有边 node 的漏斗行)
  await expect(page.locator('.funnel-arrow').first()).toBeVisible()

  // bo 是 isolated node → 含 .badge("原始检测 N")
  const badgeEl = page.locator('.badge').filter({ hasText: '原始检测' })
  await expect(badgeEl).toBeVisible()

  // 关 bo node → 截图核对
  await page.locator('[data-node-id="bo"]').click()
  await page.screenshot({ path: 'e2e-bo-off.png' })

  // 再开 bo node
  await page.locator('[data-node-id="bo"]').click()
  await page.screenshot({ path: 'e2e-bo-on.png' })
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 2: level 切档(Matched / Qualified / Detected)
// ─────────────────────────────────────────────────────────────────────────────
test('level control: Detected → Qualified → Matched active class + screenshot', async ({ page }) => {
  await ensureScanLoaded(page)

  const levelBar = page.locator('[data-testid="level-control"]')
  await expect(levelBar).toBeVisible()

  // 获取三个按钮
  const matchedBtn  = levelBar.getByRole('button', { name: 'Matched' })
  const tracedBtn   = levelBar.getByRole('button', { name: 'Qualified' })
  const detectedBtn = levelBar.getByRole('button', { name: 'Detected' })

  // 初始状态:Matched 应为 active(store 默认 level = 'matched')
  await expect(matchedBtn).toHaveClass(/active/)
  await expect(tracedBtn).not.toHaveClass(/active/)
  await expect(detectedBtn).not.toHaveClass(/active/)

  // 切到 Detected
  await detectedBtn.click()
  await expect(detectedBtn).toHaveClass(/active/)
  await expect(matchedBtn).not.toHaveClass(/active/)
  await expect(tracedBtn).not.toHaveClass(/active/)
  await page.screenshot({ path: 'e2e-level-detected.png' })

  // 切到 Qualified
  await tracedBtn.click()
  await expect(tracedBtn).toHaveClass(/active/)
  await expect(matchedBtn).not.toHaveClass(/active/)
  await expect(detectedBtn).not.toHaveClass(/active/)
  await page.screenshot({ path: 'e2e-level-qualified.png' })

  // 切回 Matched
  await matchedBtn.click()
  await expect(matchedBtn).toHaveClass(/active/)
  await expect(tracedBtn).not.toHaveClass(/active/)
  await expect(detectedBtn).not.toHaveClass(/active/)
  await page.screenshot({ path: 'e2e-level-matched.png' })
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 3: 双向高亮——点 sidebar 候选表行 → selectedEventId 更新 → 截图
// ─────────────────────────────────────────────────────────────────────────────
test('bidirectional highlight: sidebar candidate row click → selected class + chart screenshot', async ({ page }) => {
  await ensureScanLoaded(page)

  // 先切到 Detected 档以确保有候选行
  await page.locator('[data-testid="level-control"]').getByRole('button', { name: 'Detected' }).click()

  // 等 diag 加载好,漏斗行出现
  await expect(page.locator('.funnel-row').first()).toBeVisible({ timeout: 15_000 })

  // 找第一个 pattern node(有漏斗箭头,可展开) — 点击展开
  // funnel-row:not isolated → 有 .funnel-arrow
  const clickableFunnelRow = page.locator('.funnel-row').filter({ has: page.locator('.funnel-arrow') }).first()
  await expect(clickableFunnelRow).toBeVisible()
  await clickableFunnelRow.click()

  // 等候选表展开(出现 .candidate-table-wrap)
  await expect(page.locator('.candidate-table-wrap')).toBeVisible({ timeout: 5_000 })

  // 候选表中应有 .attr-row 行
  const firstAttrRow = page.locator('.attr-row').first()
  await expect(firstAttrRow).toBeVisible()

  // 记录 event_id(通过 data-event-id 属性 OR 文字内容)
  // 点击第一行 → 触发 view.focusEvent(row.event_id)
  await firstAttrRow.click()

  // 被点行应获得 attr-row--selected class
  await expect(firstAttrRow).toHaveClass(/attr-row--selected/)

  // 截图:chart 上 highlight 描边应出现(白色描边 marker)
  await page.screenshot({ path: 'e2e-highlight-selected.png' })

  // 点第二行(若存在)以测试选中切换
  const secondAttrRow = page.locator('.attr-row').nth(1)
  const secondVisible = await secondAttrRow.isVisible().catch(() => false)
  if (secondVisible) {
    await secondAttrRow.click()
    await expect(secondAttrRow).toHaveClass(/attr-row--selected/)
    await expect(firstAttrRow).not.toHaveClass(/attr-row--selected/)
    await page.screenshot({ path: 'e2e-highlight-selected-2.png' })
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// Test 4: 漏斗 + 候选表展开——4 pattern node 行 + 1 bo 密度行 + 展开后有 clause 列
// ─────────────────────────────────────────────────────────────────────────────
test('funnel overview: 4 pattern-node rows + 1 bo badge row + expand shows clause table', async ({ page }) => {
  await ensureScanLoaded(page)

  // 等 diag 加载好
  await expect(page.locator('.funnel-row').first()).toBeVisible({ timeout: 15_000 })

  // 5 个 funnel-row
  await expect(page.locator('.funnel-row')).toHaveCount(5)

  // 4 个 pattern node 行(含 funnel-arrow ▸)— 即有边 node
  const patternNodeRows = page.locator('.funnel-row').filter({ has: page.locator('.funnel-arrow') })
  await expect(patternNodeRows).toHaveCount(4)

  // 1 个 bo 密度行(含 .badge "原始检测")
  const boRow = page.locator('.funnel-row').filter({ has: page.locator('.badge') })
  await expect(boRow).toHaveCount(1)
  await expect(boRow.locator('.badge')).toContainText('原始检测')

  // 切到 Detected 档确保候选行非空
  await page.locator('[data-testid="level-control"]').getByRole('button', { name: 'Detected' }).click()

  // 展开第一个 pattern node 行
  const firstPatternRow = patternNodeRows.first()
  await firstPatternRow.click()

  // 候选表容器出现
  await expect(page.locator('.candidate-table-wrap')).toBeVisible({ timeout: 5_000 })

  // 候选表标题(含 "候选")
  await expect(page.locator('.candidate-table-title')).toContainText('候选')

  // 有表头(clause 列)或"无候选数据"提示
  const hasTable = await page.locator('.candidate-table').isVisible().catch(() => false)
  const hasHint  = await page.locator('.candidate-table-wrap .hint').isVisible().catch(() => false)
  expect(hasTable || hasHint).toBe(true)

  if (hasTable) {
    // 表头至少有"事件"列
    await expect(page.locator('.candidate-table thead th').first()).toBeVisible()
    // 至少有一行候选数据
    await expect(page.locator('.attr-row').first()).toBeVisible()
  }

  // 截图:展开状态
  await page.screenshot({ path: 'e2e-funnel-expanded.png' })

  // 点同一行收起
  await firstPatternRow.click()
  await expect(page.locator('.candidate-table-wrap')).not.toBeVisible()

  // 截图:收起状态
  await page.screenshot({ path: 'e2e-funnel-collapsed.png' })
})
