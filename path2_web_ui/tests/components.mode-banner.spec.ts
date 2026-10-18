/** 看图工作流的调试模式:后端报调试模式时页顶挂横幅(文字 + 明暗,不靠色相)、标签页标题加前缀、
 *  两个视图的整页高度减掉横幅;放大图的标题行里再写一遍。正式模式什么都不挂。 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const LABEL = '调试模式：2021-10～2022-09，不进正式账'
const modeResp = vi.hoisted(() => ({ value: null as any }))
vi.mock('../src/api', () => ({
  getMode: vi.fn(async () => modeResp.value),
  listWorkflowLists: vi.fn(async () => []),
  getWorkflowState: vi.fn(async () => ({ path: '/x', from_env: false, env_var: 'X', ok: true, message: null })),
  recordChartView: vi.fn(async () => ({ ok: true, ts: '2026-10-18T10:00:00' })),
}))

import ModeBanner from '../src/components/ModeBanner.vue'
import WorkflowView from '../src/components/WorkflowView.vue'
import { useModeStore } from '../src/stores/mode'
import { useWorkflowStore } from '../src/stores/workflow'

let w: VueWrapper
describe('调试模式横幅', () => {
  beforeEach(() => { setActivePinia(createPinia()); document.title = 'path2 web UI' })
  afterEach(() => { w?.unmount(); document.documentElement.style.removeProperty('--mode-banner-h') })

  it('调试模式:挂横幅、标题加前缀、整页高度让出横幅', async () => {
    modeResp.value = { mode: 'debug', label: LABEL, view_floor: '2021-10-01', train_end: '2022-09-30' }
    w = mount(ModeBanner)
    await flushPromises()
    const b = w.find('[data-testid="mode-banner"]')
    expect(b.exists()).toBe(true)
    expect(b.text()).toBe(LABEL)
    expect(document.title).toBe(`【调试模式】path2 web UI`)
    expect(document.documentElement.style.getPropertyValue('--mode-banner-h')).toBe('30px')
  })

  it('正式模式:什么都不挂', async () => {
    modeResp.value = { mode: 'formal', label: null, view_floor: '2025-01-01', train_end: '2025-12-31' }
    w = mount(ModeBanner)
    await flushPromises()
    expect(w.find('[data-testid="mode-banner"]').exists()).toBe(false)
    expect(document.title).toBe('path2 web UI')
    expect(document.documentElement.style.getPropertyValue('--mode-banner-h')).toBe('0px')
  })

  it('后端读不到模式:按正式模式处理', async () => {
    modeResp.value = Promise.reject(new Error('down'))
    w = mount(ModeBanner)
    await flushPromises()
    expect(w.find('[data-testid="mode-banner"]').exists()).toBe(false)
  })

  it('放大图盖住页顶横幅时,标题行里再写一遍', async () => {
    useModeStore().info = { mode: 'debug', label: LABEL, view_floor: '2021-10-01', train_end: '2022-09-30' }
    w = mount(WorkflowView, { attachTo: document.body,
                              global: { stubs: { AnnotChart: true, AnnotReviewPanel: true } } })
    await flushPromises()
    const store = useWorkflowStore()
    store.current = {
      schema: 'chart_workflow.list/1', list_id: 'dbg-a', kind: 'bigmoves', title: 't', created_at: '',
      train_start: '2021-10-01', train_end: '2022-09-30', params: {},
      groups: [{ key: 'all', title: '全部', item_ids: ['A@2022-03-01'] }],
      items: [{ item_id: 'A@2022-03-01', symbol: 'A', t: '2022-03-01', entry_date: '2022-03-02',
                view_start: '2021-11-01', view_end: '2022-04-28', marks: {}, metrics: {}, tags: [] }],
    } as any
    store.setZoom('A@2022-03-01')
    await flushPromises()
    expect(w.find('[data-testid="wf-zoom-mode"]').text()).toContain(LABEL)
    document.body.innerHTML = ''
  })
})
