/** 看图工作流 store:草稿的增删改、发送的请求体、发送后清空、没标完不发送(新的必填规则)、
 *  多买点的主买点规则、初始右边界与「点买点前看过后续」、改点痕迹(第一次露出结果时的买点、
 *  看过结果后改过,清除后也留着)、状态根信息、判定文字。 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { WorkflowList } from '../src/types'

const sendAnnotations = vi.fn()
const recordChartView = vi.fn(async (..._args: any[]) => ({ ok: true, ts: '2026-10-17T10:00:00' }))
vi.mock('../src/api', () => ({
  recordChartView: (...args: any[]) => (recordChartView as any)(...args),
  listWorkflowLists: vi.fn(async () => []),
  loadWorkflowList: vi.fn(),
  getWorkflowState: vi.fn(async () => ({ path: '/tmp/st', from_env: true,
                                         env_var: 'CHART_WORKFLOW_STATE_ROOT', ok: true,
                                         message: null })),
  sendAnnotations: (...args: any[]) => sendAnnotations(...args),
}))

import { useWorkflowStore, PAGE_SIZE, missingFields, labelText, randomRight } from '../src/stores/workflow'
import { loadWorkflowList } from '../src/api'

function mkList(n = 8, kind: WorkflowList['kind'] = 'bigmoves'): WorkflowList {
  const items = Array.from({ length: n }, (_, i) => ({
    item_id: `S${i}@2025-03-${String(10 + i).padStart(2, '0')}`, symbol: `S${i}`,
    t: `2025-03-${String(10 + i).padStart(2, '0')}`, entry_date: '2025-03-20',
    view_start: '2024-09-20', view_end: '2025-05-12',
    marks: { decision: '2025-03-10', entry: '2025-03-11' }, metrics: { M: 0.05 },
    tags: i % 2 ? ['跳空'] : ['不跳空'],
  }))
  return {
    schema: 'chart_workflow.list/1', list_id: 'r001', kind, title: 't', created_at: '2026-10-08T10:00:00',
    train_start: '2024-01-01', train_end: '2025-12-31', params: {},
    groups: [{ key: 'all', title: '全部', item_ids: items.map(x => x.item_id) },
             { key: 'tail', title: '尾', item_ids: [items[n - 1].item_id] }],
    items,
  }
}

describe('workflow store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendAnnotations.mockReset()
  })

  it('upsert 新建 / 合并,delete 删除', () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.upsertAnnotation(id, { range_start: '2025-01-06', range_end: '2025-03-10' })
    expect(s.draftCount).toBe(1)
    const a1 = s.drafts.get(id)!
    expect(a1.symbol).toBe('S0')
    expect(a1.label).toBeNull()
    expect(a1.ann_id).toMatch(/[0-9a-f-]{36}/)
    s.upsertAnnotation(id, { label: 'positive', note: '放量' })
    const a2 = s.drafts.get(id)!
    expect(a2.ann_id).toBe(a1.ann_id)
    expect(a2.range_start).toBe('2025-01-06')
    expect(a2.label).toBe('positive')
    expect(a2.note).toBe('放量')
    s.upsertAnnotation(id, { note: '改了' })
    expect(s.drafts.get(id)!.note).toBe('改了')
    expect(s.draftCount).toBe(1)                     // 每个 item 最多一条
    s.deleteAnnotation(id)
    expect(s.draftCount).toBe(0)
    s.upsertAnnotation('not-in-list', { note: 'x' })
    expect(s.draftCount).toBe(0)
  })

  it('send 的请求体 = list_id + 全部草稿;成功后清空并记下批次', async () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const [i0, i1] = s.current.items
    s.upsertAnnotation(i0.item_id, { range_start: '2025-01-06', range_end: '2025-03-10',
                                     buy_points: [{ date: '2025-03-10', primary: true }],
                                     label: 'positive', note: 'a' })
    s.upsertAnnotation(i1.item_id, { range_start: '2025-02-03', range_end: '2025-03-11',
                                     label: 'negative' })
    sendAnnotations.mockResolvedValue({ batch_id: '20261008T101500', path: '/x/y.json', n: 2 })
    const ok = await s.send()
    expect(ok).toBe(true)
    expect(sendAnnotations).toHaveBeenCalledTimes(1)
    const [listId, anns] = sendAnnotations.mock.calls[0]
    expect(listId).toBe('r001')
    expect(anns).toHaveLength(2)
    expect(anns[0]).toMatchObject({ item_id: i0.item_id, symbol: 'S0', range_start: '2025-01-06',
                                    range_end: '2025-03-10',
                                    buy_points: [{ date: '2025-03-10', primary: true }],
                                    label: 'positive', note: 'a', peeked_before_buy: false,
                                    first_buy_points: [{ date: '2025-03-10', primary: true }],
                                    changed_after_reveal: false })
    expect(Object.keys(anns[0]).sort()).toEqual(
      ['ann_id', 'buy_points', 'changed_after_reveal', 'first_buy_points', 'item_id', 'label',
       'note', 'peeked_before_buy', 'range_end', 'range_start', 'symbol', 'updated_at'])
    expect(anns[1]).toMatchObject({ first_buy_points: null, changed_after_reveal: false })
    expect(anns[1]).toMatchObject({ item_id: i1.item_id, buy_points: [], label: 'negative' })
    expect(s.draftCount).toBe(0)
    expect(s.lastSent).toEqual({ batch_id: '20261008T101500', path: '/x/y.json', n: 2 })
  })

  it('没标完(缺判定)不发送;发送失败保留草稿', async () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.setBuyPoint(id, '2025-03-10')
    expect(await s.send()).toBe(false)
    expect(sendAnnotations).not.toHaveBeenCalled()
    expect(s.sendError).toContain('标签')
    s.upsertAnnotation(id, { label: 'negative' })                   // 不框也能发
    sendAnnotations.mockRejectedValue(new Error('发送失败(400):bad'))
    expect(await s.send()).toBe(false)
    expect(s.draftCount).toBe(1)
    expect(s.sendError).toContain('400')
  })

  it('分页、标签筛选与 gotoItem', () => {
    const s = useWorkflowStore()
    s.current = mkList(8)
    s.setGroup('all')
    expect(s.pageItems).toHaveLength(PAGE_SIZE)
    expect(s.pageCount).toBe(2)
    s.setTagFilter('跳空')
    expect(s.filteredItems).toHaveLength(4)
    expect(s.pageCount).toBe(1)
    s.gotoItem(s.current.items[6].item_id)           // 不跳空、在第 2 页 → 清掉筛选并翻页
    expect(s.tagFilter).toBe('')
    expect(s.page).toBe(1)
    expect(s.highlightItemId).toBe(s.current.items[6].item_id)
  })

  it('openList 深链:翻到含该条的页、高亮并放大(从全段开始)', async () => {
    const s = useWorkflowStore()
    const doc = mkList(8)
    ;(loadWorkflowList as any).mockResolvedValue(doc)
    s.setZoom(doc.items[0].item_id, { start: 20, end: 60 })      // 上一次放大留下的窗口不能带过来
    await s.openList('r001', { itemId: doc.items[7].item_id })
    expect(s.groupKey).toBe('all')
    expect(s.page).toBe(1)
    expect(s.zoomItemId).toBe(doc.items[7].item_id)
    expect(s.zoomWindow).toBeNull()
    expect(s.highlightItemId).toBe(doc.items[7].item_id)
  })

  it('数据有误标签照常发送', async () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.upsertAnnotation(id, { range_start: '2025-01-06', range_end: '2025-01-08',
                             label: 'data_error', note: '和 Nasdaq 对不上' })
    sendAnnotations.mockResolvedValue({ batch_id: 'b', path: '/p', n: 1 })
    expect(await s.send()).toBe(true)
    expect(sendAnnotations.mock.calls[0][1][0]).toMatchObject({ label: 'data_error',
                                                                note: '和 Nasdaq 对不上' })
  })

})


describe('workflow store · 阶段 0 补丁', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendAnnotations.mockReset()
  })

  it('missingFields:判定必填;数据有误要起止;正例要至少一个买点;其余不要求框选', () => {
    const base = { ann_id: 'x', item_id: 'i', symbol: 'S', range_start: null, range_end: null,
                   buy_points: [], label: null, note: '', peeked_before_buy: false, updated_at: '' }
    expect(missingFields(base as any)).toEqual(['标签'])
    expect(missingFields({ ...base, label: 'positive' } as any)).toEqual(['买点'])
    expect(missingFields({ ...base, label: 'positive',
                           buy_points: [{ date: '2025-03-10', primary: true }] } as any)).toEqual([])
    expect(missingFields({ ...base, label: 'negative' } as any)).toEqual([])
    expect(missingFields({ ...base, label: 'data_error' } as any)).toEqual(['起止'])
    expect(missingFields({ ...base, label: 'data_error', range_start: '2025-01-02',
                           range_end: '2025-01-03' } as any)).toEqual([])
  })

  it('setBuyPoint 只留一个主买点;toggleBuyPoint 加 / 去,去掉主买点时最早加入的接任', () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.toggleBuyPoint(id, '2025-03-05')
    s.toggleBuyPoint(id, '2025-03-03')
    s.toggleBuyPoint(id, '2025-03-07')
    expect(s.drafts.get(id)!.buy_points).toEqual([
      { date: '2025-03-05', primary: true }, { date: '2025-03-03', primary: false },
      { date: '2025-03-07', primary: false }])
    s.toggleBuyPoint(id, '2025-03-05')
    expect(s.drafts.get(id)!.buy_points).toEqual([
      { date: '2025-03-03', primary: true }, { date: '2025-03-07', primary: false }])
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)!.buy_points).toEqual([{ date: '2025-03-10', primary: true }])
    s.toggleBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)!.buy_points).toEqual([])
  })

  it('打开清单时每张图随机一个初始右边界(3~15);看过后续记进草稿', async () => {
    const s = useWorkflowStore()
    const doc = mkList(8)
    ;(loadWorkflowList as any).mockResolvedValue(doc)
    await s.openList('r001')
    for (const it of doc.items) {
      const k = s.initialRight.get(it.item_id)!
      expect(k >= 3 && k <= 15).toBe(true)
    }
    expect(randomRight(() => 0)).toBe(3)
    expect(randomRight(() => 0.9999)).toBe(15)
    const [a, b] = doc.items
    s.upsertAnnotation(a.item_id, { label: 'negative' })
    s.markPeeked(a.item_id)
    expect(s.drafts.get(a.item_id)!.peeked_before_buy).toBe(true)
    s.markPeeked(b.item_id)
    s.upsertAnnotation(b.item_id, { label: 'negative' })
    expect(s.drafts.get(b.item_id)!.peeked_before_buy).toBe(true)
    s.upsertAnnotation(b.item_id, { note: 'x' })
    expect(s.drafts.get(b.item_id)!.peeked_before_buy).toBe(true)
    expect(s.logScale).toBe(true)
    s.toggleLogScale()
    expect(s.logScale).toBe(false)
  })

  it('判定文字随清单种类变,存的值不变', () => {
    expect(labelText('negative', 'bigmoves')).toBe('像但不买')
    expect(labelText('positive', 'bigmoves')).toBe('正例')
    expect(labelText('positive', 'contrast_blind')).toBe('是我的意思')
    expect(labelText('negative', 'contrast_blind')).toBe('不是我的意思')
    expect(labelText('negative', 'contrast')).toBe('反例')
    expect(labelText('data_error', 'bigmoves')).toBe('数据有误')
  })
})


describe('workflow store · 改点痕迹', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendAnnotations.mockReset()
  })

  it('先随手点一个买点看到结果,再普通点击改到别处:记下第一次的买点,标「看过结果后改过」', () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.upsertAnnotation(id, { label: 'positive' })                 // 只选判定:结果还没露
    expect(s.drafts.get(id)).toMatchObject({ first_buy_points: null, changed_after_reveal: false })
    s.setBuyPoint(id, '2025-03-14')                              // 结果此刻露出
    expect(s.drafts.get(id)).toMatchObject({
      first_buy_points: [{ date: '2025-03-14', primary: true }], changed_after_reveal: false })
    s.upsertAnnotation(id, { note: '备注' })                      // 改别的不算
    expect(s.drafts.get(id)!.changed_after_reveal).toBe(false)
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)).toMatchObject({
      buy_points: [{ date: '2025-03-10', primary: true }],
      first_buy_points: [{ date: '2025-03-14', primary: true }], changed_after_reveal: true })
  })

  it('先点买点看到结果,再「清除」重点:痕迹留着,还记成点买点前看过后续', () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.setBuyPoint(id, '2025-03-14')
    s.deleteAnnotation(id)
    expect(s.drafts.has(id)).toBe(false)
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)).toMatchObject({
      buy_points: [{ date: '2025-03-10', primary: true }],
      first_buy_points: [{ date: '2025-03-14', primary: true }],
      changed_after_reveal: true, peeked_before_buy: true })
  })

  it('Shift 加点、去点都算改过;去掉全部买点也记看过后续', () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const [a, b] = s.current.items.map(it => it.item_id)
    s.toggleBuyPoint(a, '2025-03-14')
    s.toggleBuyPoint(a, '2025-03-17')                            // 加一个
    expect(s.drafts.get(a)!.changed_after_reveal).toBe(true)
    expect(s.drafts.get(a)!.first_buy_points).toEqual([{ date: '2025-03-14', primary: true }])
    s.toggleBuyPoint(b, '2025-03-14')
    s.toggleBuyPoint(b, '2025-03-14')                            // 去掉唯一的买点
    expect(s.drafts.get(b)).toMatchObject({ buy_points: [], changed_after_reveal: true,
                                            peeked_before_buy: true })
  })

  it('重新打开同一份清单、切走再切回,痕迹都还在;不同清单的同名条目各记各的', async () => {
    const s = useWorkflowStore()
    const doc = mkList()
    ;(loadWorkflowList as any).mockResolvedValue(doc)
    await s.openList('r001')
    const id = doc.items[0].item_id
    s.setBuyPoint(id, '2025-03-14')
    s.deleteAnnotation(id)
    s.markPeeked(doc.items[1].item_id)
    await s.openList('r001')                                     // 没有草稿,不用确认
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)!.changed_after_reveal).toBe(true)
    expect(s.isPeeked(doc.items[1].item_id)).toBe(true)
    s.clearDrafts()
    const other = { ...mkList(), list_id: 'r009' }
    ;(loadWorkflowList as any).mockResolvedValue(other)
    await s.openList('r009')
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)).toMatchObject({ changed_after_reveal: false, peeked_before_buy: false })
  })

  it('只在大涨段清单记痕迹:对照清单一开始就看得到结果', () => {
    const s = useWorkflowStore()
    s.current = mkList(8, 'contrast')
    const id = s.current.items[0].item_id
    s.setBuyPoint(id, '2025-03-14')
    s.setBuyPoint(id, '2025-03-10')
    expect(s.drafts.get(id)).toMatchObject({ first_buy_points: null, changed_after_reveal: false })
  })

  it('loadLists 顺带取状态根信息;取不到时为 null', async () => {
    const s = useWorkflowStore()
    await s.loadLists()
    expect(s.stateInfo).toMatchObject({ path: '/tmp/st', from_env: true })
    const api = await import('../src/api')
    ;(api.getWorkflowState as any).mockRejectedValueOnce(new Error('503'))
    await s.loadLists()
    expect(s.stateInfo).toBeNull()
  })
})

describe('workflow store · 单张图的看过事件', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendAnnotations.mockReset()
    recordChartView.mockClear()
  })
  const calls = () => recordChartView.mock.calls.map((c: any[]) => c.slice(1, 3).join(':'))

  it('放大、点买点 / 选判定、露出结果各记一次;重新打开清单再记', async () => {
    const s = useWorkflowStore()
    const doc = mkList()
    ;(loadWorkflowList as any).mockResolvedValue(doc)
    await s.openList('r001')
    const [a, b] = doc.items.map(it => it.item_id)
    s.setZoom(a)
    s.setZoom(null)
    s.setZoom(a)                                        // 同一次打开里再放大:不再记
    s.upsertAnnotation(a, { note: '只写备注' })          // 备注不算标注
    expect(calls()).toEqual([`${a}:zoom`])
    s.upsertAnnotation(a, { label: 'negative' })
    s.setBuyPoint(a, '2025-03-14')                       // 大涨段:结果此刻露出
    s.setBuyPoint(a, '2025-03-10')
    expect(calls()).toEqual([`${a}:zoom`, `${a}:annotate`, `${a}:reveal`])
    const reveal = recordChartView.mock.calls.find((c: any[]) => c[2] === 'reveal')!
    expect(reveal[0]).toBe('r001')
    expect(reveal[3]).toEqual([{ date: '2025-03-14', primary: true }])
    s.setZoom(b)
    expect(calls().at(-1)).toBe(`${b}:zoom`)
    s.clearDrafts()
    await s.openList('r001')
    s.setZoom(a)
    expect(calls().filter(c => c === `${a}:zoom`)).toHaveLength(2)
  })

  it('对照清单不记 reveal;记不进去时写说明,下次可以再记', async () => {
    const s = useWorkflowStore()
    s.current = mkList(8, 'contrast')
    const id = s.current.items[0].item_id
    s.setBuyPoint(id, '2025-03-14')
    expect(calls()).toEqual([`${id}:annotate`])
    recordChartView.mockRejectedValueOnce(new Error('503:状态根不可用'))
    s.setZoom(id)
    await new Promise(r => setTimeout(r, 0))
    expect(s.viewError).toContain('503')
    s.setZoom(id)
    expect(calls().filter(c => c === `${id}:zoom`)).toHaveLength(2)
  })

  it('发送标注前先等单张图事件落地(reveal 要在标注之前记上)', async () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    const waiting: Array<() => void> = []
    recordChartView.mockImplementation(() => new Promise(r => { waiting.push(() => r({ ok: true })) }) as any)
    s.upsertAnnotation(id, { label: 'positive', buy_points: [{ date: '2025-03-14', primary: true }] })
    sendAnnotations.mockResolvedValue({ batch_id: 'b', path: '/x', n: 1 })
    const done = s.send()
    await new Promise(r => setTimeout(r, 0))
    expect(sendAnnotations).not.toHaveBeenCalled()
    expect(waiting).toHaveLength(2)                      // reveal + annotate
    waiting.forEach(f => f())
    expect(await done).toBe(true)
    expect(sendAnnotations).toHaveBeenCalledTimes(1)
    recordChartView.mockImplementation(async () => ({ ok: true, ts: '' }) as any)
  })
})
