import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { getPreview, getDiagnose } from '../src/api'
import { SCAN_FILE, ANALYSIS, PATTERN, DIAG } from './fixtures'

vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve(DIAG)),
  getPreview: vi.fn(),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
}))

// Task 9(workingCopy 探索态状态机):previewEnabled 现在是 isExploring 的 computed 别名,
// 只有 fork 出 WorkingCopy(需要 scan file 内嵌 params_snapshot)后才能进入探索态。共享
// fixtures.ts::SCAN_FILE 是 legacy 夹具(无 snapshot,故意保持 —— 其余 8+ 个消费它的测试文件
// 测的是 legacy 场景),故本文件派生一份带 snapshot 的本地副本,不改共享 fixture。
const SCAN_FILE_WC = {
  ...SCAN_FILE,
  per_pattern: {
    ...SCAN_FILE.per_pattern,
    bottom_breakout_burst: {
      ...SCAN_FILE.per_pattern.bottom_breakout_burst,
      params_snapshot: { bo: { total_window: 10 } },
    },
  },
}

const PREVIEW_ANALYSIS = {
  ...ANALYSIS,
  matches: [{ ...ANALYSIS.matches[0], event_id: 'preview_match_1' }],
}
const PREVIEW_RESP = {
  analysis: PREVIEW_ANALYSIS,
  summary: { events: 6, matches: 1 },
  pattern_spec: PATTERN,
  scan: { ...SCAN_FILE.scan, win_start: '2025-01-01', win_end: '2025-12-31' },
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(getPreview).mockReset()
  vi.mocked(getPreview).mockResolvedValue(PREVIEW_RESP as any)
})

describe('view.preview computed', () => {
  it('effectiveAnalysis falls back to scanFile when previewEnabled=false', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    expect(v.effectiveAnalysis?.matches[0].event_id).toBe('m1')
  })

  it('effectiveAnalysis falls back when preview.symbol mismatches symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')            // Task 9:进探索态才能启用 preview
    await v.setPreviewEnabled(true)
    await flushPromises()
    // 切到别股(scanFile.results 没有 BBB,但内存仍可设)
    v.selectSymbol('OTHER')                              // preview 被清,但即便保留也应 fall back
    expect(v.effectiveAnalysis).toBeNull()               // OTHER 不在 scanFile.results
  })

  it('effectiveAnalysis uses preview when three conditions met', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true)
    await flushPromises()
    expect(v.effectiveAnalysis?.matches[0].event_id).toBe('preview_match_1')
  })

  it('effectivePattern uses preview pattern_spec when active', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.effectivePattern).toBe(PREVIEW_RESP.pattern_spec)
  })

  it('effectiveScan uses preview scan when active', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.effectiveScan?.win_start).toBe('2025-01-01')
  })
})

