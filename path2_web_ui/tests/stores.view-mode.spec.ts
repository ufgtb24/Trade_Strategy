// 主视图模式:按代码打开落在 annotate(拿不到任何 app 产物);从扫描列表进来是 app
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

  it('app 下删掉当前扫描:清空图并回到 annotate', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    v.clearScanFile()
    expect(v.mode).toBe('annotate')
    expect(v.symbol).toBeNull()
  })
})
