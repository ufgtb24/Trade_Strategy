import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { useScanStore } from '../src/stores/scan'
import { getDiagnose } from '../src/api'
import { SCAN_FILE, DIAG } from './fixtures'
import type { Diagnostics } from '../src/types'

vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve(DIAG)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], role_index: {} },
    summary: { events: 0, matches: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
}))

describe('view store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loadResult sets analysis + resets toggles; role toggle reflected in roleVisible', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.selectSymbol('AAPL')
    expect(v.currentAnalysis?.matches.length).toBe(1)
    // 关 bo role → roleVisible 记录
    v.toggleRole('bo')
    expect(v.roleVisible.bo).toBe(false)
  })

  it('roleColors derived from current pattern_spec', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    expect(v.roleColors.bo).toBe('#2563eb')
    expect(v.roleColors.down).not.toBe(v.roleColors.side)
  })

  it('level 默认 matched,setLevel 改', () => {
    const v = useViewStore()
    expect(v.level).toBe('matched')
    v.setLevel('detected'); expect(v.level).toBe('detected')
  })

  it('selectEvent/hoverEvent set 单值 ref;同值幂等', () => {
    const v = useViewStore()
    v.selectEvent('burst_1_9'); expect(v.selectedEventId).toBe('burst_1_9')
    v.selectEvent('burst_1_9'); expect(v.selectedEventId).toBe('burst_1_9')
    v.hoverEvent('bo_3_3'); expect(v.hoveredEventId).toBe('bo_3_3')
  })

  it('computed matchedIds/eventTier 反映 analysis', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    expect(v.matchedIds.has('bo9')).toBe(true)
    expect(v.matchedIds.has('boX')).toBe(false)
    // boX 未匹配 → detected(无 diag qualified 覆盖它);bo9 匹配 → matched
    const boX = v.currentAnalysis!.events.find(e => e.event_id === 'boX')!
    const bo9 = v.currentAnalysis!.events.find(e => e.event_id === 'bo9')!
    expect(v.eventTier(boX)).toBe('detected')
    expect(v.eventTier(bo9)).toBe('matched')
  })

  it('diag 预取接线 + qualified 档:未匹配 event 全-satisfied → qualified', async () => {
    // 自定义 diag:给未匹配的 boX 造一行 clauses 全 satisfied 的 AttrRow → qualified。
    const customDiag: Diagnostics = {
      symbol: 'AAPL', pattern_id: 'bottom_breakout_burst',
      roles: {
        bo: { attr: [{ event_id: 'boX', start_idx: 20, end_idx: 20,
                       clauses: { first_drought: { satisfied: true, measured: 70, op: '>=', threshold: 60 } } }],
              rel: [] },
      },
      note: 'qualified teeth',
    }
    vi.mocked(getDiagnose).mockResolvedValueOnce(customDiag)

    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await flushPromises()                                // 等 watch 的 async 预取解析

    // ① 预取接线真的填充了 store
    expect(v.diag).toEqual(customDiag)
    // ② boX 进 qualifiedIds 且不在 matchedIds → qualified(中间档)
    expect(v.qualifiedIds.has('boX')).toBe(true)
    expect(v.matchedIds.has('boX')).toBe(false)
    const boX = v.currentAnalysis!.events.find(e => e.event_id === 'boX')!
    expect(v.eventTier(boX)).toBe('qualified')
  })
})

describe('view store clearScanFile', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clearScanFile resets scanFile/symbol/selected/event ids', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.selectSymbol('AAPL')
    v.selectEvent('burst_1_9')
    expect(v.scanFile).not.toBeNull()
    v.clearScanFile()
    expect(v.scanFile).toBeNull()
    expect(v.symbol).toBeNull()
    expect(v.selectedEventId).toBeNull()
  })
})

describe('scan store remove + cancel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('remove(pid, ts) calls deleteScan with both args', async () => {
    const { deleteScan } = await import('../src/api')
    const s = useScanStore()
    await s.remove('pat_x', '20260601T100000')
    expect(deleteScan).toHaveBeenCalledWith('pat_x', '20260601T100000')
  })

  it('cancel no-op when not running', async () => {
    const { cancelScan } = await import('../src/api')
    const s = useScanStore()
    // running=false,currentScanId=null → 直接 return,不调 cancelScan
    await s.cancel(false)
    expect(cancelScan).not.toHaveBeenCalled()
  })

  it('cancel(true) calls cancelScan(scan_id, true) when running', async () => {
    const { cancelScan } = await import('../src/api')
    const s = useScanStore()
    ;(s as any).running = true
    ;(s as any).currentScanId = 'scan_id_x'
    setTimeout(() => { (s as any).running = false }, 0)
    await s.cancel(true)
    expect(cancelScan).toHaveBeenCalledWith('scan_id_x', true)
  })

  it('cancel(false) calls cancelScan(scan_id, false) when running', async () => {
    const { cancelScan } = await import('../src/api')
    const s = useScanStore()
    ;(s as any).running = true
    ;(s as any).currentScanId = 'scan_id_y'
    setTimeout(() => { (s as any).running = false }, 0)
    await s.cancel(false)
    expect(cancelScan).toHaveBeenCalledWith('scan_id_y', false)
  })
})

