import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CrosshairOverlay from '../src/components/CrosshairOverlay.vue'

describe('CrosshairOverlay', () => {
  it('renders dashed line at given x', () => {
    const w = mount(CrosshairOverlay, { props: { x: 100 } })
    const el = w.get('.crosshair-overlay').element as HTMLElement
    expect(el.style.left).toBe('100px')
  })

  it('does not render when x is null', () => {
    const w = mount(CrosshairOverlay, { props: { x: null } })
    expect(w.find('.crosshair-overlay').exists()).toBe(false)
  })

  it('updates left when x prop changes', async () => {
    const w = mount(CrosshairOverlay, { props: { x: 100 } })
    await w.setProps({ x: 250 })
    const el = w.get('.crosshair-overlay').element as HTMLElement
    expect(el.style.left).toBe('250px')
  })
})
