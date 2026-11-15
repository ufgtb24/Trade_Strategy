// designer：读真页面显示栏 / 选中卡的文字（selInfo），供样张照抄。只读。
const { chromium } = require('@playwright/test')
const fs = require('fs'); const path = require('path')
const S = (body) => `(() => { const P = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s; const v = P.get('view'); ${body} })()`
;(async () => {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1200 } })
  await ctx.addInitScript(() => { try { localStorage.setItem('path2_web_ui.annotation.current_pattern.v1', JSON.stringify('new_step')) } catch {} })
  const page = await ctx.newPage()
  await page.goto('http://localhost:5171/', { waitUntil: 'networkidle' }); await page.waitForTimeout(1200)
  await page.evaluate(S(`v.openSymbol('CRNC', { start: '2024-10-28', end: '2024-12-31' })`)); await page.waitForTimeout(2500)
  await page.evaluate(S(`P.get('appLink').setMode('compare')`)); await page.waitForTimeout(5000)
  const scenes = {
    s1: `v.focusMark(['today_795#0'])`,
    s2: `v.setPath([{kind:'hit_family',familyKey:'hits@774'},{kind:'buy',day:795}])`,
    s3: `v.focusMark(['step_789_790#0'])`,
    s4: `v.focusHit('new_step@774-795#plateau:plateau_774_795#0', {day: 795})`,
    s5: `P.get('compare').focusSample('s-pc-44')`,
    s6: `v.focusMark(['step_789_790#0']); v.stepPos(1)`,
    s7: `v.clickFamilyLine('hits@774')`,
    s8: `v.selectNode('step')`,
    s9: `v.focusMark(['old_plat_774_788#0'])`,
    s10: `v.focusMark(['plateau_774_795#0'])`,
    s11: `P.get('compare').focusSample('s-pc-44'); v.stepStack(1)`,
  }
  const out = {}
  for (const [k, js] of Object.entries(scenes)) {
    await page.evaluate(S(`v.clearFocus(); ${js}`)); await page.waitForTimeout(500)
    out[k] = await page.evaluate(S(`const i = v.selInfo; return { path: v.selPath, kind: i?.kind, node: i?.node, date: i?.date, name: i?.name, diff: i?.diff, in: i?.in, day: i?.day, stack: i?.stack, buys: i?.buys, hits: i?.hits, nodes: i?.nodes, copy: i?.copyTail, cur: v.currentDay }`))
  }
  fs.writeFileSync(path.join(__dirname, 'designer_bars.json'), JSON.stringify(out, null, 1))
  for (const [k, o] of Object.entries(out)) console.log(k, JSON.stringify({ kind: o.kind, node: o.node, date: o.date, diff: o.diff, in: o.in, day: o.day, stack: o.stack, buys: o.buys, hits: o.hits?.head, copy: o.copy }))
  await browser.close()
})()
