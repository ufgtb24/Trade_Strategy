import { describe, it, expect, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import {
  useFloatingPanel, clampRect, defaultRect, loadRect, saveRect,
  RECT_KEY, MIN_W, MIN_H, EDGE_KEEP_X, EDGE_KEEP_Y,
} from '../src/components/useFloatingPanel'

// jsdom 未实现 PointerEvent 构造函数(仅 MouseEvent),补最小 polyfill(同 resizable-divider 测试)
if (typeof globalThis.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number
    constructor(type: string, params: MouseEventInit & { pointerId?: number } = {}) {
      super(type, params)
      this.pointerId = params.pointerId ?? 0
    }
  }
  // @ts-expect-error jsdom 测试环境 polyfill
  globalThis.PointerEvent = PointerEventPolyfill
}

const VW = 1000
const VH = 800

function setViewport(w = VW, h = VH) {
  Object.defineProperty(window, 'innerWidth', { value: w, writable: true, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: h, writable: true, configurable: true })
}

/** 在真实组件实例内跑 composable(它注册 onBeforeUnmount / window 监听),
    并按 WorkingCopyDrawer 的真实结构绑定两个 handler:标题栏(内含按钮)+ 右下角把手。 */
function mountPanel() {
  let api!: ReturnType<typeof useFloatingPanel>
  const wrapper = mount(defineComponent({
    setup() {
      api = useFloatingPanel()
      return () => h('div', [
        h('div', { class: 'hdr', onPointerdown: api.onDragPointerDown }, [h('button', { class: 'close' })]),
        h('div', { class: 'resize-handle', onPointerdown: api.onResizePointerDown }),
      ])
    },
  }), { attachTo: document.body })
  const root = wrapper.element as HTMLElement
  return {
    api,
    wrapper,
    hdr: root.querySelector('.hdr') as HTMLElement,
    btn: root.querySelector('button') as HTMLElement,
    handle: root.querySelector('.resize-handle') as HTMLElement,
  }
}

function down(el: EventTarget, x: number, y: number, id = 1) {
  el.dispatchEvent(new PointerEvent('pointerdown', { clientX: x, clientY: y, button: 0, pointerId: id, bubbles: true }))
}
function move(x: number, y: number, id = 1) {
  window.dispatchEvent(new PointerEvent('pointermove', { clientX: x, clientY: y, pointerId: id }))
}
function up(x: number, y: number, id = 1) {
  window.dispatchEvent(new PointerEvent('pointerup', { clientX: x, clientY: y, pointerId: id }))
}

beforeEach(() => {
  localStorage.clear()
  setViewport()
})

describe('clampRect', () => {
  it('尺寸不低于下限,不超过视口', () => {
    const r = clampRect({ x: 0, y: 0, w: 10, h: 10 }, VW, VH)
    expect(r.w).toBe(MIN_W)
    expect(r.h).toBe(MIN_H)
    const big = clampRect({ x: 0, y: 0, w: 5000, h: 5000 }, VW, VH)
    expect(big.w).toBe(VW)
    expect(big.h).toBe(VH)
  })

  it('向左拖出视口时,右边缘至少留 EDGE_KEEP_X 可见', () => {
    const r = clampRect({ x: -9999, y: 100, w: 480, h: 400 }, VW, VH)
    expect(r.x + r.w).toBe(EDGE_KEEP_X)
  })

  it('向右拖出视口时,左边缘至多到 vw - EDGE_KEEP_X', () => {
    const r = clampRect({ x: 9999, y: 100, w: 480, h: 400 }, VW, VH)
    expect(r.x).toBe(VW - EDGE_KEEP_X)
  })

  it('标题栏不会被拖出视口顶端,也不会整个沉到底下', () => {
    expect(clampRect({ x: 0, y: -500, w: 480, h: 400 }, VW, VH).y).toBe(0)
    expect(clampRect({ x: 0, y: 9999, w: 480, h: 400 }, VW, VH).y).toBe(VH - EDGE_KEEP_Y)
  })
})

describe('defaultRect', () => {
  it('右上角贴边,尺寸不超视口', () => {
    const r = defaultRect(VW, VH)
    expect(r.x + r.w).toBe(VW - 12)
    expect(r.y).toBe(12)
    expect(r.w).toBe(480)
    expect(r.h).toBeLessThanOrEqual(VH - 24)
  })

  it('窄视口下退化为可用尺寸而非溢出', () => {
    const r = defaultRect(400, 300)
    expect(r.w).toBeLessThanOrEqual(400)
    expect(r.h).toBeLessThanOrEqual(300)
  })
})

