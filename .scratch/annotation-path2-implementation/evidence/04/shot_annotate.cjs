// 一次性截图脚本(不入库):打开主视图,按代码打开一只股票,拍整页与侧栏
const { chromium } = require('/home/yu/PycharmProjects/Trade_Strategy-04-open-by-symbol-shell/path2_web_ui/node_modules/playwright-core')
const OUT = process.argv[2]
const SYM = process.argv[3] || 'AAPL'
;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1 })
  await page.goto('http://localhost:5144/')
  await page.waitForSelector('[data-testid="symbol-input"]')
  await page.screenshot({ path: `${OUT}/00-startup.png`, fullPage: true })
  await page.fill('[data-testid="symbol-input"]', SYM)
  await page.press('[data-testid="symbol-input"]', 'Enter')
  await page.waitForSelector(`.symbol-title-bar [data-symbol="${SYM}"]`)
  await page.waitForTimeout(1200)
  await page.screenshot({ path: `${OUT}/01-annotate-${SYM}.png`, fullPage: true })
  await page.fill('[data-testid="symbol-input"]', 'ZZZQ26')
  await page.press('[data-testid="symbol-input"]', 'Enter')
  await page.waitForSelector('[data-testid="symbol-status"]')
  await page.screenshot({ path: `${OUT}/02-not-found.png`, fullPage: true })
  await page.locator('[data-testid="top-bar"]').screenshot({ path: `${OUT}/03-top-bar.png` })
  await page.locator('[data-testid="annotation-sidebar"]').screenshot({ path: `${OUT}/04-sidebar.png` })
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
