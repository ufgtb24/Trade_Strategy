import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ShiftPairBanner from '../../src/components/ShiftPairBanner.vue'
import { useViewStore } from '../../src/stores/view'

describe('ShiftPairBanner', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shiftPairPending=false 时不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([])
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })

  it('shiftPairPending=true + candidateMatchIds 空 → 渲染 + 文本精确匹配', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ instance_id: 'e1', node_id: 'BO', source: 'main' }])
    const wrapper = mount(ShiftPairBanner)
    const el = wrapper.find('.shift-pair-banner')
    expect(el.exists()).toBe(true)
    expect(el.text()).toBe('入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消')
  })

  it('shiftPairPending=true + candidateMatchIds 非空 → 排他,不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ instance_id: 'e1', node_id: 'BO', source: 'main' }])
    view.candidateMatchIds = new Set(['m1']) as any
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })

  it('length=2 → shiftPairPending=false → 不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([
      { instance_id: 'e1', node_id: 'BO', source: 'main' },
      { instance_id: 'e2', node_id: 'TA', source: 'main' },
    ])
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })
})
