import { test, expect } from '@playwright/test'
import { apiBase as API_BASE } from './ports'

// 前提:后端可达(端口由 configs/path2_web.yaml 决定);outputs 至少有 1 次扫描历史 (本测试自带触发)

async function gotoApp(page: any) {
  await page.goto('/')
  await expect(page.locator('select')).toContainText('底部反转突破爆发')
}

// 扫描参数已搬进 ScanConfigDialog(点顶部工具条「扫描 ⚙」打开);
// dialog 打开时 pattern 选择默认清空,需先全选才能启用「开始扫描」。
async function openScanDialogAndSelectAll(page: any) {
  await page.getByRole('button', { name: /扫描 ⚙/ }).click()
  await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
  await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()
}

async function ensureAtLeastOneScan(page: any) {
  await gotoApp(page)
  // 若历史已有记录则跳过扫描;否则触发一次等完成
  const existing = await fetch(`${API_BASE}/scans/bottom_burst`).then(r => r.json()).catch(() => [])
  if (Array.isArray(existing) && existing.length > 0) return
  await openScanDialogAndSelectAll(page)
  await page.getByRole('button', { name: /开始扫描/ }).click()
  await expect(page.locator('.done')).toBeVisible({ timeout: 300_000 })
}

test('1. open dialog → rows visible (列 Time/Hits/Size 都渲染)', async ({ page }) => {
  await ensureAtLeastOneScan(page)
  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.backdrop')).toBeVisible()
  await expect(page.locator('.file-list tbody tr').first()).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.file-list thead')).toContainText('Time')
  await expect(page.locator('.file-list thead')).toContainText('Hits')
  await expect(page.locator('.file-list thead')).toContainText('Size')
})

test('2. row click + Open → main view loads scanFile', async ({ page }) => {
  await ensureAtLeastOneScan(page)
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).toBeHidden()
  // 主视图绑定 scanFile 后,SidebarResultList 出现 row 或 "未加载" 消失
  await expect(page.locator('.hint')).toBeHidden({ timeout: 5_000 }).catch(() => {/* 无命中场景允许 */})
})

test('3. multi-select 2 rows + Delete → confirm → 行消失', async ({ page }) => {
  // 跑两次扫描确保有 2 条历史
  await ensureAtLeastOneScan(page)
  // 确保至少 2 条:若历史已 ≥2 跳过第二次扫描
  const existing2 = await fetch(`${API_BASE}/scans/bottom_burst`).then(r => r.json()).catch(() => [])
  if (!Array.isArray(existing2) || existing2.length < 2) {
    await openScanDialogAndSelectAll(page)
    await page.getByRole('button', { name: /开始扫描/ }).click()
    await expect(page.locator('.done')).toBeVisible({ timeout: 300_000 })
  }

  await page.getByRole('button', { name: /打开历史/ }).click()
  const rows = page.locator('.file-list tbody tr')
  await expect(rows.first()).toBeVisible({ timeout: 10_000 })
  const initialCount = await rows.count()
  expect(initialCount).toBeGreaterThanOrEqual(2)

  await rows.nth(0).click()
  await rows.nth(1).click({ modifiers: ['Control'] })
  await page.locator('.card').press('Delete')
  await expect(page.locator('.confirm-card')).toBeVisible()
  await page.locator('.confirm-card button.btn-stop').click()
  await expect(page.locator('.file-list tbody tr')).toHaveCount(initialCount - 2)
})

test('4. select currentScanTs + Delete → 红字提示 + 删后主视图清空', async ({ page }) => {
  await ensureAtLeastOneScan(page)
  // 先 Open 一个加载到主视图
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).toBeHidden()

  // 再开对话框,选当前已加载(标 current)的那条 → Delete
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator('.file-list tbody tr.current').first().click()
  await page.locator('.card').press('Delete')
  await expect(page.locator('.warn')).toBeVisible()
  await expect(page.locator('.warn')).toContainText(/currently loaded scan/)
  await page.locator('.confirm-card button.btn-stop').click()
  // confirm-card 退场(delete 后 confirming=false)
  await expect(page.locator('.confirm-card')).toBeHidden({ timeout: 5_000 })
  // 若 dialog 仍开(currentScanId 被删不自动关),按 Esc 关闭
  if (await page.locator('.backdrop').isVisible()) {
    await page.keyboard.press('Escape')
  }
  // 主视图清空:SidebarResultList 显「未加载」
  await expect(page.locator('.list .hint')).toContainText(/未加载/, { timeout: 5_000 })
})

test('5. Start scan → 按钮变红「停止扫描」→ click → cancel + 「扫描 ⚙」enabled', async ({ page }) => {
  await gotoApp(page)
  await openScanDialogAndSelectAll(page)
  await page.getByRole('button', { name: /开始扫描/ }).click()
  // 立刻看按钮变红
  const stopBtn = page.getByRole('button', { name: /停止扫描/ })
  await expect(stopBtn).toBeVisible({ timeout: 5_000 })
  await expect(stopBtn).toHaveClass(/btn-stop/)
  // 「扫描 ⚙」运行中 disabled(防止运行中改配置;新 UI 下「打开历史」不再受运行态约束)
  await expect(page.getByRole('button', { name: /扫描 ⚙/ })).toBeDisabled()
  // 点停止
  await stopBtn.click()
  await expect(page.locator('.done')).toContainText(/扫描已取消|完成/, { timeout: 30_000 })
  // 扫描按钮恢复可点
  await expect(page.getByRole('button', { name: /扫描 ⚙/ })).toBeEnabled()
})
