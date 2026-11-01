// 票 15「界面显示的对称与统一」落地后的核对：打开改过的各个状态截图（t15_shots/），并机械核对
// 1) pattern 页每个计数点开后，各排 pos / neg 之和等于汇总的分母，第一排等于分子；
// 2) 主图上的 tag 都带悬停，点在 tag 上照样选中它底下的框；
// 3) 题视图 q1、q2 与 features 区同一个点开的排头一致。
// 用法（仓库根）：node docs/research/2026-10-28_annotation-web-loop/repro/t15_check.mjs ；前提同 smoke.mjs（8792 端口已起）
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../../..')
const url = 'http://localhost:8792/2026-10-28_annotation-web-loop/repro/mock_v4.html'
const shots = join(here, 't15_shots'); mkdirSync(shots, { recursive: true })
const require = createRequire(join(repoRoot, 'path2_web_ui', 'package.json'))
const { chromium } = require('playwright')
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = [], fails = [], out = {}
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) })
page.on('pageerror', e => errs.push(e.message))
const fresh = async (hash = '') => { await page.goto('about:blank'); await page.goto(url + hash, { waitUntil: 'load' }); await page.waitForTimeout(300) }
const ev = (f, a) => page.evaluate(f, a)
async function snap(name, side = true) {
  await page.addStyleTag({ content: '#wrap{height:auto!important} #side{overflow:visible!important} #chartcol{overflow:visible!important}' })
  await page.screenshot({ path: join(shots, name + '.png'), fullPage: true })
  if (side) out[name] = await ev(() => document.getElementById('side').innerText)
}

// ── 1 pattern 页（有 app）：逐个点开计数，核对各排之和 ──
async function checkDoors(label) {
  const doors = await ev(() => [...document.querySelectorAll('#side button.vdoor[data-act]')].map(b => b.getAttribute('data-act')))
  for (const act of doors) {
    await ev(a => document.querySelector(`#side [data-act="${CSS.escape(a)}"]`).click(), act)
    await page.waitForTimeout(60)
    const r = await ev(a => {
      const d = document.querySelector(`#side [data-act="${CSS.escape(a)}"]`), txt = d.textContent.trim()
      const xp = a.startsWith('lkopen:') ? d.closest('.conn').nextElementSibling : document.querySelector('#side .vinline')   // 计数一次只开一个
      const heads = xp ? [...xp.querySelectorAll(':scope > .vstrip > .row:first-child')].map(e => e.firstElementChild.textContent.trim()) : null
      const cards = xp ? [...xp.querySelectorAll(':scope > .vstrip')].map(s => s.querySelectorAll('.vth').length) : null
      return { txt, heads, cards, pressed: d.getAttribute('aria-pressed') }
    }, act)
    const m = /pos (\d+)\/(\d+) · neg (\d+)\/(\d+)/.exec(r.txt)
    if (!r.heads || !r.heads.length) { fails.push(`${label} ${act}: 没有点开的排`); continue }
    if (m) {
      const rows = r.heads.map(h => /pos (\d+) · neg (\d+)/.exec(h)).map(x => x ? [+x[1], +x[2]] : null)
      if (rows.some(x => !x)) { fails.push(`${label} ${act}: 排头格式 ${JSON.stringify(r.heads)}`); continue }
      const sp = rows.reduce((t, x) => t + x[0], 0), sn = rows.reduce((t, x) => t + x[1], 0)
      if (sp !== +m[2] || sn !== +m[4]) fails.push(`${label} ${act}: 各排之和 pos ${sp} · neg ${sn} ≠ 分母 ${m[2]} / ${m[4]}`)
      if (rows[0][0] !== +m[1] || rows[0][1] !== +m[3]) fails.push(`${label} ${act}: 第一排 ${rows[0]} ≠ 分子 ${m[1]} / ${m[3]}`)
      r.heads.forEach((h, i) => { const x = rows[i]; if (r.cards[i] !== x[0] + x[1]) fails.push(`${label} ${act}: 「${h}」卡数 ${r.cards[i]}`) })
    } else {
      const n = +(/(\d+)\s*$/.exec(r.txt) || [])[1], c = r.cards[0]
      if (c !== n) fails.push(`${label} ${act}: 「${r.txt}」点开 ${c} 张卡`)
    }
    out[`${label} ${act}`] = { door: r.txt, rows: r.heads }
    await ev(a => document.querySelector(`#side [data-act="${CSS.escape(a)}"]`).click(), act)   // 收起
    await page.waitForTimeout(40)
  }
  return doors.length
}
await fresh(); await ev(() => { S.tab = 'pattern'; render() })
await snap('01_pattern_app')
const nd = await checkDoors('pattern_app')
for (const [k, n] of [['feat|横盘', '02_open_optional_in'], ['qual|横盘', '02b_open_optional_qualified'], ['qual|回踩', '03_open_qualified'], ['attr|放量突破|突破过好几个峰', '04_open_attr'], ['feat|派发', '05_open_must_not_in'], ['feat|缩量', '06_open_excluded'], ['jdg|neg', '07_open_header_neg'], ['match|pos|unmatched', '08_open_match_zero']]) {
  await fresh(); await ev(k => { S.tab = 'pattern'; S.vKey = k; render() }, k); await snap(n)
}
await fresh(); await ev(() => { S.tab = 'pattern'; S.lkOpen = '放量突破→回踩'; render() }); await snap('09_open_link')

