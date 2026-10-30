// web-loop 回归 gate（smoke）：mock_v4.html 的两道检查，任一不过退出码非 0。
// 1) 把页面里所有内联 <script>（不带 src 的）抽出来逐段 node --check；
// 2) 用系统 chrome 打开页面，console error 与 pageerror 必须为零；
// 3) 每道题的图：带 #q=q1 打开、再换 hash 到 q2～q4，侧栏都要出现那道题的题号和 close，点 close 后收起、hash 清掉。
// 用法（在仓库根或 worktree 根）：node docs/research/2026-10-28_annotation-web-loop/repro/smoke.mjs
// 前提：docs/research 下已起 python3 -m http.server 8792。playwright 从 path2_web_ui/node_modules 解析。
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../../..')
const html = join(here, 'mock_v4.html')
const url = 'http://localhost:8792/2026-10-28_annotation-web-loop/repro/mock_v4.html'

let fail = 0
const src = readFileSync(html, 'utf-8')
const blocks = [...src.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1])
const tmp = mkdtempSync(join(tmpdir(), 'mock-v4-smoke-'))
blocks.forEach((code, i) => {
  const f = join(tmp, `inline_${i}.js`)
  writeFileSync(f, code)
  try { execFileSync(process.execPath, ['--check', f], { stdio: 'pipe' }); console.log(`node --check inline #${i}: ok`) }
  catch (e) { fail = 1; console.log(`node --check inline #${i}: FAIL\n${String(e.stderr || e.message)}`) }
})
rmSync(tmp, { recursive: true, force: true })
if (!blocks.length) { fail = 1; console.log('没有找到内联脚本') }

const require = createRequire(join(repoRoot, 'path2_web_ui', 'package.json'))
const { chromium } = require('playwright')
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const page = await browser.newPage({ viewport: { width: 2560, height: 1440 } })
const errs = []
page.on('console', m => { if (m.type() === 'error') errs.push(`console: ${m.text()}`) })
page.on('pageerror', e => errs.push(`pageerror: ${e.message}`))
const resp = await page.goto(url, { waitUntil: 'load' })
if (!resp || resp.status() !== 200) { fail = 1; console.log(`页面状态 ${resp ? resp.status() : '无响应'}`) }
await page.waitForTimeout(1500)
await page.goto(url + '#q=q1', { waitUntil: 'load' })
for (const q of ['q1', 'q2', 'q3', 'q4']) {
  if (q !== 'q1') { await page.evaluate(h => { location.hash = h }, 'q=' + q); await page.waitForTimeout(200) }
  const head = await page.evaluate(() => { const c = document.querySelector('#side [data-act="qclose"]'); return c ? c.parentElement.querySelector('.sym').textContent : null })
  if (head !== q) { fail = 1; console.log(`#q=${q}：侧栏题号是 ${head}`) } else console.log(`#q=${q}: ok`)
}
await page.click('#side [data-act="qclose"]'); await page.waitForTimeout(200)
const closed = await page.evaluate(() => !document.querySelector('#side [data-act="qclose"]') && !location.hash)
if (!closed) { fail = 1; console.log('close 后没收起') } else console.log('close: ok')
await browser.close()
if (errs.length) { fail = 1; console.log(errs.join('\n')) } else console.log('console / pageerror: 0')
console.log(fail ? 'SMOKE FAIL' : 'SMOKE PASS')
process.exit(fail)
