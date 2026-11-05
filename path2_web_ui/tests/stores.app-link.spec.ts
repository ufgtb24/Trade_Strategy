// 当前 pattern 的 app(stores/appLink.ts):mapping 决定 compare / app 可不可用;切进这两档对当前股票跑 app
// (/preview,区间是这只股票截到训练段末日的全部 K 线);换股票、换 app 重跑,两档之间互切不重跑;
// 当前 pattern 没有 app 了回到 annotate。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { LABEL_HORIZON, WHOLE_HISTORY_START, useAppLinkStore } from '../src/stores/appLink'
import { useAnnotationStore } from '../src/stores/annotation'
import { useViewStore } from '../src/stores/view'
import { TRAIN_END } from '../src/annotate/directLinks'
import * as api from '../src/api'

const ANALYSIS = {
  events: [{ instance_id: 'bo@3-3#0', node_id: 'bo', instance_idx: 0, start_idx: 3, end_idx: 3 }],
  hits: [{ hit_id: 'm0', start_idx: 3, end_idx: 3, node_index: { bo: 'bo@3-3#0' }, children: ['bo@3-3#0'] }],
}
const SPEC = { pattern_id: 'bo_only', topology: { nodes: [{ node_id: 'bo', where_rules: [] }], edges: [] },
               event_styles: {}, debug_enabled_nodes: [] }

vi.mock('../src/api', () => ({
  getMappings: vi.fn(() => Promise.resolve([
    { app: 'bo_only', pattern: 'P', features: { 'w-pc-1': 'bo' }, problem: null },
    { app: 'bad_app', pattern: 'BAD', features: {}, problem: 'node not in app bad_app: x' },
    { app: 'a1', pattern: 'DUP', features: {}, problem: 'pattern also mapped by app a2' },
    { app: 'a2', pattern: 'DUP', features: {}, problem: 'pattern also mapped by app a1' },
  ])),
  getPreview: vi.fn((app: string) => Promise.resolve({
    analysis: ANALYSIS, summary: {}, pattern_spec: { ...SPEC, pattern_id: app },
    scan: { start_date: '1900-01-01', end_date: '2025-12-31', win_start: '1899-09-01', win_end: '2025-12-31',
            label_horizon: 20, end_node: 'bo' },
  })),
  getDiagnose: vi.fn(() => Promise.resolve({ nodes: {} })),
  getAnnotations: vi.fn(() => new Promise(() => {})),
  postAnnotationBatch: vi.fn(),
}))

async function setup(pattern: string | null, symbol: string | null = 'AAPL') {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const links = useAppLinkStore()
  await links.load()
  ann.setCurrentPattern(pattern)
  if (symbol) view.openSymbol(symbol)
  return { view, ann, links }
}

describe('当前 pattern 的 app', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); localStorage.clear() })

  it('恰好一个、没有问题的 mapping 才算有 app;有问题的给出原因;没写 mapping 的没有原因', async () => {
    const { ann, links } = await setup('P')
    expect(links.mapping?.app).toBe('bo_only')
    expect(links.available).toBe(true)
    ann.setCurrentPattern('BAD')
    expect([links.mapping, links.available]).toEqual([null, false])
    expect(links.problem).toBe('bad_app: node not in app bad_app: x')
    ann.setCurrentPattern('DUP')
    expect(links.mapping).toBeNull()
    expect(links.problem).toContain('a1: pattern also mapped by app a2')
    ann.setCurrentPattern('NONE')
    expect([links.mapping, links.problem]).toEqual([null, null])
  })

  it('没打开股票时不可用;没有 app 时切不过去', async () => {
    const { view, links } = await setup('P', null)
    expect(links.available).toBe(false)
    links.setMode('compare')
    expect(view.mode).toBe('annotate')
    const s = await setup('NONE')
    s.links.setMode('app')
    expect(s.view.mode).toBe('annotate')
  })

  it('切到 compare:对当前股票跑 app,区间是全部 K 线、终点训练段末日;compare 里拿到它的输出', async () => {
    const { view, links } = await setup('P')
    links.setMode('compare')
    expect(view.mode).toBe('compare')
    await flushPromises()
    expect(api.getPreview).toHaveBeenCalledWith('bo_only', 'AAPL', WHOLE_HISTORY_START, TRAIN_END, LABEL_HORIZON)
    expect(links.runStatus).toBeNull()
    expect(view.effectiveAnalysis).toEqual(ANALYSIS)
    expect(view.effectivePattern?.pattern_id).toBe('bo_only')
    expect(view.appId).toBe('bo_only')
    expect(view.endNode).toBe('bo')
    // 诊断(qualified 档靠它)按 app 跑的同一区间要
    expect(api.getDiagnose).toHaveBeenCalledWith('bo_only', 'AAPL', '1899-09-01', '2025-12-31', undefined)
  })

  it('compare 与 app 之间互切不重跑;回 annotate 再切回来重跑(参数文件改了切一下就看到)', async () => {
    const { view, links } = await setup('P')
    links.setMode('compare')
    await flushPromises()
    links.setMode('app')
    await flushPromises()
    expect([view.mode, view.appSource, view.linkedView]).toEqual(['app', 'linked', true])
    expect(api.getPreview).toHaveBeenCalledTimes(1)
    expect(view.effectiveAnalysis).toEqual(ANALYSIS)
    links.setMode('annotate')
    await flushPromises()
    expect(view.effectiveAnalysis).toBeNull()
    links.setMode('compare')
    await flushPromises()
    expect(api.getPreview).toHaveBeenCalledTimes(2)
  })

  it('compare 下换股票:留在 compare,对新股票重跑;别的模式换股票落在 annotate', async () => {
    const { view, links } = await setup('P')
    links.setMode('compare')
    await flushPromises()
    view.openSymbol('MSFT')
    expect(view.mode).toBe('compare')
    expect(view.effectiveAnalysis).toBeNull()                    // 旧股票的输出不拿来画新股票
    await flushPromises()
    expect(vi.mocked(api.getPreview).mock.calls.at(-1)?.[1]).toBe('MSFT')
    expect(view.effectiveAnalysis).toEqual(ANALYSIS)
    links.setMode('app')
    view.openSymbol('NVDA')
    expect(view.mode).toBe('annotate')
  })

  it('换了一个没有 app 的 pattern:回到 annotate', async () => {
    const { view, ann, links } = await setup('P')
    links.setMode('app')
    await flushPromises()
    ann.setCurrentPattern('NONE')
    await flushPromises()
    expect(view.mode).toBe('annotate')
  })

  it('跑的时候换了股票:回来的结果不用;没跑成 → load_failed', async () => {
    let resolveSlow: (v: any) => void = () => {}
    vi.mocked(api.getPreview).mockImplementationOnce(() => new Promise((r) => { resolveSlow = r }))
    const { view, links } = await setup('P', 'SLOW')
    links.setMode('compare')
    await nextTick()
    expect(links.runStatus).toBe('loading')
    view.openSymbol('MSFT')
    await flushPromises()
    resolveSlow({ analysis: { events: [], hits: [] }, summary: {}, pattern_spec: SPEC,
                  scan: { win_start: 'x', win_end: 'y' } })
    await flushPromises()
    expect(view.linkedRun?.symbol).toBe('MSFT')
    vi.mocked(api.getPreview).mockImplementationOnce(() => Promise.reject(new Error('500')))
    view.openSymbol('DOWN')
    await flushPromises()
    expect([links.runStatus, view.effectiveAnalysis]).toEqual(['load_failed', null])
  })
})
