/** AnnotChart:模拟 brush 事件后草稿里有起止,模拟点击后有买点,盲看清单不渲染上下线;
 *  TradingView 链接(新标签页、盲看不给)、「数据有误」标签。
 *  jsdom 没有 canvas,mock 掉 echarts.init,改为捕获事件处理函数与 setOption 入参。 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { Bar, WorkflowItem, WorkflowList } from '../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const BARS: Bar[] = ['2025-03-10', '2025-03-11', '2025-03-12', '2025-03-13', '2025-03-14',
                     '2025-03-17'].map((d, i) => ({ date: d, o: 10 + i, h: 11 + i, l: 9 + i,
                                                      c: 10.5 + i, v: 1000, rv: 1 }))
vi.mock('../src/api', () => ({
  getWorkflowOhlc: vi.fn(async () => ({ symbol: 'AAA', bars: BARS })),
}))

let handlers: Record<string, (p?: any) => void> = {}
let zrHandlers: Record<string, (p?: any) => void> = {}
let lastOption: any = null
function makeFakeChart() {
  return {
    setOption: vi.fn((o: any) => { lastOption = o }),
    on: vi.fn((ev: string, fn: any) => { handlers[ev] = fn }),
    off: vi.fn(),
    getZr: () => ({ on: (ev: string, fn: any) => { zrHandlers[ev] = fn }, off: vi.fn() }),
    dispatchAction: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    containPixel: vi.fn(() => true),
    convertFromPixel: vi.fn(() => [3.2, 12]),
  }
}
vi.mock('echarts', () => ({ init: vi.fn(() => makeFakeChart()) }))

import AnnotChart from '../src/components/AnnotChart.vue'
import { useWorkflowStore } from '../src/stores/workflow'

const ITEM: WorkflowItem = {
  item_id: 'AAA@2025-03-12', symbol: 'AAA', t: '2025-03-12', entry_date: '2025-03-13',
  view_start: '2025-03-10', view_end: '2025-03-17',
  marks: { decision: '2025-03-12', entry: '2025-03-13', up_line: 14, down_line: 8,
           peak_date: '2025-03-14' },
  metrics: { rel: 3.4, rise: 0.85, M: 0.06, max_jump: 1.8 }, tags: ['跳空'], exchange: 'NASDAQ',
}

function mkList(kind: WorkflowList['kind'], item: WorkflowItem): WorkflowList {
  return { schema: 'chart_workflow.list/1', list_id: 'r1', kind, title: 't',
           created_at: '2026-10-08T10:00:00', train_start: '2024-01-01', train_end: '2025-12-31',
           params: {}, groups: [{ key: 'all', title: '全部', item_ids: [item.item_id] }],
           items: [item] }
}

async function mountChart(kind: WorkflowList['kind'], item = ITEM) {
  const store = useWorkflowStore()
  store.current = mkList(kind, item)
  const w = mount(AnnotChart, { props: { item } })
  await flushPromises()
  return { w, store }
}

describe('AnnotChart', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    handlers = {}
    zrHandlers = {}
    lastOption = null
  })

  it('brush 事件 → 草稿里有起止日期', async () => {
    const { w, store } = await mountChart('bigmoves')
    await w.find('[data-testid="tool-brush"]').trigger('click')
    handlers.brushselected({ batch: [{ areas: [{ coordRange: [1, 4] }] }] })
    handlers.brushEnd()
    const a = store.drafts.get(ITEM.item_id)!
    expect(a.range_start).toBe('2025-03-11')
    expect(a.range_end).toBe('2025-03-14')
  })

  it('点买点模式下点击 → 草稿里有买点;未开启时点击无效', async () => {
    const { w, store } = await mountChart('bigmoves')
    zrHandlers.click({ offsetX: 100, offsetY: 50 })
    expect(store.drafts.get(ITEM.item_id)).toBeUndefined()
    await w.find('[data-testid="tool-buy"]').trigger('click')
    zrHandlers.click({ offsetX: 100, offsetY: 50 })
    expect(store.drafts.get(ITEM.item_id)!.buy_date).toBe('2025-03-13')   // round(3.2) = 3
  })

  it('正例 / 反例 / 备注 / 清除', async () => {
    const { w, store } = await mountChart('bigmoves')
    await w.find('[data-testid="label-negative"]').setValue(true)
    expect(store.drafts.get(ITEM.item_id)!.label).toBe('negative')
    await w.find('[data-testid="note"]').setValue('长期横盘')
    expect(store.drafts.get(ITEM.item_id)!.note).toBe('长期横盘')
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    await w.find('[data-testid="tool-clear"]').trigger('click')
    expect(store.drafts.has(ITEM.item_id)).toBe(false)
  })

  it('普通清单画上下线与最高点;用户标注画成 markArea 与买点', async () => {
    const { w, store } = await mountChart('bigmoves')
    const lines = lastOption.series[0].markLine.data
    expect(lines.some((d: any) => d.yAxis === 14)).toBe(true)
    expect(lines.some((d: any) => d.yAxis === 8)).toBe(true)
    expect(lastOption.series[0].markPoint.data.some((p: any) => p.name === '最高点')).toBe(true)
    store.upsertAnnotation(ITEM.item_id, { range_start: '2025-03-11', range_end: '2025-03-14',
                                           buy_date: '2025-03-14', label: 'negative' })
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    const area = lastOption.series[0].markArea.data[0]
    expect(area[0].xAxis).toBe('2025-03-11')
    expect(area[1].xAxis).toBe('2025-03-14')
    expect(area[0].name).toBe('反例')
    expect(area[0].itemStyle.borderType).toBe('dashed')
    expect(lastOption.series[0].markPoint.data.some((p: any) => p.name === '买点')).toBe(true)
  })

  it('盲看清单只画决策日和买入日,不渲染上下线和最高点,头部不露结果', async () => {
    const { w } = await mountChart('contrast_blind')     // 即使 item 带了结果字段也不画
    const lines = lastOption.series[0].markLine.data
    expect(lines.every((d: any) => d.yAxis === undefined)).toBe(true)
    expect(lines.map((d: any) => d.label.formatter).sort()).toEqual(['买入日', '决策日'])
    expect(lastOption.series[0].markPoint.data).toHaveLength(0)
    expect(w.text()).not.toContain('涨幅')
    expect(w.text()).not.toContain('跳空')
    expect(w.find('[data-testid="tv-link"]').exists()).toBe(false)   // TradingView 会露出之后的走势
  })

  it('TradingView 链接在新标签页打开;没有交易所时只用代码', async () => {
    const { w } = await mountChart('bigmoves')
    const a = w.find('[data-testid="tv-link"]')
    expect(a.attributes('href')).toBe('https://www.tradingview.com/chart/?symbol=NASDAQ:AAA')
    expect(a.attributes('target')).toBe('_blank')
    expect(a.attributes('rel')).toContain('noopener')
    expect(w.text()).toContain('最大单日跳变')
    await w.setProps({ item: { ...ITEM, exchange: null } })
    expect(w.find('[data-testid="tv-link"]').attributes('href'))
      .toBe('https://www.tradingview.com/chart/?symbol=AAA')
  })

  it('「数据有误」标签:写进草稿,范围用点线框并写明', async () => {
    const { w, store } = await mountChart('bigmoves')
    await w.find('[data-testid="label-data-error"]').setValue(true)
    expect(store.drafts.get(ITEM.item_id)!.label).toBe('data_error')
    store.upsertAnnotation(ITEM.item_id, { range_start: '2025-03-11', range_end: '2025-03-13' })
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    const area = lastOption.series[0].markArea.data[0]
    expect(area[0].name).toBe('数据有误')
    expect(area[0].itemStyle.borderType).toBe('dotted')
  })
})
