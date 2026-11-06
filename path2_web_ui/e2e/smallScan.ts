import { expect, type Page } from '@playwright/test'
import { apiBase, baseURL } from './ports'

/**
 * e2e 夹具:对在线后端发起一次 new_step 小扫描(RGTI、CRNC 两只股票,2024-01 ~ 2025-06),扫完在界面上打开。
 * 历史里现存的扫描或是 bo_only、或越过数据墙打不开,不能拿来当夹具;用完调 deleteSmallScan 删掉这个扫描文件。
 * 每个 spec 文件用自己的名字(name 带时间戳),互不干扰。
 */
export function smallScanName(tag: string): string {
  return `e2e_${tag}_${Date.now()}`
}

export async function runSmallScan(name: string): Promise<void> {
  const r = await fetch(`${apiBase}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern_ids: ['new_step'], start_date: '2024-01-01', end_date: '2025-06-30', workers: 2,
                           ticker_regex: '^(RGTI|CRNC)$', label_horizon: 20, note: name }),
  })
  expect(r.ok).toBe(true)
  for (let i = 0; i < 240; i++) {
    const scans: Array<{ name: string; partial: boolean }> = await (await fetch(`${apiBase}/scans/`)).json()
    if (scans.some((x) => x.name === name && !x.partial)) return
    await new Promise((res) => setTimeout(res, 1000))
  }
  throw new Error('new_step 小扫描 4 分钟内没有完成')
}

export async function deleteSmallScan(name: string): Promise<void> {
  await fetch(`${apiBase}/scans/${encodeURIComponent(name)}`, { method: 'DELETE' }).catch(() => {})
}

/** 首页 → 打开历史 → 选这个扫描 → Open,等扫描文件进 store。 */
export async function openSmallScan(page: Page, name: string): Promise<void> {
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator(`.file-list tbody tr:has-text("${name}")`).click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).not.toBeVisible({ timeout: 30_000 })
  await page.waitForFunction(() => !!(window as any).__e2e?.view?.scanFile)
}
