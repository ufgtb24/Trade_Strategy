import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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

  it('renders a node per topology node with node_id', () => {
    const { wrapper } = mountIt()
    expect(wrapper.findAll('[data-node-id]').length).toBe(4)
    expect(wrapper.text()).toContain('down')
    expect(wrapper.text()).toContain('bo')
  })

  it('clicking a node toggles node visibility in store', async () => {
    const { wrapper, v } = mountIt()
    // 用 createEvent 设置 detail=1 模拟真实单击(test-utils trigger 不传 detail)
    const btn = wrapper.get('[data-node-id="bo"]').element
    const evt = new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 })
    btn.dispatchEvent(evt)
    vi.advanceTimersByTime(300)
    expect(v.nodeVisible.bo).toBe(false)
  })

  it('node carries inline background style', () => {
    const { wrapper } = mountIt()
    expect(wrapper.get('[data-node-id="bo"]').attributes('style') ?? '').toMatch(/background/)
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
    const style = wrapper.get('[data-node-id="bo"]').attributes('style') ?? ''
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
    // dblclick 走 toggleExpandedNode(手动语义 add-to-set);验证 expandedNodeIds 含 bo。
    const { wrapper, v } = mountIt()
    await wrapper.get('[data-node-id="bo"]').trigger('dblclick')
    expect(v.expandedNodeIds.has('bo')).toBe(true)
  })

  // ---- 入口 B 降级:点 edge 标签 → scope=nodes → PairListCard(本次改造新增) ----

  it('clicking an edge label fetches scope=nodes and renders PairListCard', async () => {
    const fakeResp = {
      scope: 'nodes',
      payload: { edge_id: 'bo_to_tb', total_pair: 4, ok_pair: 1,
                miss_reasons: { gap_out: 3, anchor_mismatch: 0, strict_fail: 0, negation_violated: 0 },
                example_failed_pairs: [
                  { src_event_id: 'bo9', dst_event_id: 'tb16', subcheck_stage: 'gap_out',
                    measured: null, threshold: null, edge_kind: 'TemporalEdge' },
                ] },
      caveats: [{ code: 'measured_not_kind_aware', message: '硬伤 E 未修' }],
    }
    // 注:mount 时 store 的全局 diag 预取 watch(view.ts)也会 fetch 一次 legacy /diagnose
    // (无 scope 参数);故这里按 URL 过滤出本次 edge click 触发的 scope=nodes 调用,
    // 不断言总调用次数。mockImplementation(非 mockResolvedValue)每次 new 一个 Response——
    // Response.json() 只能读一次,多次调用共享同一实例会 "body already read"。
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => new Response(JSON.stringify(fakeResp), { status: 200 }))
    const { wrapper } = mountIt()
    await flushPromises()
    await wrapper.findAll('.elabel')[2].trigger('click')   // 第 3 条边 = bo→tb(edges 数组序)
    await flushPromises()
    const nodesCall = fetchSpy.mock.calls.find((c) => (c[0] as string).includes('scope=nodes'))
    expect(nodesCall).toBeTruthy()
    const url = nodesCall![0] as string
    expect(url).toContain('scope=nodes')
    expect(url).toContain('src_node=bo')
    expect(url).toContain('dst_node=tb')
    expect(wrapper.text()).toContain('bo_to_tb')
    expect(wrapper.text()).toContain('1 / 4 通过')
    expect(wrapper.text()).toContain('硬伤 E 未修')
  })

  it('close button clears the nodes popover', async () => {
    const fakeResp = {
      scope: 'nodes',
      payload: { edge_id: 'bo_to_tb', total_pair: 0, ok_pair: 0, miss_reasons: {}, example_failed_pairs: [] },
      caveats: [],
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => new Response(JSON.stringify(fakeResp), { status: 200 }))
    const { wrapper } = mountIt()
    await flushPromises()
    await wrapper.findAll('.elabel')[2].trigger('click')
    await flushPromises()
    expect(wrapper.find('.nodes-popover').exists()).toBe(true)
    await wrapper.get('.close-btn').trigger('click')
    expect(wrapper.find('.nodes-popover').exists()).toBe(false)
  })
})
