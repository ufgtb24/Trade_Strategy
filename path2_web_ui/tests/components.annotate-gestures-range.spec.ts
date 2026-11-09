// feedback 工具的拖选手势(components/annotateGestures.ts 的 range):起止换算成首尾两根 K 线的日期(左小右大)、
// 拖动中给竖带预览、松手先熄工具再交出范围与松开处;点一下不拖当普通点击、工具不熄;拖出去又回到按下处 4 像素
// 以内松手也算点一下;副图 app 区与用户区都归它,轨名栏、成交量带照旧平移;光标十字。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createAnnotateGestures, type GestureDeps } from '../src/components/annotateGestures'
import { SUB_GRID_LEFT } from '../src/render/subGeometry'

const DATES = Array.from({ length: 40 }, (_, i) => `2025-03-${String(i + 1).padStart(2, '0')}`)
// x 像素 → K 线下标:图区从 56 起,一根 10 像素
const idx = (x: number) => (x - 56) / 10
const px = (i: number) => 56 + 10 * i

function fakeChart(kGridBottom = 300) {
  return {
    convertFromPixel: (_: unknown, x: number) => idx(x),
    convertToPixel: (_: unknown, i: number) => px(i),
    // 主图:grid 0 是 K 线区(y < kGridBottom),grid 1 是成交量带
    containPixel: ({ gridIndex }: { gridIndex: number }, [, y]: number[]) =>
      gridIndex === 0 ? y < kGridBottom : y >= kGridBottom,
    dispatchAction: vi.fn(),
  } as any
}

function el(width = 800) {
  const d = document.createElement('div')
  Object.defineProperty(d, 'clientWidth', { value: width })
  document.body.appendChild(d)
  return d
}

function setup(tool: GestureDeps['tool'] = () => 'feedback', claimsBelow = 200) {
  const mainEl = el(), subEl = el()
  const main = fakeChart(), sub = fakeChart()
  const calls: string[] = []
  const deps: GestureDeps = {
    main: () => main, sub: () => sub, mainEl: () => mainEl, subEl: () => subEl,
    active: () => true,
    tool,
    toolDone: vi.fn(() => calls.push('toolDone')),
    dates: () => DATES, lanes: () => [], geom: () => [], bracket: () => null, marks: () => null,
    zoom: () => ({ start: 0, end: 100 }),
    sampleAt: () => null,
    limitOf: () => null,
    setDraft: vi.fn(), setPreview: vi.fn(), setStop: vi.fn(),
    setRange: vi.fn(),
    rangeDone: vi.fn(() => calls.push('rangeDone')),
    createBox: vi.fn(), resizeBox: vi.fn(),
    select: vi.fn(), selectSample: vi.fn(), placeSample: vi.fn(), take: vi.fn(),
    // compare:用户区在副图 y < claimsBelow,下面是 app 区
    claims: (y: number) => y < claimsBelow,
  }
  const g = createAnnotateGestures(deps)
  g.attach()
  return { g, deps, mainEl, subEl, main, calls }
}

const down = (target: HTMLElement, x: number, y: number) =>
  target.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: x, clientY: y, bubbles: true, cancelable: true }))
const move = (x: number, y: number) => window.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y }))
const up = (x: number, y: number) => window.dispatchEvent(new MouseEvent('mouseup', { button: 0, clientX: x, clientY: y }))

let cur: ReturnType<typeof setup> | null = null
beforeEach(() => { document.body.innerHTML = '' })
afterEach(() => { cur?.g.detach(); cur = null })

