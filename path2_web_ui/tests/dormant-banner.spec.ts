// Task 13 · DormantDraftBanner:休眠草稿恢复 banner(chip 行下方)
// spec = docs/research/2026-07-20_params-profiles-dev-modes
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import DormantDraftBanner from '../src/components/DormantDraftBanner.vue'
import { useViewStore } from '../src/stores/view'

describe('DormantDraftBanner', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any)))
  })

  it('有休眠草稿 → banner 显示,点恢复装回内容轴(chip 灰,不自动激活)', async () => {
    localStorage.setItem('p2wc:20260720T000000:bbb', JSON.stringify(
      { dict: { bo: { total_window: 42 } }, baseline: { bo: { total_window: 10 } }, savedAt: 1 }))
    const v = useViewStore()
    v.loadScanFile({
      pattern_ids: ['bbb'],
      per_pattern: { bbb: { pattern_spec: { pattern_id: 'bbb', topology: { nodes: [], edges: [] }, event_styles: {} },
                            end_node: 'tb', params_snapshot: { bo: { total_window: 10 } } } },
      scan: { scan_ts: '20260720T000000', start_date: '2025-01-01', end_date: '2025-06-01', label_horizon: 20 },
      results: [{ symbol: 'A', per_pattern: {} }],
    } as any)
    const w = mount(DormantDraftBanner)
    expect(w.text()).toContain('未扫描的工作副本草稿')
    await w.get('[data-testid="dormant-restore-bbb"]').trigger('click')
    expect(v.workingCopy['bbb']!.currentDict).toEqual({ bo: { total_window: 42 } })  // 草稿装回 WC
    expect(v.isExploring).toBe(false)                    // 决策2:恢复只回内容轴,视图仍 snapshot
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 10 } })
    v.setWorkingCopyEnabled('bbb', true)                 // chip 点亮
    expect(v.effectiveParamsOverride).toEqual({ bo: { total_window: 42 } })
  })
})
