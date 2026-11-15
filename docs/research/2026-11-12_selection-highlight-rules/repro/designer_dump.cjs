// designer：从真页面（只读）导出 CRNC / new_step / compare 副图的几何与关系，供静态样张 mock.html 按真数据画。
// 运行：仓库根 NODE_PATH=path2_web_ui/node_modules node docs/research/2026-11-12_selection-highlight-rules/repro/designer_dump.cjs
const { chromium } = require('@playwright/test')
const fs = require('fs')
const path = require('path')
;(async () => {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1800, height: 1100 } })
  await ctx.addInitScript(() => { try { localStorage.setItem('path2_web_ui.annotation.current_pattern.v1', JSON.stringify('new_step')) } catch {} })
  const page = await ctx.newPage()
  await page.goto('http://localhost:5171/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.evaluate(() => {
    const P = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s
    P.get('view').openSymbol('CRNC', { start: '2024-10-28', end: '2024-12-31' })
  })
  await page.waitForTimeout(2500)
  await page.evaluate(() => document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('appLink').setMode('compare'))
  await page.waitForTimeout(5000)
  const data = await page.evaluate(async () => {
    const P = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s
    const v = P.get('view')
    const fold = await import('/src/render/fold.ts')
    const geo = await import('/src/render/geometry.ts')
    const walk = await import('/src/render/walk.ts')
    const an = v.effectiveAnalysis
    const pat = v.effectivePattern
    const events = an.events
    const hits = an.hits
    const byId = new Map(events.map(e => [e.instance_id, e]))
    const topo = pat.topology
    const bandsOrder = topo.nodes.map(n => n.node_id)
    const out = { dates: v.barDates, nodes: topo.nodes.map(n => ({ id: n.node_id, is_point: n.is_point, parent_refs: n.parent_refs, produced_by: n.produced_by })), endNode: v.endNode ?? null, bands: {}, hitFams: [], bound: {}, using: {}, tier: {} }
    for (const level of ['in_hit', 'qualified', 'detected']) {
      out.bands[level] = {}
      for (const band of bandsOrder) {
        const spec = topo.nodes.find(n => n.node_id === band)
        const evs = events.filter(e => v.bandKey(e) === band)
        const fams = fold.foldBand(evs, { band, isPoint: spec?.is_point === true, tierOf: v.eventTier, level, levelImmune: spec?.solve === false })
        const packed = geo.packLanes(fams.map(f => ({ ...f, start_idx: f.start, end_idx: f.end })))
        out.bands[level][band] = packed.map(f => ({ key: f.key, start: f.start, end: f.end, multi: f.multi, isPoint: f.isPoint, lane: f.lane, memberIds: f.memberIds, marks: f.marks }))
      }
    }
    const hf = fold.foldHits(hits, events, v.endNode)
    const hp = geo.packLanes(hf.map(f => ({ ...f, start_idx: f.start, end_idx: f.end })))
    out.hitFams = hp.map(f => ({ key: f.key, start: f.start, end: f.end, lane: f.lane, hitIds: f.hitIds, marks: f.marks, buys: f.buys }))
    for (const m of hits) out.bound[m.hit_id] = [...walk.boundEvents(m, byId)]
    const usingOf = walk.usingIndex(hits, events)
    for (const e of events) { out.using[e.instance_id] = usingOf(e.instance_id).map(m => m.hit_id); out.tier[e.instance_id] = v.eventTier(e) }
    out.events = events.map(e => ({ id: e.instance_id, node: e.node_id, s: e.start_idx, e: e.end_idx, child_refs: e.child_refs }))
    out.hits = hits.map(m => ({ id: m.hit_id, s: m.start_idx, e: m.end_idx }))
    out.nodeColors = pat.event_styles ?? null
    const cmp = P.get('compare')
    out.samples = JSON.parse(JSON.stringify(cmp.samples))
    const ch = P.get('annotation').state?.charts?.find(c => c.symbol === 'CRNC')
    out.boxesRaw = JSON.parse(JSON.stringify(ch?.boxes ?? []))
    out.feedbackRaw = JSON.parse(JSON.stringify(ch?.feedback ?? []))
    out.sampleDays = JSON.parse(JSON.stringify(cmp.sampleDays))
    out.sampleReads = [...cmp.sampleReads.entries()].map(([id, r]) => ({ id, pairedHitId: r.pairing?.hitId ?? null, match: r.match ?? null }))
    return out
  })
  fs.writeFileSync(path.join(__dirname, 'designer_data.json'), JSON.stringify(data))
  console.log('events', data.events.length, 'hits', data.hits.length, 'dates', data.dates.length, 'colors', JSON.stringify(data.nodeColors), 'samples', JSON.stringify(data.samples).slice(0, 400))
  await browser.close()
})()
