import { test, expect, type Locator, type Page } from '@playwright/test'
import { mkdirSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apiBase } from './ports'

// 前提:后端已在 configs/path2_web.yaml 的 backend_port 上运行,而且必须用临时状态根启动——
//   python -m chart_workflow.state init /tmp/<临时目录>
//   CHART_WORKFLOW_STATE_ROOT=/tmp/<临时目录> uv run python scripts/path2/run_path2_web.py
// 绝不能让端到端测试写进主目录的状态根:那里的文件进 git,测试批次会混进真实账本。
// 本测试从同一个环境变量取批次目录,没设就直接失败;开跑前还向后端 /workflow/state 核对:后端的状态根
// 必须来自环境变量、而且和这里是同一个目录,否则整组测试不跑(防止后端是不带环境变量启动的)。K 线读截断副本,先运行过
// python -m chart_workflow.snapshot。清单写到本 worktree 的 outputs/chart_workflow/lists/
// (workflow.root 用默认),跑完删掉它;发出的批次留在临时状态根里,由建它的人整个删掉——
// 单删批次文件会让状态根的水位核对认为「账本比上次看到的少」,后面的测试就打不开清单了。
// 跑法:CHART_WORKFLOW_STATE_ROOT=/tmp/<临时目录> npx playwright test e2e/workflow.spec.ts --workers=1

const here = dirname(fileURLToPath(import.meta.url))
const WF_ROOT = resolve(here, '../../outputs/chart_workflow')
const LIST_ID = 'e2e-workflow-fixture'
const LIST_PATH = resolve(WF_ROOT, 'lists', `${LIST_ID}.json`)
const STATE_ROOT = process.env.CHART_WORKFLOW_STATE_ROOT
if (!STATE_ROOT) throw new Error('必须设 CHART_WORKFLOW_STATE_ROOT(与后端同一个临时状态根),不回落到 outputs/chart_workflow')
const ANN_DIR = resolve(STATE_ROOT, 'annotations')
const ITEM_A = 'AAPL@2025-06-02'
const ITEM_B = 'MSFT@2025-07-01'

