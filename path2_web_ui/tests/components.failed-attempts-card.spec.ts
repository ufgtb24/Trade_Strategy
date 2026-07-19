import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FailedAttemptsCard from '../src/components/FailedAttemptsCard.vue'
import type { GateFailure, TimePayload } from '../src/types'

function makeGate(overrides: Partial<GateFailure>): GateFailure {
  return {
    failure_event_window: [155, 159],
    start_idx: 155,
    gate_idx: 159,
    anchor_bar: 154,
    class_id: 'tb',
    gate_name: 'stub',
    measured: { kind: 'count', value: 5, label: '' },
    threshold: 5,
    op: null,
    threshold_param: null,
    evaluation_lookback: null,
    symbol: 'TEST',
    code_location: 'breakout.py:138',
    ...overrides,
  }
}

function mountCard(gate: GateFailure) {
  const payload: TimePayload = { frame: [150, 160], failed_attempts: [gate] }
  return mount(FailedAttemptsCard, {
    props: { payload, eventClass: '' },
  })
}

describe('FailedAttemptsCard · clause 结构化', () => {
  it('真阈值型 gate 渲染 `${value} ${op} ${threshold} (${param}) ✗`', () => {
    const gate = makeGate({
      class_id: 'bo',
      gate_name: 'peak_side_bars_insufficient',
      measured: { kind: 'side_bars_offset', value: 3, label: '' },
      threshold: 6,
      op: '>=',
      threshold_param: 'min_side_bars',
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('3')
    expect(clause).toContain('>=')
    expect(clause).toContain('6')
    expect(clause).toContain('(min_side_bars)')
    expect(clause).toContain('✗')
    // gate_name 独立成行
    expect(wrapper.find('.gate').text()).toContain('peak_side_bars_insufficient')
  })

  it('sentinel/timeout 型 gate 降级渲染 `${value} ✗`', () => {
    const gate = makeGate({
      class_id: 'tb',
      gate_name: 'phase1_no_trough_timeout',
      measured: { kind: 'count', value: 5, label: '触发次数' },
      threshold: 5,
      op: null,
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('5')
    expect(clause).toContain('✗')
    // 不应出现 op 或 (param)
    expect(clause).not.toMatch(/>=|<=|==/)
    expect(clause).not.toMatch(/\([a-z_]+\)/)
    expect(wrapper.find('.gate').text()).toContain('phase1_no_trough_timeout')
  })
})

describe('FailedAttemptsCard · sentinel-numeric 分支', () => {
  it('op 非 null 且 threshold_param 为 null 时,渲染 `${value} ${op} ${threshold} ✗` 不带括号', () => {
    const gate = makeGate({
      class_id: 'tb',
      gate_name: 'phase1_break',
      measured: { kind: 'anchor_delta', value: -0.2, label: '破位差' },
      threshold: 0.0,
      op: '>=',
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('>=')
    expect(clause).toMatch(/-?\d+(\.\d+)?\s*>=\s*0/)   // value >= 0 形状,而非仅松散含 '0'
    expect(clause).toContain('✗')
    expect(clause).not.toMatch(/\([a-z_]+\)/)   // 无 (param) 括号
  })
})

describe('FailedAttemptsCard · degraded 分支加 label 前缀', () => {
  it('op=null 时,渲染 `${measured.label}: ${value} ✗`', () => {
    const gate = makeGate({
      class_id: 'bo',
      gate_name: 'no_active_peak_broken',
      measured: { kind: 'breakout_price', value: 42.10, label: '突破价' },
      threshold: null,
      op: null,
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('突破价:')
    expect(clause).toMatch(/突破价:\s*42/)   // 冒号 + label + 值须连在一起出现
    expect(clause).toContain('✗')
    expect(clause).not.toMatch(/>=|<=|==/)
  })
})

describe('FailedAttemptsCard · code_location 展示', () => {
  it('非空时渲染 .code-location', () => {
    const gate = makeGate({ code_location: 'throwback.py:136' })
    const wrapper = mountCard(gate)
    expect(wrapper.find('.code-location').exists()).toBe(true)
    expect(wrapper.find('.code-location').text()).toContain('throwback.py:136')
  })

  it('空串时不渲染 .code-location(v-if truthy 过滤)', () => {
    const gate = makeGate({ code_location: '' })
    const wrapper = mountCard(gate)
    expect(wrapper.find('.code-location').exists()).toBe(false)
  })
})
