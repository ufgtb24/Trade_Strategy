// 主图上按住 Shift 复制一天、一段(components/shiftCopyGesture.ts,spec 1.14「复制一天、一段」):
// 没拖开复制按下那一天,拖开给竖带预览、松手复制这一段(左小右大);按下与跟着的 click 都截下,图表和标注手势收不到;
// 在 event 记号上 Shift+点照旧是配对查询,从记号上拖开仍是复制一段;拖出图区按图窗的首尾 K 线截住;
// 没按 Shift、不在主图上、不是左键都放过。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createShiftCopyGesture, type ShiftCopyDeps } from '../src/components/shiftCopyGesture'

// x 像素 → K 线下标:图区从 56 起到 456,一根 10 像素(40 根)
const px = (i: number) => 56 + 10 * i + 5
const fakeChart = {
  convertFromPixel: (_: unknown, x: number) => Math.round((x - 61) / 10),
} as any

function setup(opts: { marker?: string | null; onChart?: (x: number, y: number) => boolean } = {}) {
  const mainEl = document.createElement('div')
  const inner = document.createElement('canvas')   // 图表自己的画布层(容器里面)
  mainEl.appendChild(inner)
  document.body.appendChild(mainEl)
  const deps: ShiftCopyDeps = {
    main: () => fakeChart, mainEl: () => mainEl,
    count: () => 40,
    plot: () => ({ left: 56, right: 456 }),
    onChart: opts.onChart ?? ((_x, y) => y < 300),
    markerAt: () => opts.marker ?? null,
    pick: vi.fn(),
    setPreview: vi.fn(),
    copy: vi.fn(),
  }
  // 图表与标注手势的替身:挂在画布层上 / 主图容器的冒泡阶段
  const chartDown = vi.fn(), chartClick = vi.fn(), gestureDown = vi.fn()
  inner.addEventListener('mousedown', chartDown)
  inner.addEventListener('click', chartClick)
  mainEl.addEventListener('mousedown', gestureDown)
  const g = createShiftCopyGesture(deps)
  g.attach()
  return { g, deps, mainEl, inner, chartDown, chartClick, gestureDown }
}

const down = (t: HTMLElement, x: number, y: number, shiftKey = true, button = 0) => {
  const ev = new MouseEvent('mousedown', { button, shiftKey, clientX: x, clientY: y, bubbles: true, cancelable: true })
  t.dispatchEvent(ev)
  return ev
}
const move = (x: number, y: number, shiftKey = true) =>
  window.dispatchEvent(new MouseEvent('mousemove', { shiftKey, clientX: x, clientY: y }))
const up = (x: number, y: number, shiftKey = true) =>
  window.dispatchEvent(new MouseEvent('mouseup', { button: 0, shiftKey, clientX: x, clientY: y }))
const click = (t: HTMLElement, x: number, y: number) =>
  t.dispatchEvent(new MouseEvent('click', { button: 0, clientX: x, clientY: y, bubbles: true, cancelable: true }))

let cur: ReturnType<typeof setup> | null = null
beforeEach(() => { document.body.innerHTML = ''; vi.useRealTimers() })
afterEach(() => { cur?.g.detach(); cur = null })

describe('Shift+点:复制按下那一天', () => {
  it('没拖开 → 复制这一天;按下截下(图表、标注手势都收不到),挡住浏览器扩展文字选区', () => {
    const s = cur = setup()
    const ev = down(s.inner, px(7), 50)
    expect(ev.defaultPrevented).toBe(true)
    expect(s.chartDown).not.toHaveBeenCalled()
    expect(s.gestureDown).not.toHaveBeenCalled()
    up(px(7) + 2, 51)
    expect(s.deps.copy).toHaveBeenCalledWith(7, 7)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith(null)
  })
  it('松手后跟着来的 click 截下(不被图表当成点空白清掉选中);之后真正的点击照常', async () => {
    const s = cur = setup()
    down(s.inner, px(7), 50); up(px(7), 50); click(s.inner, px(7), 50)
    expect(s.chartClick).not.toHaveBeenCalled()
    await new Promise(r => setTimeout(r, 0))
    click(s.inner, px(9), 50)
    expect(s.chartClick).toHaveBeenCalledTimes(1)
  })
  it('拖出去又回到按下处 4 像素以内松手:算点一下', () => {
    const s = cur = setup()
    down(s.inner, px(7), 50)
    move(px(12), 50)
    up(px(7) + 3, 50)
    expect(s.deps.copy).toHaveBeenCalledWith(7, 7)
  })
})

