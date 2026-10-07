import { test, expect, type Locator, type Page } from '@playwright/test'
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// 前提:后端已在 configs/path2_web.yaml 的 backend_port 上运行(workflow.root 用默认
// outputs/chart_workflow)。本测试先往 lists/ 写一份 2 条的固定清单,跑完删掉它和自己发出的批次文件。
// 跑法:cd path2_web_ui && npx playwright test e2e/workflow.spec.ts --workers=1

const here = dirname(fileURLToPath(import.meta.url))
const WF_ROOT = resolve(here, '../../outputs/chart_workflow')
const LIST_ID = 'e2e-workflow-fixture'
const LIST_PATH = resolve(WF_ROOT, 'lists', `${LIST_ID}.json`)
const ANN_DIR = resolve(WF_ROOT, 'annotations')
const ITEM_A = 'AAPL@2025-06-02'
const ITEM_B = 'MSFT@2025-07-01'

function fixture() {
  const item = (id: string, sym: string, t: string, entry: string, vs: string, ve: string) => ({
    item_id: id, symbol: sym, t, entry_date: entry, view_start: vs, view_end: ve,
    marks: { decision: t, entry, up_line: 260, down_line: 180, peak_date: ve },
    metrics: { rel: 2.1, rise: 0.3, M: 0.02, dir: 1, mag: 0.3, dd: -0.05 },
    tags: ['不跳空'],
  })
  return {
    schema: 'chart_workflow.list/1', list_id: LIST_ID, kind: 'bigmoves', title: 'e2e 固定清单',
    created_at: '2000-01-01T00:00:00', train_start: '2024-01-01', train_end: '2025-12-31',
    params: {},
    groups: [{ key: 'all', title: '全部（2）', item_ids: [ITEM_A, ITEM_B] }],
    items: [item(ITEM_A, 'AAPL', '2025-06-02', '2025-06-03', '2025-03-03', '2025-07-30'),
            item(ITEM_B, 'MSFT', '2025-07-01', '2025-07-02', '2025-04-01', '2025-08-27')],
  }
}

const listBatches = () => (existsSync(ANN_DIR) ? readdirSync(ANN_DIR).filter(f => f.endsWith('.json')) : [])

async function chartBox(cell: Locator) {
  const box = await cell.locator('.chart').boundingBox()
  if (!box) throw new Error('chart 没有尺寸')
  return box
}

/** 在第一格主图上横向拖一段(相对宽度 fromX..toX,纵向取主图区 30% 高度处)。 */
async function brush(page: Page, cell: Locator, fromX: number, toX: number) {
  await cell.getByTestId('tool-brush').click()
  await expect(cell.getByTestId('tool-brush')).toHaveAttribute('aria-pressed', 'true')
  const b = await chartBox(cell)
  const y = b.y + b.height * 0.3
  await page.mouse.move(b.x + b.width * fromX, y)
  await page.mouse.down()
  await page.mouse.move(b.x + b.width * ((fromX + toX) / 2), y, { steps: 5 })
  await page.mouse.move(b.x + b.width * toX, y, { steps: 5 })
  await page.mouse.up()
}

async function clickBuy(page: Page, cell: Locator, x: number) {
  await cell.getByTestId('tool-buy').click()
  await expect(cell.getByTestId('tool-buy')).toHaveAttribute('aria-pressed', 'true')
  const b = await chartBox(cell)
  await page.mouse.click(b.x + b.width * x, b.y + b.height * 0.3)
}

async function annotateFirst(page: Page, cell: Locator, note: string) {
  await brush(page, cell, 0.4, 0.7)
  await expect(cell.getByTestId('ann-summary')).not.toContainText('未框')
  await clickBuy(page, cell, 0.6)
  await expect(cell.getByTestId('ann-summary')).not.toContainText('买点 无')
  await cell.getByTestId('label-positive').check()
  await cell.getByTestId('note').fill(note)
  await expect(cell.getByTestId('ann-summary')).toContainText('正例')
}

test.beforeAll(() => {
  mkdirSync(dirname(LIST_PATH), { recursive: true })
  writeFileSync(LIST_PATH, JSON.stringify(fixture(), null, 1))
})

const created: string[] = []
test.afterAll(() => {
  rmSync(LIST_PATH, { force: true })
  for (const f of created) rmSync(resolve(ANN_DIR, f), { force: true })
})

test('看图工作流:框选、点买点、标正例、写备注 → 抽屉里改、删、再标 → 发送落盘', async ({ page }) => {
  const before = new Set(listBatches())
  await page.goto(`/?wf=${LIST_ID}`)
  await expect(page.locator('.annot-chart')).toHaveCount(2, { timeout: 20_000 })
  const cell = page.locator(`.annot-chart[data-item-id="${ITEM_A}"]`)
  await expect(cell.locator('canvas').first()).toBeVisible({ timeout: 20_000 })

  await annotateFirst(page, cell, 'e2e 备注一')
  await expect(page.getByTestId('wf-drawer')).toHaveText('已标注 (1)')

  // 抽屉:改备注
  await page.getByTestId('wf-drawer').click()
  const panel = page.getByTestId('review-panel')
  const row = panel.locator(`tr[data-item-id="${ITEM_A}"]`)
  await expect(row).toBeVisible()
  await row.getByTestId('row-note').fill('e2e 备注二')
  await expect(cell.getByTestId('note')).toHaveValue('e2e 备注二')

  // 删掉再标回来
  await row.getByTestId('row-delete').click()
  await expect(page.getByTestId('wf-drawer')).toHaveText('已标注 (0)')
  await expect(cell.getByTestId('ann-summary')).toHaveCount(0)
  await annotateFirst(page, cell, 'e2e 备注三')
  await expect(panel.locator(`tr[data-item-id="${ITEM_A}"]`)).toBeVisible()

  // 发送
  await panel.getByTestId('send').click()
  await expect(panel.getByTestId('send-ok')).toContainText('已发送：批次', { timeout: 10_000 })
  await expect(page.getByTestId('wf-drawer')).toHaveText('已标注 (0)')

  const fresh = listBatches().filter(f => !before.has(f))
  created.push(...fresh)
  expect(fresh).toHaveLength(1)
  const saved = JSON.parse(readFileSync(resolve(ANN_DIR, fresh[0]), 'utf8'))
  expect(saved.schema).toBe('chart_workflow.annotations/1')
  expect(saved.list_id).toBe(LIST_ID)
  expect(saved.train_end).toBe('2025-12-31')
  expect(saved.annotations).toHaveLength(1)
  const a = saved.annotations[0]
  expect(a.item_id).toBe(ITEM_A)
  expect(a.symbol).toBe('AAPL')
  expect(a.label).toBe('positive')
  expect(a.note).toBe('e2e 备注三')
  expect(a.range_start <= a.range_end).toBe(true)
  expect(a.range_start >= '2025-03-03' && a.range_end <= '2025-07-30').toBe(true)
  expect(a.buy_date >= a.range_start && a.buy_date <= a.range_end).toBe(true)
  expect(a.ann_id).toMatch(/[0-9a-f-]{36}/)
})
