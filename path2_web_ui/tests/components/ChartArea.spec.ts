import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'
import { useViewStore } from '../../src/stores/view'

describe('ChartArea – level control', () => {
  beforeEach(() => setActivePinia(createPinia()))

  function mountIt() {
    const v = useViewStore()
    const wrapper = mount(ChartArea, {
      global: {
        stubs: {
          KlineChart: true,
          DetailSidebar: true,
          TopologyControl: true,
        },
      },
    })
    return { wrapper, v }
  }

  it('renders 3 level options (matched / qualified / detected)', () => {
    const { wrapper } = mountIt()
    const ctrl = wrapper.get('[data-testid="level-control"]')
    const buttons = ctrl.findAll('button')
    expect(buttons.length).toBe(3)
    const labels = buttons.map((b) => b.text())
    expect(labels).toContain('Matched')
    expect(labels).toContain('Qualified')
    expect(labels).toContain('Detected')
  })

  it('defaults to "matched" active', () => {
    const { wrapper } = mountIt()
    const active = wrapper.findAll('.level-btn.active')
    expect(active.length).toBe(1)
    expect(active[0].text()).toBe('Matched')
  })

  it('clicking "Detected" updates store.level and moves active class', async () => {
    const { wrapper, v } = mountIt()
    const buttons = wrapper.findAll('.level-btn')
    const detectedBtn = buttons.find((b) => b.text() === 'Detected')!
    await detectedBtn.trigger('click')
    expect(v.level).toBe('detected')
    expect(detectedBtn.classes()).toContain('active')
    // 原来的 Matched 不再 active
    const matchedBtn = buttons.find((b) => b.text() === 'Matched')!
    expect(matchedBtn.classes()).not.toContain('active')
  })
})
