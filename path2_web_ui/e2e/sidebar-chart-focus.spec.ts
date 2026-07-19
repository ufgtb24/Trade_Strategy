import { test, expect, type Page } from '@playwright/test'
import { baseURL } from './ports'

// e2e:sidebar-chart-focus 5 场景端到端(spec docs/superpowers/specs/2026-07-09-
// sidebar-chart-focus-unification-design.md §3.2 六种交互一致性表 + §6.3 五场景)。
//
// 前提:后端 + 前端 dev server 在线(playwright.config.ts 的 webServer 自动启动前端;
//       后端须外部启动 uv run python -m path2_web.main)。
//
// fixture:复用既有 marker-click-focus-highlight.spec.ts / subchart-band-zoom.spec.ts /
// subchart-tooltip-crosshair.spec.ts 的 golden ticker BTMWW · bottom_burst。不写死具体
// scan_ts(那几个旧 spec 写死的 2026-06-30 17:52:56 已不在 outputs/path2_web/scans/ 下,
// 历史文件会随时间滚动),改为「打开历史 → 首行(list_scans_flat 按 scan_ts 倒序 = 最新一次
// 扫描)」。
//
// 归属发现:不写死具体 event_id。用 src/render/visible.ts::matchedIds 的算法原样在浏览器端
// 复刻(matchedIdsJs),对 window.__e2e.view.effectiveAnalysis 实时计算「event_id → 归属
// match_id 列表」,动态挑一个多归属(len>=2)与一个非孤立角色的单归属(len===1)event。
// 已用 Python 对当前两份 outputs/path2_web/scans/*.json(4825 symbol × 2 pattern)做穷举
// 验证:BTMWW 的 bo_162/bo_163 因 burst 前缀族(burst_162_163 ⊂ burst_162_164)天然多归属
// ——且这是当前 dag_spec 下唯一可能真实多归属的角色(bo,因为 tb/burst 在各自 match 里都是
// 1:1 使用)。bo 同时是孤立流源角色(isolatedNodeIds,zero-edge),DetailSidebar 候选表按
// 既有设计(spec §3.4a `!isolated.has(node.node_id)` 闸,非本 spec 范围)永不为孤立角色渲染
// ——故场景 3「候选表 pending 行黄底」改用等价的 markedEventIds 派生态断言(驱动
// `.attr-row--selected` 的判据本身),而非该 DOM 节点(结构性不存在,非 bug)。
//
// 场景 5「detected event」:已用 curl /diagnose 核实 bottom_burst 的 tb/bo 两角色
// where_rules 为空、任何候选行的 clauses={} 按 isQualifiedRow(Object.values({}).every(...)
// 空数组恒 true)天然落 qualified 档,故「detected-only」在该 pattern 下不可达;转而找
// 「非 matched(可能是 qualified)」候选行(tb_163 = qualified 但未进 match),与任务书
// skeleton 自身 `/detected|qualified/` 的宽松断言一致,只是这里精确断言到 'qualified'。

const SYMBOL = 'BTMWW'
const PATTERN = 'bottom_burst'
const LS_KEY_BAND_ZOOM = 'kline-band-zoom-v1'
const HL_FOCUS_EDGE = '#1e293b'

// ─── 场景无关的 setup / 几何 / 发现 helper ──────────────────────────────────────

async function ensureScanLoaded(page: Page): Promise<void> {
  await page.goto(baseURL + '/')
  await page.evaluate((key) => { try { localStorage.removeItem(key) } catch { /* noop */ } }, LS_KEY_BAND_ZOOM)
  await page.reload()

  const openHistBtn = page.getByRole('button', { name: /打开历史/ })
  await expect(openHistBtn).toBeVisible({ timeout: 15_000 })
  await openHistBtn.click()
  await expect(page.locator('.backdrop')).toBeVisible({ timeout: 5_000 })
  await expect(page.locator('.state')).not.toContainText('Loading', { timeout: 5_000 }).catch(() => {})

  const hasRows = (await page.locator('.file-list tbody tr').count()) > 0
  if (!hasRows) {
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible()

    await page.getByRole('button', { name: /扫描 ⚙/ }).click()
    await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
    await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()

    const scanBtn = page.getByRole('button', { name: /开始扫描/ })
    await expect(scanBtn).toBeEnabled({ timeout: 10_000 })
    await scanBtn.click()
    await expect(page.locator('.done')).toBeVisible({ timeout: 240_000 })

    await openHistBtn.click()
    await expect(page.locator('.backdrop')).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('.file-list')).toBeVisible({ timeout: 5_000 })
  }

  // 最新一次扫描排首行(scan.py::list_scans_flat 按 scan_ts 倒序)
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('.backdrop')).not.toBeVisible()
}

