// 主视图模式:按代码打开落在 annotate(拿不到任何 app 产物);从扫描列表进来是 app(扫描结果);
// 顶栏切到 compare / app 时 app 产物取当前 pattern 的 app 现算的(linkedRun)
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { SCAN_FILE } from './fixtures'

describe('view store · mode', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('默认 annotate,没有打开的图', () => {
    const v = useViewStore()
    expect(v.mode).toBe('annotate')
    expect(v.symbol).toBeNull()
  })

  it('加载扫描结果 → app,能拿到这只股票的 app 产物', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    expect(v.mode).toBe('app')
    expect(v.symbol).toBe('AAPL')
    expect(v.effectiveAnalysis?.events.length).toBeGreaterThan(0)
  })

  it('openSymbol → annotate:即使扫描结果里有这只股票,也拿不到 app 产物;扫描与 active pattern 不动', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('AAPL')
    expect(v.mode).toBe('annotate')
    expect(v.symbol).toBe('AAPL')
    expect(v.effectiveAnalysis).toBeNull()
    expect(v.scanFile).toBe(SCAN_FILE)
    expect(v.activePatternId).toBe('bottom_burst')
  })

  it('openSymbol 带图窗:记下图窗(拷一份);不带图窗就清掉', () => {
    const v = useViewStore()
    const win = { start: '2024-01-02', end: '2024-06-28' }
    v.openSymbol('AAPL', win)
    expect(v.mode).toBe('annotate')
    expect(v.viewWindow).toEqual(win)
    expect(v.viewWindow).not.toBe(win)
    v.openSymbol('MSFT')
    expect(v.viewWindow).toBeNull()
  })

  it('annotate 下从扫描列表选股 → 回到 app', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('MSFT')
    v.selectSymbol('AAPL')
    expect(v.mode).toBe('app')
    expect(v.effectiveAnalysis).not.toBeNull()
  })

  it('annotate 下删掉当前扫描:按代码打开的图不跟着清', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('MSFT')
    v.clearScanFile()
    expect(v.mode).toBe('annotate')
    expect(v.symbol).toBe('MSFT')
  })

  it('compare:标注照旧(annotating),app 产物只取当前 pattern 的 app 在这只股票上现算的(linkedRun),别的股票的不拿', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('AAPL')
    v.enterLinked('compare')
    expect([v.mode, v.annotating, v.comparing, v.linkedView, v.appSource]).toEqual(['compare', true, true, true, 'linked'])
    expect(v.effectiveAnalysis).toBeNull()                         // 扫描结果里有 AAPL,也不拿
    const run = { symbol: 'MSFT', app: 'bo_only', analysis: { events: [], hits: [] },
                  pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_nodes: [] },
                  scan: { win_start: '1899-09-01', win_end: '2025-12-31', end_node: 'bo' } as any }
    v.setLinkedRun(run)
    expect(v.effectiveAnalysis).toBeNull()                         // 别的股票的
    v.setLinkedRun({ ...run, symbol: 'AAPL' })
    expect(v.effectiveAnalysis).toEqual(run.analysis)
    expect([v.appId, v.endNode]).toEqual(['bo_only', 'bo'])
    expect(v.appWindowOf()).toEqual({ start: '1899-09-01', end: '2025-12-31' })
    v.enterLinked('app')
    expect([v.mode, v.annotating, v.linkedView]).toEqual(['app', false, true])
    expect(v.effectiveAnalysis).toEqual(run.analysis)
  })

  it('openSymbol:compare 下换图留在 compare(换图不退出 compare);annotate、app 下落在 annotate', () => {
    const v = useViewStore()
    v.openSymbol('AAPL')
    v.enterLinked('compare')
    v.openSymbol('MSFT', { start: '2024-01-02', end: '2024-06-28' })
    expect([v.symbol, v.mode]).toEqual(['MSFT', 'compare'])
    v.enterLinked('app')
    v.openSymbol('AAPL')
    expect(v.mode).toBe('annotate')
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('MSFT')
    expect(v.mode).toBe('annotate')
  })

  it('现算的 app 下删掉扫描:图不清;从扫描列表选股回到扫描结果的 app', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.openSymbol('MSFT')
    v.enterLinked('app')
    v.clearScanFile()
    expect([v.mode, v.symbol]).toEqual(['app', 'MSFT'])
    v.loadScanFile(SCAN_FILE)
    v.enterLinked('compare')
    v.selectSymbol('AAPL')
    expect([v.mode, v.appSource, v.linkedView]).toEqual(['app', 'scan', false])
    expect(v.effectiveAnalysis?.events.length).toBeGreaterThan(0)
  })

  it('tiers 默认开', () => {
    const v = useViewStore()
    expect(v.tiers).toBe(true)
    v.setTiers(false)
    expect(v.tiers).toBe(false)
  })

  it('app 下删掉当前扫描:清空图并回到 annotate', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.clearScanFile()
    expect(v.mode).toBe('annotate')
    expect(v.symbol).toBeNull()
  })
})