describe('loadRect / saveRect', () => {
  it('无存储时回默认', () => {
    expect(loadRect(VW, VH)).toEqual(defaultRect(VW, VH))
  })

  it('坏 JSON / 缺字段 / 非有限数一律回默认', () => {
    const def = defaultRect(VW, VH)
    localStorage.setItem(RECT_KEY, '{ not json')
    expect(loadRect(VW, VH)).toEqual(def)
    localStorage.setItem(RECT_KEY, JSON.stringify({ x: 10, y: 10 }))
    expect(loadRect(VW, VH)).toEqual(def)
    localStorage.setItem(RECT_KEY, JSON.stringify({ x: 10, y: 10, w: NaN, h: 400 }))
    expect(loadRect(VW, VH)).toEqual(def)
    localStorage.setItem(RECT_KEY, JSON.stringify({ x: 'a', y: 10, w: 480, h: 400 }))
    expect(loadRect(VW, VH)).toEqual(def)
  })

  it('往返:存进去的合法值读得回来', () => {
    const r = { x: 120, y: 60, w: 500, h: 420 }
    saveRect(r)
    expect(loadRect(VW, VH)).toEqual(r)
  })

  it('存的值若因视口变小而越界,读回时被钳进视口', () => {
    saveRect({ x: 900, y: 700, w: 480, h: 600 })
    const r = loadRect(600, 500)
    expect(r).toEqual(clampRect({ x: 900, y: 700, w: 480, h: 600 }, 600, 500))
    expect(r.x).toBeLessThanOrEqual(600 - EDGE_KEEP_X)
  })
})

describe('useFloatingPanel 拖拽', () => {
  it('pointermove 按 delta 平移,尺寸不变', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    move(340, 190)
    expect(api.rect.value).toEqual({ x: 240, y: 140, w: 480, h: 400 })
    up(340, 190)
  })

  it('delta 相对按下点累计(非逐帧增量)', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    move(340, 190)
    move(310, 160)
    expect(api.rect.value).toEqual({ x: 210, y: 110, w: 480, h: 400 })
    up(310, 160)
  })

  it('pointerup 后再 move 不生效,dragging 复位', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    move(340, 190)
    up(340, 190)
    expect(api.dragging.value).toBe(false)
    move(900, 700)
    expect(api.rect.value.x).toBe(240)
  })

  it('非同一 pointerId 的 move 被忽略', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150, 1)
    move(900, 700, 2)
    expect(api.rect.value.x).toBe(200)
    up(300, 150, 1)
  })

  it('标题栏内的按钮不起拖(点 × 不会把面板拽走)', () => {
    const { api, btn } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(btn, 300, 150)
    move(340, 190)
    expect(api.rect.value.x).toBe(200)
  })

  it('拖动越界时被钳制', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    move(-5000, -5000)
    expect(api.rect.value.x + api.rect.value.w).toBe(EDGE_KEEP_X)
    expect(api.rect.value.y).toBe(0)
    up(-5000, -5000)
  })

  it('拖动结束写入 localStorage', () => {
    const { api, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    move(340, 190)
    up(340, 190)
    expect(JSON.parse(localStorage.getItem(RECT_KEY)!)).toEqual({ x: 240, y: 140, w: 480, h: 400 })
  })
})

describe('useFloatingPanel 缩放', () => {
  it('右下角把手按 delta 改尺寸,位置不变', () => {
    const { api, handle } = mountPanel()
    api.rect.value = { x: 100, y: 100, w: 480, h: 400 }
    down(handle, 580, 500)
    move(620, 560)
    expect(api.rect.value).toEqual({ x: 100, y: 100, w: 520, h: 460 })
    up(620, 560)
  })

  it('缩到极小时被下限钳住', () => {
    const { api, handle } = mountPanel()
    api.rect.value = { x: 100, y: 100, w: 480, h: 400 }
    down(handle, 580, 500)
    move(-5000, -5000)
    expect(api.rect.value.w).toBe(MIN_W)
    expect(api.rect.value.h).toBe(MIN_H)
    up(-5000, -5000)
  })

  it('缩放结束写入 localStorage', () => {
    const { api, handle } = mountPanel()
    api.rect.value = { x: 100, y: 100, w: 480, h: 400 }
    down(handle, 580, 500)
    move(620, 560)
    up(620, 560)
    expect(JSON.parse(localStorage.getItem(RECT_KEY)!)).toEqual({ x: 100, y: 100, w: 520, h: 460 })
  })
})

describe('视口 resize', () => {
  it('窗口变小后面板被重新钳进视口', () => {
    const { api } = mountPanel()
    api.rect.value = { x: 900, y: 700, w: 480, h: 400 }
    setViewport(600, 500)
    window.dispatchEvent(new Event('resize'))
    expect(api.rect.value.x).toBeLessThanOrEqual(600 - EDGE_KEEP_X)
    expect(api.rect.value.y).toBeLessThanOrEqual(500 - EDGE_KEEP_Y)
  })
})

describe('卸载清理', () => {
  it('组件卸载后遗留的 pointermove 不再改 rect', () => {
    const { api, wrapper, hdr } = mountPanel()
    api.rect.value = { x: 200, y: 100, w: 480, h: 400 }
    down(hdr, 300, 150)
    wrapper.unmount()
    move(900, 700)
    expect(api.rect.value.x).toBe(200)
  })
})
