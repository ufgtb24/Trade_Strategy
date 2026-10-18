/** 页顶横幅:后端报调试模式时挂调试横幅(文字 + 明暗,不靠色相)、标签页标题加前缀、两个视图的整页高度减掉
 *  横幅;放大图的标题行里再写一遍。正式模式什么都不挂。后端没连上 → 挂「模式未知」并定时重试;
 *  启动脚本说的模式和后端报的不一样 → 报警。 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const LABEL = '调试模式：2021-10～2022-09，不进正式账'
const modeResp = vi.hoisted(() => ({ value: null as any }))
const launch = vi.hoisted(() => ({ mode: null as 'formal' | 'debug' | null }))
vi.mock('../src/api', () => ({
  getMode: vi.fn(async () => {
    if (modeResp.value instanceof Error) throw modeResp.value
    if (modeResp.value === 'hang') return new Promise(() => {})
    return modeResp.value
  }),
  listWorkflowLists: vi.fn(async () => []),
  getWorkflowState: vi.fn(async () => ({ path: '/x', from_env: false, env_var: 'X', ok: true, message: null })),
  recordChartView: vi.fn(async () => ({ ok: true, ts: '2026-10-18T10:00:00' })),
}))

vi.mock('../src/shared/launchMode', () => ({ launchMode: () => launch.mode }))

import ModeBanner from '../src/components/ModeBanner.vue'
import WorkflowView from '../src/components/WorkflowView.vue'
import { useModeStore, RETRY_MS, RECHECK_MS, TIMEOUT_MS } from '../src/stores/mode'
import { getMode } from '../src/api'
import { useWorkflowStore } from '../src/stores/workflow'

const DEBUG = { mode: 'debug', label: LABEL, view_floor: '2021-10-01', train_end: '2022-09-30' }
const FORMAL = { mode: 'formal', label: null, view_floor: '2025-01-01', train_end: '2025-12-31' }
const banner = () => w.find('[data-testid="mode-banner"]')

let w: VueWrapper
describe('调试模式横幅', () => {
  beforeEach(() => {
    setActivePinia(createPinia()); document.title = 'path2 web UI'; launch.mode = null
    vi.mocked(getMode).mockClear()
  })
  afterEach(() => {
    w?.unmount(); document.documentElement.style.removeProperty('--mode-banner-h'); vi.useRealTimers()
  })

  it('调试模式:挂横幅、标题加前缀、整页高度让出横幅', async () => {
    modeResp.value = DEBUG
    w = mount(ModeBanner)
    await flushPromises()
    const b = w.find('[data-testid="mode-banner"]')
    expect(b.exists()).toBe(true)
    expect(b.text()).toBe(LABEL)
    expect(document.title).toBe(`【调试模式】path2 web UI`)
    expect(document.documentElement.style.getPropertyValue('--mode-banner-h')).toBe('30px')
  })

  it('正式模式:什么都不挂', async () => {
    modeResp.value = FORMAL
    w = mount(ModeBanner)
    await flushPromises()
    expect(w.find('[data-testid="mode-banner"]').exists()).toBe(false)
    expect(document.title).toBe('path2 web UI')
    expect(document.documentElement.style.getPropertyValue('--mode-banner-h')).toBe('0px')
  })

  it('后端读不到模式:挂「模式未知」横幅、定时重试,连上以后换成实际模式', async () => {
    vi.useFakeTimers()
    launch.mode = 'debug'
    modeResp.value = new Error('down')
    w = mount(ModeBanner)
    await flushPromises()
    expect(banner().attributes('data-kind')).toBe('unknown')
    expect(banner().text()).toContain('模式未知：后端没连上')
    expect(banner().text()).toContain('按调试模式启动')
    expect(document.title).toBe('【模式未知】path2 web UI')
    expect(document.documentElement.style.getPropertyValue('--mode-banner-h')).toBe('30px')
    expect(getMode).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(RETRY_MS)
    expect(getMode).toHaveBeenCalledTimes(2)                     // 还没连上:接着重试
    expect(banner().attributes('data-kind')).toBe('unknown')
    modeResp.value = DEBUG
    await vi.advanceTimersByTimeAsync(RETRY_MS)
    expect(getMode).toHaveBeenCalledTimes(3)
    expect(banner().attributes('data-kind')).toBe('debug')
    expect(banner().text()).toBe(LABEL)
    expect(document.title).toBe('【调试模式】path2 web UI')
    await vi.advanceTimersByTimeAsync(RETRY_MS)
    expect(getMode).toHaveBeenCalledTimes(3)                     // 连上以后放慢,隔一阵再核对
    modeResp.value = new Error('down again')
    await vi.advanceTimersByTimeAsync(RECHECK_MS)
    expect(banner().attributes('data-kind')).toBe('unknown')     // 后端又没了:不再挂着旧模式
  })

  it('后端一直不回应:超时按读不到处理', async () => {
    vi.useFakeTimers()
    modeResp.value = 'hang'
    w = mount(ModeBanner)
    await flushPromises()
    expect(banner().exists()).toBe(false)                        // 第一次还没读完:先不挂
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS)
    expect(banner().attributes('data-kind')).toBe('unknown')
    expect(banner().text()).not.toContain('启动的')               // 手工起的前端不知道启动模式,不提
  })

  it.each([
    ['debug', FORMAL, '网页按调试模式启动，后端却是正式模式'],
    ['formal', DEBUG, '网页按正式模式启动，后端却是调试模式'],
  ] as const)('启动脚本说 %s、后端报的不一样:报警', async (expected, resp, text) => {
    launch.mode = expected
    modeResp.value = resp
    w = mount(ModeBanner)
    await flushPromises()
    expect(banner().attributes('data-kind')).toBe('mismatch')
    expect(banner().attributes('role')).toBe('alert')
    expect(banner().text()).toContain(text)
    expect(document.title).toBe('【模式对不上】path2 web UI')
  })

  it('启动脚本说正式模式、后端也是:什么都不挂', async () => {
    launch.mode = 'formal'
    modeResp.value = FORMAL
    w = mount(ModeBanner)
    await flushPromises()
    expect(banner().exists()).toBe(false)
    expect(document.title).toBe('path2 web UI')
  })

  it.each(['down', 'hang'] as const)('横幅卸下以后不再重试(卸下时%s)', async (how) => {
    vi.useFakeTimers()
    modeResp.value = how === 'hang' ? 'hang' : new Error('down')   // hang:卸下时那一次读取还没回来
    w = mount(ModeBanner)
    await flushPromises()
    w.unmount()
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS + RETRY_MS * 3)
    expect(getMode).toHaveBeenCalledTimes(1)
  })

  it('放大图盖住页顶横幅时,标题行里再写一遍', async () => {
    useModeStore().info = DEBUG as any
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
    useModeStore().failed = true                                   // 后端没连上:放大图里同样写出来
    await flushPromises()
    expect(w.find('[data-testid="wf-zoom-mode"]').text()).toContain('模式未知')
    document.body.innerHTML = ''
  })
})
