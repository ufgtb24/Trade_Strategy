// Task 12 · scan 发起/完成 与 Working Copy 生命周期联动(hash 守卫自动清 WC + toast)
// spec = docs/research/2026-07-20_params-profiles-dev-modes
//
// 契约:
// - markWcLaunch(pids):发起扫描时记参与 pid 的 WC.currentDict 字节快照
// - settleWcAfterDone({partial}):done 回调里调用;非-partial 且 WC 字节等价(scan 期间未再编辑)才清
//   (discardWorkingCopy + toast「已固化」);partial 一律不清;scan 期间被继续编辑的 pid 也不清(保留新编辑)
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { useScanStore } from '../src/stores/scan'

const fakeScanFile = () => ({
  pattern_ids: ['bbb'],
  per_pattern: { bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
                        end_node: 'tb', params_snapshot: { bo: { total_window: 10 } } } },
  scan: { scan_ts: '20260720T000000', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
  results: [{ symbol: 'A', per_pattern: {} }],
})

describe('scan 完成自动清 WC(hash 守卫)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any)))
  })

  it('scan 期间 WC 未再编辑 → done 后清空 + toast', () => {
    const v = useViewStore(); const s = useScanStore()
    v.loadScanFile(fakeScanFile() as any)
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    s.markWcLaunch(['bbb'])                 // 发起时记 hash
    s.settleWcAfterDone({ partial: false })  // 完成回调
    expect(v.workingCopy['bbb']).toBeUndefined()
    expect(localStorage.getItem('p2wc:20260720T000000:bbb')).toBeNull()
    expect(v.toastMsg).toContain('固化')
  })

  it('scan 期间 WC 被继续编辑 → 不清(hash 守卫)', () => {
    const v = useViewStore(); const s = useScanStore()
    v.loadScanFile(fakeScanFile() as any)
    v.forkWorkingCopy('bbb')
    v.updateWorkingCopy('bbb', { bo: { total_window: 42 } })
    s.markWcLaunch(['bbb'])
    v.updateWorkingCopy('bbb', { bo: { total_window: 43 } })   // 异步扫描期间又改了
    s.settleWcAfterDone({ partial: false })
    expect(v.workingCopy['bbb']).toBeDefined()                  // 保留新编辑
  })

  it('partial save → 不清', () => {
    const v = useViewStore(); const s = useScanStore()
    v.loadScanFile(fakeScanFile() as any)
    v.forkWorkingCopy('bbb')
    s.markWcLaunch(['bbb'])
    s.settleWcAfterDone({ partial: true })
    expect(v.workingCopy['bbb']).toBeDefined()
  })
})