async function setupChart(page: Page): Promise<void> {
  await ensureScanLoaded(page)
  await page.waitForFunction(() => !!(window as any).__e2e?.view, { timeout: 10_000 })

  // DetailSidebar 面板默认隐藏(panels store 首次访问全隐,spec 2026-07-03-subchart-boundary-model
  // §1),5 场景全依赖右侧诊断侧栏可见,需先开面板开关。
  const sidebarToggle = page.locator('[data-testid="panel-toggle-sidebar"]')
  if (!(await sidebarToggle.evaluate((el) => el.classList.contains('active')))) {
    await sidebarToggle.click()
  }
  await expect(page.locator('.sidebar')).toBeVisible({ timeout: 5_000 })

  // 切 active pattern → bottom_burst(轮询等选项就绪 + 切换生效,消除加载竞态)
  await page.waitForFunction((pid) => {
    const sel = document.querySelector('select[data-role="active-pattern"]') as HTMLSelectElement | null
    return !!sel && Array.from(sel.options).some((o) => o.value === pid)
  }, PATTERN)
  await page.evaluate((pid) => {
    const sel = document.querySelector('select[data-role="active-pattern"]') as HTMLSelectElement
    sel.value = pid
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  }, PATTERN)
  await page.waitForFunction(
    (pid) => (document.querySelector('select[data-role="active-pattern"]') as HTMLSelectElement | null)?.value === pid,
    PATTERN,
  )

  // 选股:直接调 view.selectSymbol,绕开 sidebar 虚拟滚动
  await page.evaluate((sym) => { (window as any).__e2e?.view?.selectSymbol(sym) }, SYMBOL)

  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && typeof e.chartMain === 'function' && typeof e.chartSub === 'function' && e.chartMain() && e.chartSub())
  }, { timeout: 15_000 })
  // BTMWW/bottom_burst 已知 2 条 match(多归属发现的前提)
  await page.waitForFunction(
    () => ((window as any).__e2e?.view?.effectiveAnalysis?.matches?.length ?? 0) >= 2,
    { timeout: 15_000 },
  )
  await page.waitForTimeout(300)
}

/** 以某 bar index 为中心 zoom 主图(联动副图,既有 marker-click-focus-highlight.spec.ts 手法)。 */
async function zoomAroundBar(page: Page, centerIdx: number, halfWindowPct = 3): Promise<void> {
  await page.evaluate(({ centerIdx, halfWindowPct }) => {
    const main = (window as any).__e2e.chartMain()
    const n = (main.getOption().xAxis?.[0]?.data || []).length
    const c = (centerIdx / n) * 100
    main.dispatchAction({ type: 'dataZoom', start: Math.max(0, c - halfWindowPct), end: Math.min(100, c + halfWindowPct) })
  }, { centerIdx, halfWindowPct })
  await page.waitForTimeout(300)
}

type Attribution = {
  multi: { eventId: string; matchIds: string[] } | null
  unique: { eventId: string; matchId: string } | null
}

/** 在浏览器端复刻 src/render/visible.ts::matchedIds 算法,对当前 symbol/pattern 的
 *  effectiveAnalysis 实时计算「event_id → 归属 match_id 列表」,挑一个多归属 + 一个
 *  非孤立角色的单归属 event(单归属候选排除孤立角色,理由见文件头注释)。 */
