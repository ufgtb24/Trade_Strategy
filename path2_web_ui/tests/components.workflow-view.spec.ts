/** WorkflowView 翻页:页码框输入跳转(越界夹到首末页、非数字回显当前页)、PgUp / PgDn 翻页;
 *  焦点在文字输入框里或放大框开着时不接管 PgUp / PgDn。图格与抽屉用桩替掉。 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { WorkflowList } from '../src/types'

function mkList(n: number): WorkflowList {
  const items = Array.from({ length: n }, (_, i) => ({
    item_id: `S${i}@2025-03-10`, symbol: `S${i}`, t: '2025-03-10', entry_date: '2025-03-11',
    view_start: '2024-09-20', view_end: '2025-05-12',
    marks: { decision: '2025-03-10', entry: '2025-03-11' }, metrics: { M: 0.05 }, tags: [],
  }))
  return {
    schema: 'chart_workflow.list/1', list_id: 'r001', kind: 'bigmoves', title: 't',
    created_at: '2026-10-08T10:00:00', train_start: '2024-01-01', train_end: '2025-12-31', params: {},
    groups: [{ key: 'all', title: '全部', item_ids: items.map(x => x.item_id) }], items,
  }
}

vi.mock('../src/api', () => ({
  listWorkflowLists: vi.fn(async () => [{ list_id: 'r001', kind: 'bigmoves', title: 't', n_items: 20,
                                          created_at: '2026-10-08T10:00:00' }]),
  loadWorkflowList: vi.fn(async () => mkList(20)),           // 20 条 → 4 页
  sendAnnotations: vi.fn(),
}))

import WorkflowView from '../src/components/WorkflowView.vue'
import { useWorkflowStore } from '../src/stores/workflow'
import { listWorkflowLists, loadWorkflowList } from '../src/api'

let w: VueWrapper
async function mountView() {
  w = mount(WorkflowView, { attachTo: document.body,
                            global: { stubs: { AnnotChart: true, AnnotReviewPanel: true } } })
  await flushPromises()
  return useWorkflowStore()
}
function key(k: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }))
}

describe('WorkflowView 翻页', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

  it('页码框:输入后跳到那一页;越界夹到首末页;不是数字时回显当前页', async () => {
    const store = await mountView()
    const input = w.find('[data-testid="wf-page-input"]')
    const el = input.element as HTMLInputElement
    expect(el.value).toBe('1')
    expect(w.find('.pager').text()).toContain('/ 4 页')
    await input.setValue('3')
    expect(store.page).toBe(2)
    await input.setValue('99')
    expect(store.page).toBe(3)
    expect(el.value).toBe('4')
    await input.setValue('0')
    expect(store.page).toBe(0)
    expect(el.value).toBe('1')
    await input.setValue('')
    expect(store.page).toBe(0)
    expect(el.value).toBe('1')
  })

  it('PgDn / PgUp 翻页,到头不再翻', async () => {
    const store = await mountView()
    key('PageUp')
    expect(store.page).toBe(0)
    for (let i = 0; i < 5; i++) key('PageDown')
    expect(store.page).toBe(3)
    key('PageUp')
    expect(store.page).toBe(2)
    await w.vm.$nextTick()
    expect((w.find('[data-testid="wf-page-input"]').element as HTMLInputElement).value).toBe('3')
  })

  it('焦点在文字输入框里不接管 PgDn;单选框、按钮上照样翻页;放大框开着时不翻', async () => {
    const store = await mountView()
    const text = document.createElement('input')
    text.type = 'text'
    document.body.appendChild(text)
    key('PageDown', text)
    key('PageDown', w.find('[data-testid="wf-page-input"]').element)
    expect(store.page).toBe(0)
    const radio = document.createElement('input')
    radio.type = 'radio'
    document.body.appendChild(radio)
    key('PageDown', radio)
    expect(store.page).toBe(1)
    key('PageDown', w.find('[data-testid="wf-drawer"]').element)
    expect(store.page).toBe(2)
    store.setZoom(store.pageItems[0].item_id)
    key('PageDown')
    expect(store.page).toBe(2)
  })
})


describe('WorkflowView 记账类文件不可用 / 打不开清单', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

  it('清单目录带 blocked:在下拉上方显示后端给的消息;打开清单得到 503 时显示后端正文', async () => {
    const msg = '状态根 /x 下没有标记文件 STATE_ROOT.md:主目录当前分支没有记账文件,可能切到了别的分支。'
    ;(listWorkflowLists as any).mockResolvedValueOnce([
      { list_id: 'r001', kind: 'bigmoves', title: 't', n_items: 20, created_at: '2026-10-08T10:00:00',
        blocked: 'state_root_missing', blocked_message: msg }])
    ;(loadWorkflowList as any).mockRejectedValueOnce(new Error(`503:${msg}`))
    await mountView()
    const blocked = w.find('[data-testid="wf-blocked"]')
    expect(blocked.text()).toContain('可能切到了别的分支')
    const html = w.html()
    expect(html.indexOf('wf-blocked')).toBeLessThan(html.indexOf('data-testid="wf-list"'))
    expect(w.find('[data-testid="wf-load-error"]').text()).toContain('503')
  })
})


describe('WorkflowView 标签筛选', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

  function tagged(kind: WorkflowList['kind']): WorkflowList {
    const doc = mkList(4)
    doc.kind = kind
    doc.items.forEach((it, i) => { it.tags = [i % 2 ? '跳空' : '不跳空'] })
    return doc
  }

  it('大涨段清单不给标签筛选(标签描述决策日当天,按它筛等于提示决策日);对照清单照常给', async () => {
    ;(loadWorkflowList as any).mockResolvedValueOnce(tagged('bigmoves'))
    let store = await mountView()
    expect(store.allTags.length).toBe(2)
    expect(w.find('[data-testid="wf-tag"]').exists()).toBe(false)
    w.unmount()
    setActivePinia(createPinia())
    ;(loadWorkflowList as any).mockResolvedValueOnce(tagged('contrast'))
    store = await mountView()
    expect(w.find('[data-testid="wf-tag"]').exists()).toBe(true)
    expect(store.allTags).toEqual(['不跳空', '跳空'])
  })
})
