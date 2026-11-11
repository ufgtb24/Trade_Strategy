import { test, expect } from '@playwright/test'
import { copyFileSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  FIXTURE, OTHER_FINGERPRINT, TRAIN_END, annState, barCount, boxOn, boxesOf, drag, drawOnKline, featureId, klineY, laneY,
  name, openSymbol, routeTo, settled, startBackend, stopBackend, xOf, type Backend,
} from './annotateHelpers'

/**
 * 画框、起名与词表(annotate):
 * 1. 按代码打开 → 在 K 线区拖框 → 起名 → 刷新,框和名字都还在;在特征轨上拖出的框直接带这个名字;
 *    拖框边改起止;属性 true → 再点一下 → null(存下的是「没有这个键」);框套框的子框轨与 ⊂;
 *    改名后所有用到这个名字的框处处跟着变(两只股票);合并先显示会波及几个框,刷新后照样能拆回,拆回后恢复原样。
 * 1b. 工具默认都不亮:K 线区、副图上拖动是平移、不画框,拖框边不改起止;Shift+B 点亮 box,画完一个框就熄;
 *    亮着时 Esc 只熄灭工具,选中的框还在。
 * 2. 用标注存储的例子文件(tests/path2_web/fixtures/annotation_store_v1)造出冲突与指纹不符:
 *    两种提示各出现一次,图照常显示;冲突点 ok 后刷新不再出现。
 *
 * 标注会写批次文件,绝不能写进用户的标注目录:后端与转发见 ./annotateHelpers.ts。
 */

test.use({ viewport: { width: 2560, height: 1440 } })

