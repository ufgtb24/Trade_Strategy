/**
 * Task 2 · triggerEventDebug action + AbortController 单槽位覆盖 + clearDetailCard 清 debug state
 *
 * v2 契约:
 * - triggerEventDebug 新签名(eventId, anchorKey): 取 anchor bar · 调 getTimeDiagnose · 单槽位 abort 旧
 * - clearDetailCard 同步清 debug state(D9)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import * as api from '../src/api'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

function seedStore(store: ReturnType<typeof useViewStore>, tbEvent: any, boEvent: any) {
  // 直接注入 preview.value(effectiveAnalysis 依赖) —— seed 一个最小 analysis
  //
  // 【fixture 修正,相对 brief 原版】effectiveAnalysis 走 preview 分支要求
  // _previewHits = previewEnabled && preview.symbol===symbol && preview.pattern_spec.pattern_id===activePatternId
  // (view.ts _previewHits computed),brief 原版漏了 previewEnabled/pattern_spec,_previewHits 恒 false
  // → effectiveAnalysis 落回 currentAnalysis(经 scanFile.results,此处为空 [] → null)→ events=[] →
  // triggerEventDebug 找不到 event 提前 return。且 scan 字段原用 { window: {start,end} },
  // 与 ScanMeta 实际要求的扁平 win_start/win_end(windowOf() 消费)不符,会在 triggerEventDebug 内
  // windowOf() 处直接 throw。均为 brief 测试代码相对当前实际类型契约的 bug,非设计分歧;
  // 已核对 view.ts::_previewHits/currentAnalysis/currentPerStock 与 types.ts::ScanMeta 修正。
  //
  // 【Task 9 修正】previewEnabled 由 ref 改 computed(isExploring 别名),直接赋值静默 no-op。
  // 改为直接注入 workingCopy 槽位(enabled=true)达到同等效果 —— isExploring 只看
  // workingCopy.value[activePatternId]?.enabled,不需要真实 fork(此处无 params_snapshot)。
  ;(store as any).workingCopy = { bottom_burst: { enabled: true, baseline: {}, currentDict: {} } }
  ;(store as any).preview = {
    symbol: 'AAPL',
    pattern_spec: { pattern_id: 'bottom_burst' },
    scan: { win_start: '2025-01-01', win_end: '2025-12-31' },
    analysis: {
      events: [boEvent, tbEvent],
      matches: [],
      summary: {},
      gate_failures: [],
    },
  }
  ;(store as any).symbol = 'AAPL'
  ;(store as any).activePatternId = 'bottom_burst'
  ;(store as any).scanFile = {
    scan: { win_start: '2025-01-01', win_end: '2025-12-31' },
    results: [],
  }
}

describe('triggerEventDebug', () => {
  it('调 getTimeDiagnose · anchor=trough → bar=event.start_idx', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    const spy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({} as any)
    await store.triggerEventDebug('tb_1', 'trough')
    expect(spy).toHaveBeenCalledOnce()
    const [_pid, _sym, _s, _e, startBar, endBar] = spy.mock.calls[0]
    expect(startBar).toBe(42)
    expect(endBar).toBe(42)
  })

  it('anchor=entry → bar=findBoBar(anchor_bo_id) = bo.end_idx', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 33 }
    seedStore(store, tb, bo)

    const spy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({} as any)
    await store.triggerEventDebug('tb_1', 'entry')
    const [, , , , startBar, endBar] = spy.mock.calls[0]
    expect(startBar).toBe(33)
    expect(endBar).toBe(33)
  })

  it('anchor=end → bar=event.end_idx', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    const spy = vi.spyOn(api, 'getTimeDiagnose').mockResolvedValue({} as any)
    await store.triggerEventDebug('tb_1', 'end')
    const [, , , , startBar, endBar] = spy.mock.calls[0]
    expect(startBar).toBe(55)
    expect(endBar).toBe(55)
  })

  it('单槽位 abort · 新请求 abort 旧 controller', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    // 第一次调用 hang 住(never resolve),第二次 abort 它
    let firstAbortSignal: AbortSignal | null = null
    vi.spyOn(api, 'getTimeDiagnose').mockImplementation((...args: any[]) => {
      firstAbortSignal = args[7] as AbortSignal
      return new Promise(() => {})  // hang
    })

    void store.triggerEventDebug('tb_1', 'entry')
    await new Promise(r => setTimeout(r, 10))  // yield
    expect(firstAbortSignal).not.toBeNull()

    // 第二次调用应 abort 第一个
    vi.mocked(api.getTimeDiagnose).mockResolvedValue({} as any)
    void store.triggerEventDebug('tb_1', 'trough')
    await new Promise(r => setTimeout(r, 10))
    expect(firstAbortSignal!.aborted).toBe(true)
  })

  it('debugTarget 设为 { eventId, bar, className, anchor }', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    let resolveFn: any
    vi.spyOn(api, 'getTimeDiagnose').mockImplementation(() =>
      new Promise(r => { resolveFn = r })
    )

    void store.triggerEventDebug('tb_1', 'trough')
    await new Promise(r => setTimeout(r, 10))
    expect(store.debugTarget).toEqual({
      eventId: 'tb_1', bar: 42, className: 'tb', anchor: 'trough',
    })
    expect(store.debugPending).toBe(true)
    expect(store.activeDetailCard).toBe('debug')

    resolveFn({})
    await new Promise(r => setTimeout(r, 10))
    expect(store.debugPending).toBe(false)
  })
})

describe('clearDetailCard 扩展清 debug state', () => {
  it('clearDetailCard 后 debugTarget/debugPending null', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    let controller: AbortController | null = null
    vi.spyOn(api, 'getTimeDiagnose').mockImplementation((...args: any[]) => {
      controller = new AbortController()
      // 用参数中的 signal 关联
      const sig = args[7] as AbortSignal
      return new Promise((_r, reject) => {
        sig.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    })

    void store.triggerEventDebug('tb_1', 'entry')
    await new Promise(r => setTimeout(r, 10))
    expect(store.debugTarget).not.toBeNull()

    store.clearDetailCard()
    expect(store.debugTarget).toBeNull()
    expect(store.debugPending).toBe(false)
    expect(store.activeDetailCard).toBeNull()
  })
})

describe('cancelDebug', () => {
  it('cancelDebug abort 旧 controller · pending 变 false', async () => {
    const store = useViewStore()
    const tb = { event_id: 'tb_1', class_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1' }
    const bo = { event_id: 'bo_1', class_id: 'bo', start_idx: 30, end_idx: 30 }
    seedStore(store, tb, bo)

    let sig: AbortSignal | null = null
    vi.spyOn(api, 'getTimeDiagnose').mockImplementation((...args: any[]) => {
      sig = args[7] as AbortSignal
      return new Promise(() => {})
    })

    void store.triggerEventDebug('tb_1', 'trough')
    await new Promise(r => setTimeout(r, 10))
    store.cancelDebug()
    expect(sig!.aborted).toBe(true)
    expect(store.debugPending).toBe(false)
  })
})
