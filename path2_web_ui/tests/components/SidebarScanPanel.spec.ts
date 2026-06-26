import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SidebarScanPanel from '../../src/components/SidebarScanPanel.vue'
import StopScanDialog from '../../src/components/StopScanDialog.vue'
import { useScanStore } from '../../src/stores/scan'
import { usePatternsStore } from '../../src/stores/patterns'

vi.mock('../../src/api', () => ({
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ok: true})),
  cancelScan: vi.fn(() => Promise.resolve({ok: true})),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  loadConfig: vi.fn(() => Promise.resolve({scan: null} as any)),
  saveConfig: vi.fn(() => Promise.resolve()),
}))

describe('SidebarScanPanel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('button shows 开始扫描 when not running', async () => {
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const primary = w.findAll('button')[0]
    expect(primary.text()).toContain('开始扫描')
  })

  it('button shows 停止扫描 + btn-stop class when running', async () => {
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const s = useScanStore()
    ;(s as any).running = true
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const primary = w.findAll('button')[0]
    expect(primary.text()).toContain('停止扫描')
    expect(primary.classes()).toContain('btn-stop')
  })

  it('「打开历史」button disabled while running', async () => {
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const s = useScanStore()
    ;(s as any).running = true
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const openHist = w.findAll('button')[1]
    expect(openHist.attributes('disabled')).toBeDefined()
  })

  it('clicking 停止扫描 calls scan.cancel', async () => {
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const s = useScanStore()
    ;(s as any).running = true
    ;(s as any).currentScanId = 'scan_id_x'
    const spy = vi.spyOn(s, 'cancel').mockResolvedValue()
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.findAll('button')[0].trigger('click')
    expect(spy).toHaveBeenCalled()
  })

  it('clicking 打开历史 mounts ScanResultDialog', async () => {
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel, { attachTo: document.body })
    await flushPromises()
    await w.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.backdrop')).not.toBeNull()
    w.unmount()
  })
})

describe('SidebarScanPanel onPrimary 三分支', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hits=0 时点停止 → 直接 cancel(false),不弹 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 0, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValue()
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    expect(cancelSpy).toHaveBeenCalledWith(false)
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('hits>0 时点停止 → 弹 StopScanDialog,不立刻调 cancel', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValue()
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    expect(cancelSpy).not.toHaveBeenCalled()
    expect(w.findComponent(StopScanDialog).exists()).toBe(true)
  })

  it('dialog emit save → cancel(true) + 关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValue()
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('save')
    expect(cancelSpy).toHaveBeenCalledWith(true)
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog emit discard → cancel(false) + 关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValue()
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('discard')
    expect(cancelSpy).toHaveBeenCalledWith(false)
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog emit continue → 关 dialog,不调 cancel', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const cancelSpy = vi.spyOn(scan, 'cancel').mockResolvedValue()
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    const dlg = w.findComponent(StopScanDialog)
    await dlg.vm.$emit('continue')
    expect(cancelSpy).not.toHaveBeenCalled()
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })

  it('dialog 开着时 running 变 false → 自动关 dialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 5, total: 100, hits: 3, errors: 0 }
    ;(scan as any).currentScanId = 'sid'
    const p = usePatternsStore(); (p as any).selectedId = 'pat_x'
    const w = mount(SidebarScanPanel)
    await flushPromises()
    await w.get('button.btn-stop').trigger('click')
    expect(w.findComponent(StopScanDialog).exists()).toBe(true)
    ;(scan as any).running = false
    await flushPromises()
    expect(w.findComponent(StopScanDialog).exists()).toBe(false)
  })
})