describe('feedback 拖选:起止换算', () => {
  it('主图 K 线区从左往右拖:拖动中给竖带,松手先熄工具、再交出首尾两根的日期与松开处', () => {
    const s = cur = setup()
    down(s.mainEl, px(3), 50)
    move(px(5), 52)
    expect(s.deps.setRange).toHaveBeenLastCalledWith({ start: DATES[3], end: DATES[5] })
    move(px(9), 60)
    expect(s.deps.setRange).toHaveBeenLastCalledWith({ start: DATES[3], end: DATES[9] })
    up(px(9), 60)
    expect(s.deps.setRange).toHaveBeenLastCalledWith(null)
    expect(s.calls).toEqual(['toolDone', 'rangeDone'])
    expect(s.deps.rangeDone).toHaveBeenCalledWith(DATES[3], DATES[9], { x: px(9), y: 60 })
    expect(s.deps.select).not.toHaveBeenCalled()
  })

  it('从右往左拖:start 仍是左边那根', () => {
    const s = cur = setup()
    down(s.mainEl, px(12), 50)
    move(px(4), 50)
    up(px(4), 50)
    expect(s.deps.rangeDone).toHaveBeenCalledWith(DATES[4], DATES[12], { x: px(4), y: 50 })
  })

  it('拖到图外:按最边上那根 K 线算', () => {
    const s = cur = setup()
    down(s.mainEl, px(37), 50)
    move(px(60), 50)
    up(px(60), 50)
    expect(s.deps.rangeDone).toHaveBeenCalledWith(DATES[37], DATES[39], expect.anything())
  })

  it('点一下不拖:当普通点击(主图点空白清选中),工具不熄、不交范围', () => {
    const s = cur = setup()
    down(s.mainEl, px(3), 50)
    move(px(3) + 2, 51)
    up(px(3) + 2, 51)
    expect(s.deps.toolDone).not.toHaveBeenCalled()
    expect(s.deps.rangeDone).not.toHaveBeenCalled()
    expect(s.deps.setRange).not.toHaveBeenCalledWith(expect.objectContaining({ start: expect.any(String) }))
    expect(s.deps.select).toHaveBeenCalledWith(null)
  })

  it('拖出去又回到按下处 4 像素以内松手:算点一下(图表这时也会派 click)', () => {
    const s = cur = setup()
    down(s.mainEl, px(3), 50)
    move(px(8), 50)
    up(px(3) + 3, 50)
    expect(s.deps.toolDone).not.toHaveBeenCalled()
    expect(s.deps.rangeDone).not.toHaveBeenCalled()
    expect(s.deps.setRange).toHaveBeenLastCalledWith(null)
    expect(s.deps.select).toHaveBeenCalledWith(null)
  })

  it('副图 app 区也归它;app 区点一下留给图表自己的点击(不清选中)', () => {
    const s = cur = setup()
    down(s.subEl, px(2), 250)
    move(px(6), 250)
    up(px(6), 255)
    expect(s.deps.rangeDone).toHaveBeenCalledWith(DATES[2], DATES[6], { x: px(6), y: 255 })
    s.calls.length = 0
    down(s.subEl, px(2), 250)
    up(px(2), 250)
    expect(s.deps.select).not.toHaveBeenCalled()
    expect(s.calls).toEqual([])
  })

  it('副图用户区点一下照常选中(点空白什么都不选);拖动同样拖出一段', () => {
    const s = cur = setup()
    down(s.subEl, px(2), 50)
    up(px(2), 50)
    expect(s.deps.select).toHaveBeenCalledWith(null)
    down(s.subEl, px(2), 50)
    move(px(4), 50)
    up(px(4), 50)
    expect(s.deps.rangeDone).toHaveBeenCalledWith(DATES[2], DATES[4], expect.anything())
  })

  it('副图左边轨名栏、主图成交量带上拖动照旧平移,不拖选', () => {
    const s = cur = setup()
    down(s.subEl, SUB_GRID_LEFT - 20, 250)
    move(SUB_GRID_LEFT + 60, 250)
    up(SUB_GRID_LEFT + 60, 250)
    down(s.mainEl, px(3), 350)
    move(px(9), 350)
    up(px(9), 350)
    expect(s.deps.setRange).not.toHaveBeenCalled()
    expect(s.deps.rangeDone).not.toHaveBeenCalled()
    expect(s.main.dispatchAction).toHaveBeenCalled()      // 平移
  })

  it('cancel:拖到一半作废,竖带收起', () => {
    const s = cur = setup()
    down(s.mainEl, px(3), 50)
    move(px(8), 50)
    s.g.cancel()
    expect(s.deps.setRange).toHaveBeenLastCalledWith(null)
    up(px(8), 50)
    expect(s.deps.rangeDone).not.toHaveBeenCalled()
  })

  it('工具不是 feedback 时副图 app 区仍是平移', () => {
    const s = cur = setup(() => null)
    down(s.subEl, px(2), 250)
    move(px(6), 250)
    up(px(6), 250)
    expect(s.deps.setRange).not.toHaveBeenCalled()
    expect(s.main.dispatchAction).toHaveBeenCalled()
  })
})

describe('feedback 亮着时的光标', () => {
  it('主图 K 线区与整张副图(含 app 区)是十字,轨名栏不管', () => {
    const s = cur = setup()
    expect(s.g.cursorAt('main', px(3), 50)).toBe('crosshair')
    expect(s.g.cursorAt('sub', px(3), 50)).toBe('crosshair')
    expect(s.g.cursorAt('sub', px(3), 250)).toBe('crosshair')
    expect(s.g.cursorAt('sub', SUB_GRID_LEFT - 20, 250)).toBeNull()
  })
})
