/** 看图工作流 store:草稿的增删改、发送的请求体、发送后清空、没标完不发送。 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { WorkflowList } from '../src/types'

const sendAnnotations = vi.fn()
vi.mock('../src/api', () => ({
  listWorkflowLists: vi.fn(async () => []),
  loadWorkflowList: vi.fn(),
  sendAnnotations: (...args: any[]) => sendAnnotations(...args),
}))

import { useWorkflowStore, PAGE_SIZE } from '../src/stores/workflow'
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
                                     buy_date: '2025-03-10', label: 'positive', note: 'a' })
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
                                    range_end: '2025-03-10', buy_date: '2025-03-10',
                                    label: 'positive', note: 'a' })
    expect(Object.keys(anns[0]).sort()).toEqual(
      ['ann_id', 'buy_date', 'item_id', 'label', 'note', 'range_end', 'range_start', 'symbol',
       'updated_at'])
    expect(anns[1]).toMatchObject({ item_id: i1.item_id, buy_date: null, label: 'negative' })
    expect(s.draftCount).toBe(0)
    expect(s.lastSent).toEqual({ batch_id: '20261008T101500', path: '/x/y.json', n: 2 })
  })

  it('没标完(缺起止或正反例)不发送;发送失败保留草稿', async () => {
    const s = useWorkflowStore()
    s.current = mkList()
    const id = s.current.items[0].item_id
    s.upsertAnnotation(id, { buy_date: '2025-03-10' })
    expect(await s.send()).toBe(false)
    expect(sendAnnotations).not.toHaveBeenCalled()
    expect(s.sendError).toContain('起止')
    s.upsertAnnotation(id, { range_start: '2025-01-06', range_end: '2025-03-10', label: 'negative' })
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

  it('openList 深链:翻到含该条的页、高亮并放大', async () => {
    const s = useWorkflowStore()
    const doc = mkList(8)
    ;(loadWorkflowList as any).mockResolvedValue(doc)
    await s.openList('r001', { itemId: doc.items[7].item_id })
    expect(s.groupKey).toBe('all')
    expect(s.page).toBe(1)
    expect(s.zoomItemId).toBe(doc.items[7].item_id)
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