describe('scan store ignores progress while cancelling', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('progress events arriving after cancel() fires are dropped (stale SSE queue)', async () => {
    const { streamScan, startScan, cancelScan, loadScan, listScans } = await import('../src/api')
    vi.mocked(loadScan).mockResolvedValueOnce(SCAN_FILE as any)
    vi.mocked(listScans).mockResolvedValueOnce([
      { scan_ts: 'scan_id_p', hits: 1, total: 10, size: 100, partial: true } as any
    ])
    vi.mocked(startScan).mockResolvedValueOnce('scan_id_p')
    let onEvt: ((e: any) => void) | null = null
    vi.mocked(streamScan).mockImplementationOnce((_id, cb) => {
      onEvt = cb as any
      return { close: () => {} } as any
    })
    vi.mocked(cancelScan).mockResolvedValueOnce({ ok: true })
    const s = useScanStore()
    await s.run({ pattern_id: 'pat_p', start_date: '2025-01-01', end_date: '2025-12-31',
                  workers: 1, ticker_regex: null, label_horizon: 20 })
    // 扫描中一条 progress event — 正常更新 store.progress
    onEvt!({ scanned: 10, total: 100, hits: 1, errors: 0 })
    expect(s.progress).toEqual({ scanned: 10, total: 100, hits: 1, errors: 0 })
    // 发起 cancel(true) — cancelling 同步置 true,await cancelScan (mock) 立即 resolve
    const cancelPromise = s.cancel(true)
    // 此刻 cancelling=true,后续 SSE progress event 应被忽略
    onEvt!({ scanned: 999, total: 100, hits: 99, errors: 0 })
    expect(s.progress).toEqual({ scanned: 10, total: 100, hits: 1, errors: 0 })
    await cancelPromise
  })
})

describe('scan store auto-load on done', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  // 共用 helper:从 streamScan mock 抓 on_progress 回调,模拟一条 SSE 事件
  async function dispatchDone(done: any) {
    const { streamScan, startScan, loadScan } = await import('../src/api')
    vi.mocked(loadScan).mockResolvedValueOnce(SCAN_FILE as any)
    vi.mocked(startScan).mockResolvedValueOnce('scan_id_x')
    let onEvt: ((e: any) => void) | null = null
    vi.mocked(streamScan).mockImplementationOnce((_id, cb) => {
      onEvt = cb as any
      return { close: () => {} } as any
    })
    const s = useScanStore()
    await s.run({ pattern_id: 'pat_x', start_date: '2025-01-01', end_date: '2025-12-31',
                  workers: 1, ticker_regex: null, label_horizon: 20 })
    onEvt!(done)
    await flushPromises()
  }

  it('done success → loadScan(pid, scan_ts) called + view.scanFile injected', async () => {
    const { loadScan } = await import('../src/api')
    await dispatchDone({ type: 'done', hits: 1, errors: 0, total: 1,
                         pattern_id: 'pat_x', scan_ts: '20260618T100000' })
    expect(loadScan).toHaveBeenCalledWith('pat_x', '20260618T100000')
    expect(useViewStore().scanFile).not.toBeNull()
  })

  it('done cancelled → loadScan NOT called + view.scanFile stays null', async () => {
    const { loadScan } = await import('../src/api')
    await dispatchDone({ type: 'done', hits: 0, errors: 0, total: 0,
                         pattern_id: 'pat_x', scan_ts: '20260618T100000', cancelled: true })
    expect(loadScan).not.toHaveBeenCalled()
    expect(useViewStore().scanFile).toBeNull()
  })

  it('done error → loadScan NOT called', async () => {
    const { loadScan } = await import('../src/api')
    await dispatchDone({ type: 'done', hits: 0, errors: 0, total: 0,
                         error: 'boom' })
    expect(loadScan).not.toHaveBeenCalled()
    expect(useViewStore().scanFile).toBeNull()
  })
})
