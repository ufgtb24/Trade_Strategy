// auditor 核实：把一个已冻结样本的成员框拉长到跨过样本日，看成员是否悄悄掉出、界面有无提示。只在内存里改，不改文件。
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(resolve(here, '../../../..'), 'path2_web_ui', 'package.json'))
const { chromium } = require('playwright')
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
await page.goto('about:blank'); await page.goto('http://localhost:8792/2026-10-28_annotation-web-loop/repro/mock_v4.html'); await page.waitForTimeout(400)
const r = await page.evaluate(() => {
  const st = STOCKS[0], a = annOf(st)
  const smp = a.samples.find(x => x.idx === 167), box = a.boxes.find(b => b.s === 164 && b.e === 167)
  const before = membersOf(smp, st).map(b => txt(b.name))
  const sigBefore = sigOf(smp, st), diffBefore = diffKey(diffOf(smp, st)), mtBefore = sampleVerdict(smp, st).match
  box.e = 170   // 模拟拖右边到样本日之后
  S.sel = { type: 'box', id: box.id }; S.tab = 'selection'; render()
  const after = membersOf(smp, st).map(b => txt(b.name))
  return { frozen: !!smp.frozen, before, after, sigBefore, sigAfter: sigOf(smp, st), diffBefore, diffAfter: diffKey(diffOf(smp, st)), mtBefore, mtAfter: sampleVerdict(smp, st).match,
           side: document.getElementById('side').innerText.slice(0, 400) }
})
console.log(JSON.stringify(r, null, 1))
await browser.close()
