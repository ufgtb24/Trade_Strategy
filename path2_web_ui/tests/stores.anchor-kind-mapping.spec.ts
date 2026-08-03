/**
 * v3 · store 两入口的 anchorKind 供给测试。
 *
 * 契约:
 * - triggerEventDebug(id, 'entry') → getTimeDiagnose 调用参数 anchorKind='entry'
 * - triggerEventDebug(id, 'trough') → anchorKind='trough'
 * - triggerEventDebug(id, 'end') → anchorKind='end'
 * - 入口 A(brush · triggerTimeQuery 路径)→ getTimeDiagnose 调用 anchorKind='gate'
 *
 * 前后端 anchorKind 字面量一致性靠此测试兜底(与 test_throwback_debug_anchor_kinds Python 侧联防)。
 *
 * 【fixture 修正 · 相对 task-4-brief.md 原版】与既有先例 stores.triggerEventDebug.spec.ts
 * (Task 2)记录的同一个 bug:effectiveAnalysis 走 preview 分支要求
 *   _previewHits = previewEnabled && preview.symbol===symbol && preview.pattern_spec.pattern_id===activePatternId
 * (view.ts _previewHits computed)。brief 原版 fixture 只塞了 `preview.pattern_spec: {}`、未设
 * `previewEnabled`,_previewHits 恒 false → effectiveAnalysis 落回 currentAnalysis(经
 * scanFile.value.results.find(...),brief 原版 scanFile 无 results 字段 → 直接 throw
 * "Cannot read properties of undefined (reading 'find')")。且即便修好 previewEnabled/pattern_id,
 * brief 原版 `preview.scan: {}` 缺 win_start/win_end,会在 windowOf() 内 throw。
 * 已按 stores.triggerEventDebug.spec.ts 的既有修法对齐:previewEnabled=true +
 * pattern_spec.pattern_id 对齐 activePatternId + preview.scan 补 win_start/win_end。
 *
 * 【Task 9 修正】previewEnabled 由 ref 改 computed(isExploring 别名),直接赋值静默 no-op;
 * 改为直接注入 workingCopy 槽位(enabled=true),同 stores.triggerEventDebug.spec.ts 的修法。
 *
 * 【类型修正 · 同上一处】brief 原版 `getTimeDiagnoseSpy: ReturnType<typeof vi.spyOn>` 塌缩成
 * `MockInstance<(...args: unknown[]) => unknown>`,与 `vi.spyOn(api, 'getTimeDiagnose')` 的具体
 * 返回类型不兼容(vue-tsc TS2322)。改用 `MockInstance<typeof api.getTimeDiagnose>`。
 */
import { describe, it, expect, vi, beforeEach, type MockInstance } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import * as api from '../src/api'

// 最小 fixture · 模拟 store 已加载 scan 结果 + 已选 pattern + 已选 symbol
function seedStoreForDebug(store: ReturnType<typeof useViewStore>) {
  store.symbol = 'AAA'
  store.activePatternId = 'bottom_burst'
  // 塞一个 tb event 供 anchorsOf 查
  const tbEvent = {
    event_id: 'ev_tb_1', class_id: 'tb', start_idx: 100, end_idx: 105,
    anchor_bo_id: 'ev_bo_1',
  } as any
  const boEvent = {
    event_id: 'ev_bo_1', class_id: 'bo', start_idx: 50, end_idx: 90,
  } as any
  ;(store as any).workingCopy = { bottom_burst: { enabled: true, baseline: {}, currentDict: {} } }
  ;(store as any).preview = {
    symbol: 'AAA',
    pattern_spec: { pattern_id: 'bottom_burst' },
    scan: { win_start: '2024-01-01', win_end: '2024-07-01' },
    analysis: { events: [tbEvent, boEvent], matches: [], summary: {}, gate_failures: [] },
  }
  ;(store as any).scanFile = {
    scan: {
      start_date: '2024-01-01', end_date: '2024-07-01',
      label_horizon: 20, win_start: '2024-01-01', win_end: '2024-07-01',
    } as any,
    results: [],
  } as any
}


describe('triggerEventDebug 供 anchorKind', () => {
  let getTimeDiagnoseSpy: MockInstance<typeof api.getTimeDiagnose>

  beforeEach(() => {
    setActivePinia(createPinia())
    getTimeDiagnoseSpy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({
      scope: 'time', payload: {}, caveats: [],
    } as any)
  })

  it('anchor.key="entry" → getTimeDiagnose anchorKind="entry"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'entry')
    // getTimeDiagnose 签名末位是 anchorKind(第 9 位 · 0-indexed 是 8)
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('entry')
  })

  it('anchor.key="trough" → getTimeDiagnose anchorKind="trough"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'trough')
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('trough')
  })

  it('anchor.key="end" → getTimeDiagnose anchorKind="end"', async () => {
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerEventDebug('ev_tb_1', 'end')
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('end')
  })
})


describe('入口 A(brush)供 anchorKind="gate"', () => {
  let getTimeDiagnoseSpy: MockInstance<typeof api.getTimeDiagnose>

  beforeEach(() => {
    setActivePinia(createPinia())
    getTimeDiagnoseSpy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({
      scope: 'time', payload: {}, caveats: [],
    } as any)
  })

  it('brush 触发的 diag 调用 · getTimeDiagnose 参数 anchorKind="gate"', async () => {
    // 入口 A 的实际触发点是 store 已导出的 named action triggerTimeQuery(startBar, endBar,
    // eventClass?)(view.ts:509,由 KlineChart.vue brush handler 与 DetailSidebar 下拉共同调用)。
    // 读代码确认它并非内联匿名函数 —— brief Step 4.10 的「抽 named action」refactor 不适用,
    // 直接调用既有 action 即可精确复现 brush 触发的真实调用路径。
    const store = useViewStore()
    seedStoreForDebug(store)
    await store.triggerTimeQuery(50, 80)
    const args = getTimeDiagnoseSpy.mock.calls[0]
    expect(args[8]).toBe('gate')
  })
})
