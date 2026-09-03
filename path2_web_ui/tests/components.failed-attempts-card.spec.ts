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
    node_id: 'tb',
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
    props: { payload, node: '' },
  })
}

describe('FailedAttemptsCard · clause 结构化', () => {
  it('真阈值型 gate 渲染 `${value} ${op} ${threshold} (${param}) ✗`', () => {
    const gate = makeGate({
      node_id: 'bo',
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
      node_id: 'tb',
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
      node_id: 'tb',
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
      node_id: 'bo',
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

describe('FailedAttemptsCard · 动态 class 过滤选项', () => {
  it('all_nodes 缺失时回退实际失败集(全部可选,不硬编码 tb)', () => {
    const payload: TimePayload = {
      frame: [150, 160],
      failed_attempts: [
        makeGate({ node_id: 'bo' }),
        makeGate({ node_id: 'tb_v1', failure_event_window: [155, 159] }),
        makeGate({ node_id: 'burst' }),
        makeGate({ node_id: 'bo', failure_event_window: [156, 158] }),
      ],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: '' } })
    const options = wrapper.findAll('select.event-class-filter option').map(o => o.text())
    // '全部' 固定首项;其余 = 去重排序后的真实 node_id
    expect(options[0]).toBe('全部')
    expect(options.slice(1)).toEqual(['bo', 'burst', 'tb_v1'])
    expect(options).not.toContain('tb')   // 硬编码旧词不再出现
  })

  it('all_nodes 全集渲染:无失败的 node 置灰 disabled、有失败的 enabled', () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'burst', 'tb', 'tb_seg'],
      failed_attempts: [
        makeGate({ node_id: 'bo' }),
        makeGate({ node_id: 'burst' }),
        makeGate({ node_id: 'bo', failure_event_window: [156, 158] }),
      ],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: '' } })
    const opts = wrapper.findAll('select.event-class-filter option')
    const texts = opts.map(o => o.text())
    // 全集可见:tb / tb_seg 存在(即使本区间零失败),但置灰不可选
    expect(texts).toEqual(['全部', 'bo', 'burst', 'tb', 'tb_seg'])
    const disabled = (c: string) => opts.find(o => o.text() === c)!.attributes('disabled') !== undefined
    expect(disabled('bo')).toBe(false)
    expect(disabled('burst')).toBe(false)
    expect(disabled('tb')).toBe(true)
    expect(disabled('tb_seg')).toBe(true)
  })

  it('all_nodes ∪ 实际失败:后端漏发的失败类型仍可选', () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'burst'],
      failed_attempts: [makeGate({ node_id: 'tb_v1' })],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: '' } })
    const opts = wrapper.findAll('select.event-class-filter option')
    const texts = opts.map(o => o.text())
    expect(texts).toEqual(['全部', 'bo', 'burst', 'tb_v1'])
    expect(opts.find(o => o.text() === 'tb_v1')!.attributes('disabled')).toBeUndefined()
  })

  it('node 残留(该区间无失败,置灰)→ 自动回退空(全部)', async () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'tb'],
      failed_attempts: [makeGate({ node_id: 'bo' })],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: 'tb' } })
    // watch(failedNodes) 触发后 emit update:node ''
    await new Promise(r => setTimeout(r, 0))
    expect(wrapper.emitted('update:node')).toBeTruthy()
    expect(wrapper.emitted('update:node')![0]).toEqual([''])
  })

  it('node 指向有失败的 class 时不触发回退', async () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'tb'],
      failed_attempts: [makeGate({ node_id: 'tb' })],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: 'tb' } })
    await new Promise(r => setTimeout(r, 0))
    expect(wrapper.emitted('update:node')).toBeFalsy()
  })
})

describe('FailedAttemptsCard · 本地过滤显示(不重新请求)', () => {
  it('node 非空 → 只显示该 class 的 attempt、计数跟随', () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'burst'],
      failed_attempts: [
        makeGate({ node_id: 'bo' }),
        makeGate({ node_id: 'burst' }),
        makeGate({ node_id: 'bo', failure_event_window: [156, 158] }),
      ],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: 'bo' } })
    expect(wrapper.findAll('.attempt-card').length).toBe(2)
    expect(wrapper.find('header').text()).toContain('框内 2 个 attempt')
    expect(wrapper.findAll('.node-id').map(e => e.text())).toEqual(['bo', 'bo'])
  })

  it("node=''(全部) → 显示全部 attempt", () => {
    const payload: TimePayload = {
      frame: [150, 160],
      all_nodes: ['bo', 'burst'],
      failed_attempts: [
        makeGate({ node_id: 'bo' }),
        makeGate({ node_id: 'burst' }),
      ],
    }
    const wrapper = mount(FailedAttemptsCard, { props: { payload, node: '' } })
    expect(wrapper.findAll('.attempt-card').length).toBe(2)
    expect(wrapper.find('header').text()).toContain('框内 2 个 attempt')
  })
})
