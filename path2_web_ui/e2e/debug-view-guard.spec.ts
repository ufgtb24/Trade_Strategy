import { test, expect } from '@playwright/test'
import { existsSync, readFileSync, realpathSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'

// 调试视图的看图范围护栏(path2_web/guard.py)端到端:
//   ① 读了完整行情的旧扫描在历史列表里标「旧扫描」、不列成绩,双击打不开并提示原因;
//   ② 新扫描的区间被截进看图范围(训练段末日为止、不早于看图下界),文件带 view_guard;
//   ③ 打开新扫描、点一只股票:K 线最后一根不晚于训练段末日,看图下界之前的 bar 没有价格,
//      状态根的看过记录里多一条 surface=debug 的 show_chart。
// 前提与 workflow.spec.ts 相同:后端用临时状态根启动(CHART_WORKFLOW_STATE_ROOT),截断副本已生成。
// 扫描文件写在本 worktree 的 outputs/path2_web/scans/,跑完删掉;看过记录留在临时状态根里,由建它的人整个删掉。
// 跑法:CHART_WORKFLOW_STATE_ROOT=/tmp/<临时目录> npx playwright test e2e/debug-view-guard.spec.ts --workers=1

const here = dirname(fileURLToPath(import.meta.url))
const SCANS = resolve(here, '../../outputs/path2_web/scans')
const OLD = 'e2e-guard-old'
const NEW = 'e2e-guard-new'
const STATE_ROOT = process.env.CHART_WORKFLOW_STATE_ROOT
if (!STATE_ROOT) throw new Error('必须设 CHART_WORKFLOW_STATE_ROOT(与后端同一个临时状态根)')
const FLOOR = '2025-01-01'
const TRAIN_END = '2025-12-31'

function views(): any[] {
  const p = resolve(STATE_ROOT!, 'views.jsonl')
  return existsSync(p) ? readFileSync(p, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)) : []
}

test.describe.configure({ mode: 'serial' })

test.beforeAll(async ({ request }) => {
  const st = await (await request.get(`${apiBase}/workflow/state`)).json()
  if (!st.from_env || realpathSync(st.path) !== realpathSync(STATE_ROOT!)) {
    throw new Error(`后端的状态根不是这个临时目录(后端:${st.path}),不跑`)
  }
  mkdirSync(SCANS, { recursive: true })
  for (const n of [OLD, NEW]) rmSync(resolve(SCANS, `${n}.json`), { force: true })
  writeFileSync(resolve(SCANS, `${OLD}.json`), JSON.stringify({
    pattern_ids: ['bo_only'],
    scan: { scan_ts: '20000101T000000', name: OLD, start_date: '2024-01-02', end_date: '2026-06-01',
            win_start: '2023-01-03', win_end: '2026-08-07', label_horizon: 40, hits: 1, scanned: 1,
            errors: 0, workers: 1, dataset_dir: 'datasets/pkls', first_passage_k: 5 },
    per_pattern: { bo_only: { stats: { median: 0.04 } } },
    results: [{ symbol: 'AAPL', per_pattern: { bo_only: { summary: { matches: 3 } } } }],
  }))
})

test.afterAll(() => {
  for (const n of [OLD, NEW]) rmSync(resolve(SCANS, `${n}.json`), { force: true })
})

test('新扫描的区间截进看图范围、带 view_guard', async ({ request }) => {
  const r = await request.post(`${apiBase}/scan`, { data: {
    pattern_ids: ['bo_only'], start_date: '2024-06-03', end_date: '2026-03-02', workers: 2,
    ticker_regex: '^(AAPL|MSFT|NVDA|AMD|TSLA|META)$', label_horizon: 20, note: NEW,
  } })
  expect(r.status()).toBe(200)
  const path = resolve(SCANS, `${NEW}.json`)
  await expect.poll(() => existsSync(path), { timeout: 120_000 }).toBe(true)
  const s = JSON.parse(readFileSync(path, 'utf8')).scan
  expect([s.start_date, s.end_date]).toEqual([FLOOR, TRAIN_END])
  expect(s.view_guard).toEqual({ view_floor: FLOOR, train_end: TRAIN_END })
  expect(s.hits).toBeGreaterThan(0)
})

test('旧扫描标出来、不列成绩、打不开', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /打开历史/ }).click()
  const old = page.locator('.file-list tbody tr', { hasText: OLD })
  await expect(old.locator('.old-badge')).toHaveText('旧扫描')
  await expect(old.locator('.hits-num')).toHaveCount(0)
  await old.dblclick()
  await expect(page.locator('.toast')).toContainText('请重新扫描')
  await expect(page.locator('.file-list')).toBeVisible()           // 对话框还在
})

test('新扫描的 K 线只到训练段末日、看图下界之前不给价格,看过记一条 debug', async ({ page }) => {
  const before = views().filter(v => v.surface === 'debug').length
  await page.goto('/')
  await page.getByRole('button', { name: /打开历史/ }).click()
  const row = page.locator('.file-list tbody tr', { hasText: NEW })
  await expect(row.locator('.old-badge')).toHaveCount(0)
  await row.click()
  // 打开扫描会自动选中第一只股票并取它的 K 线
  const resp = page.waitForResponse(r => r.url().includes('/ohlc?'), { timeout: 60_000 })
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('[data-symbol]').first()).toBeVisible({ timeout: 30_000 })
  const res = await resp
  const sym = new URL(res.url()).searchParams.get('symbol')
  const body = await res.json()
  const bars = body.bars as Array<{ date: string; o: number | null; c: number | null }>
  expect(bars.at(-1)!.date <= TRAIN_END).toBe(true)
  const pre = bars.filter(b => b.date < FLOOR)
  expect(pre.length).toBeGreaterThan(0)                          // 探测器预热段占位
  expect(pre.every(b => b.o === null && b.c === null)).toBe(true)
  expect(bars.filter(b => b.date >= FLOOR).every(b => b.o !== null)).toBe(true)
  await expect.poll(() => views().filter(v => v.surface === 'debug').length).toBe(before + 1)
  const v = views().filter(x => x.surface === 'debug').at(-1)
  expect(v.event).toBe('show_chart')
  expect(v.charts[0].symbol).toBe(sym)
  expect(v.charts[0].start >= FLOOR && v.charts[0].end <= TRAIN_END).toBe(true)
})
