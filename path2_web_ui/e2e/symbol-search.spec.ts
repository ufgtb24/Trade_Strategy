import { test, expect } from '@playwright/test'

// 前提:后端在 localhost:8000 在线;已有一次命中扫描(或本测试触发扫描)。
// 复用 flow.spec.ts 的 ensureScanLoaded 辅助模式(e2e 允许小重复)。

async function openScanDialogAndSelectAll(page: any) {
  await page.getByRole('button', { name: /扫描 ⚙/ }).click()
  await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
  await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()
}

async function ensureScanLoaded(page: any) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: /打开历史/ })).toBeVisible()
  await page.getByRole('button', { name: /打开历史/ }).click()
  // 历史列表异步加载:先等 Loading 态清空,再读 rowCount,避免读到过渡态误判 0 行
  await expect(page.locator('.state', { hasText: 'Loading' })).toHaveCount(0, { timeout: 15_000 })
  await expect(page.locator('.file-list, .state')).toBeVisible({ timeout: 5_000 })
  const rowCount = await page.locator('.file-list tbody tr').count()
  if (rowCount === 0) {
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible()
    await openScanDialogAndSelectAll(page)
    await page.getByRole('button', { name: /开始扫描/ }).click()
    await expect(page.locator('.done')).toBeVisible({ timeout: 180_000 })
    await page.getByRole('button', { name: /打开历史/ }).click()
    await expect(page.locator('.state', { hasText: 'Loading' })).toHaveCount(0, { timeout: 15_000 })
    await expect(page.locator('.file-list')).toBeVisible({ timeout: 5_000 })
  }
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('[data-symbol]').first()).toBeVisible({ timeout: 30_000 })
}

test.describe('symbol search e2e', () => {
  test('empty state: search bar not rendered', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-testid="symbol-search"]')).toHaveCount(0)
  })

  test('after scan load: search bar visible + typing narrows list + Esc clears + Shift+B safe', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))

    await ensureScanLoaded(page)

    // 搜索框出现
    const search = page.locator('[data-testid="symbol-search"]')
    await expect(search).toBeVisible({ timeout: 10_000 })

    // 记录初始行数
    const initialCount = await page.locator('[data-symbol]').count()
    expect(initialCount).toBeGreaterThan(0)

    // 全局字符转发:body 焦点下按字符 'a',应自动 focus 搜索框且值为 'a'
    await page.locator('body').click({ position: { x: 5, y: 5 } })  // 先把焦点撞出可能的 input
    await page.keyboard.press('KeyA')
    await expect(search).toBeFocused()
    await expect(search).toHaveValue('a')

    // 列表数量下降或相等(过滤后 ≤ 初始)
    const afterCount = await page.locator('[data-symbol]').count()
    expect(afterCount).toBeLessThanOrEqual(initialCount)

    // 数量提示可见
    await expect(page.locator('[data-testid="symbol-search-count"]')).toBeVisible()

    // Esc 清空 query
    await page.keyboard.press('Escape')
    await expect(search).toHaveValue('')

    // Shift+B 回归入口 A:不抛错(brush toggle 生效或 no-op,不做视觉断言避免脆)
    await page.locator('body').click({ position: { x: 5, y: 5 } })
    await page.keyboard.press('Shift+KeyB')
    expect(errors).toEqual([])
    // 先清 query 保证起点为空(Esc-清空要求此刻搜索框仍持有焦点,故先清后再 blur 到 body,
    // 而不是像原草稿那样先 blur 到 body 再按 Esc —— 那样 Esc 不作用于搜索框会不清空)
    await page.keyboard.press('Escape')
    await expect(search).toHaveValue('')

    // 单字符 B(裸 b)应吸到搜索框而非触发 brush
    await page.locator('body').click({ position: { x: 5, y: 5 } })
    await page.keyboard.press('KeyB')
    await expect(search).toBeFocused()
    await expect(search).toHaveValue('b')
    expect(errors).toEqual([])
  })
})
