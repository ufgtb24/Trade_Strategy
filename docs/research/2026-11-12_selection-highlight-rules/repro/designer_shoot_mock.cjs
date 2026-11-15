// designer：把 mock.html 的各节截成图（file:// 打开，本地静态页）。
const { chromium } = require('@playwright/test')
const path = require('path')
const OUT = path.join(__dirname, 'screenshots')
;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1300, height: 1200 }, deviceScaleFactor: 1.5 })
  const errs = []
  page.on('pageerror', e => errs.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) })
  await page.goto('file://' + path.join(__dirname, 'mock.html'))
  await page.waitForTimeout(800)
  if (errs.length) console.log('ERR', errs)
  const only = process.argv.slice(2)
  const ids = await page.$$eval('section.scene', s => s.map(x => x.id))
  for (const id of ids) {
    if (only.length && !only.includes(id)) continue
    await page.locator('#' + id).screenshot({ path: path.join(OUT, `designer_mock_${id}.jpg`), type: 'jpeg', quality: 80 })
  }
  await page.locator('#law').screenshot({ path: path.join(OUT, 'designer_mock_law.jpg'), type: 'jpeg', quality: 85 })
  await page.locator('#legend').screenshot({ path: path.join(OUT, 'designer_mock_legend.jpg'), type: 'jpeg', quality: 85 })
  console.log(ids.join(' '))
  await browser.close()
})()
