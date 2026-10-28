// ui 截图脚本（groups 重想，2026-10-28）：在 path2_web_ui 目录下运行（那里有 node_modules/playwright）
//   cd path2_web_ui && node ../docs/research/2026-10-28_annotation-groups-rethink/repro/shot.mjs <页面名> <输出前缀> [状态...]
// 页面名：mock_v3 或 variant_x_xxx（不带 .html）；状态：app（横盘突破回踩，有 app）/ noapp（把未归类里底部反转两个挪进新 pattern「底部反转」）/ uns（未归类）/ open（点开 no_buy 的 app 总数）/ feat（点开回踩 in 2/3）/ noappfeat（接在 noapp 后：点开回踩 in 1/2）/ full（整页）
// 侧栏改成不滚动、整段展开后做元素级截图；视口 2560×1440
import { createRequire } from 'module'
const { chromium } = createRequire(process.cwd() + '/')('playwright')   // 从运行目录（path2_web_ui）解析
const [page0, prefix, ...states] = process.argv.slice(2)
const OUT = '/home/yu/PycharmProjects/Trade_Strategy/docs/research/2026-10-28_annotation-groups-rethink/'
const url = page0 === 'mock_v3'
  ? 'http://localhost:8793/2026-10-26_annotation-workflow-polish/repro/mock_v3.html'
  : `http://localhost:8793/2026-10-28_annotation-groups-rethink/repro/${page0}.html`
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome' })
const page = await browser.newPage({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1 })
const errs = []
page.on('pageerror', e => errs.push(String(e)))
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) })
await page.goto(url)
await page.waitForTimeout(400)
const setState = async st => {
  await page.evaluate(st => {
    S.tab = 'pattern'; S.sel = null
    if (st === 'app') S.cur = '横盘突破回踩'
    if (st === 'uns') S.cur = '未归类'
    if (st === 'noapp') {
      if (!S.patterns.includes('底部反转')) S.patterns.push('底部反转')
      for (const st of STOCKS) for (const bp of annOf(st).buys) if (bp.pattern === '未归类' && sigOf(bp, st).startsWith('下跌')) bp.pattern = '底部反转'
      S.cur = '底部反转'
    }
    if (st === 'open') { S.cur = '横盘突破回踩'; S.vKey = 'app|no_buy' }   // 点开 no_buy 的 app:buy 总数（B 筛下面的列表，C 就地列出）
    if (st === 'feat') { S.cur = '横盘突破回踩'; S.vKey = 'feat|回踩' }    // 点开 features 区回踩的 in 2/3
    if (st === 'noappfeat') { S.vKey = 'feat|回踩' }                       // 接在 noapp 后面用
    render()
  }, st)
  await page.waitForTimeout(200)
}
for (const st of states) {
  if (st === 'full') { await page.screenshot({ path: OUT + prefix + '_full.png' }); continue }
  await setState(st)
  await page.addStyleTag({ content: '#wrap{height:auto!important} #side{overflow:visible!important}' })
  await page.waitForTimeout(100)
  await page.locator('#side').screenshot({ path: OUT + prefix + '_' + st + '.png' })
}
if (errs.length) console.log('ERRORS:\n' + errs.join('\n'))
await browser.close()
