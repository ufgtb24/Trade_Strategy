import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ScanConfigDialog from '../../src/components/ScanConfigDialog.vue'
import { usePatternsStore } from '../../src/stores/patterns'
import { useConfigStore } from '../../src/stores/config'
import { useScanStore } from '../../src/stores/scan'

vi.mock('../../src/api', () => ({
  getPatterns: vi.fn(() => Promise.resolve([
    { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} },
    { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} },
    { pattern_id: 'three',   topology: { nodes: [], edges: [] }, event_styles: {} },
  ])),
  getConfig: vi.fn(() => Promise.resolve({
    dataset_dir: '/d',
    scan: { start_date: '2025-01-01', end_date: '2025-12-31',
            workers: 8, ticker_regex: null, label_horizon: 20 },
    last_selected_pattern: '',
  })),
  putConfig: vi.fn(() => Promise.resolve()),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
}))

describe('ScanConfigDialog', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('[开始扫描] enabled after selecting one pattern', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore()
    ps.toggleSelected('bo_only')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('click row (no modifier) replaces selection', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')
    await rows[1].trigger('click')                    // 单选替换
    const ps = usePatternsStore()
    expect([...ps.selectedIds]).toEqual(['bbb'])
  })

  it('ctrl+click toggles current only', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')                    // {bo_only}
    await rows[2].trigger('click', { ctrlKey: true }) // {bo_only, three}
    const ps = usePatternsStore()
    expect([...ps.selectedIds].sort()).toEqual(['bo_only', 'three'])
  })

  it('shift+click selects range from anchor to current', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const rows = w.findAll('li[data-pid]')
    await rows[0].trigger('click')                    // anchor = 0, {bo_only}
    await rows[2].trigger('click', { shiftKey: true })// 0..2 全选
    const ps = usePatternsStore()
    expect([...ps.selectedIds].sort()).toEqual(['bbb', 'bo_only', 'three'])
  })

  it('[全选] / [清空] / [反选] buttons work', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore()
    const btns = w.findAll('.patterns-block button')
    const btnAll = btns.find(b => b.text() === '全选')!
    const btnNone = btns.find(b => b.text() === '清空')!
    const btnInv = btns.find(b => b.text() === '反选')!
    await btnAll.trigger('click')
    expect(ps.selectedIds.size).toBe(3)
    await btnNone.trigger('click')
    expect(ps.selectedIds.size).toBe(0)
    ps.toggleSelected('bo_only')
    await btnInv.trigger('click')
    expect([...ps.selectedIds].sort()).toEqual(['bbb', 'three'])
  })

  it('[开始扫描] saves 5 fields + runs scan + emits close', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.toggleSelected('bo_only')
    const cfg = useConfigStore()
    const scan = useScanStore()
    const spySave = vi.spyOn(cfg, 'save')
    const spyRun = vi.spyOn(scan, 'run')
    await w.vm.$nextTick()
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    btn.trigger('click')
    await flushPromises()
    expect(spySave).toHaveBeenCalled()
    const savedArg = spySave.mock.calls[0][0]
    expect(savedArg.scan).toMatchObject({
      start_date: '2025-01-01', end_date: '2025-12-31',
      workers: 8, label_horizon: 20, ticker_regex: null,
    })
    expect(spyRun).toHaveBeenCalled()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('[取消] emits close without save', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const cfg = useConfigStore()
    const spySave = vi.spyOn(cfg, 'save')
    const btn = w.findAll('button').find(b => b.text() === '取消')!
    await btn.trigger('click')
    expect(spySave).not.toHaveBeenCalled()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('ticker regex empty string -> saved as null', async () => {
    const w = mount(ScanConfigDialog)
    await flushPromises()
    const ps = usePatternsStore(); ps.toggleSelected('bo_only')
    const cfg = useConfigStore()
    const spySave = vi.spyOn(cfg, 'save')
    const tr = w.find('input[data-field="ticker_regex"]')
    await tr.setValue('  ')                            // 空白 -> null
    const btn = w.findAll('button').find(b => b.text() === '开始扫描')!
    await btn.trigger('click')
    expect(spySave.mock.calls[0][0].scan.ticker_regex).toBe(null)
  })
})