function fixture() {
  const item = (id: string, sym: string, t: string, entry: string, vs: string, ve: string) => ({
    item_id: id, symbol: sym, exchange: sym === 'AAPL' ? 'NASDAQ' : null,
    t, entry_date: entry, view_start: vs, view_end: ve,
    xcheck: sym === 'AAPL'
      ? { status: 'mismatch', n_compared: 60, n_missing: 0,
          mismatch_days: [{ date: '2025-06-10', r_ours: 0.9, r_nasdaq: 0.01 }] }
      : { status: 'ok', n_compared: 60, n_missing: 0, mismatch_days: [] },
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

/** 点买点模式下单击要等一下(src/stores/workflow.ts 的 CLICK_DELAY_MS = 250)没有双击才生效 */
const CLICK_SETTLE_MS = 450

async function clickBuy(page: Page, cell: Locator, x: number) {
  await cell.getByTestId('tool-buy').click()
  await expect(cell.getByTestId('tool-buy')).toHaveAttribute('aria-pressed', 'true')
  const b = await chartBox(cell)
  await page.mouse.click(b.x + b.width * x, b.y + b.height * 0.3)
  await page.waitForTimeout(CLICK_SETTLE_MS)
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

test.beforeAll(async () => {
  const st = await fetch(`${apiBase}/workflow/state`).then(r => r.json())
  const mine = realpathSync(STATE_ROOT)
  if (!st.from_env || !st.ok || st.path !== mine) {
    throw new Error(`后端的状态根不是本测试的临时目录(后端:${st.path},来自环境变量:${st.from_env};`
                    + `本测试:${mine}),不跑——免得测试批次写进真账本`)
  }
  mkdirSync(dirname(LIST_PATH), { recursive: true })
  writeFileSync(LIST_PATH, JSON.stringify(fixture(), null, 1))
})

test.afterAll(() => {
  rmSync(LIST_PATH, { force: true })
})

test('看图工作流:框选、点买点、标正例、写备注 → 抽屉里改、删、再标 → 发送落盘', async ({ page }) => {
  const before = new Set(listBatches())
  await page.goto(`/?wf=${LIST_ID}`)
  await expect(page.locator('.annot-chart')).toHaveCount(2, { timeout: 20_000 })
  const cell = page.locator(`.annot-chart[data-item-id="${ITEM_A}"]`)
  await expect(cell.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
  // 后端用的是临时状态根:顶上有文字提示
  await expect(page.getByTestId('wf-state-env')).toContainText(realpathSync(STATE_ROOT))

  // 跨源比对:大涨段点第一个买点前不显示(列出的日子可能在决策日之后);有了买点后,
  // 不一致的段图头写明那几天,一致的段不显示
  await expect(cell.getByTestId('xcheck-warn')).toHaveCount(0)
  await annotateFirst(page, cell, 'e2e 备注一')
  await expect(cell.getByTestId('xcheck-warn')).toContainText('两份数据不一致：2025-06-10')
  await expect(page.locator(`.annot-chart[data-item-id="${ITEM_B}"]`).getByTestId('xcheck-warn'))
    .toHaveCount(0)

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
  expect(fresh).toHaveLength(1)
  const saved = JSON.parse(readFileSync(resolve(ANN_DIR, fresh[0]), 'utf8'))
  expect(saved.schema).toBe('chart_workflow.annotations/2')
  expect(saved.list_kind).toBe('bigmoves')
  expect(saved.outcome_visible).toBe(true)
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
  expect(a.buy_points).toHaveLength(1)
  expect(a.buy_points[0].primary).toBe(true)
  expect(a.buy_points[0].date >= a.range_start && a.buy_points[0].date <= a.range_end).toBe(true)
  expect(a.buy_date).toBeUndefined()
  expect(a.ann_id).toMatch(/[0-9a-f-]{36}/)
  // 看到结果后在抽屉里删掉再标:带着第一次的买点和「看过结果后改过」、记成看过后续
  expect(a.changed_after_reveal).toBe(true)
  expect(a.peeked_before_buy).toBe(true)
  expect(a.first_buy_points).toHaveLength(1)
  expect(a.first_buy_points[0].primary).toBe(true)
})

/** 从格子的标注摘要里读起止与买点。 */
async function readSummary(cell: Locator) {
  const t = await cell.getByTestId('ann-summary').innerText()
  const m = t.match(/起止 (\S+) → (\S+) · 买点 (\S+)/)
  if (!m) throw new Error(`摘要格式不对:${t}`)
  return { start: m[1], end: m[2], buy: m[3].replace('★', '').split('、')[0] }
}
const dayDiff = (a: string, b: string) => Math.abs(Date.parse(a) - Date.parse(b)) / 86_400_000
const daySpan = (r: { start: string, end: string }) => dayDiff(r.start, r.end)

test('看图工作流:小图双击放大;放大图滚轮以鼠标处为中心横向缩放;放大图双击退出', async ({ page }) => {
  await page.goto(`/?wf=${LIST_ID}`)
  const cell = page.locator(`.annot-chart[data-item-id="${ITEM_B}"]`)
  await expect(cell.locator('canvas').first()).toBeVisible({ timeout: 20_000 })

  // 开着「点买点」双击小图:打开放大,双击带出的点击不留买点
  await cell.getByTestId('tool-buy').click()
  await cell.locator('.chart').dblclick({ position: { x: 200, y: 60 } })
  const zoom = page.getByTestId('wf-zoom')
  await expect(zoom).toBeVisible()
  await expect(cell.getByTestId('ann-summary')).toHaveCount(0)

  const big = zoom.locator('.annot-chart')
  await expect(big.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(300)

  // 缩放前:横向拉满框一段、在 60% 处点买点
  await brush(page, big, 0.08, 0.97)
  await clickBuy(page, big, 0.6)
  const before = await readSummary(big)

  // 鼠标停在 60% 处滚轮放大
  const b = await chartBox(big)
  await page.mouse.move(b.x + b.width * 0.6, b.y + b.height * 0.3)
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(80) }

  // 缩放后:同样拉满框一段,跨度明显变窄;同一位置再点买点,仍是同一根 K 线(不动点在鼠标处)
  await brush(page, big, 0.08, 0.97)
  await clickBuy(page, big, 0.6)
  const after = await readSummary(big)
  expect(daySpan(after)).toBeLessThan(daySpan(before) * 0.7)
  expect(dayDiff(after.buy, before.buy)).toBeLessThanOrEqual(4)
  expect(after.start <= before.buy && before.buy <= after.end).toBe(true)
  // 只在已取回的 K 线里缩放:不越出图窗
  expect(after.start >= '2025-04-01' && after.end <= '2025-08-27').toBe(true)

  // 开着「点买点」在放大图别处双击:退出放大,买点不变
  await big.locator('.chart').dblclick({ position: { x: b.width * 0.3, y: b.height * 0.3 } })
  await expect(zoom).toHaveCount(0)
  expect((await readSummary(cell)).buy).toBe(after.buy)
})

/** 横向框满整个可见区:从主图左边缘内侧拖到图右缘外(超出部分被夹到主图边上)。 */
async function brushAll(page: Page, cell: Locator) {
  const b = await chartBox(cell)
  await brush(page, cell, 54 / b.width, 1 - 2 / b.width)
}

test('看图工作流:小图也能滚轮缩放;放大图从小图当时的范围开始', async ({ page }) => {
  await page.goto(`/?wf=${LIST_ID}`)
  const cell = page.getByTestId('wf-grid').locator(`.annot-chart[data-item-id="${ITEM_A}"]`)
  await expect(cell.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(300)

  await brushAll(page, cell)
  await clickBuy(page, cell, 0.6)
  const before = await readSummary(cell)

  const b = await chartBox(cell)
  await page.mouse.move(b.x + b.width * 0.6, b.y + b.height * 0.3)
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(80) }

  await brushAll(page, cell)
  await clickBuy(page, cell, 0.6)
  const after = await readSummary(cell)
  expect(daySpan(after)).toBeLessThan(daySpan(before) * 0.7)
  expect(dayDiff(after.buy, before.buy)).toBeLessThanOrEqual(4)
  expect(after.start <= before.buy && before.buy <= after.end).toBe(true)

  // 双击放大:放大图横向拉满框一段,范围和小图缩放后的一致
  await cell.locator('.chart').dblclick({ position: { x: b.width * 0.5, y: b.height * 0.3 } })
  const zoom = page.getByTestId('wf-zoom')
  await expect(zoom).toBeVisible()
  expect((await readSummary(cell)).buy).toBe(after.buy)
  const big = zoom.locator('.annot-chart')
  await expect(big.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(300)
  await brushAll(page, big)
  const inBig = await readSummary(big)
  expect(dayDiff(inBig.start, after.start)).toBeLessThanOrEqual(4)
  expect(dayDiff(inBig.end, after.end)).toBeLessThanOrEqual(4)

  // 开着框选双击退出:不改起止
  const bb = await chartBox(big)
  await big.locator('.chart').dblclick({ position: { x: bb.width * 0.5, y: bb.height * 0.3 } })
  await expect(zoom).toHaveCount(0)
  const back = await readSummary(cell)
  expect([back.start, back.end]).toEqual([inBig.start, inBig.end])
})

const PAGES_ID = 'e2e-workflow-pages'
const PAGES_PATH = resolve(WF_ROOT, 'lists', `${PAGES_ID}.json`)

/** 13 条 → 3 页(每页 6 条)。 */
function pagesFixture() {
  const days = ['2025-06-02', '2025-06-03', '2025-06-04', '2025-06-05', '2025-06-06', '2025-06-09',
                '2025-06-10', '2025-06-11', '2025-06-12', '2025-06-13', '2025-06-16', '2025-06-17',
                '2025-06-18']
  const items = days.map(t => ({
    item_id: `AAPL@${t}`, symbol: 'AAPL', exchange: 'NASDAQ', t, entry_date: t,
    view_start: '2025-03-03', view_end: '2025-07-30',
    marks: { decision: t, entry: t }, metrics: { M: 0.02 }, tags: [],
  }))
  return {
    schema: 'chart_workflow.list/1', list_id: PAGES_ID, kind: 'bigmoves', title: 'e2e 翻页清单',
    created_at: '2000-01-01T00:00:00', train_start: '2024-01-01', train_end: '2025-12-31', params: {},
    groups: [{ key: 'all', title: '全部（13）', item_ids: items.map(x => x.item_id) }], items,
  }
}

test('看图工作流:页码框跳转、PgUp / PgDn 翻页', async ({ page }) => {
  writeFileSync(PAGES_PATH, JSON.stringify(pagesFixture(), null, 1))
  try {
    await page.goto(`/?wf=${PAGES_ID}`)
    const input = page.getByTestId('wf-page-input')
    const first = page.locator('.annot-chart').first()
    await expect(input).toHaveValue('1', { timeout: 20_000 })
    await expect(page.locator('.pager')).toContainText('/ 3 页')
    await expect(first).toHaveAttribute('data-item-id', 'AAPL@2025-06-02')

    await page.keyboard.press('PageDown')
    await expect(input).toHaveValue('2')
    await expect(first).toHaveAttribute('data-item-id', 'AAPL@2025-06-10')

    // 点过单选框后焦点在它上面,PgDn 照样翻页
    await first.getByTestId('label-positive').check()
    await page.keyboard.press('PageDown')
    await expect(input).toHaveValue('3')
    await expect(page.locator('.annot-chart')).toHaveCount(1)
    await page.keyboard.press('PageDown')
    await expect(input).toHaveValue('3')
    await page.keyboard.press('PageUp')
    await expect(input).toHaveValue('2')

    // 在备注里按 PgDn 不翻页
    await first.getByTestId('note').click()
    await page.keyboard.press('PageDown')
    await expect(input).toHaveValue('2')

    // 页码框:回车跳转;超出页数跳到最后一页
    await input.fill('1')
    await input.press('Enter')
    await expect(input).toHaveValue('1')
    await expect(first).toHaveAttribute('data-item-id', 'AAPL@2025-06-02')
    await input.fill('9')
    await input.press('Enter')
    await expect(input).toHaveValue('3')
    // 回车后焦点离开页码框,PgUp 直接可用
    await page.keyboard.press('PageUp')
    await expect(input).toHaveValue('2')
  } finally {
    rmSync(PAGES_PATH, { force: true })
  }
})


const V2_ID = 'e2e-workflow-v2'
const V2_PATH = resolve(WF_ROOT, 'lists', `${V2_ID}.json`)

test('看图工作流:点买点前图头不露结果;Shift 多买点;正例不框也能发送;批次是 v2 且批次头有清单种类', async ({ page }) => {
  const doc = fixture()
  doc.list_id = V2_ID
  doc.title = 'e2e v2 清单'
  writeFileSync(V2_PATH, JSON.stringify(doc, null, 1))
  try {
    const before = new Set(listBatches())
    await page.goto(`/?wf=${V2_ID}`)
    const cell = page.locator(`.annot-chart[data-item-id="${ITEM_B}"]`)
    await expect(cell.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
    await page.waitForTimeout(300)
    // 大涨段清单还没有买点:图头不显示决策日、相对涨幅、涨幅;判定文字是「像但不买」
    await expect(cell.locator('.head')).not.toContainText('涨幅')
    await expect(cell.locator('.head')).not.toContainText('决策日')
    await expect(cell.getByTestId('outcome-hidden')).toBeVisible()
    await expect(page.getByTestId('wf-tag')).toHaveCount(0)          // 大涨段不给标签筛选
    await expect(cell.locator('.radio', { has: page.getByTestId('label-negative') })).toContainText('像但不买')
    await expect(cell.getByTestId('tool-log')).toHaveAttribute('aria-pressed', 'true')

    // 点一个买点 → 图头照常显示;再 Shift 点一个 → 两个买点(主买点带 ★)
    await clickBuy(page, cell, 0.5)
    await expect(cell.locator('.head')).toContainText('相对涨幅')
    const b = await chartBox(cell)
    await page.keyboard.down('Shift')
    await page.mouse.click(b.x + b.width * 0.75, b.y + b.height * 0.3)
    await page.keyboard.up('Shift')
    await expect(cell.getByTestId('ann-summary')).toContainText('★')
    await expect(cell.getByTestId('ann-summary')).toContainText('、')
    await expect(cell.getByTestId('ann-summary')).toContainText('起止 未框')
    await cell.getByTestId('label-positive').check()

    await page.getByTestId('wf-drawer').click()
    const panel = page.getByTestId('review-panel')
    await expect(panel.locator(`tr[data-item-id="${ITEM_B}"] [data-testid="row-buys"] div`)).toHaveCount(2)
    await panel.getByTestId('send').click()
    await expect(panel.getByTestId('send-ok')).toContainText('已发送：批次', { timeout: 10_000 })

    const fresh = listBatches().filter(f => !before.has(f))
    expect(fresh).toHaveLength(1)
    const saved = JSON.parse(readFileSync(resolve(ANN_DIR, fresh[0]), 'utf8'))
    expect(saved.schema).toBe('chart_workflow.annotations/2')
    expect(saved.list_kind).toBe('bigmoves')
    expect(saved.outcome_visible).toBe(true)
    const a = saved.annotations[0]
    expect(a.item_id).toBe(ITEM_B)
    expect(a.range_start).toBeNull()
    expect(a.buy_points).toHaveLength(2)
    expect(a.buy_points.filter((x: any) => x.primary)).toHaveLength(1)
    expect(a.buy_points[0].primary).toBe(true)
    expect(a.buy_points.every((x: any) => x.date >= '2025-04-01' && x.date <= '2025-08-27')).toBe(true)
    // 露出结果后又 Shift 加了一个买点:记下第一次的买点,标「看过结果后改过」
    expect(a.first_buy_points).toEqual([a.buy_points[0]])
    expect(a.changed_after_reveal).toBe(true)
  } finally {
    rmSync(V2_PATH, { force: true })
  }
})
