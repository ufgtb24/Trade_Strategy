import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'
import { usePanelsStore } from '../../src/stores/panels'

function mountIt() {
  const wrapper = mount(ChartArea, {
    global: {
      stubs: {
        KlineChart: true,
        DetailSidebar: true,
        TopologyControl: true,
      },
    },
  })
  const panels = usePanelsStore()
  return { wrapper, panels }
}

describe('ChartArea — panel toggle chips', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('renders three panel-toggle chips in level-bar (testids)', () => {
    const { wrapper } = mountIt()
    expect(wrapper.find('[data-testid="panel-toggle-topology"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-toggle-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-toggle-slider"]').exists()).toBe(true)
  })

  it('by default: TopologyControl + DetailSidebar are not rendered; .no-sidebar class on .chart-area', () => {
    const { wrapper } = mountIt()
    expect(wrapper.findComponent({ name: 'TopologyControl' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'DetailSidebar' }).exists()).toBe(false)
    expect(wrapper.find('.chart-area').classes()).toContain('no-sidebar')
  })

  it('clicking topology chip mounts TopologyControl and adds active class', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-topology"]')
    await chip.trigger('click')
    expect(panels.showTopology).toBe(true)
    expect(chip.classes()).toContain('active')
    expect(wrapper.findComponent({ name: 'TopologyControl' }).exists()).toBe(true)
  })

  it('clicking sidebar chip mounts DetailSidebar and removes .no-sidebar', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-sidebar"]')
    await chip.trigger('click')
    expect(panels.showSidebar).toBe(true)
    expect(chip.classes()).toContain('active')
    expect(wrapper.findComponent({ name: 'DetailSidebar' }).exists()).toBe(true)
    expect(wrapper.find('.chart-area').classes()).not.toContain('no-sidebar')
  })

  it('clicking slider chip toggles panels.showSlider (no DOM mount, render-side concern)', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-slider"]')
    await chip.trigger('click')
    expect(panels.showSlider).toBe(true)
    expect(chip.classes()).toContain('active')
  })
})
