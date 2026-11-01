// auditor 核实用：打开 mock_v4 的若干状态，截图并导出侧栏可见文字。只读，不改原型。
// 用法：node docs/research/2026-10-30_annotation-user-manual/repro/a_capture.mjs
import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../../..')
const url = 'http://localhost:8792/2026-10-28_annotation-web-loop/repro/mock_v4.html'
const require = createRequire(join(repoRoot, 'path2_web_ui', 'package.json'))
const { chromium } = require('playwright')
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('pageerror', e => errs.push(e.message))
const out = {}
async function fresh(hash = '') { await page.goto('about:blank'); await page.goto(url + hash, { waitUntil: 'load' }); await page.waitForTimeout(400) }
async function snap(name) {
  await page.screenshot({ path: join(here, 'a_shots', name + '.png'), fullPage: true })
  out[name] = await page.evaluate(() => ({ top: document.getElementById('top').innerText, side: document.getElementById('side').innerText }))
}
const act = async a => { await page.click(`[data-act="${a}"]`); await page.waitForTimeout(150) }
const ev = f => page.evaluate(f)
// 1 初始
await fresh(); await snap('01_initial')
// 2 selection：选中 TVRD 的第一个 sample（2024-12-24 正例那个 idx 167）
await ev(() => { S.sel = { type: 'sample', id: annOf(STOCKS[0]).samples[0].id }; S.tab = 'selection'; render() }); await snap('02_sample_annotate')
await act('mode:compare'); await snap('03_sample_compare')
// 4 选中框（放量突破 159-164）compare
await ev(() => { const b = annOf(STOCKS[0]).boxes.find(b => b.s === 159); S.sel = { type: 'box', id: b.id }; render() }); await snap('04_box_compare')
await ev(() => { const b = annOf(STOCKS[0]).boxes.find(b => b.s === 159); S.sel = { type: 'box', id: b.id }; S.mode = 'annotate'; render() }); await snap('05_box_annotate')
// 6 app 模式
await ev(() => { S.mode = 'app'; S.sel = null; render() }); await snap('06_app_mode')
// 7 pattern 页（有 app）
await fresh(); await ev(() => { S.tab = 'pattern'; render() }); await snap('07_pattern_app')
await ev(() => { S.vKey = 'feat|横盘'; render() }); await snap('08_pattern_feat_open')
await ev(() => { S.vKey = null; S.lkOpen = '放量突破→回踩:connected'; render() }); await snap('09_pattern_link_open')
// 10 unsorted 页
await fresh(); await ev(() => { S.cur = null; S.tab = 'pattern'; S.stock = 2; render() }); await snap('10_unsorted')
// 11 没有 app 的 pattern：把 unsorted 的全部挪进新 pattern P
await ev(() => { S.patterns.push('P'); for (const st of STOCKS) for (const s of annOf(st).samples) if (s.pattern === null) s.pattern = 'P'; S.cur = 'P'; render() }); await snap('11_pattern_noapp')
// 12 features 页
await fresh(); await ev(() => { S.tab = 'features'; render() }); await snap('12_features')
// 13 json 页
await ev(() => { S.tab = 'json'; render() }); await snap('13_json')
// 14-17 题
for (const q of ['q1', 'q2', 'q3', 'q4']) { await fresh('#q=' + q); await snap('14_' + q) }
// 18 新图 WHLRP 空白 + 新 box 未命名
await fresh(); await ev(() => { S.stock = 1; render() }); await snap('18_whlrp')
// 19 TVGN 选中 neg 229 compare
await fresh(); await ev(() => { S.stock = 3; S.mode = 'compare'; const s = annOf(STOCKS[3]).samples.find(x => x.idx === 229); S.sel = { type: 'sample', id: s.id }; S.tab = 'selection'; render() }); await snap('19_tvgn_neg_compare')
// 20 TVGN 选中 unsorted 166，看 ◂ 与 others
await ev(() => { S.mode = 'annotate'; S.cur = null; const s = annOf(STOCKS[3]).samples.find(x => x.idx === 166); S.sel = { type: 'sample', id: s.id }; render() }); await snap('20_tvgn_unsorted_sample')
writeFileSync(join(here, 'a_states.json'), JSON.stringify(out, null, 1))
await browser.close()
console.log('errors:', errs.length ? errs.join('\n') : 0)