test.describe('画框、起名与词表', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => { backend = await startBackend() })
  test.afterAll(() => stopBackend(backend))

  test('拖框起名刷新后还在;轨上拖出带名字的框;改起止;属性回到 null;子框轨;改名处处生效;合并预览与拆回', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const [A, B] = [symbols[Math.floor(symbols.length / 2)], symbols[Math.floor(symbols.length / 2) + 1]]
    await page.goto('/')
    await openSymbol(page, A)
    const n = await barCount(page)

    // ── 在 K 线区拖框 → 起名 ──
    const b1 = await drawOnKline(page, n - 80, n - 40)
    await expect(page.getByTestId('feature-input')).toBeFocused()
    await name(page, '横盘')
    await expect(page.getByTestId('definition-input')).toBeVisible()      // 新特征第一次用,留一格写定义
    await page.getByTestId('definition-input').fill('窄幅震荡、量缩')
    await page.getByTestId('definition-input').press('Enter')
    await expect(page.getByTestId('definition-text')).toHaveText('窄幅震荡、量缩')
    await settled(page)
    let st = await annState(page)
    const [box1] = boxesOf(st, A)
    expect(box1.id).toBe(b1)
    expect(box1.feature).toBe(featureId(st, '横盘'))
    expect(box1.end <= TRAIN_END).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('01-drawn-named.png'), fullPage: true })

    // ── 刷新:框和名字都还在 ──
    await page.reload()
    await openSymbol(page, A)
    expect(boxesOf(await annState(page), A)).toEqual([box1])
    const yLane = await laneY(page, '横盘')
    await page.mouse.click((await xOf(page, n - 60, 'sub')), yLane)                 // 点框中间 → 选中
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')
    await expect(page.getByTestId('definition-text')).toHaveText('窄幅震荡、量缩')

    // ── 在特征轨上拖 → 新框直接带这个名字 ──
    await boxOn(page)
    await drag(page, await xOf(page, n - 30, 'sub'), yLane, await xOf(page, n - 20, 'sub'), yLane)
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')
    await settled(page)
    expect(boxesOf(await annState(page), A).map((b: any) => b.feature)).toEqual([box1.feature, box1.feature])

    // ── 拖框的右边改终点 ──
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    const halfBar = ((await xOf(page, n - 39, 'sub')) - (await xOf(page, n - 40, 'sub'))) / 2
    await boxOn(page)
    await drag(page, (await xOf(page, n - 40, 'sub')) + halfBar, yLane, await xOf(page, n - 50, 'sub'), yLane)
    await settled(page)
    expect(boxesOf(await annState(page), A).find((b: any) => b.id === b1).end).toBe(dates[n - 50])
    expect(boxesOf(await annState(page), A)).toHaveLength(2)

    // ── 子框:在大框里画一个小框,默认属于大框;子框轨写成「缩量 ⊂ 横盘」;⊂ 点掉 = detach ──
    await drawOnKline(page, n - 70, n - 60)
    await name(page, '缩量')
    await expect(page.getByTestId('parent-toggle').first()).toHaveClass(/on/)
    await expect(page.getByTestId('parent-rel').first()).toHaveText('contains')
    await laneY(page, '缩量 ⊂ 横盘')
    await page.screenshot({ path: testInfo.outputPath('02-child-lane.png'), fullPage: true })
    await page.getByTestId('parent-toggle').first().click()
    await expect(page.getByTestId('parent-toggle').first()).not.toHaveClass(/on/)
    await laneY(page, '缩量')
    await page.getByTestId('parent-toggle').first().click()
    await laneY(page, '缩量 ⊂ 横盘')

    // ── 属性三态:true → 再点一下 → null(存下的是没有这个键,不是 false)──
    await page.getByTestId('attr-input').fill('放量')
    await page.getByTestId('attr-input').press('Enter')
    await expect(page.getByTestId('attr-true-放量')).toHaveClass(/on/)
    await page.getByTestId('attr-true-放量').click()
    await expect(page.getByTestId('attr-null-放量')).toBeVisible()
    await settled(page)
    st = await annState(page)
    const shrink = boxesOf(st, A).find((b: any) => b.feature === featureId(st, '缩量'))
    expect(shrink.attrs ?? {}).not.toHaveProperty(featureId(st, '放量'))

    // ── 另一只股票上也用「横盘」(从候选里点选)──
    await openSymbol(page, B)
    await expect(page.getByTestId('box-panel')).toHaveCount(0)            // 换了图,选中的框跟着清掉
    const m = await barCount(page)
    await drawOnKline(page, m - 100, m - 70)
    await page.getByTestId('suggest-横盘').click()
    await expect(page.getByTestId('box-feature')).toHaveText('横盘')

    // ── 改名:改一处,两只股票上处处跟着变 ──
    await page.getByTestId('annotation-tab-features').click()
    await page.getByTestId('feature-横盘').getByTestId('rename').click()
    await page.getByTestId('rename-input').fill('盘整')
    await page.getByTestId('rename-input').press('Enter')
    await expect(page.getByTestId('feature-盘整')).toBeVisible()
    await expect(page.getByTestId('feature-盘整').getByTestId('usage')).toHaveText('box×3 · attr×0')
    await laneY(page, '盘整')
    await openSymbol(page, A)
    await laneY(page, '盘整')
    await laneY(page, '缩量 ⊂ 盘整')

    // ── 合并:先显示会波及几个框,合并后被并的词不见;拆回后恢复原样 ──
    await openSymbol(page, B)
    await drawOnKline(page, m - 50, m - 30)
    await name(page, '整理')
    await settled(page)
    const beforeMerge = await annState(page)
    await page.getByTestId('annotation-tab-features').click()
    await page.getByTestId('feature-整理').getByTestId('merge-select').selectOption({ label: '盘整' })
    await expect(page.getByTestId('merge-preview')).toContainText('box×1 · attr×0')
    await page.screenshot({ path: testInfo.outputPath('03-merge-preview.png'), fullPage: true })
    await page.getByTestId('merge-apply').click()
    await expect(page.getByTestId('feature-整理')).toHaveCount(0)
    await expect(page.getByTestId('merged-整理')).toBeVisible()
    await settled(page)
    const merged = await annState(page)
    expect(boxesOf(merged, B).every((b: any) => b.feature === featureId(merged, '盘整'))).toBe(true)
    await expect(page.getByTestId('feature-盘整').getByTestId('usage')).toHaveText('box×4 · attr×0')
    // 合并记在标注文件里:刷新之后照样能拆回
    await page.reload()
    await openSymbol(page, B)
    await page.getByTestId('annotation-tab-features').click()
    await expect(page.getByTestId('merged-整理')).toContainText('box×1 · attr×0')
    await page.getByTestId('unmerge').click()
    await expect(page.getByTestId('feature-整理')).toBeVisible()
    await settled(page)
    const sortF = (s: any) => ({ ...s, features: [...s.features].sort((a: any, b: any) => (a.id < b.id ? -1 : 1)) })
    expect(sortF(await annState(page))).toEqual(sortF(beforeMerge))
    await laneY(page, '整理')
    await page.screenshot({ path: testInfo.outputPath('04-unmerged.png'), fullPage: true })

    // 全部图止于训练段末日
    for (const c of (await annState(page)).charts) for (const b of c.boxes) expect(b.end <= TRAIN_END).toBe(true)
  })

  test('工具默认不亮:拖动是平移;Shift+B 点亮,画完一个就熄;Esc 只熄工具不清选中;框边不亮时拖不动', async ({ page }) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const D = symbols[Math.floor(symbols.length / 2) + 3]
    await page.goto('/')
    await openSymbol(page, D)
    const n = await barCount(page)
    await expect(page.getByTestId('tool-box')).not.toHaveClass(/\bon\b/)
    await expect(page.getByTestId('tool-point')).not.toHaveClass(/\bon\b/)
    const zoomStart = () => page.evaluate(() => (window as any).__e2e.chartMain().getOption().dataZoom[0].start as number)

    // 不亮:K 线区往右拖 = 看更早的 K 线,不画框
    const z0 = await zoomStart()
    await drag(page, await xOf(page, n - 80), await klineY(page), await xOf(page, n - 40), await klineY(page))
    await expect.poll(zoomStart).toBeLessThan(z0)
    await settled(page)
    expect(boxesOf(await annState(page), D)).toHaveLength(0)

    // Shift+B 点亮,画完一个框就熄(上面往右拖了 40 根,画在图窗中间)
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('Shift+B')
    await expect(page.getByTestId('tool-box')).toHaveClass(/\bon\b/)
    const cursor = () => page.evaluate(() => (window as any).__e2e.chartMain().getZr().handler.proxy.dom.style.cursor)
    await page.mouse.move(await xOf(page, n - 100), await klineY(page))
    await page.mouse.move(await xOf(page, n - 99), await klineY(page))
    await expect.poll(cursor).toBe('crosshair')                               // 亮着:K 线区是十字
    const b = await drawOnKline(page, n - 120, n - 110)
    await name(page, '工具')
    await expect(page.getByTestId('tool-box')).not.toHaveClass(/\bon\b/)
    await page.mouse.move(await xOf(page, n - 100), await klineY(page))
    await page.mouse.move(await xOf(page, n - 99), await klineY(page))
    await expect.poll(cursor).not.toBe('crosshair')

    // 亮着时 Esc 只熄工具,框还选着;不亮时 Esc 才清选中
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('Shift+B')
    await expect(page.getByTestId('tool-box')).toHaveClass(/\bon\b/)
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('tool-box')).not.toHaveClass(/\bon\b/)
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBe(b)

    // 不亮:按在框的右边拖,框不变(图窗平移)
    const yLane = await laneY(page, '工具')
    const halfBar = ((await xOf(page, n - 109, 'sub')) - (await xOf(page, n - 110, 'sub'))) / 2
    const z1 = await zoomStart()
    await drag(page, (await xOf(page, n - 110, 'sub')) + halfBar, yLane, await xOf(page, n - 100, 'sub'), yLane)
    await settled(page)
    const [box] = boxesOf(await annState(page), D)
    const dates: string[] = await page.evaluate(() => (window as any).__e2e.chartMain().getOption().xAxis[0].data)
    expect(box.end).toBe(dates[n - 110])
    await expect.poll(zoomStart).toBeLessThan(z1)
    await page.keyboard.press('Escape')
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBeNull()
  })

  test('选中框按 Delete 删框;焦点在输入框里时不删', async ({ page }) => {
    await routeTo(page, backend!)
    const symbols: string[] = await (await fetch(`${backend!.base}/symbols`)).json()
    const C = symbols[Math.floor(symbols.length / 2) + 2]
    await page.goto('/')
    await openSymbol(page, C)
    const n = await barCount(page)
    const b = await drawOnKline(page, n - 40, n - 30)
    await name(page, '误画')
    await settled(page)
    expect(boxesOf(await annState(page), C).map((x: any) => x.id)).toEqual([b])

    // 焦点在定义格里:Delete 只删字,框还在
    await page.getByTestId('definition-input').focus()
    await page.keyboard.press('Delete')
    await settled(page)
    expect(boxesOf(await annState(page), C)).toHaveLength(1)

    // 焦点离开输入框:Delete 删掉选中的框,选中随之清空
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
    await page.keyboard.press('Delete')
    await settled(page)
    expect(boxesOf(await annState(page), C)).toHaveLength(0)
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBeNull()

    // 写着定义直接去点副图上的框:点图让出焦点(定义照常存下),Delete 删的是框
    const b2 = await drawOnKline(page, n - 60, n - 50)
    await name(page, '误画二')
    await page.getByTestId('definition-input').fill('随手写的定义')
    await expect(page.getByTestId('definition-input')).toBeFocused()
    await page.mouse.click(await xOf(page, n - 55, 'sub'), await laneY(page, '误画二'))
    expect(await page.evaluate(() => document.activeElement?.tagName)).toBe('BODY')   // 定义格存下后收起
    expect(await page.evaluate(() => (window as any).__e2e.ann().selectedBoxId)).toBe(b2)
    await page.keyboard.press('Delete')
    await settled(page)
    const st = await annState(page)
    expect(boxesOf(st, C)).toHaveLength(0)
    expect(st.features.find((f: any) => f.name === '误画二')?.definition).toBe('随手写的定义')
  })
})

