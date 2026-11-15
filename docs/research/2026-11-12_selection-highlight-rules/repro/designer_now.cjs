// designer：无头截真页面现状（只读：不按 Enter、不点 box/point、不写标注）。
// 当前 pattern 经 addInitScript 写进本无头浏览器自己的 localStorage（不走 setCurrentPattern，免得名字不存在时新建 pattern）。
// 运行：仓库根 NODE_PATH=path2_web_ui/node_modules node docs/research/2026-11-12_selection-highlight-rules/repro/designer_now.cjs
const { chromium } = require('@playwright/test')
const path = require('path')
const OUT = path.join(__dirname, 'screenshots')
const S = (body) => `(() => { const P = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s; const v = P.get('view'); ${body} })()`

;(async () => {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1780, height: 1500 }, deviceScaleFactor: 1.5 })
  await ctx.addInitScript(() => { try { localStorage.setItem('path2_web_ui.annotation.current_pattern.v1', JSON.stringify('new_step')) } catch {} })
  const page = await ctx.newPage()
  await page.goto('http://localhost:5171/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const cur = await page.evaluate(S(`return P.get('annotation').currentPattern`))
  if (cur !== 'new_step') throw new Error('current pattern not new_step: ' + cur)
  await page.evaluate(S(`v.openSymbol('CRNC', { start: '2024-10-28', end: '2025-01-31' })`))
  await page.waitForTimeout(2500)
  await page.evaluate(S(`P.get('appLink').setMode('compare')`))
  await page.waitForTimeout(5000)
  const scenes = [
    ['now_1_event_today_1202', `v.focusMark(['today_795#0'])`],
    ['now_2_buy_1202', `v.setPath([{kind:'hit_family',familyKey:'hits@774'},{kind:'buy',day:795}])`],
    ['now_3_event_step_1121_1122', `v.focusMark(['step_789_790#0'])`],
    ['now_4_hit_774_795_0', `v.focusHit('new_step@774-795#plateau:plateau_774_795#0', {day: 795})`],
    ['now_5_sample_a', `P.get('compare').focusSample('s-pc-44')`],
    ['now_6_event_step_then_buy', `v.focusMark(['step_789_790#0']); v.stepPos(1)`],
    ['now_7_sample_a_down_hit', `P.get('compare').focusSample('s-pc-44'); v.stepStack(1)`],
    ['now_8_hit_family', `v.clickFamilyLine('hits@774')`],
    ['now_9_node_step', `v.selectNode('step')`],
    ['now_10_feedback', `P.get('feedback').select('f-pc-74')`],
    ['now_11_box', `P.get('compare').focusBox && P.get('compare').focusBox('b-pc-43')`],
    ['now_12_hidden_event', `v.setPath([{kind:'sample',sampleId:'s-pc-44'},{kind:'event',instanceId:'plateau_741_794#0'}])`],
  ]
  for (const [name, js] of scenes) {
    await page.evaluate(S(`P.get('feedback').select(null); v.clearFocus(); ${js}`))
    await page.waitForTimeout(900)
    const st = await page.evaluate(S(`return JSON.stringify(v.selPath)`))
    console.log(name, st)
    const bar = await page.locator('.walk-bar, [class*=walk]').first().boundingBox().catch(() => null)
    const sub = await page.locator('.sub-outer').boundingBox()
    const top = bar ? Math.min(bar.y, sub.y) : sub.y
    await page.screenshot({ path: path.join(OUT, `designer_${name}.jpg`), type: 'jpeg', quality: 82,
      clip: { x: sub.x, y: top - 2, width: sub.width, height: sub.y + sub.height - top + 4 } })
  }
  await browser.close()
})()
