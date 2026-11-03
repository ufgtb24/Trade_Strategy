// 截图证据的生成脚本:打开第一份扫描结果,拍 app 视图下的成交量带与副图(2560x1440)。
// 用法:node shot_app.cjs <输出目录>;前端须在 localhost:5144。playwright-core 路径指向票 04 的 worktree,换地方跑时改它。
const { chromium } = require('/home/yu/PycharmProjects/Trade_Strategy-04-open-by-symbol-shell/path2_web_ui/node_modules/playwright-core')
const OUT = process.argv[2]
;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1 })
  await page.goto('http://localhost:5144/')
  await page.getByRole('button', { name: /打开历史/ }).click()
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await page.locator('td.sym[data-symbol]').first().waitFor()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${OUT}/05-app-scan-view.png`, fullPage: true })
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
