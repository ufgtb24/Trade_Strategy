import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'
import { useViewStore } from '../../src/stores/view'

describe('ChartArea – level control', () => {
  beforeEach(() => setActivePinia(createPinia()))

  function mountIt() {
    const v = useViewStore()
    v.mode = 'app'          // 档位控件属于扫描结果视图
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

  it('renders 3 level options (in_hit / qualified / detected)', () => {
    const { wrapper } = mountIt()
    const ctrl = wrapper.get('[data-testid="level-control"]')
    // 过滤掉 panel-toggle chip(新增 Topology/Sidebar/Slider),只看 level 按钮
    const levelButtons = ctrl.findAll('button').filter(
      (b) => !(b.attributes('data-testid') ?? '').startsWith('panel-toggle')
    )
    expect(levelButtons.length).toBe(3)
    const labels = levelButtons.map((b) => b.text())
    expect(labels).toContain('in_hit')
    expect(labels).toContain('qualified')
    expect(labels).toContain('detected')
  })

  it('defaults to "in_hit" active', () => {
    const { wrapper } = mountIt()
    const active = wrapper.findAll('.level-btn.active')
    expect(active.length).toBe(1)
    expect(active[0].text()).toBe('in_hit')
  })

  it('clicking "detected" updates store.level and moves active class', async () => {
    const { wrapper, v } = mountIt()
    const buttons = wrapper.findAll('.level-btn')
    const detectedBtn = buttons.find((b) => b.text() === 'detected')!
    await detectedBtn.trigger('click')
    expect(v.level).toBe('detected')
    expect(detectedBtn.classes()).toContain('active')
    // 原来的 in_hit 不再 active
    const inHitBtn = buttons.find((b) => b.text() === 'in_hit')!
    expect(inHitBtn.classes()).not.toContain('active')
  })
})
