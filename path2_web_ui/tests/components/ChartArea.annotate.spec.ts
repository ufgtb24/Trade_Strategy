// annotate 模式的外壳:不显示 app 相关的控件,右侧是 selection / features / pattern 三页
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'
import { useViewStore } from '../../src/stores/view'
import { usePanelsStore } from '../../src/stores/panels'

function mountIt() {
  return mount(ChartArea, {
    global: { stubs: { KlineChart: true, DetailSidebar: true, TopologyControl: true } },
  })
}

describe('ChartArea · annotate', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('不显示档位、pattern、参数、拓扑和诊断侧栏(即使面板开关开着)', () => {
    const panels = usePanelsStore()
    panels.toggle('topology')
    panels.toggle('sidebar')
    const w = mountIt()
    expect(useViewStore().mode).toBe('annotate')
    expect(w.find('[data-testid="level-control"]').exists()).toBe(false)
    expect(w.findComponent({ name: 'TopologyControl' }).exists()).toBe(false)
    expect(w.findComponent({ name: 'DetailSidebar' }).exists()).toBe(false)
  })

  it('右侧栏三页 selection / features / pattern,没有 json 页;点页签切页', async () => {
    const w = mountIt()
    const tabs = w.findAll('[role="tab"]')
    expect(tabs.map(t => t.text())).toEqual(['selection', 'features', 'pattern'])
    expect(w.find('[data-testid="annotation-page-selection"]').exists()).toBe(true)
    await w.get('[data-testid="annotation-tab-features"]').trigger('click')
    expect(w.find('[data-testid="annotation-page-features"]').exists()).toBe(true)
    expect(w.get('[data-testid="annotation-tab-features"]').attributes('aria-selected')).toBe('true')
  })

  it('切到 app(从扫描列表进来)→ 回到原来的档位控件与诊断侧栏', async () => {
    const w = mountIt()
    useViewStore().mode = 'app'
    await w.vm.$nextTick()
    expect(w.find('[data-testid="level-control"]').exists()).toBe(true)
    expect(w.find('[data-testid="annotation-sidebar"]').exists()).toBe(false)
  })
})