async function discoverAttribution(page: Page): Promise<Attribution> {
  return page.evaluate(() => {
    function matchedIdsJs(matches: any[], events: any[], edges: any[]): Set<string> {
      const s = new Set<string>()
      for (const m of matches) for (const c of m.children) s.add(c)
      if (events.length === 0 || s.size === 0) return s
      const byId = new Map(events.map((e: any) => [e.event_id, e]))
      const anchorFields = new Set<string>()
      for (const e of edges) if (e.anchor_field) anchorFields.add(e.anchor_field)
      const queue: string[] = [...s]
      while (queue.length) {
        const id = queue.pop()!
        const ev: any = byId.get(id)
        if (!ev) continue
        const refs = ev.child_refs
        if (refs) {
          for (const ids of Object.values(refs) as string[][]) {
            for (const cid of ids) if (!s.has(cid)) { s.add(cid); queue.push(cid) }
          }
        }
        for (const af of anchorFields) {
          const v = ev[af]
          if (typeof v === 'string' && !s.has(v)) { s.add(v); queue.push(v) }
        }
      }
      return s
    }

    const view = (window as any).__e2e.view
    const matches = view.effectiveAnalysis.matches
    const events = view.effectiveAnalysis.events
    const topology = view.effectivePattern.topology
    const edges = topology.edges

    // isolatedNodeIds 复刻(src/render/visible.ts):零边角色的候选表按既有设计永不渲染
    const inEdge = new Set<string>()
    for (const e of edges) { inEdge.add(e.src); inEdge.add(e.dst) }
    const isolatedTags = new Set<string>(
      topology.nodes.filter((n: any) => !inEdge.has(n.node_id)).map((n: any) => n.source_tag),
    )

    const eventsById = new Map(events.map((e: any) => [e.event_id, e]))
    const owner = new Map<string, string[]>()
    for (const m of matches) {
      for (const eid of matchedIdsJs([m], events, edges)) {
        if (!owner.has(eid)) owner.set(eid, [])
        owner.get(eid)!.push(m.event_id)
      }
    }

    let multi: { eventId: string; matchIds: string[] } | null = null
    for (const [eid, mids] of owner) {
      if (mids.length >= 2) { multi = { eventId: eid, matchIds: mids }; break }
    }

    let unique: { eventId: string; matchId: string } | null = null
    for (const [eid, mids] of owner) {
      if (mids.length !== 1) continue
      const ev: any = eventsById.get(eid)
      if (ev && !isolatedTags.has(ev.source_tag)) { unique = { eventId: eid, matchId: mids[0] }; break }
    }

    return { multi, unique }
  })
}

type PixelPos = { clientX: number; clientY: number } | null

/** 定位任意 event 的可点击像素坐标:price-points(主图,如 bo)按
 *  makeRenderPricePoint 的锚点+像素堆叠偏移公式;points/intervals(副图,如 tb/burst)
 *  按 renderPointWithGeom/renderIntervalWithGeom 的 band 居中/lane 堆叠公式,band 的
 *  top/height 从 option.graphic 里对应的 zebra rect(z===1)反查(与
 *  marker-click-focus-highlight.spec.ts 同手法)。 */
