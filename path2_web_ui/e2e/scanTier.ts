import { expect, type Page } from '@playwright/test'

/**
 * 进顶栏 mode 的 scan 档:扫描面板(扫描 ⚙、打开历史)和扫描结果列表只在 scan 档的左栏出现,
 * annotate / compare / app 三档的左栏是找图清单。没加载扫描时落在 no_scan,左栏是扫描面板和空列表。
 *
 * - enterScanTier:在当前页面上点 scan(已在 scan 档时不动);
 * - gotoScanTier:打开 url(默认首页)再点 scan。原来打开首页就直接点左栏「打开历史」「扫描 ⚙」的用例走这里。
 */
export async function enterScanTier(page: Page): Promise<void> {
  await page.getByTestId('mode-scan').click()
  await expect(page.getByTestId('mode-scan')).toHaveClass(/\bon\b/)
  await expect(page.getByRole('button', { name: /打开历史/ })).toBeVisible()
}

export async function gotoScanTier(page: Page, url = '/'): Promise<void> {
  await page.goto(url)
  await enterScanTier(page)
}
