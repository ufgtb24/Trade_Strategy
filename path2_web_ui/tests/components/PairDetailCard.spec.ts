import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PairDetailCard from '../../src/components/PairDetailCard.vue'
import type { PairPayload } from '../../src/types'

describe('PairDetailCard', () => {
  it('4 subcheck 短路显示', () => {
    const payload: PairPayload = {
      src_event_id: 'burst_1', dst_event_id: 'tb_1', applied_swap: false,
      original_first_click: 'burst_1', original_second_click: 'tb_1',
      valid: true, invalid_reason: null, edge_id: 'burst_to_tb', edge_kind: 'TemporalEdge',
      subchecks: [
        { channel: 'feasible_window', passed: true, measured: null, threshold: null, reason: null },
        { channel: 'satisfies', passed: false, measured: { kind: 'gap', value: 15, label: 'gap' }, threshold: 10, reason: 'gap 越界' },
      ],
    }
    const w = mount(PairDetailCard, { props: { payload } })
    expect(w.text()).toContain('gap 越界')
    expect(w.findAll('.subcheck').length).toBe(2)
  })

  it('applied_swap · 显切换提示 + 撤回按钮 · 点击撤回 emit undo-swap', async () => {
    const payload: PairPayload = {
      src_event_id: 'burst_1', dst_event_id: 'tb_1',
      applied_swap: true,
      original_first_click: 'tb_1', original_second_click: 'burst_1',
      valid: true, invalid_reason: null, edge_id: 'burst_to_tb', edge_kind: 'TemporalEdge',
      subchecks: [],
    }
    const w = mount(PairDetailCard, { props: { payload } })
    expect(w.text()).toContain('顺序已自动切换')
    expect(w.find('button.undo-swap').exists()).toBe(true)
    await w.find('button.undo-swap').trigger('click')
    expect(w.emitted('undo-swap')).toBeTruthy()
  })

  it('invalid_reason=same_node 显对应提示', () => {
    const payload: PairPayload = {
      src_event_id: 'a', dst_event_id: 'b', applied_swap: false,
      original_first_click: 'a', original_second_click: 'b',
      valid: false, invalid_reason: 'same_node',
      edge_id: null, edge_kind: null, subchecks: null,
    }
    const w = mount(PairDetailCard, { props: { payload } })
    expect(w.text()).toContain('同一 node')
  })

  it('invalid_reason=no_edge_between_nodes 显对应提示', () => {
    const payload: PairPayload = {
      src_event_id: 'a', dst_event_id: 'b', applied_swap: false,
      original_first_click: 'a', original_second_click: 'b',
      valid: false, invalid_reason: 'no_edge_between_nodes',
      edge_id: null, edge_kind: null, subchecks: null,
    }
    const w = mount(PairDetailCard, { props: { payload } })
    expect(w.text()).toContain('无直连 edge')
  })

  it('valid=true 时渲染 src → dst header + edge_kind/edge_id', () => {
    const payload: PairPayload = {
      src_event_id: 'burst_1', dst_event_id: 'tb_1', applied_swap: false,
      original_first_click: 'burst_1', original_second_click: 'tb_1',
      valid: true, invalid_reason: null, edge_id: 'burst_to_tb', edge_kind: 'TemporalEdge',
      subchecks: [],
    }
    const w = mount(PairDetailCard, { props: { payload } })
    expect(w.text()).toContain('burst_1 → tb_1')
    expect(w.text()).toContain('TemporalEdge')
    expect(w.text()).toContain('burst_to_tb')
  })
})
