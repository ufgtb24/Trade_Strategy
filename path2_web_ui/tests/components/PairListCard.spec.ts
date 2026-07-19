import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PairListCard from '../../src/components/PairListCard.vue'
import type { NodesPayload } from '../../src/types'

const PAYLOAD: NodesPayload = {
  edge_id: 'burst_to_tb',
  total_pair: 5,
  ok_pair: 2,
  miss_reasons: { gap_out: 1, anchor_mismatch: 1, strict_fail: 1, negation_violated: 0 },
  example_failed_pairs: [
    { src_event_id: 'burst1', dst_event_id: 'tb1', subcheck_stage: 'gap_out', measured: null, threshold: null, edge_kind: 'TemporalEdge' },
    { src_event_id: 'burst2', dst_event_id: 'tb2', subcheck_stage: 'anchor_mismatch', measured: null, threshold: null, edge_kind: 'TemporalEdge' },
  ],
}

describe('PairListCard', () => {
  it('renders edge_id and pass/fail summary', () => {
    const wrapper = mount(PairListCard, { props: { payload: PAYLOAD } })
    expect(wrapper.text()).toContain('burst_to_tb')
    expect(wrapper.text()).toContain('2 / 5 通过')
    expect(wrapper.text()).toContain('3 失败')
  })

  it('renders miss_reasons distribution', () => {
    const wrapper = mount(PairListCard, { props: { payload: PAYLOAD } })
    expect(wrapper.text()).toContain('gap 越界:1')
    expect(wrapper.text()).toContain('anchor 破位:1')
    expect(wrapper.text()).toContain('strict fail:1')
  })

  it('renders one row per example_failed_pairs entry', () => {
    const wrapper = mount(PairListCard, { props: { payload: PAYLOAD } })
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('burst1')
    expect(rows[0].text()).toContain('tb1')
    expect(rows[0].text()).toContain('gap_out')
  })

  it('emits pair-deep-dive with src/dst event ids on row click', async () => {
    const wrapper = mount(PairListCard, { props: { payload: PAYLOAD } })
    await wrapper.findAll('tbody tr')[0].trigger('click')
    const emitted = wrapper.emitted('pair-deep-dive')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ src_event_id: 'burst1', dst_event_id: 'tb1' })
  })

  it('shows hint instead of table when example_failed_pairs is empty', () => {
    const empty: NodesPayload = { ...PAYLOAD, example_failed_pairs: [] }
    const wrapper = mount(PairListCard, { props: { payload: empty } })
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).toContain('无失败样例')
  })

  it('defends against missing miss_reasons keys (no_such_edge empty-dict payload)', () => {
    const sparse: NodesPayload = {
      edge_id: 'bo_to_burst', total_pair: 0, ok_pair: 0, miss_reasons: {}, example_failed_pairs: [],
    }
    const wrapper = mount(PairListCard, { props: { payload: sparse } })
    expect(wrapper.text()).toContain('gap 越界:0')
    expect(wrapper.text()).toContain('anchor 破位:0')
    expect(wrapper.text()).toContain('strict fail:0')
  })
})
