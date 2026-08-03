// 探索态列表对照行:previewListRow 纯 computed(从 preview 派生,只填 active pattern、其余空)
// spec = docs/superpowers/specs/2026-07-23-explore-list-preview-row-design.md
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

function scanFile2(): any {
  return {
    pattern_ids: ['bbb', 'ccc'],
    per_pattern: {
      bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
             end_node: 'tb', params_snapshot: { bo: { total_window: 10 } } },
      ccc: { pattern_spec: { pattern_id: 'ccc', topology: { nodes: [], edges: [] }, event_styles: {} },
             end_node: 'tb', params_snapshot: { bo: { total_window: 5 } } },
    },
    scan: { scan_ts: '20260720T000000', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
    results: [{ symbol: 'ACRS', per_pattern: {} }],
  }
}
// 直接注入 preview + workingCopy(enabled=true)驱动探索态,避开 runPreview 异步(范式同 view.multi.spec.ts)
function enterExplore(v: any, matches: any[]) {
  ;(v as any).preview = {
    symbol: 'ACRS',
    analysis: { events: [], matches },
    pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
    scan: { label_horizon: 20 },
  }
  ;(v as any).workingCopy = { bbb: { enabled: true, baseline: {}, currentDict: {} } }
}

describe('previewListRow', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any)))
  })

  it('探索态+preview:active pattern 填现算 num/fr(max)/fd(min),其余 pattern 空(filled=false)', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb')
    v.selectSymbol('ACRS')
    enterExplore(v, [
      { forward_return: 0.12, forward_drawdown: -0.04 },
      { forward_return: 0.30, forward_drawdown: -0.11 },
      { forward_return: null, forward_drawdown: null },
    ])
    expect(v.previewListRow).toEqual({
      symbol: 'ACRS',
      cells: [
        // num=len;fr=max(skip null);fd=min(skip null) — fr/fd 口径对偶
        { pid: 'bbb', num: 3, fr: 0.30, fd: -0.11, filled: true },
        { pid: 'ccc', num: null, fr: null, fd: null, filled: false },
      ],
    })
  })

  it('浏览态(未 enable WC)→ null', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb')
    v.selectSymbol('ACRS')
    ;(v as any).preview = {
      symbol: 'ACRS', analysis: { events: [], matches: [{ forward_return: 0.1 }] },
      pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} }, scan: { label_horizon: 20 },
    }
    expect(v.isExploring).toBe(false)
    expect(v.previewListRow).toBeNull()
  })

  it('preview 未设 / 选中股≠preview.symbol → null', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb'); v.selectSymbol('ACRS')
    ;(v as any).workingCopy = { bbb: { enabled: true, baseline: {}, currentDict: {} } }
    expect(v.previewListRow).toBeNull()                 // preview 未设
    enterExplore(v, [{ forward_return: 0.1 }])
    ;(v as any).symbol = 'OTHER'                        // 选中股与 preview.symbol 不符
    expect(v.previewListRow).toBeNull()
  })

  it('active pattern 现算 0 命中:num=0 / fr=null / fd=null,仍 filled=true(渲染层显 —)', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb'); v.selectSymbol('ACRS')
    enterExplore(v, [])
    expect(v.previewListRow!.cells[0]).toEqual({ pid: 'bbb', num: 0, fr: null, fd: null, filled: true })
  })

  it('fd 取 min(最差下行),skip null — 与 fr 取 max 对偶', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb'); v.selectSymbol('ACRS')
    // 三条 match:fd 分别 -0.03 / -0.22 / null → min=-0.22(跳过 null)
    enterExplore(v, [
      { forward_return: 0.05, forward_drawdown: -0.03 },
      { forward_return: 0.08, forward_drawdown: -0.22 },
      { forward_return: 0.02, forward_drawdown: null },
    ])
    expect(v.previewListRow!.cells[0].fd).toBeCloseTo(-0.22)
  })

  it('所有 match.forward_drawdown 都缺 → fd=null(无对偶值)', () => {
    const v = useViewStore()
    v.loadScanFile(scanFile2())
    v.setActivePattern('bbb'); v.selectSymbol('ACRS')
    enterExplore(v, [{ forward_return: 0.05 }, { forward_return: 0.08 }])
    expect(v.previewListRow!.cells[0].fd).toBeNull()
  })
})
