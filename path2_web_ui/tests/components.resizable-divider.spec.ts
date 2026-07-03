import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ResizableDivider from '../src/components/ResizableDivider.vue'

// jsdom (as of v25) 未实现 PointerEvent 构造函数(仅有 MouseEvent),
// 这里补一个最小 polyfill 供测试环境使用;不影响其他测试文件。
if (typeof globalThis.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number
    isPrimary: boolean
    constructor(type: string, params: MouseEventInit & { pointerId?: number; isPrimary?: boolean } = {}) {
      super(type, params)
      this.pointerId = params.pointerId ?? 0
      this.isPrimary = params.isPrimary ?? true
    }
  }
  // @ts-expect-error jsdom 测试环境 polyfill
  globalThis.PointerEvent = PointerEventPolyfill
}

describe('ResizableDivider (Task 3)', () => {
  it('renders with row-resize cursor', () => {
    const w = mount(ResizableDivider)
    const root = w.find('.resizable-divider')
    expect(root.exists()).toBe(true)
    expect(root.element.getAttribute('role')).toBe('separator')
    expect(root.element.getAttribute('aria-orientation')).toBe('horizontal')
  })

  it('emits drag(dy) on pointermove with cumulative delta from pointerdown Y', async () => {
    const w = mount(ResizableDivider, { attachTo: document.body })
    const root = w.find('.resizable-divider')
    // pointerdown at y=100
    root.element.dispatchEvent(new PointerEvent('pointerdown', { clientY: 100, button: 0, isPrimary: true, pointerId: 1 }))
    // pointermove at y=130 (dy=30)
    window.dispatchEvent(new PointerEvent('pointermove', { clientY: 130, pointerId: 1 }))
    // pointermove at y=95 (dy=-5)
    window.dispatchEvent(new PointerEvent('pointermove', { clientY: 95, pointerId: 1 }))
    // pointerup
    window.dispatchEvent(new PointerEvent('pointerup', { clientY: 95, pointerId: 1 }))

    const dragEvents = w.emitted('drag') ?? []
    expect(dragEvents.length).toBe(2)
    expect(dragEvents[0]).toEqual([30])
    expect(dragEvents[1]).toEqual([-5])
    expect(w.emitted('dragend')).toBeTruthy()
    w.unmount()
  })

  it('does not emit drag before pointerdown', () => {
    const w = mount(ResizableDivider, { attachTo: document.body })
    window.dispatchEvent(new PointerEvent('pointermove', { clientY: 200, pointerId: 1 }))
    expect(w.emitted('drag')).toBeFalsy()
    w.unmount()
  })

  it('stops emitting after pointerup', () => {
    const w = mount(ResizableDivider, { attachTo: document.body })
    const root = w.find('.resizable-divider')
    root.element.dispatchEvent(new PointerEvent('pointerdown', { clientY: 100, button: 0, isPrimary: true, pointerId: 1 }))
    window.dispatchEvent(new PointerEvent('pointerup', { clientY: 100, pointerId: 1 }))
    window.dispatchEvent(new PointerEvent('pointermove', { clientY: 150, pointerId: 1 }))
    const dragEvents = w.emitted('drag') ?? []
    expect(dragEvents.length).toBe(0)
    w.unmount()
  })
})

describe('ResizableDivider — Task 5 dblclick emit', () => {
  it('emits dblclick when host element receives native dblclick', async () => {
    const wrapper = mount(ResizableDivider)
    await wrapper.trigger('dblclick')
    expect(wrapper.emitted('dblclick')).toBeTruthy()
    expect(wrapper.emitted('dblclick')!.length).toBe(1)
  })

  it('dblclick does not trigger drag emit', async () => {
    const wrapper = mount(ResizableDivider)
    await wrapper.trigger('dblclick')
    // native dblclick 不触发 pointerdown 链路 → drag 不 emit
    expect(wrapper.emitted('drag')).toBeUndefined()
    expect(wrapper.emitted('dragend')).toBeUndefined()
  })
})