// ── 2 题视图 ──
for (const q of ['q1', 'q2', 'q3', 'q4']) { await fresh('#q=' + q); await snap('10_' + q) }
await fresh('#q=q1'); const q1 = await ev(() => [...document.querySelectorAll('#side > .blk')[0].querySelectorAll('.vstrip .sym')].map(e => e.textContent))
await ev(() => { S.q = null; S.tab = 'pattern'; S.vKey = 'feat|长下跌'; render() })
const f1 = await ev(() => [...document.querySelectorAll('#side .vinline .vstrip .sym')].map(e => e.textContent))
if (JSON.stringify(q1) !== JSON.stringify(f1)) fails.push(`q1 与 features 区点开的排头不同：${JSON.stringify(q1)} / ${JSON.stringify(f1)}`)
out.q1_vs_features = { q1, f1 }

// ── 3 unsorted 页、没有 app 的 pattern（把 unsorted 和一个负样本挪进新 pattern P） ──
await fresh(); await ev(() => { S.cur = null; S.tab = 'pattern'; render() }); await snap('11_unsorted')
await checkDoors('unsorted')
await fresh(); await ev(() => { S.patterns.push('P'); for (const st of STOCKS) for (const s of annOf(st).samples) if (s.pattern === null || (s.judgment === 'neg' && s.idx === 229)) s.pattern = 'P'; S.cur = 'P'; S.tab = 'pattern'; render() })
await snap('12_pattern_noapp')
await checkDoors('noapp')

// ── 4 主图：compare 档 TVRD，三角下的 = 与 match、字母；selection 页样本页头的 tag；负样本的成员链 ──
await fresh(); await ev(() => { S.mode = 'compare'; const s = annOf(STOCKS[0]).samples.find(x => x.idx === 167); S.sel = { type: 'sample', id: s.id }; S.tab = 'selection'; render() })
await snap('13_compare_tvrd_pos')
await fresh(); await ev(() => { S.mode = 'compare'; const s = annOf(STOCKS[0]).samples.find(x => x.idx === 175); S.sel = { type: 'sample', id: s.id }; S.tab = 'selection'; render() })
await snap('14_compare_tvrd_neg')
out.neg_chain_links = await ev(() => [...document.querySelectorAll('#side .chain .arr .tag')].map(e => e.textContent))
if (!out.neg_chain_links.length) fails.push('负样本的成员链上没有两段之间的 tag')
const tips = await ev(() => [...document.querySelectorAll('#chart [data-tip]')].map(g => [g.textContent.replace(g.querySelector('title').textContent, '').trim(), g.querySelector('title').textContent]))
out.chart_tips = tips
if (!tips.some(([t]) => t === '=')) fails.push('主图三角下没有画 =')
// 点在 tag 上：照样选中它底下的框（tag 只接悬停）
const pass = await ev(() => {
  const res = []
  for (const g of document.querySelectorAll('#chart [data-tip]')) {
    const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2
    const below = document.elementsFromPoint(x, y).find(e => !e.closest('[data-tip]'))
    const id = below && below.getAttribute('data-box'); if (!id) continue
    g.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: x, clientY: y }))
    res.push(S.sel && S.sel.type === 'box' && S.sel.id === id)
    if (res.length >= 3) break
  }
  return res
})
out.tag_click_passthrough = pass
if (pass.some(x => !x)) fails.push('点在 tag 上没有选中底下的框')
// tiers 关掉：missing 仍在（造一个没有 app 事件的放量突破框）
await fresh(); await ev(() => { S.mode = 'compare'; S.stock = 1; const a = annOf(STOCKS[1]); a.boxes.push({ id: 'bx1', name: wid('放量突破'), s: 20, e: 24, attrs: {}, note: '' }); S.tiers = false; render() })
out.missing_with_tiers_off = await ev(() => [...document.querySelectorAll('#chart [data-tip]')].map(g => g.querySelector('title').textContent).filter(t => t === ST_TIP.missing).length)
if (!out.missing_with_tiers_off) fails.push('tiers 关掉后 missing 不见了')
await snap('15_tiers_off_missing')
// WHLRP 只有一个样本：也标字母 a
await fresh(); await ev(() => { S.stock = 1; const s = annOf(STOCKS[1]).samples[0]; S.sel = { type: 'sample', id: s.id }; S.tab = 'selection'; render() })
out.single_letter = await ev(() => document.querySelector('#side .hdr .sym').textContent)
if (!/^a · /.test(out.single_letter)) fails.push('一个样本时 selection 页头没有字母 a')
await snap('16_single_sample_letter')
// 选中框：member_of 一行
await fresh(); await ev(() => { const b = annOf(STOCKS[0]).boxes.find(b => b.s === 159); S.sel = { type: 'box', id: b.id }; S.tab = 'selection'; render() })
out.box_fields = await ev(() => [...document.querySelectorAll('#side .kv > .k')].map(e => e.textContent))
await snap('17_box_member_of')
// features 页、标签页
await fresh(); await ev(() => { S.tab = 'features'; render() }); await snap('18_features_tab')
out.tabs = await ev(() => [...document.querySelectorAll('#tabs button')].map(b => b.textContent))

writeFileSync(join(shots, 't15_check.json'), JSON.stringify(out, null, 1))
await browser.close()
console.log(`pattern 页计数入口 ${nd} 个`)
console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'console / pageerror: 0')
console.log(fails.length ? 'FAIL:\n' + fails.join('\n') : 'CHECK PASS')
process.exit(errs.length || fails.length ? 1 : 0)
