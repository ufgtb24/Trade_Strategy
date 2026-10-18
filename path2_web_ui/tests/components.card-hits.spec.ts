/** 卡成立日清单(只在调试模式下用):每张图只有「是」「不是」两个按钮(不框选、不点买点、不选判定);「不是」要写
 *  一句为什么才能记下;后端记上之前只取到成立日的 K 线,记上之后重取到露出终点;记不上就继续藏着并提示;
 *  打开时已经标过的直接取全段,改过的注明第一下;顶上显示标了几张,没有已标注抽屉。
 *  jsdom 没有 canvas,mock 掉 echarts.init。 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { CardMark, WorkflowItem, WorkflowList } from '../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const markResp = vi.hoisted(() => ({ fail: null as string | null }))
vi.mock('../src/api', () => ({
  getWorkflowOhlc: vi.fn(async (_s: string, _a: string, end: string) => ({
    symbol: 'C1', bars: [{ date: '2022-03-01', o: 1, h: 2, l: 0.5, c: 1.5, v: 10 },
                         { date: end, o: 1, h: 2, l: 0.5, c: 1.5, v: 10 }] })),
  recordChartView: vi.fn(async () => ({ ok: true, ts: '2026-10-18T10:00:00' })),
  postCardMark: vi.fn(async (_l: string, _i: string, verdict: 'yes' | 'no', reason: string) => {
    if (markResp.fail) throw new Error(markResp.fail)
    return { reveal_end: '2022-05-10',
             card_mark: { mark_id: 'm1', verdict, reason, ts: '2026-10-18T10:00:00', first_verdict: verdict, n: 1 } }
  }),
  listWorkflowLists: vi.fn(async () => []),
  getWorkflowState: vi.fn(async () => ({ path: '/x', from_env: false, env_var: 'X', ok: true, message: null })),
}))
let lastOption: any = null
vi.mock('echarts', () => ({ init: vi.fn(() => ({
  setOption: vi.fn((o: any) => { lastOption = o }), getOption: () => ({}), on: vi.fn(), off: vi.fn(),
  getZr: () => ({ on: vi.fn(), off: vi.fn() }), dispatchAction: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
})) }))

import { getWorkflowOhlc, postCardMark } from '../src/api'
import AnnotChart from '../src/components/AnnotChart.vue'
import WorkflowView from '../src/components/WorkflowView.vue'
import { useWorkflowStore } from '../src/stores/workflow'

const ITEM: WorkflowItem = {
  item_id: 'C1@2022-03-15', symbol: 'C1', t: '2022-03-15', entry_date: '2022-03-15',
  view_start: '2021-11-01', view_end: '2022-03-15', reveal_end: '2022-05-10',
  marks: { decision: '2022-03-15' }, metrics: {}, tags: [], card_true_runs: [['2022-03-01', '2022-03-01']],
}

function mkList(marks: Record<string, CardMark> = {}): WorkflowList {
  return { schema: 'chart_workflow.list/1', list_id: 'dbg-hits-s001-v1', kind: 'card_hits', title: '【调试】卡成立日',
           created_at: '2026-10-18T09:00:00', train_start: '2021-10-01', train_end: '2022-09-30',
           params: { card_hits: { card_lines: ['必须有:E001「收盘越过前面的峰」(按收盘越过的峰个数至少 1)'],
                                  note: '同一只股票大致只列一张' } },
           groups: [{ key: 'all', title: '全部', item_ids: [ITEM.item_id] }], items: [ITEM],
           card_marks: marks }
}

async function mountChart(marks: Record<string, CardMark> = {}) {
  const store = useWorkflowStore()
  store.current = mkList(marks)
  store.cardMarks = new Map(Object.entries(marks))
  const w = mount(AnnotChart, { props: { item: ITEM } })
  await flushPromises()
  return { w, store }
}

const lastEnd = () => vi.mocked(getWorkflowOhlc).mock.calls.at(-1)?.[2]

describe('卡成立日清单', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getWorkflowOhlc).mockClear()
    vi.mocked(postCardMark).mockClear()
    markResp.fail = null
  })

  it('只有「是 / 不是」;标之前只取到成立日', async () => {
    const { w } = await mountChart()
    expect(w.find('[data-testid="card-tools"]').exists()).toBe(true)
    for (const id of ['tool-brush', 'tool-buy', 'label-positive', 'note', 'tool-clear']) {
      expect(w.find(`[data-testid="${id}"]`).exists()).toBe(false)
    }
    expect(lastEnd()).toBe('2022-03-15')
    expect(w.find('[data-testid="decision"]').text()).toBe('卡成立日 2022-03-15')
    expect(w.find('[data-testid="card-hint"]').text()).toContain('标完才露出成立日之后的走势')
  })

  it('成立日之前卡也成立过的段画成浅灰底,写「卡也成立」', async () => {
    await mountChart()
    const areas = lastOption.series[0].markArea.data
    expect(areas).toHaveLength(1)
    expect(areas[0][0]).toMatchObject({ xAxis: '2022-03-01', name: '卡也成立' })
    expect(areas[0][1]).toEqual({ xAxis: '2022-03-15' })        // 只成立一天:画到下一根,不是零宽
  })

  it('点「不是」要写一句为什么才能记下;记上之后才取到露出终点', async () => {
    const { w } = await mountChart()
    await w.find('[data-testid="card-no"]').trigger('click')
    const submit = w.find('[data-testid="card-no-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    await w.find('[data-testid="card-reason"]').setValue('放量不在突破那天')
    await w.find('[data-testid="card-no-submit"]').trigger('click')
    await flushPromises()
    expect(postCardMark).toHaveBeenCalledWith('dbg-hits-s001-v1', ITEM.item_id, 'no', '放量不在突破那天')
    expect(lastEnd()).toBe('2022-05-10')
    expect(w.find('[data-testid="card-verdict"]').text()).toBe('已标：不是')
    expect(w.find('[data-testid="card-hint"]').text()).toContain('放量不在突破那天')
  })

  it('点「是」立刻记下,然后露出', async () => {
    const { w } = await mountChart()
    await w.find('[data-testid="card-yes"]').trigger('click')
    await flushPromises()
    expect(postCardMark).toHaveBeenCalledWith('dbg-hits-s001-v1', ITEM.item_id, 'yes', '')
    expect(lastEnd()).toBe('2022-05-10')
  })

  it('记不上:继续藏着,提示出来', async () => {
    markResp.fail = '503:调试账不可用'
    const { w } = await mountChart()
    await w.find('[data-testid="card-yes"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(getWorkflowOhlc).mock.calls.every(c => c[2] === '2022-03-15')).toBe(true)
    expect(w.find('.err').text()).toContain('调试账不可用')
    expect(w.find('[data-testid="card-verdict"]').exists()).toBe(false)
  })

  it('打开时已经标过:直接取全段,改过的注明第一下', async () => {
    const { w } = await mountChart({ [ITEM.item_id]: { mark_id: 'm2', verdict: 'no', reason: '量不够', ts: '',
                                                         first_verdict: 'yes', n: 2 } })
    expect(lastEnd()).toBe('2022-05-10')
    expect(w.find('[data-testid="card-changed"]').text()).toContain('第一下是「是」')
    expect(w.find('[data-testid="card-late"]').exists()).toBe(false)
  })

  it('揭开后才标的注明不进统计', async () => {
    const { w } = await mountChart({ [ITEM.item_id]: { mark_id: 'm3', verdict: 'yes', reason: '', ts: '',
                                                         first_verdict: 'yes', n: 1, late: true } })
    expect(w.find('[data-testid="card-late"]').text()).toContain('不进统计')
  })

  it('顶上显示标了几张,没有已标注抽屉', async () => {
    const store = useWorkflowStore()
    store.current = mkList({ [ITEM.item_id]: { mark_id: 'm1', verdict: 'yes', reason: '', ts: '', first_verdict: 'yes', n: 1 } })
    store.cardMarks = new Map(Object.entries(store.current.card_marks!))
    const w = mount(WorkflowView, { global: { stubs: { AnnotChart: true, AnnotReviewPanel: true } } })
    await flushPromises()
    expect(w.find('[data-testid="wf-card-count"]').text()).toContain('已标 1 / 1 张')
    expect(w.find('[data-testid="wf-card-lines"]').text()).toContain('必须有:E001「收盘越过前面的峰」')
    expect(w.find('[data-testid="wf-card-note"]').text()).toContain('同一只股票大致只列一张')
    expect(w.find('[data-testid="wf-drawer"]').exists()).toBe(false)
  })
})
