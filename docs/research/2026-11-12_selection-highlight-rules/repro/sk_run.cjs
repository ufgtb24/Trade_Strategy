// sk 的无头走查脚本：开一个独立的无头 Chromium 打开真页面（只读），按步骤文件驱动选中、截图。
// 用法（仓库根）：NODE_PATH=path2_web_ui/node_modules node docs/research/2026-11-12_selection-highlight-rules/repro/sk_run.cjs <steps.json>
// steps.json：[{ "eval": "js 表达式，可用 v(view store)、e2e" } | { "shot": "名字", "sel": "css 选择器(可选)", "clip": [x,y,w,h](可选) } | { "wait": 毫秒 }]
// 纪律：拦掉一切非 GET 请求（不写任何标注 / 反馈 / 配置）；不按 Enter（symbol 回车除外，那是打开股票）；不点图。
const { chromium } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

const SHOTS = path.join(__dirname, 'screenshots')
const steps = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const SYMBOL = process.env.SYM || 'CRNC'

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1800, height: 1100 }, deviceScaleFactor: Number(process.env.DSF || 1) })
  await ctx.addInitScript((pat) => { try { localStorage.setItem('path2_web_ui.annotation.current_pattern.v1', JSON.stringify(pat)) } catch {} }, process.env.PAT || 'new_step')
  const page = await ctx.newPage()
  const blocked = []
  await page.route('**/*', (route) => {
    const m = route.request().method()
    if (m !== 'GET' && m !== 'OPTIONS') { blocked.push(m + ' ' + route.request().url()); return route.abort() }
    return route.continue()
  })
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await page.goto('http://localhost:5171/', { waitUntil: 'networkidle' })
  const input = page.getByTestId('symbol-input')
  await input.fill(SYMBOL)
  await input.press('Enter')
  await page.locator(`.symbol-title-bar [data-symbol="${SYMBOL}"]`).waitFor({ timeout: 30000 })
  await page.waitForFunction(() => (window.__e2e?.chartMain()?.getOption()?.xAxis?.[0]?.data ?? []).length > 100, null, { timeout: 30000 })
  await page.getByTestId('mode-compare').click()
  await page.waitForTimeout(4000)
  const out = {}
  for (const s of steps) {
    if (s.wait) { await page.waitForTimeout(s.wait); continue }
    if (s.key) {
      if (/enter/i.test(s.key)) throw new Error('Enter 不许按')
      await page.keyboard.press(s.key); console.log('[key]', s.key); await page.waitForTimeout(s.after ?? 600); continue
    }
    if (s.mouse) {
      const b = await page.locator(s.mouse.sel).first().boundingBox()
      await page.mouse.click(b.x + s.mouse.x, b.y + s.mouse.y); console.log('[mouse]', JSON.stringify(s.mouse))
      await page.waitForTimeout(s.after ?? 600); continue
    }
    if (s.symbol) {
      const inp = page.getByTestId('symbol-input'); await inp.fill(s.symbol); await inp.press('Enter')
      await page.locator(`.symbol-title-bar [data-symbol="${s.symbol}"]`).waitFor({ timeout: 30000 })
      console.log('[symbol]', s.symbol); await page.waitForTimeout(s.after ?? 3000); continue
    }
    if (s.eval) {
      const r = await page.evaluate((code) => {
        const e2e = window.__e2e
        const v = e2e.view
        // eslint-disable-next-line no-eval
        const res = eval(code)
        try { return JSON.parse(JSON.stringify(res, (k, x) => x instanceof Set ? [...x] : x instanceof Map ? Object.fromEntries(x) : x)) } catch (e) { return String(res) }
      }, s.eval)
      if (s.as) out[s.as] = r
      console.log('[eval]', s.as || s.eval.slice(0, 80), '=>', JSON.stringify(r)?.slice(0, s.max || 2000))
      await page.waitForTimeout(s.after ?? 600)
      continue
    }
    if (s.shot) {
      const jpg = !!s.jpg
      const file = path.join(SHOTS, s.shot + (jpg ? '.jpg' : '.png'))
      const o = jpg ? { path: file, type: 'jpeg', quality: 80 } : { path: file }
      if (s.sel) await page.locator(s.sel).first().screenshot(o)
      else if (s.clip) await page.screenshot({ ...o, clip: { x: s.clip[0], y: s.clip[1], width: s.clip[2], height: s.clip[3] } })
      else await page.screenshot(o)
      console.log('[shot]', file, fs.statSync(file).size)
    }
  }
  if (blocked.length) console.log('[blocked non-GET]', blocked)
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