describe('Shift+拖:预览并复制一段', () => {
  it('从左往右:拖动中给竖带预览(左小右大),松手收起预览、复制首尾下标', () => {
    const s = cur = setup()
    down(s.inner, px(3), 50)
    move(px(3) + 2, 50)
    expect(s.deps.setPreview).not.toHaveBeenCalled()   // 没超过 4 像素不算拖开
    move(px(6), 52)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith([3, 6])
    move(px(9), 60)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith([3, 9])
    up(px(9), 60)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith(null)
    expect(s.deps.copy).toHaveBeenCalledWith(3, 9)
  })
  it('从右往左一样;途中松开 Shift 不影响', () => {
    const s = cur = setup()
    down(s.inner, px(20), 50)
    move(px(11), 50, false)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith([11, 20])
    up(px(11), 50, false)
    expect(s.deps.copy).toHaveBeenCalledWith(11, 20)
  })
  it('拖出图区:按图窗的首尾 K 线截住(左边截在第 0 根,右边截在最后一根)', () => {
    const s = cur = setup()
    down(s.inner, px(10), 50)
    move(-200, 400)
    expect(s.deps.setPreview).toHaveBeenLastCalledWith([0, 10])
    up(900, 400)
    expect(s.deps.copy).toHaveBeenCalledWith(10, 39)
  })
})

describe('event 记号上:Shift+点照旧是配对查询,拖开仍是复制一段', () => {
  it('没拖开 → 交给配对查询,不复制', () => {
    const s = cur = setup({ marker: 'ev-1' })
    down(s.inner, px(5), 50)
    up(px(5), 50)
    expect(s.deps.pick).toHaveBeenCalledWith('ev-1')
    expect(s.deps.copy).not.toHaveBeenCalled()
    expect(s.chartDown).not.toHaveBeenCalled()
  })
  it('从记号上拖开 → 复制一段,不做配对查询', () => {
    const s = cur = setup({ marker: 'ev-1' })
    down(s.inner, px(5), 50)
    move(px(8), 50)
    up(px(8), 50)
    expect(s.deps.copy).toHaveBeenCalledWith(5, 8)
    expect(s.deps.pick).not.toHaveBeenCalled()
  })
})

describe('放过:不是这个手势的按下照旧交给图表与标注手势', () => {
  it('没按 Shift', () => {
    const s = cur = setup()
    const ev = down(s.inner, px(5), 50, false)
    up(px(9), 50, false)
    expect(ev.defaultPrevented).toBe(false)
    expect(s.chartDown).toHaveBeenCalled()
    expect(s.gestureDown).toHaveBeenCalled()
    expect(s.deps.copy).not.toHaveBeenCalled()
  })
  it('不在主图的 K 线区、成交量带上(onChart 不接)', () => {
    const s = cur = setup()
    down(s.inner, px(5), 350)
    up(px(5), 350)
    expect(s.chartDown).toHaveBeenCalled()
    expect(s.deps.copy).not.toHaveBeenCalled()
  })
  it('不是左键', () => {
    const s = cur = setup()
    down(s.inner, px(5), 50, true, 2)
    up(px(5), 50)
    expect(s.chartDown).toHaveBeenCalled()
    expect(s.deps.copy).not.toHaveBeenCalled()
  })
  it('没跟着这个手势的 click 不截', () => {
    const s = cur = setup()
    click(s.inner, px(5), 50)
    expect(s.chartClick).toHaveBeenCalledTimes(1)
  })
})

describe('cancel:换股票时收起拖到一半的手势', () => {
  it('收起预览,之后松手不复制', () => {
    const s = cur = setup()
    down(s.inner, px(3), 50)
    move(px(8), 50)
    s.g.cancel()
    expect(s.deps.setPreview).toHaveBeenLastCalledWith(null)
    up(px(8), 50)
    expect(s.deps.copy).not.toHaveBeenCalled()
  })
})
