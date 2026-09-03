import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FailedAttemptsCard from '../../src/components/FailedAttemptsCard.vue'
import type { TimePayload } from '../../src/types'

const PAYLOAD: TimePayload = {
  frame: [100, 150],
  failed_attempts: [
    {
      failure_event_window: [105, 118], start_idx: 105, gate_idx: 118,
      anchor_bar: 118, node_id: 'tb', gate_name: 'phase2_break',
      measured: { kind: 'anchor_delta', value: -0.3, label: '破位差' },
      threshold: 0, op: null, threshold_param: null,
      evaluation_lookback: [86, 100], symbol: 'DGNX',
      code_location: '',
    },
  ],
}

describe('FailedAttemptsCard', () => {
  it('每 attempt 一张子卡', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, node: '' } })
    expect(w.findAll('.attempt-card').length).toBe(1)
  })

  it('overlap 徽标依 (start, end) vs frame 分色:严格 ⊆ → fully_inside', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, node: '' } })
    // (105, 118) 完全 ⊆ [100, 150] · 应绿色徽标
    expect(w.find('.overlap-fully_inside').exists()).toBe(true)
  })

  it('gate 判据 · fmt kind-aware 渲染(anchor_delta)', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, node: '' } })
    expect(w.text()).toContain('phase2_break')
    expect(w.text()).toContain('Δanchor=-0.300')
  })

  it('evaluation_lookback 存在时渲染参照历史', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, node: '' } })
    expect(w.text()).toContain('参照历史')
    expect(w.text()).toContain('86')
  })

  it('无 attempts 显 hint', () => {
    const empty: TimePayload = { frame: [0, 10], failed_attempts: [] }
    const w = mount(FailedAttemptsCard, { props: { payload: empty, node: '' } })
    expect(w.text()).toContain('框内无 gate 失败样例')
  })

  it('event-class 下拉 change → emit update:node', async () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, node: '' } })
    const sel = w.find<HTMLSelectElement>('.event-class-filter')
    expect(sel.exists()).toBe(true)
    // 选项动态取自 payload 实际 node_id(tb),选真实存在的值才不会被残留回退重置
    await sel.setValue('tb')
    expect(w.emitted('update:node')).toBeTruthy()
    expect(w.emitted('update:node')!.at(-1)).toEqual(['tb'])
  })
})