test.describe('冲突与指纹不符', () => {
  test.setTimeout(300_000)
  let backend: Backend | null = null
  test.beforeAll(async () => {
    // 例子文件原样带着一处冲突(两台同步前都改了「回踩」);把每批记的指纹换成另一份副本的,造出指纹不符
    backend = await startBackend((dir) => {
      for (const f of readdirSync(FIXTURE)) {
        const src = join(FIXTURE, f)
        if (!/^[A-Za-z0-9_]+-\d{8}T/.test(f)) { copyFileSync(src, join(dir, f)); continue }
        const doc = JSON.parse(readFileSync(src, 'utf8'))
        writeFileSync(join(dir, f), JSON.stringify({ ...doc, data_fingerprint: OTHER_FINGERPRINT }))
      }
    })
  })
  test.afterAll(() => stopBackend(backend))

  test('两种提示各出现一次,图照常显示;冲突看过后不再出现', async ({ page }, testInfo) => {
    await routeTo(page, backend!)
    await page.goto('/')
    await openSymbol(page, 'AAPL')
    await expect(page.getByTestId('notice-fingerprint')).toHaveCount(1)
    await expect(page.getByTestId('notice-fingerprint')).toContainText('mismatched')
    await expect(page.getByTestId('notice-conflict')).toHaveCount(1)
    await expect(page.getByTestId('notice-conflict')).toContainText('×1')
    await expect(page.getByTestId('notice-conflict')).toContainText('回踩')
    // 图照常显示:K 线与例子里的框都在
    expect(await barCount(page)).toBeGreaterThan(100)
    await laneY(page, '放量突破')
    await page.screenshot({ path: testInfo.outputPath('05-conflict-fingerprint.png'), fullPage: true })

    await page.getByTestId('notice-conflict-ok').click()
    await expect(page.getByTestId('notice-conflict')).toHaveCount(0)
    await page.reload()
    await openSymbol(page, 'AAPL')
    await expect(page.getByTestId('notice-fingerprint')).toHaveCount(1)
    await expect(page.getByTestId('notice-conflict')).toHaveCount(0)
  })
})
