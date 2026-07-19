import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RelBadge from '../src/shared/RelBadge.vue'

describe('RelBadge', () => {
  it('显示 K/N ✓ 格式', () => {
    const w = mount(RelBadge, { props: { ok: 8, total: 10 } })
    expect(w.text()).toContain('8/10')
  })
  it('全过时显示 ✓', () => {
    const w = mount(RelBadge, { props: { ok: 10, total: 10 } })
    expect(w.find('.badge-ok').exists()).toBe(true)
  })
  it('部分过时显示黄', () => {
    const w = mount(RelBadge, { props: { ok: 5, total: 10 } })
    expect(w.find('.badge-warn').exists()).toBe(true)
  })
  it('零过时显示红', () => {
    const w = mount(RelBadge, { props: { ok: 0, total: 10 } })
    expect(w.find('.badge-fail').exists()).toBe(true)
  })
})