async function locateEventPixel(page: Page, eventId: string): Promise<PixelPos> {
  return page.evaluate((eid) => {
    const win = window as any
    const main = win.__e2e.chartMain()
    const sub = win.__e2e.chartSub()
    const mainCanvas = document.querySelector('.main-chart canvas') as HTMLElement | null
    const subCanvas = document.querySelector('.sub-inner canvas') as HTMLElement | null
    if (!mainCanvas || !subCanvas) return null

    // price-points(主图,render_grid='price',如 bo):src/render/chart.ts::makeRenderPricePoint
    // BO_STACK_PT=48(有 pk)/ BO_STACK_PT_NO_PKS=15(无 pk),锚点上方像素堆叠偏移。
    const pp = main.getOption().series.find((s: any) => s.name === 'price-points')
    const ppItem = pp?.data?.find((d: any) => d.event_id === eid)
    if (ppItem) {
      const rect = mainCanvas.getBoundingClientRect()
      const [cx, anchorPx] = main.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [ppItem.value[0], ppItem.anchorY])
      const stackOffset = ppItem.hasPks ? 48 : 15
      return { clientX: rect.left + cx, clientY: rect.top + anchorPx - stackOffset }
    }

    const graphicArr = sub.getOption().graphic
    const els = Array.isArray(graphicArr) ? (graphicArr[0]?.elements ?? graphicArr) : (graphicArr?.elements ?? [])
    const zebra = els.filter((e: any) => e.type === 'rect' && e.z === 1)

    // points(副图,render_grid='time' 单点,如 tb):renderPointWithGeom centerY = g.top+g.h/2
    const pointsIdx = sub.getOption().series.findIndex((s: any) => s.name === 'points')
    const ptItem = pointsIdx >= 0 ? sub.getOption().series[pointsIdx].data.find((d: any) => d.event_id === eid) : null
    if (ptItem) {
      const rect = subCanvas.getBoundingClientRect()
      const zb = zebra[ptItem.value[2]]
      if (!zb) return null
      const px = sub.convertToPixel({ seriesIndex: pointsIdx }, [ptItem.value[0], 0])
      return { clientX: rect.left + px[0], clientY: rect.top + zb.top + zb.shape.height / 2 }
    }

    // intervals(副图,render_grid='time' 跨 bar,如 burst):renderIntervalWithGeom lane 堆叠
    const intervalsIdx = sub.getOption().series.findIndex((s: any) => s.name === 'intervals')
    const ivItem = intervalsIdx >= 0 ? sub.getOption().series[intervalsIdx].data.find((d: any) => d.event_id === eid) : null
    if (ivItem) {
      const rect = subCanvas.getBoundingClientRect()
      const zb = zebra[ivItem.value[3]]
      if (!zb) return null
      const lane = ivItem.value[2]
      const laneH = 7, gap = 2, topPad = 4, botPad = 4   // BAND_MARKER_H/BAND_LANE_GAP/BAND_TOP_PAD/BAND_BOT_PAD,zoomFactor 默认 1.0
      const rawY = zb.top + topPad + lane * (laneH + gap)
      const y = Math.max(zb.top + topPad, Math.min(rawY, zb.top + zb.shape.height - botPad - laneH))
      const px0 = sub.convertToPixel({ seriesIndex: intervalsIdx }, [ivItem.value[0], 0])
      const px1 = sub.convertToPixel({ seriesIndex: intervalsIdx }, [ivItem.value[1], 0])
      return { clientX: rect.left + (px0[0] + px1[0]) / 2, clientY: rect.top + y + laneH / 2 }
    }

    return null
  }, eventId)
}

/** 定位 bracket 可点击像素坐标:src/render/chart.ts::makeRenderBracket
 *  top = BAND_TOP_PAD + lane*BAND_LANE_H*zoomFactor(默认 1.0),bracket 区独立坐标(canvas
 *  局部 y=0 起,非挂某 band),故直接用常量算,不查 zebra。 */
async function locateBracketPixel(page: Page, matchId: string): Promise<PixelPos> {
  return page.evaluate((mid) => {
    const win = window as any
    const sub = win.__e2e.chartSub()
    const subCanvas = document.querySelector('.sub-inner canvas') as HTMLElement | null
    if (!subCanvas) return null
    const idx = sub.getOption().series.findIndex((s: any) => s.name === 'brackets')
    const s = sub.getOption().series[idx]
    const d = s?.data?.find((x: any) => x.match_id === mid)
    if (!d) return null
    const rect = subCanvas.getBoundingClientRect()
    const px0 = sub.convertToPixel({ seriesIndex: idx }, [d.value[0], 0])
    const px1 = sub.convertToPixel({ seriesIndex: idx }, [d.value[1], 0])
    const lane = d.value[2] || 0
    const top = 4 + lane * 9   // BAND_TOP_PAD(4) + lane*BAND_LANE_H(9)*zoomFactor(默认 1.0)
    const innerY = top + 7 / 2   // BAND_MARKER_H(7)/2
    return { clientX: rect.left + (px0[0] + px1[0]) / 2, clientY: rect.top + innerY }
  }, matchId)
}

