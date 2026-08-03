import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ScanResultDialog from '../../src/components/ScanResultDialog.vue'
import { useViewStore } from '../../src/stores/view'

vi.mock('../../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  listScans: vi.fn(() => Promise.resolve([
    {name: '20260603T120000', scan_ts: '20260603T120000', hits: 5, total: 200, size: 8192, partial: false},
    {name: '20260601T100000', scan_ts: '20260601T100000', hits: 0, total: 200, size: 4096, partial: false},
  ])),
  loadScan: vi.fn(() => Promise.resolve({results: [], pattern_ids: [], scan: {scan_ts: '20260603T120000', name: '20260603T120000'}, pattern_spec: {topology: {nodes: []}}} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
}))

describe('ScanResultDialog', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders rows with formatted ts/hits/size', async () => {
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const rows = w.findAll('.file-list tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('2026-06-03 12:00:00')
    expect(rows[0].text()).toContain('5 / 200')
    expect(rows[0].text()).toContain('8.0 KB')
    w.unmount()
  })

  it('emits close on Esc / Cancel button', async () => {
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    await w.find('footer button:first-of-type').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('Open button disabled when selection size != 1', async () => {
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const openBtn = w.find('footer button:last-of-type')
    expect(openBtn.attributes('disabled')).toBeDefined()       // 无选择
    await w.findAll('.file-list tbody tr')[0].trigger('click')
    expect(openBtn.attributes('disabled')).toBeUndefined()     // 单选
    // ctrl-click 第二行 → 多选
    await w.findAll('.file-list tbody tr')[1].trigger('click', { ctrlKey: true })
    expect(openBtn.attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('Delete on selection opens confirm layer', async () => {
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    await w.findAll('.file-list tbody tr')[0].trigger('click')
    await w.find('.card').trigger('keydown', { key: 'Delete' })
    await flushPromises()
    expect(w.find('.confirm-card').exists()).toBe(true)
    expect(w.find('.confirm-card').text()).toMatch(/Delete/)
    w.unmount()
  })

  it('confirm 层内回车即删(Delete 为默认动作)', async () => {
    const { deleteScan } = await import('../../src/api')
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    await w.findAll('.file-list tbody tr')[0].trigger('click')
    await w.find('.card').trigger('keydown', { key: 'Delete' })   // 打开确认层
    await flushPromises()
    expect(w.find('.confirm-card').exists()).toBe(true)
    await w.find('.card').trigger('keydown', { key: 'Enter' })    // 回车 → 直接删
    await flushPromises()
    expect(vi.mocked(deleteScan)).toHaveBeenCalledWith('20260603T120000')
    expect(w.find('.confirm-card').exists()).toBe(false)          // 确认层收起
    w.unmount()
  })

  it('confirm 层内 Esc 只收起确认(等同 Keep),不关整个对话框', async () => {
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    await w.findAll('.file-list tbody tr')[0].trigger('click')
    await w.find('.card').trigger('keydown', { key: 'Delete' })
    await flushPromises()
    expect(w.find('.confirm-card').exists()).toBe(true)
    await w.find('.card').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('.confirm-card').exists()).toBe(false)          // 确认层收起
    expect(w.emitted('close')).toBeFalsy()                        // 对话框未关闭
    w.unmount()
  })

  it('显示「未完成」标当某行 partial=true', async () => {
    const { listScans } = await import('../../src/api')
    vi.mocked(listScans).mockResolvedValueOnce([
      { name: '20260619T100000', scan_ts: '20260619T100000', hits: 3, total: 5, size: 200, partial: true },
      { name: '20260619T100100', scan_ts: '20260619T100100', hits: 9, total: 9, size: 500, partial: false },
    ] as any)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    const rows = w.findAll('.file-list tbody tr')
    expect(rows[0].html()).toContain('未完成')      // partial=true 行显示标
    expect(rows[1].html()).not.toContain('未完成')  // partial=false 行不显示标
    w.unmount()
  })

  it('confirm with current loaded ts calls view.clearScanFile', async () => {
    const v = useViewStore()
    v.loadScanFile({results: [], pattern_ids: [], scan: {scan_ts: '20260603T120000', name: '20260603T120000'}, pattern_spec: {topology: {nodes: []}}} as any)
    const w = mount(ScanResultDialog, { attachTo: document.body })
    await flushPromises()
    await w.findAll('.file-list tbody tr')[0].trigger('click')   // 选当前已加载
    await w.find('.card').trigger('keydown', { key: 'Delete' })
    await flushPromises()
    expect(w.find('.warn').exists()).toBe(true)                  // 红字提示
    await w.find('.confirm-card button.btn-stop').trigger('click')  // 点确认 Delete
    await flushPromises()
    expect(v.scanFile).toBeNull()
    w.unmount()
  })
})