describe('view.preview actions', () => {
  it('setPreviewEnabled(true) triggers runPreview', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    // Task 9:首次 setWorkingCopyEnabled(无既有 WC 槽位)只 fork、不 fetch(baseline===snapshot
    // 时视图与浏览态一致,无需重算);先显式 fork,让随后的 setPreviewEnabled(true) 命中"WC 已存在"
    // 分支从而真正触发 runPreview —— 与生产 UI 流程一致(先"编辑参数"进入探索态,再用 checkbox A/B)。
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce()
  })

  it('setPreviewEnabled(false) clears preview state', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.preview).not.toBeNull()
    await v.setPreviewEnabled(false)
    expect(v.preview).toBeNull()
    expect(v.previewError).toBeNull()
    expect(v.previewEnabled).toBe(false)
  })

  it('selectSymbol clears preview and refetches when enabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    vi.mocked(getPreview).mockClear()
    v.selectSymbol('BBB')
    expect(v.preview).toBeNull()                         // 旧 preview 清
    await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce() // 新股自动 fetch
  })

  it('selectSymbol does not fetch when disabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    vi.mocked(getPreview).mockClear()
    v.selectSymbol('BBB')
    await flushPromises()
    expect(vi.mocked(getPreview)).not.toHaveBeenCalled()
  })

  it('clearScanFile resets all preview state', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    v.clearScanFile()
    expect(v.preview).toBeNull()
    expect(v.previewEnabled).toBe(false)
    expect(v.previewError).toBeNull()
  })

  it('runPreview stale-token guard on symbol change', async () => {
    let aaplResolver: (v: any) => void = () => {}
    let bbbResolver: (v: any) => void = () => {}
    let call = 0
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => {
      call++; if (call === 1) aaplResolver = r; else bbbResolver = r
    }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    void v.setPreviewEnabled(true)                       // 启动 AAPL fetch,未 resolve
    v.selectSymbol('BBB')                                // 切走 → 触发 BBB fetch
    aaplResolver(PREVIEW_RESP)                           // 旧 AAPL 响应回来
    await flushPromises()
    expect(v.preview).toBeNull()                         // AAPL 响应被丢弃,BBB fetch 未完成
    bbbResolver(PREVIEW_RESP)                            // 让 BBB 也完成
    await flushPromises()
  })

  it('runPreview stale-token guard on disable', async () => {
    let resolver: (v: any) => void = () => {}
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => { resolver = r }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    void v.setPreviewEnabled(true)
    await v.setPreviewEnabled(false)                     // 取消勾选
    resolver(PREVIEW_RESP)
    await flushPromises()
    expect(v.preview).toBeNull()
  })

  it('runPreview error sets previewError, keeps preview null', async () => {
    vi.mocked(getPreview).mockRejectedValueOnce(new Error('500: boom'))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    expect(v.preview).toBeNull()
    expect(v.previewError).toContain('boom')
  })

  it('runPreview can be called again to refresh (no cache)', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    vi.mocked(getPreview).mockClear()
    await v.runPreview(); await flushPromises()
    expect(vi.mocked(getPreview)).toHaveBeenCalledOnce()
  })

  it('runPreview always passes original strict window — no buffer compounding on refresh', async () => {
    // C1 regression: consecutive runPreview() calls must send identical start/end
    // equal to scanFile.scan.start_date/end_date, never the buffered win_start/win_end
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    await v.setPreviewEnabled(true); await flushPromises()
    // first call
    const firstCall = vi.mocked(getPreview).mock.calls[0]
    const [, , start1, end1] = firstCall
    // second call (refresh)
    vi.mocked(getPreview).mockClear()
    await v.runPreview(); await flushPromises()
    const secondCall = vi.mocked(getPreview).mock.calls[0]
    const [, , start2, end2] = secondCall
    // both calls use strict dates from scanFile.scan, not buffered win_start/win_end
    expect(start1).toBe(SCAN_FILE.scan.start_date)
    expect(end1).toBe(SCAN_FILE.scan.end_date)
    expect(start2).toBe(SCAN_FILE.scan.start_date)
    expect(end2).toBe(SCAN_FILE.scan.end_date)
  })

  it('previewLoading is not cleared by stale response', async () => {
    let firstResolver: (v: any) => void = () => {}
    let secondResolver: (v: any) => void = () => {}
    let call = 0
    vi.mocked(getPreview).mockImplementation(() => new Promise(r => {
      call++; if (call === 1) firstResolver = r; else secondResolver = r
    }))
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE_WC); v.selectSymbol('AAPL')
    v.forkWorkingCopy('bottom_breakout_burst')
    void v.setPreviewEnabled(true)                       // 第一次 fetch
    v.selectSymbol('BBB')                                // 触发第二次 fetch(同 enabled)
    firstResolver(PREVIEW_RESP)                          // 旧响应先回
    await flushPromises()
    expect(v.previewLoading).toBe(true)                  // 不被旧响应清
    secondResolver({ ...PREVIEW_RESP, scan: { ...PREVIEW_RESP.scan, win_start: 'X' } })
    await flushPromises()
    expect(v.previewLoading).toBe(false)                 // 新响应清
  })
})