async function getFocusState(page: Page) {
  return page.evaluate(() => {
    const v = (window as any).__e2e.view
    return {
      focusedMatchId: v.focusedMatchId as string | null,
      focusedEventId: v.focusedEventId as string | null,
      showTrace: v.showTrace as boolean,
      markedMatchIds: Array.from(v.markedMatchIds) as string[],
      markedEventIds: Array.from(v.markedEventIds) as string[],
      candidateMatchIds: Array.from(v.candidateMatchIds) as string[],
      pendingDisambigEventId: v.pendingDisambigEventId as string | null,
      highlightedEventIds: Array.from(v.highlightedEventIds) as string[],
      level: v.level as string,
    }
  })
}

/** brackets series renderItem 探针(既有 marker-click-focus-highlight.spec.ts 手法):
 *  直接调真实挂载的 renderItem 拿渲染产物,验证选中态描边色/虚线等闭包烘焙的样式。 */
async function probeBracketStyle(page: Page, matchId: string) {
  return page.evaluate((mid) => {
    const sub = (window as any).__e2e.chartSub()
    const idx = sub.getOption().series.findIndex((x: any) => x.name === 'brackets')
    const s = sub.getOption().series[idx]
    const i = s.data.findIndex((d: any) => d.match_id === mid)
    if (i < 0) return null
    const d = s.data[i]
    const fakeApi = { value: (k: number) => d.value[k], coord: () => [100, 200], size: () => [10, 0] }
    const shape = s.renderItem({ dataIndex: i }, fakeApi)
    return shape?.children?.[0]?.style ?? null
  }, matchId)
}

// ─── 5 场景(spec §6.3) ─────────────────────────────────────────────────────

test('场景 1: bracket click → group 黑框亮 + bracket 深实边 + 命中匹配单行黄底 + trace 展开', async ({ page }) => {
  test.setTimeout(300_000)
  await setupChart(page)

  const matchIds: string[] = await page.evaluate(() =>
    ((window as any).__e2e.view.effectiveAnalysis.matches as any[]).map((m) => m.event_id))
  const targetMatchId = matchIds[0]

  const barIdx = await page.evaluate((mid) => {
    const m = ((window as any).__e2e.view.effectiveAnalysis.matches as any[]).find((x) => x.event_id === mid)
    return Math.floor((m.start_idx + m.end_idx) / 2)
  }, targetMatchId)
  await zoomAroundBar(page, barIdx)

  const pos = await locateBracketPixel(page, targetMatchId)
  expect(pos).not.toBeNull()
  await page.mouse.click(pos!.clientX, pos!.clientY)
  await page.waitForTimeout(500)

  const state = await getFocusState(page)
  expect(state.focusedMatchId).toBe(targetMatchId)
  expect(state.focusedEventId).toBeNull()
  expect(state.showTrace).toBe(true)
  expect(state.markedMatchIds).toEqual([targetMatchId])
  expect(state.highlightedEventIds.length).toBeGreaterThan(0)   // 视觉层:group 展开集非空

  await expect(page.locator('.match-trace')).toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(1)

  const style = await probeBracketStyle(page, targetMatchId)
  expect(style?.stroke).toBe(HL_FOCUS_EDGE)   // bracket 自身即被点者 → focus 深实边
})

