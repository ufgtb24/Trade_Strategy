import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TopologyControl from '../../src/components/TopologyControl.vue'
import { useViewStore } from '../../src/stores/view'
import { SCAN_FILE } from '../fixtures'

describe('TopologyControl', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  function mountIt() {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.selectSymbol('AAPL')
    return { wrapper: mount(TopologyControl), v }
  }

  // ---- 行为保持回归(改造前已有) ----

  it('renders a node per topology role with node_id', () => {
    const { wrapper } = mountIt()
    expect(wrapper.findAll('[data-role-node]').length).toBe(4)
    expect(wrapper.text()).toContain('down')
    expect(wrapper.text()).toContain('bo')
  })

  it('clicking a node toggles role visibility in store', async () => {
    const { wrapper, v } = mountIt()
    // 用 createEvent 设置 detail=1 模拟真实单击(test-utils trigger 不传 detail)
    const btn = wrapper.get('[data-role-node="bo"]').element
    const evt = new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 })
    btn.dispatchEvent(evt)
    vi.advanceTimersByTime(300)
    expect(v.roleVisible.bo).toBe(false)
  })

  it('node carries inline background style', () => {
    const { wrapper } = mountIt()
    expect(wrapper.get('[data-role-node="bo"]').attributes('style') ?? '').toMatch(/background/)
  })

  it('renders edges with rule text', () => {
    const { wrapper } = mountIt()
    expect(wrapper.text()).toContain('contains')
    expect(wrapper.text()).toContain('gap=1')
  })

  // ---- node+edge 图结构(本次改造新增) ----

  it('draws one svg edge-line per topology edge', () => {
    const { wrapper } = mountIt()
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.findAll('.edge-line').length).toBe(3)       // 3 条边(不含 marker 箭头 path)
  })

  it('positions nodes absolutely from layout', () => {
    const { wrapper } = mountIt()
    const style = wrapper.get('[data-role-node="bo"]').attributes('style') ?? ''
    expect(style).toMatch(/left/)
    expect(style).toMatch(/top/)
  })

  it('edge labels show edge kind without the Edge suffix', () => {
    const { wrapper } = mountIt()
    expect(wrapper.text()).toContain('Temporal')      // TemporalEdge → Temporal
    expect(wrapper.text()).toContain('Containment')   // ContainmentEdge → Containment
    expect(wrapper.text()).not.toContain('TemporalEdge')     // 证明 Edge 后缀确被剥除
    expect(wrapper.text()).not.toContain('ContainmentEdge')
  })

  it('keeps double-click diagnose wiring', async () => {
    const { wrapper, v } = mountIt()
    await wrapper.get('[data-role-node="bo"]').trigger('dblclick')
    expect(v.selected).toEqual({ kind: 'role', nodeId: 'bo' })
  })
})
