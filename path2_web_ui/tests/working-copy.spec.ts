// Task 9 · workingCopy store 核心(探索态状态机)
// spec = docs/research/2026-07-20_params-profiles-dev-modes
//
// 契约(Task 10-13 强依赖):
// - 浏览态(WC 未 fork/未 enable):effectiveParamsOverride = scan file 内嵌 params_snapshot
// - 探索态(WC.enabled=true):effectiveParamsOverride = WC.currentDict
// - legacy scan(无 snapshot):effectiveParamsOverride = null,fork 不动作
// - localStorage 休眠恢复:updateWorkingCopy 落盘,刷新后不自动激活(dormantDrafts 列出,
//   需显式 restoreDormant 装回内容轴;恢复后 enabled=false,再点 chip 才生效)
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

function fakeScanFile(): any {
  return {
    pattern_ids: ['bbb'],
    per_pattern: { bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
                          end_node: 'tb', params_snapshot: { bo: { total_window: 10 } } } },
    scan: { scan_ts: '20260720T000000', win_start: '2024-09-19', win_end: '2025-12-01', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
    results: [{ symbol: 'ACRS', per_pattern: {} }],
  }
}

describe('workingCopy store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any)))
  })

  it('浏览态 effectiveParamsOverride = snapshot(三环节一致性核心)', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 10 } })
    expect(v.isExploring).toBe(false)
  })

  it('fork → 探索态,edit 后 override = WC dict,重置回 baseline', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    expect(v.isExploring).toBe(true)
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 42 } })
    expect(v.wcDirty('bbb')).toBe(true)
    v.resetWorkingCopy('bbb')
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 10 } })
  })

  it('setWorkingCopyEnabled(false) 切回浏览态但 dict 保留(A/B 对比)', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    v.setWorkingCopyEnabled('bbb', false)
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 10 } })  // 视图回 snapshot
    v.setWorkingCopyEnabled('bbb', true)
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 42 } })  // dict 没丢
  })

  it('legacy scan(无 snapshot):override=null,fork 不动作', () => {
    const v = useViewStore()
    const f = fakeScanFile()
    delete f.per_pattern.bbb.params_snapshot
    v.loadScanFile(f)
    expect(v.effectiveParamsOverride).toBeNull()
    v.forkWorkingCopy('bbb')
    expect(v.workingCopy['bbb']).toBeUndefined()
  })

  it('updateWorkingCopy 写 localStorage;loadScanFile 发现草稿 → dormant 不自动激活', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    expect(localStorage.getItem('p2wc:20260720T000000:bbb')).toBeTruthy()
    // 模拟刷新:新 pinia 重新 load 同一 scan
    setActivePinia(createPinia())
    const v2 = useViewStore()
    v2.loadScanFile(fakeScanFile())
    expect(v2.workingCopy['bbb']).toBeUndefined()          // 休眠:不自动激活
    expect(v2.dormantDrafts.map(d => d.pid)).toContain('bbb')
    v2.restoreDormant('bbb')
    expect(v2.workingCopy['bbb']!.currentDict).toEqual({ bo: { total_window: 42 } })  // 内容轴回来了
    expect(v2.isExploring).toBe(false)                                                // 决策2:不自动激活视图
    expect(v2.effectiveParamsOverride).toEqual({ bo: { total_window: 10 } })          // 仍锚 snapshot
    v2.setWorkingCopyEnabled('bbb', true)                                             // chip 点亮才生效
    expect(v2.effectiveParamsOverride).toEqual({ bo: { total_window: 42 } })
  })

  it('discardWorkingCopy 清 slot + localStorage', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    v.discardWorkingCopy('bbb')
    expect(v.workingCopy['bbb']).toBeUndefined()
    expect(localStorage.getItem('p2wc:20260720T000000:bbb')).toBeNull()
  })

  it('ensureWorkingCopy:无 WC 时以传入 baseline 创建(enabled=false,不进探索);有 WC 时纯 no-op', () => {
    const v = useViewStore()
    const f = fakeScanFile()
    delete f.per_pattern.bbb.params_snapshot          // legacy:无 snapshot
    v.loadScanFile(f)
    v.ensureWorkingCopy('bbb', { bo: { total_window: 7 } })
    expect(v.workingCopy['bbb']!.baseline).toEqual({ bo: { total_window: 7 } })
    expect(v.workingCopy['bbb']!.enabled).toBe(false)  // 不变量:enabled 只有 chip(setWorkingCopyEnabled)一个写者
    expect(v.isExploring).toBe(false)
    v.setWorkingCopyEnabled('bbb', true)               // chip 点亮
    v.setWorkingCopyEnabled('bbb', false)              // chip 切灰
    v.ensureWorkingCopy('bbb', { bo: { total_window: 99 } })  // 已有 WC:纯 no-op(不覆盖、不 re-enable)
    expect(v.workingCopy['bbb']!.baseline).toEqual({ bo: { total_window: 7 } })
    expect(v.isExploring).toBe(false)
  })

  it('ensureWorkingCopy 深拷贝 baseline(外部改动不串)', () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    const b = { bo: { total_window: 7 } }
    v.ensureWorkingCopy('bbb', b)
    b.bo.total_window = 999
    expect(v.workingCopy['bbb']!.baseline).toEqual({ bo: { total_window: 7 } })
  })

  it('updateWorkingCopy 触发 wc.json 镜像落盘(POST /params/wc-mirror,body 含 pid/scan_ts/win/wc/enabled)', async () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    await new Promise(r => setTimeout(r, 0))
    const mirrors = (fetch as any).mock.calls.filter((c: any[]) => typeof c[0] === 'string' && c[0].includes('/params/wc-mirror'))
    expect(mirrors.length).toBeGreaterThanOrEqual(1)
    const body = JSON.parse(mirrors[mirrors.length - 1][1].body)
    expect(body.pid).toBe('bbb')
    expect(body.scan_ts).toBe('20260720T000000')
    expect(body.win_start).toBe('2024-09-19')
    expect(body.win_end).toBe('2025-12-01')
    expect(body.start_date).toBe('2025-01-01')
    expect(body.end_date).toBe('2025-06-01')
    expect(body.wc.bo.total_window).toBe(42)
    expect(body.enabled).toBe(true)
  })

  it('setWorkingCopyEnabled(false) 落盘 enabled=false(终端据此回退 scan)', async () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.setWorkingCopyEnabled('bbb', false)
    await new Promise(r => setTimeout(r, 0))
    const mirrors = (fetch as any).mock.calls.filter((c: any[]) => typeof c[0] === 'string' && c[0].includes('/params/wc-mirror'))
    const body = JSON.parse(mirrors[mirrors.length - 1][1].body)
    expect(body.enabled).toBe(false)
  })

  it('discardWorkingCopy 触发 wc.json 清理(POST /params/wc-clear)', async () => {
    const v = useViewStore()
    v.loadScanFile(fakeScanFile())
    v.forkWorkingCopy('bbb')
    v.discardWorkingCopy('bbb')
    await new Promise(r => setTimeout(r, 0))
    const clear = (fetch as any).mock.calls.find((c: any[]) => typeof c[0] === 'string' && c[0].includes('/params/wc-clear'))
    expect(clear).toBeTruthy()
    expect(clear[1].method).toBe('POST')
    expect(JSON.parse(clear[1].body).pid).toBe('bbb')
  })
})