test('场景 2: event marker 唯一归属 click → group 黑框 + focus 深边 + 命中匹配单行 + trace 不展', async ({ page }) => {
  test.setTimeout(300_000)
  await setupChart(page)

  const attribution = await discoverAttribution(page)
  expect(attribution.unique).not.toBeNull()
  const { eventId, matchId } = attribution.unique!

  const barIdx = await page.evaluate((eid) => {
    const ev = ((window as any).__e2e.view.effectiveAnalysis.events as any[]).find((e) => e.event_id === eid)
    return ev.start_idx
  }, eventId)
  await zoomAroundBar(page, barIdx)

  const pos = await locateEventPixel(page, eventId)
  expect(pos).not.toBeNull()
  await page.mouse.click(pos!.clientX, pos!.clientY)
  await page.waitForTimeout(500)

  const state = await getFocusState(page)
  expect(state.focusedEventId).toBe(eventId)
  expect(state.focusedMatchId).toBe(matchId)
  expect(state.showTrace).toBe(false)
  expect(state.markedMatchIds).toEqual([matchId])
  expect(state.markedEventIds).toEqual([eventId])
  expect(state.highlightedEventIds).toContain(eventId)

  await expect(page.locator('.match-trace')).not.toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(1)
  await expect(page.locator('.candidate-table-wrap')).toBeVisible()
  await expect(page.locator('.attr-row.attr-row--selected')).toHaveCount(1)

  // 视觉层:被点 event 本体 kind='focus'(sub chart highlight 系列,tb/burst 均落 render_grid=time)
  const kind = await page.evaluate((eid) => {
    const sub = (window as any).__e2e.chartSub()
    const s = sub.getOption().series.find((x: any) => x.name === 'highlight')
    return s?.data?.find((d: any) => d.event_id === eid)?.kind ?? null
  }, eventId)
  expect(kind).toBe('focus')
})

test('场景 3: event marker 多归属 click → 无 group + 候选虚线 + pending 闪烁 + 命中匹配多行同亮', async ({ page }) => {
  test.setTimeout(300_000)
  await setupChart(page)

  const attribution = await discoverAttribution(page)
  expect(attribution.multi).not.toBeNull()
  const { eventId, matchIds } = attribution.multi!
  expect(matchIds.length).toBeGreaterThanOrEqual(2)

  const barIdx = await page.evaluate((eid) => {
    const ev = ((window as any).__e2e.view.effectiveAnalysis.events as any[]).find((e) => e.event_id === eid)
    return ev.start_idx
  }, eventId)
  await zoomAroundBar(page, barIdx)

  const pos = await locateEventPixel(page, eventId)
  expect(pos).not.toBeNull()
  await page.mouse.click(pos!.clientX, pos!.clientY)
  await page.waitForTimeout(500)

  const state = await getFocusState(page)
  expect(state.focusedMatchId).toBeNull()
  expect(state.focusedEventId).toBeNull()
  expect(state.showTrace).toBe(false)
  expect(state.pendingDisambigEventId).toBe(eventId)
  expect(new Set(state.candidateMatchIds)).toEqual(new Set(matchIds))
  expect(new Set(state.markedMatchIds)).toEqual(new Set(matchIds))
  // markedEventIds 是「候选表 pending 行黄底」的判据本身(DetailSidebar.vue:
  // `.attr-row--selected` ← markedEventIds.has(row.event_id));bo 是孤立流源角色
  // (isolatedNodeIds,zero-edge),候选表按既有设计永不为孤立角色渲染,故此处断言派生态
  // 而非该 DOM 节点(结构性不存在,非 bug;详见文件头注释)。
  expect(state.markedEventIds).toEqual([eventId])
  expect(state.highlightedEventIds).toHaveLength(0)   // 视觉层:disambig 前不亮 group

  await expect(page.locator('.match-trace')).not.toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(matchIds.length)

  // 视觉层(主图 highlight-price 系列,bo 是 price-anchored):pending 项 kind='pendingDisambig'
  const kind = await page.evaluate((eid) => {
    const main = (window as any).__e2e.chartMain()
    const s = main.getOption().series.find((x: any) => x.name === 'highlight-price')
    return s?.data?.find((d: any) => d.event_id === eid)?.kind ?? null
  }, eventId)
  expect(kind).toBe('pendingDisambig')

  // candidate brackets 虚线琥珀:两条 match 的 bracket renderItem 都应落 isCandidate 分支
  for (const mid of matchIds) {
    const style = await probeBracketStyle(page, mid)
    expect(style?.lineDash).toEqual([4, 3])
    expect(style?.stroke).toBe('#f59e0b')
  }
})

