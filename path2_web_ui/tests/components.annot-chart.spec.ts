/** AnnotChart:模拟 brush 事件后草稿里有起止,模拟点击后有买点(Shift 多买点、主买点规则),
 *  盲看清单不渲染上下线;大涨段清单点买点前不露结果、初始右边界、往右看过后续的记录;
 *  跨源比对不一致的提示(盲看不显示)、「数据有误」标签、判定文字随清单种类变;空心 / 实心 K 线、
 *  对数开关、证券类别;小图双击放大、放大图的滚轮缩放。
 *  jsdom 没有 canvas,mock 掉 echarts.init,改为捕获事件处理函数与 setOption 入参。 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { Bar, WorkflowItem, WorkflowList } from '../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const BARS: Bar[] = ['2025-03-10', '2025-03-11', '2025-03-12', '2025-03-13', '2025-03-14',
                     '2025-03-17'].map((d, i) => ({ date: d, o: 10 + i, h: 11 + i, l: 9 + i,
                                                      c: 10.5 + i, v: 1000, rv: 1 }))
let OHLC: Bar[] = BARS
vi.mock('../src/api', () => ({
  getWorkflowOhlc: vi.fn(async () => ({ symbol: 'AAA', bars: OHLC })),
}))

let handlers: Record<string, (p?: any) => void> = {}
let zrHandlers: Record<string, (p?: any) => void> = {}
let lastOption: any = null
let currentZoom: { start: number, end: number } | null = null   // 模拟用户滚轮缩放后的窗口
function makeFakeChart() {
  return {
    setOption: vi.fn((o: any) => { lastOption = o }),
    getOption: () => ({ ...lastOption, dataZoom: currentZoom ? [currentZoom] : lastOption?.dataZoom }),
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

import * as echarts from 'echarts'
import AnnotChart from '../src/components/AnnotChart.vue'
import { useWorkflowStore } from '../src/stores/workflow'

const ITEM: WorkflowItem = {
  item_id: 'AAA@2025-03-12', symbol: 'AAA', t: '2025-03-12', entry_date: '2025-03-13',
  view_start: '2025-03-10', view_end: '2025-03-17',
  marks: { decision: '2025-03-12', entry: '2025-03-13', up_line: 14, down_line: 8,
           peak_date: '2025-03-14' },
  metrics: { rel: 3.4, rise: 0.85, M: 0.06, max_jump: 1.8 }, tags: ['跳空'], exchange: 'NASDAQ',
  xcheck: { status: 'mismatch', n_compared: 5, n_missing: 0,
            mismatch_days: [{ date: '2025-03-13', r_ours: 4.029, r_nasdaq: -0.3714 }] },
}

function mkList(kind: WorkflowList['kind'], item: WorkflowItem): WorkflowList {
  return { schema: 'chart_workflow.list/1', list_id: 'r1', kind, title: 't',
           created_at: '2026-10-08T10:00:00', train_start: '2024-01-01', train_end: '2025-12-31',
           params: {}, groups: [{ key: 'all', title: '全部', item_ids: [item.item_id] }],
           items: [item] }
}

async function mountChart(kind: WorkflowList['kind'], item = ITEM, large = false) {
  const store = useWorkflowStore()
  store.current = mkList(kind, item)
  const w = mount(AnnotChart, { props: { item, large } })
  await flushPromises()
  return { w, store }
}

describe('AnnotChart', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    handlers = {}
    zrHandlers = {}
    lastOption = null
    currentZoom = null
    OHLC = BARS
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
    expect(store.drafts.get(ITEM.item_id)!.buy_points)
      .toEqual([{ date: '2025-03-13', primary: true }])                   // round(3.2) = 3
  })

  it('Shift + 点再加一个买点,Shift 点已有的取消;主买点实心「★买点」,其他空心「买点2」', async () => {
    const { w, store } = await mountChart('bigmoves')
    await w.find('[data-testid="tool-buy"]').trigger('click')
    zrHandlers.click({ offsetX: 100, offsetY: 50 })                          // 2025-03-13 主买点
    const fake = (echarts as any).init.mock.results.at(-1).value
    fake.convertFromPixel.mockReturnValueOnce([1, 12])
    zrHandlers.click({ offsetX: 40, offsetY: 50, event: { shiftKey: true } })   // 加 2025-03-11
    expect(store.drafts.get(ITEM.item_id)!.buy_points).toEqual([
      { date: '2025-03-13', primary: true }, { date: '2025-03-11', primary: false }])
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    const pts = lastOption.series[0].markPoint.data
    const main = pts.find((p: any) => p.name === '★买点')
    const second = pts.find((p: any) => p.name === '买点2')
    expect(main.itemStyle.color).toBe('#0f172a')
    expect(second.itemStyle.color).toBe('#ffffff')
    expect(second.itemStyle.borderColor).toBe('#0f172a')
    expect(w.find('[data-testid="ann-summary"]').text()).toContain('★2025-03-13、2025-03-11')
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { shiftKey: true } })  // Shift 点主买点 → 取消
    expect(store.drafts.get(ITEM.item_id)!.buy_points).toEqual([{ date: '2025-03-11', primary: true }])
    zrHandlers.click({ offsetX: 100, offsetY: 50 })                          // 普通点击:只留这一个
    expect(store.drafts.get(ITEM.item_id)!.buy_points).toEqual([{ date: '2025-03-13', primary: true }])
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
    const { w, store } = await mountChart('contrast')
    const lines = lastOption.series[0].markLine.data
    expect(lines.some((d: any) => d.yAxis === 14)).toBe(true)
    expect(lines.some((d: any) => d.yAxis === 8)).toBe(true)
    expect(lastOption.series[0].markPoint.data.some((p: any) => p.name === '最高点')).toBe(true)
    store.upsertAnnotation(ITEM.item_id, { range_start: '2025-03-11', range_end: '2025-03-14',
                                           buy_points: [{ date: '2025-03-14', primary: true }],
                                           label: 'negative' })
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    const area = lastOption.series[0].markArea.data[0]
    expect(area[0].xAxis).toBe('2025-03-11')
    expect(area[1].xAxis).toBe('2025-03-14')
    expect(area[0].name).toBe('反例')
    expect(area[0].itemStyle.borderType).toBe('dashed')
    expect(lastOption.series[0].markPoint.data.some((p: any) => p.name === '★买点')).toBe(true)
  })

  it('大涨段清单没有买点时不画决策日等标记、图头不显示涨幅;有买点后照常显示,窗口不动', async () => {
    const { w, store } = await mountChart('bigmoves')
    const lines = () => lastOption.series[0].markLine.data
    expect(lines()).toHaveLength(0)
    expect(lastOption.series[0].markPoint.data).toHaveLength(0)
    for (const word of ['决策日', '涨幅', '最大单日跳变', '跳空']) expect(w.text()).not.toContain(word)
    expect(w.find('[data-testid="outcome-hidden"]').exists()).toBe(true)
    currentZoom = { start: 10, end: 60 }
    store.setBuyPoint(ITEM.item_id, '2025-03-11')
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    expect(lines().map((d: any) => d.label.formatter)).toEqual(
      expect.arrayContaining(['决策日', '买入日', '上线', '下线']))
    expect(lastOption.series[0].markPoint.data.some((p: any) => p.name === '最高点')).toBe(true)
    expect(w.text()).toContain('相对涨幅')
    expect(w.text()).toContain('决策日 2025-03-12')
    expect([lastOption.dataZoom[0].start, lastOption.dataZoom[0].end]).toEqual([10, 60])
  })

  it('大涨段初始窗口:从图窗起点到决策日后 3~15 根;往右拖过它才记成点买点前看过后续', async () => {
    OHLC = Array.from({ length: 60 }, (_, i) => {
      const d = new Date(Date.UTC(2025, 2, 3 + i))
      return { date: d.toISOString().slice(0, 10), o: 10, h: 11, l: 9, c: 10.5, v: 1000, rv: 1 }
    })
    const t = OHLC[20].date
    const item = { ...ITEM, item_id: `AAA@${t}`, t, marks: { ...ITEM.marks, decision: t } }
    const { store } = await mountChart('bigmoves', item)
    const k = store.initialRight.get(item.item_id)!
    expect(k).toBeGreaterThanOrEqual(3)
    expect(k).toBeLessThanOrEqual(15)
    const dz = lastOption.dataZoom[0]
    expect(dz.startValue).toBe(0)
    expect(dz.endValue).toBe(20 + k)
    currentZoom = { startValue: 0, endValue: 20 + k } as any        // 没越过:不记
    handlers.datazoom()
    expect(store.peeked.has(item.item_id)).toBe(false)
    store.upsertAnnotation(item.item_id, { label: 'negative' })
    expect(store.drafts.get(item.item_id)!.peeked_before_buy).toBe(false)
    currentZoom = { start: 0, end: 100 }                           // 拖到最右:看过后续
    handlers.datazoom()
    expect(store.peeked.has(item.item_id)).toBe(true)
    expect(store.drafts.get(item.item_id)!.peeked_before_buy).toBe(true)
    // 放大图沿用同一个初始右边界
    store.setZoom(null)
    await mountChart('bigmoves', item, true)
    expect(lastOption.dataZoom[0].endValue).toBe(20 + k)
  })

  it('判定文字随清单种类变:大涨段「像但不买」,盲看「是我的意思 / 不是我的意思」', async () => {
    let { w } = await mountChart('bigmoves')
    expect(w.find('[data-testid="label-negative"]').element.parentElement!.textContent).toContain('像但不买')
    ;({ w } = await mountChart('contrast_blind'))
    expect(w.find('[data-testid="label-positive"]').element.parentElement!.textContent).toContain('是我的意思')
    expect(w.find('[data-testid="label-negative"]').element.parentElement!.textContent).toContain('不是我的意思')
    ;({ w } = await mountChart('contrast'))
    expect(w.find('[data-testid="label-negative"]').element.parentElement!.textContent).toContain('反例')
  })

  it('K 线涨白填充深边、跌深填充(不是红绿);量柱涨浅灰跌深灰;对数开关默认按下', async () => {
    OHLC = [{ date: '2025-03-10', o: 10, h: 11, l: 9, c: 10.5, v: 1, rv: 1 },
            { date: '2025-03-11', o: 10.5, h: 11, l: 9, c: 9.5, v: 1, rv: 1 }]
    const { w, store } = await mountChart('contrast')
    const st = lastOption.series[0].itemStyle
    expect(st).toEqual({ color: '#ffffff', color0: '#0f172a', borderColor: '#0f172a', borderColor0: '#0f172a' })
    expect(JSON.stringify(lastOption)).not.toMatch(/#47b262|#eb5454/i)
    const vol = lastOption.series[1].data
    expect(vol[0].itemStyle.color).toBe('#cbd5e1')
    expect(vol[1].itemStyle.color).toBe('#475569')
    expect(lastOption.yAxis[0].type).toBe('log')
    const btn = w.find('[data-testid="tool-log"]')
    expect(btn.attributes('aria-pressed')).toBe('true')
    await btn.trigger('click')
    expect(store.logScale).toBe(false)
    expect(lastOption.yAxis[0].type).toBe('value')
    expect(w.find('[data-testid="tool-log"]').text()).toBe('线性')
  })

  it('图头标证券类别:名录里查不到的加粗带框;旧清单没有字段就不显示', async () => {
    let { w } = await mountChart('bigmoves', { ...ITEM, sec_label: '未知（名录里查不到）', sec_known: false })
    const sec = w.find('[data-testid="sec-label"]')
    expect(sec.text()).toBe('未知（名录里查不到）')
    expect(sec.classes()).toContain('unknown')
    ;({ w } = await mountChart('bigmoves', { ...ITEM, sec_label: '普通股', sec_known: true }))
    expect(w.find('[data-testid="sec-label"]').classes()).not.toContain('unknown')
    ;({ w } = await mountChart('bigmoves'))
    expect(w.find('[data-testid="sec-label"]').exists()).toBe(false)
  })

  it('盲看清单只画决策日和买入日,不渲染上下线和最高点,头部不露结果', async () => {
    const { w } = await mountChart('contrast_blind')     // 即使 item 带了结果字段也不画
    const lines = lastOption.series[0].markLine.data
    expect(lines.every((d: any) => d.yAxis === undefined)).toBe(true)
    expect(lines.map((d: any) => d.label.formatter).sort()).toEqual(['买入日', '决策日'])
    expect(lastOption.series[0].markPoint.data).toHaveLength(0)
    expect(w.text()).not.toContain('涨幅')
    expect(w.text()).not.toContain('跳空')
    expect(w.find('[data-testid="xcheck-warn"]').exists()).toBe(false)   // 盲看不显示比对结果
  })

  it('跨源比对不一致:图头列出那几天和两边的涨跌幅;一致或取不到时不显示', async () => {
    const { w } = await mountChart('contrast')
    const warn = w.find('[data-testid="xcheck-warn"]')
    expect(warn.text()).toContain('两份数据不一致')
    expect(warn.text()).toContain('2025-03-13（我们 +402.9%，Nasdaq -37.1%）')
    expect(w.text()).toContain('最大单日跳变')
    for (const status of ['ok', 'unavailable'] as const) {
      await w.setProps({ item: { ...ITEM, xcheck: { ...ITEM.xcheck!, status, mismatch_days: [] } } })
      expect(w.find('[data-testid="xcheck-warn"]').exists()).toBe(false)
    }
    await w.setProps({ item: { ...ITEM, xcheck: undefined } })
    expect(w.find('[data-testid="xcheck-warn"]').exists()).toBe(false)
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

  it('小图双击 → 放大这一条;放大图里双击 → 退出放大', async () => {
    const { store } = await mountChart('bigmoves')
    zrHandlers.dblclick()
    expect(store.zoomItemId).toBe(ITEM.item_id)
    await mountChart('bigmoves', ITEM, true)
    zrHandlers.dblclick()
    expect(store.zoomItemId).toBeNull()
  })

  it('放大图开着点买点时双击退出:双击带出的那次点击不改买点', async () => {
    const { w, store } = await mountChart('bigmoves', ITEM, true)
    store.setZoom(ITEM.item_id)
    store.setBuyPoint(ITEM.item_id, '2025-03-11')
    await w.find('[data-testid="tool-buy"]').trigger('click')
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 1 } })
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 2 } })
    zrHandlers.dblclick()
    expect(store.zoomItemId).toBeNull()
    expect(store.drafts.get(ITEM.item_id)!.buy_points).toEqual([{ date: '2025-03-11', primary: true }])
  })

  it('点买点模式下双击:只放大,双击带出的那次点击不留买点;原有买点保持不变', async () => {
    const { w, store } = await mountChart('bigmoves')
    await w.find('[data-testid="tool-buy"]').trigger('click')
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 1 } })
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 2 } })
    zrHandlers.dblclick()
    expect(store.drafts.has(ITEM.item_id)).toBe(false)
    expect(store.zoomItemId).toBe(ITEM.item_id)

    store.upsertAnnotation(ITEM.item_id, { buy_points: [{ date: '2025-03-11', primary: true }],
                                           label: 'positive' })
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 1 } })
    expect(store.drafts.get(ITEM.item_id)!.buy_points[0].date).toBe('2025-03-13')
    zrHandlers.click({ offsetX: 100, offsetY: 50, event: { detail: 2 } })
    zrHandlers.dblclick()
    expect(store.drafts.get(ITEM.item_id)!.buy_points).toEqual([{ date: '2025-03-11', primary: true }])
    expect(store.drafts.get(ITEM.item_id)!.label).toBe('positive')
  })

  it('小图和放大图都挂滚轮缩放,同时管 K 线和成交量两根横轴,初始为全段(大涨段以外)', async () => {
    for (const large of [false, true]) {
      await mountChart('contrast', ITEM, large)
      const dz = lastOption.dataZoom[0]
      expect(dz.type).toBe('inside')
      expect(dz.xAxisIndex).toEqual([0, 1])
      expect(dz.zoomOnMouseWheel).toBe(true)
      expect([dz.start, dz.end]).toEqual([0, 100])
    }
  })

  it('小图缩放过再放大(双击或按钮),放大图从小图当时的窗口开始;关掉后窗口清空', async () => {
    const { w, store } = await mountChart('bigmoves')
    currentZoom = { start: 30, end: 70 }
    zrHandlers.dblclick()
    expect(store.zoomWindow).toEqual({ start: 30, end: 70 })
    store.setZoom(null)
    expect(store.zoomWindow).toBeNull()
    currentZoom = { start: 10, end: 50 }
    await w.find('[data-testid="tool-zoom"]').trigger('click')
    expect(store.zoomItemId).toBe(ITEM.item_id)
    expect(store.zoomWindow).toEqual({ start: 10, end: 50 })
    currentZoom = null
    await mountChart('bigmoves', ITEM, true)
    expect([lastOption.dataZoom[0].start, lastOption.dataZoom[0].end]).toEqual([10, 50])
  })

  it('缩放后改标注,重画保留缩放窗口;换一条回到全段', async () => {
    const { w, store } = await mountChart('contrast')
    currentZoom = { start: 20, end: 60 }
    store.upsertAnnotation(ITEM.item_id, { range_start: '2025-03-11', range_end: '2025-03-13' })
    await w.setProps({ annotation: store.drafts.get(ITEM.item_id)! })
    expect([lastOption.dataZoom[0].start, lastOption.dataZoom[0].end]).toEqual([20, 60])
    await w.setProps({ item: { ...ITEM, item_id: 'AAA@2025-03-13' } })
    await flushPromises()
    expect([lastOption.dataZoom[0].start, lastOption.dataZoom[0].end]).toEqual([0, 100])
  })
})
