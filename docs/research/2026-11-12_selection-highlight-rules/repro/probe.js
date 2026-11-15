// 现状矩阵探针（研究用，一次性）：在真页面上逐个设选中状态，读 store 派生值、副图各系列数据、显示栏、选中卡，
// 并按需截副图。只调用点击处理函数实际调用的那几个 store 动作；不画框、不按 Enter、不存任何东西。
// 用法：playwright MCP 的 browser_run_code_unsafe，filename 指向本文件。结果留在 window.__invMatrix（再用 browser_evaluate 存成 repro/matrix.json），截图写 repro/screenshots/。
// 跑完恢复：选中路径、当前日、视窗、标注侧栏页签、反馈选中。
async (page) => {
  const OUT = '/home/yu/PycharmProjects/Trade_Strategy/docs/research/2026-11-12_selection-highlight-rules/repro'
  const SHOT = true
  const ZOOM = [770, 816]   // 截图时的视窗（K 线下标）：2024-10 底到 2024-12 中，new_step 那几族都在里面

  // 每个状态：label、做法（在页面里执行的一段 JS，拿得到 v / c / fb / a）
  const STATES = [
    ['01 hit_family hits@774', `v.setPath([{kind:'hit_family',familyKey:'hits@774'}])`],
    ['02 buy x2 (12-02)', `v.clickBuyDay('hits@774', 795)`],
    ['03 buy x1 (hits@741 11-05)', `v.clickBuyDay('hits@741', 760)`],
    ['04 hit (774-795#0, via hits list / ↓)', `v.focusHit('new_step@774-795#plateau:plateau_774_795#0', {day:795})`],
    ['05 event today 12-02 (point, in hit)', `v.focusMark(['today_795#0'])`],
    ['06 event plateau 10-31→12-02 #0 (container, in hit)', `v.focusMark(['plateau_774_795#0'])`],
    ['07 event step 11-21→11-22 (sub-seg, shared by 39 plateaus)', `v.focusMark(['step_789_790#0'])`],
    ['08 event new_plat 10-08→12-02 (qualified, not in hit)', `v.focusMark(['new_plat_757_795#0'])`],
    ['09 event step › buy 12-02 (x2)', `v.setPath([{kind:'node',band:'step'},{kind:'event',instanceId:'step_789_790#0'},{kind:'buy',day:795}])`],
    ['10 event step › buy 12-02 › hit #1', `v.setPath([{kind:'node',band:'step'},{kind:'event',instanceId:'step_789_790#0'},{kind:'buy',day:795},{kind:'hit',hitId:'new_step@774-795#plateau:plateau_774_795#1',day:795}])`],
    ['11 node step', `v.selectNode('step')`],
    ['12 feedback f-pc-74', `v.clickFeedback({id:'f-pc-74'})`],
    ['13 feedback › first buy', `(() => { const p=[{kind:'feedback',id:'f-pc-74'}]; const b=v.world.inside(p,'day')[0]; v.setPath(b ? [...p, b.sel] : p) })()`],
    ['14 sample s-pc-44 (focus only, 11-29)', `c.focusSample('s-pc-44', {reset:true})`],
    ['15 sample s-pc-44 › first hit (↓)', `(() => { const p=[{kind:'sample',sampleId:'s-pc-44'}]; const m=v.world.inside(p,'stack')[0]; v.setPath(m ? [...p, m.sel] : p) })()`],
    ['16 sample s-pc-44 › event not in hit (diagnose card)', `v.setPath([{kind:'sample',sampleId:'s-pc-44'},{kind:'event',instanceId:'new_plat_757_794#0'}]); v.setCurrentDay(794)`],
    ['17 box b-pc-43 (click)', `a.selectBox('b-pc-43'); c.focusBox('b-pc-43', {reset:true})`],
    ['18 box b-pc-43 › first hit (↓)', `(() => { const p=[{kind:'box',boxId:'b-pc-43'}]; const m=v.world.inside(p,'stack')[0]; v.setPath(m ? [...p, m.sel] : p) })()`],
  ]

  // 页面里的读数函数（每个状态调一次）
  const READ = async () => {
    const pin = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia
    const v = pin._s.get('view'), fb = pin._s.get('feedback'), a = pin._s.get('annotation'), c = pin._s.get('compare')
    const ec = window.__invEc
    const sub = ec.getInstanceByDom(document.querySelector('.sub-inner'))
    const so = sub.getOption()
    const ser = (n) => so.series.find((s) => s.name === n)?.data ?? []
    const d = v.barDates
    const byId = new Map(v.effectiveAnalysis.events.map((e) => [e.instance_id, e]))
    const ev = (id) => { const e = byId.get(id); return e ? `${e.node_id} ${d[e.start_idx]}→${d[e.end_idx]} ${v.eventTier(e)} [${id}]` : `? [${id}]` }
    const hitTxt = (id) => id.replace('new_step@', '').replace('#plateau:plateau_', ' ')
    const set = (s) => [...(s ?? [])]
    const day = v.currentDay
    // 副图的高亮层：每条 = 画法(kind) + 形状(shape) + 哪个 event
    const hl = ser('highlight').map((h) => `${h.kind}/${h.shape} ${ev(h.instance_id)}`)
    // hits 行：选中那一格的框（粗 = 选中且没有 event 焦点）、被牵出的细框
    const selHit = v.selectedHitId
    const focusOnBracket = !!selHit && !v.focusedInstanceRef
    const cand = new Set(v.candidateHitIds)
    const br = ser('brackets')
    const bracketBoxes = []
    for (const b of br) {
      if (b.kind !== 'mark') continue
      const ids = b.hit_ids ?? [b.hit_id]
      if (selHit && ids.includes(selHit)) bracketBoxes.push(`selected-cell ${focusOnBracket ? 'thick2.5+shadow' : 'thin1.5+shadow'} @${d[b.value[0]]} (+ span box from ${d[b.family_start]})`)
      else if (ids.some((id) => cand.has(id))) bracketBoxes.push(`candidate-cell thin1.5 @${d[b.value[0]]}`)
    }
    const activeLine = ser('bracket-lines').filter((x) => x.active).map((x) => x.family_key)
    const bandActive = ser('family-lines').filter((x) => x.active).map((x) => x.family_key)
    // 当前日那一列上有哪些记号，哪些带框
    const hlIds = new Map()
    for (const h of ser('highlight')) hlIds.set(h.instance_id, `${hlIds.get(h.instance_id) ? hlIds.get(h.instance_id) + '+' : ''}${h.kind}/${h.shape}`)
    const col = []
    if (day !== null) {
      for (const x of [...ser('intervals'), ...ser('points')]) {
        const end = x.value[1], start = x.value[0]
        if (end === day || (start <= day && end >= day && x.mark_kind === 'bar')) {
          const ids = x.member_ids ?? [x.instance_id]
          const boxed = ids.map((id) => hlIds.get(id)).filter(Boolean)
          col.push(`${byId.get(ids[0])?.node_id} lane${x.value[2]} ${x.mark_kind} members=${ids.length}${boxed.length ? ' BOXED:' + boxed.join(',') : ''}`)
        }
      }
      for (const b of br) {
        if (b.value[0] === day || b.value[1] === day) {
          const ids = b.hit_ids ?? [b.hit_id]
          const boxed = selHit && ids.includes(selHit) ? 'SELECTED' : ids.some((id) => cand.has(id)) ? 'CANDIDATE' : ''
          col.push(`hits ${b.kind}${b.kind === 'mark' ? '/' + b.mark_kind : ''} ${b.family_key} hits=${ids.length}${boxed ? ' BOXED:' + boxed : ''}${b.kind === 'buy' ? ' (▼ never boxed)' : ''}`)
        }
      }
    }
    // 显示栏、选中卡、diagnose 里描边的那块、反馈竖带
    const txt = (sel) => [...document.querySelectorAll(sel)].map((e) => e.innerText.replace(/\s+/g, ' ').trim())
    const walk = txt('[data-testid="walk-bar"] .cell')
    const card = txt('[data-testid="sel-card"] .row')
    const diagCur = txt('[data-testid="diagnose-row"].cur')
    const fbBand = !!document.querySelector('[data-testid="feedback-selected-band"]')
    const markedHits = set(v.markedHitIds).length
    return {
      path: JSON.parse(JSON.stringify(v.selPath)),
      currentDay: day !== null ? d[day] : null,
      store: {
        focusedHitId: v.focusedHitId && hitTxt(v.focusedHitId),
        selectedInstanceId: v.selectedInstanceId, focusedInstanceId: v.focusedInstanceId,
        pendingDisambig: v.pendingDisambigInstanceId,
        highlightedEventIds: set(v.highlightedEventIds).map(ev),
        compositionGroupIds: set(v.compositionGroupIds).map(ev),
        candidateHitIds: set(v.candidateHitIds).map(hitTxt),
        selDayHitIds: (v.selDayHitIds ?? []).map(hitTxt),
        activeFamilyKey: v.activeFamilyKey, markedHitCount: markedHits,
        markedEventIds: set(v.markedEventIds),
        fbSelected: fb.selectedId, annSelSample: a.selectedSampleId, annSelBox: a.selectedBoxId,
        cmpFocusedSample: c.focusedSampleId, tab: a.tab,
      },
      chart: { highlight: hl, bracketBoxes, activeHitsFamilyLine: activeLine, activeBandFamilyLine: bandActive,
               cursor: ser('current-day').map((x) => d[x.value[0]]), feedbackSelectedBand: fbBand },
      column: col,
      walk, card, diagCur,
    }
  }

  // 准备：拿到 echarts 模块；记下初始状态
  await page.evaluate(async () => {
    const u = performance.getEntriesByType('resource').map((e) => e.name).find((n) => /deps\/echarts\.js/.test(n))
    window.__invEc = await import(u)
    const pin = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia
    const v = pin._s.get('view'), a = pin._s.get('annotation'), fb = pin._s.get('feedback')
    const main = window.__invEc.getInstanceByDom(document.querySelector('.main-chart'))
    const dz = main.getOption().dataZoom[0]
    window.__invInit = { path: JSON.parse(JSON.stringify(v.selPath)), day: v.currentDay, tab: a.tab,
                         selBox: a.selectedBoxId, fb: fb.selectedId, dz: [dz.startValue, dz.endValue] }
  })
  const setZoom = (sv, evv) => page.evaluate(([sv, evv]) => {
    const main = window.__invEc.getInstanceByDom(document.querySelector('.main-chart'))
    main.dispatchAction({ type: 'dataZoom', startValue: sv, endValue: evv })
  }, [sv, evv])

  // 补拍：页面上若有 window.__invCfg = { states: [[label, code, zoom?]...]，zoom 可为 [sv, ev] 或 'init'（用户原来的视窗）, zoom: [sv, ev] | null }，就只跑这些（截图名取 label 前 3 个字符）
  const cfg = await page.evaluate(() => window.__invCfg ?? null)
  if (cfg) { STATES.length = 0; STATES.push(...cfg.states); if (cfg.zoom === null) ZOOM.length = 0; else if (cfg.zoom) ZOOM.splice(0, 2, ...cfg.zoom) }
  const results = []
  if (SHOT && ZOOM.length) { await setZoom(ZOOM[0], ZOOM[1]); await page.waitForTimeout(600) }
  for (const [label, code, zoom] of STATES) {
    if (zoom === 'init') { await page.evaluate(() => { const z = window.__invInit.dz; window.__invEc.getInstanceByDom(document.querySelector('.main-chart')).dispatchAction({ type: 'dataZoom', startValue: z[0], endValue: z[1] }) }); await page.waitForTimeout(500) }
    else if (zoom) { await setZoom(zoom[0], zoom[1]); await page.waitForTimeout(500) }
    await page.evaluate((code) => {
      const pin = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia
      const v = pin._s.get('view'), c = pin._s.get('compare'), fb = pin._s.get('feedback'), a = pin._s.get('annotation')
      // eslint-disable-next-line no-eval
      eval(code)
    }, code)
    await page.waitForTimeout(700)
    const r = await page.evaluate(READ)
    r.label = label
    if (SHOT) {
      const f = `${OUT}/screenshots/${label.slice(0, cfg ? 3 : 2).trim()}.jpeg`
      await page.locator('.sub-outer').screenshot({ path: f, type: 'jpeg', quality: 70, scale: 'device' })
      r.shot = f.replace(OUT + '/', '')
    }
    results.push(r)
  }

  // 恢复
  await page.evaluate(() => {
    const pin = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia
    const v = pin._s.get('view'), a = pin._s.get('annotation'), fb = pin._s.get('feedback'), c = pin._s.get('compare')
    const i = window.__invInit
    a.selectBox(i.selBox)
    c.clearSampleFocus()
    v.setPath(i.path)
    if (i.day !== null) v.setCurrentDay(i.day)
    a.tab = i.tab
    fb.select(i.fb)
  })
  await page.waitForTimeout(300)
  await page.evaluate((dz) => {
    const main = window.__invEc.getInstanceByDom(document.querySelector('.main-chart'))
    main.dispatchAction({ type: 'dataZoom', startValue: dz[0], endValue: dz[1] })
  }, await page.evaluate(() => window.__invInit.dz))

  // 运行环境里没有 fs：结果留在页面的 window.__invMatrix，由 browser_evaluate 的 filename 存成 repro/matrix.json
  await page.evaluate((r) => { window.__invMatrix = r; window.__invCfg = null }, results)
  return results.map((r) => `${r.label}: hl=${r.chart.highlight.length} br=${r.chart.bracketBoxes.length} col=${r.column.length}`).join('\n')
}