test('场景 4: sidebar 命中匹配某行 click → 副图 bracket 反打 + trace 展开', async ({ page }) => {
  test.setTimeout(300_000)
  await setupChart(page)

  const matchIds: string[] = await page.evaluate(() =>
    ((window as any).__e2e.view.effectiveAnalysis.matches as any[]).map((m) => m.event_id))
  const targetIdx = matchIds.length > 1 ? 1 : 0
  const targetMatchId = matchIds[targetIdx]

  await page.locator('.match-row').nth(targetIdx).click()
  await page.waitForTimeout(500)

  const state = await getFocusState(page)
  expect(state.focusedMatchId).toBe(targetMatchId)
  expect(state.focusedEventId).toBeNull()
  expect(state.showTrace).toBe(true)

  await expect(page.locator('.match-trace')).toBeVisible()
  await expect(page.locator('.match-row.match-row--selected')).toHaveCount(1)

  // 反打副图 bracket:renderItem 闭包读取最新 selectedMatchId,focus 描边色应为 HL_FOCUS_EDGE
  const style = await probeBracketStyle(page, targetMatchId)
  expect(style?.stroke).toBe(HL_FOCUS_EDGE)
})

test('场景 5: sidebar 候选表非-matched event click + level=matched → level 自动降', async ({ page }) => {
  test.setTimeout(300_000)
  await setupChart(page)

  await page.locator('[data-testid="level-control"] .level-btn', { hasText: 'Matched' }).click()
  await expect(page.locator('[data-testid="level-control"] .level-btn.active:not(.panel-toggle)')).toHaveText('Matched')

  // 找一个非 matched 的候选行(tb/burst node,非孤立,候选表可展开)。
  // 注:bottom_burst 的 tb/bo where_rules 为空 → clauses={} 恒 isQualifiedRow=true,
  // 「detected-only」在该 pattern 下不可达,故只要求非 matched(可能落 qualified,与任务书
  // skeleton 自身 `/detected|qualified/` 宽松断言一致);expectedLevel 据 qualifiedIds 精确算出。
  const target = await page.evaluate(() => {
    const view = (window as any).__e2e.view
    const diag = view.diag
    const matchedIds = view.matchedIds as Set<string>
    const qualifiedIds = view.qualifiedIds as Set<string>
    for (const node of ['tb', 'burst']) {
      const rows = diag?.nodes?.[node]?.attr ?? []
      for (const row of rows) {
        if (!matchedIds.has(row.event_id)) {
          return {
            node,
            eventId: row.event_id as string,
            startIdx: row.start_idx as number,
            endIdx: row.end_idx as number,
            expectedLevel: qualifiedIds.has(row.event_id) ? 'qualified' : 'detected',
          }
        }
      }
    }
    return null
  })
  expect(target).not.toBeNull()

  await page.locator('.funnel-row', { hasText: target!.node }).first().click()
  await expect(page.locator('.candidate-table-wrap')).toBeVisible()

  await page.locator('.attr-row', { hasText: `seg@${target!.startIdx}-${target!.endIdx}` }).first().click()
  await page.waitForTimeout(500)

  const state = await getFocusState(page)
  expect(state.focusedEventId).toBe(target!.eventId)
  expect(state.level).toBe(target!.expectedLevel)

  const expectedLabel = target!.expectedLevel === 'detected' ? 'Detected' : 'Qualified'
  await expect(page.locator('[data-testid="level-control"] .level-btn.active:not(.panel-toggle)')).toHaveText(expectedLabel)

  // event 在图上可见并 focus 亮(level 已降,filter 放行该 tier)
  const kind = await page.evaluate((eid) => {
    const sub = (window as any).__e2e.chartSub()
    const s = sub.getOption().series.find((x: any) => x.name === 'highlight')
    return s?.data?.find((d: any) => d.event_id === eid)?.kind ?? null
  }, target!.eventId)
  expect(kind).toBe('focus')
})
