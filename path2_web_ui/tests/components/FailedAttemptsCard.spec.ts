import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FailedAttemptsCard from '../../src/components/FailedAttemptsCard.vue'
import type { TimePayload } from '../../src/types'

const PAYLOAD: TimePayload = {
  frame: [100, 150],
  failed_attempts: [
    {
      failure_event_window: [105, 118], start_idx: 105, gate_idx: 118,
      anchor_bar: 118, class_id: 'tb', gate_name: 'phase2_break',
      measured: { kind: 'anchor_delta', value: -0.3, label: '破位差' },
      threshold: 0, op: null, threshold_param: null,
      evaluation_lookback: [86, 100], symbol: 'DGNX',
      code_location: '',
    },
  ],
}

describe('FailedAttemptsCard', () => {
  it('每 attempt 一张子卡', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, eventClass: '' } })
    expect(w.findAll('.attempt-card').length).toBe(1)
  })

  it('overlap 徽标依 (start, end) vs frame 分色:严格 ⊆ → fully_inside', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, eventClass: '' } })
    // (105, 118) 完全 ⊆ [100, 150] · 应绿色徽标
    expect(w.find('.overlap-fully_inside').exists()).toBe(true)
  })

  it('gate 判据 · fmt kind-aware 渲染(anchor_delta)', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, eventClass: '' } })
    expect(w.text()).toContain('phase2_break')
    expect(w.text()).toContain('Δanchor=-0.300')
  })

  it('evaluation_lookback 存在时渲染参照历史', () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, eventClass: '' } })
    expect(w.text()).toContain('参照历史')
    expect(w.text()).toContain('86')
  })

  it('无 attempts 显 hint', () => {
    const empty: TimePayload = { frame: [0, 10], failed_attempts: [] }
    const w = mount(FailedAttemptsCard, { props: { payload: empty, eventClass: '' } })
    expect(w.text()).toContain('框内无 gate 失败样例')
  })

  it('event-class 下拉 change → emit update:eventClass', async () => {
    const w = mount(FailedAttemptsCard, { props: { payload: PAYLOAD, eventClass: '' } })
    const sel = w.find<HTMLSelectElement>('.event-class-filter')
    expect(sel.exists()).toBe(true)
    await sel.setValue('burst')
    expect(w.emitted('update:eventClass')).toBeTruthy()
    expect(w.emitted('update:eventClass')![0]).toEqual(['burst'])
  })
})
