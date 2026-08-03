import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SidebarScanPanel from '../../src/components/SidebarScanPanel.vue'
import { useScanStore } from '../../src/stores/scan'

vi.mock('../../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getPatterns: vi.fn(() => Promise.resolve([])),
  getConfig: vi.fn(() => Promise.resolve({ dataset_dir:'', scan:{start_date:'', end_date:'', workers:1, ticker_regex:null, label_horizon:20}, last_selected_pattern:'' })),
  putConfig: vi.fn(() => Promise.resolve()),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ ok: true })),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
  startScan: vi.fn(() => Promise.resolve('scan_id_x')),
  streamScan: vi.fn(() => ({ close: () => {} } as any)),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
}))

describe('SidebarScanPanel — topbar', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows [扫描 ⚙] and [打开历史 …] buttons', async () => {
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const btns = w.findAll('button').map(b => b.text())
    expect(btns.some(t => t.includes('扫描'))).toBe(true)
    expect(btns.some(t => t.includes('打开历史'))).toBe(true)
  })

  it('[扫描 ⚙] disabled when scan.running', async () => {
    const scan = useScanStore(); (scan as any).running = true
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const scanBtn = w.findAll('button').find(b => b.text().includes('扫描'))!
    expect(scanBtn.attributes('disabled')).toBeDefined()
  })

  it('[停止扫描] visible only when scan.running', async () => {
    const w = mount(SidebarScanPanel)
    await flushPromises()
    expect(w.findAll('button').find(b => b.text().includes('停止扫描'))).toBeUndefined()
    const scan = useScanStore(); (scan as any).running = true
    await w.vm.$nextTick()
    expect(w.findAll('button').find(b => b.text().includes('停止扫描'))).toBeDefined()
  })

  it('progress renders scanned/total/hits when running', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 12, total: 500, hits: 3, errors: 0 }
    const w = mount(SidebarScanPanel)
    await flushPromises()
    expect(w.text()).toContain('12/500')
    expect(w.text()).toContain('3')
  })

  it('click [扫描 ⚙] mounts ScanConfigDialog', async () => {
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const scanBtn = w.findAll('button').find(b => b.text().includes('扫描'))!
    await scanBtn.trigger('click')
    expect(w.find('.backdrop').exists()).toBe(true)   // ScanConfigDialog root
  })

  it('click [打开历史 …] mounts ScanResultDialog', async () => {
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const histBtn = w.findAll('button').find(b => b.text().includes('打开历史'))!
    await histBtn.trigger('click')
    // ScanResultDialog 组件有自己 root class(现有实现);用组件名断言
    expect(w.findComponent({ name: 'ScanResultDialog' }).exists()).toBe(true)
  })

  it('click [停止扫描] with hits>0 opens StopScanDialog', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 12, total: 500, hits: 3, errors: 0 }
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const stopBtn = w.findAll('button').find(b => b.text().includes('停止扫描'))!
    await stopBtn.trigger('click')
    expect(w.findComponent({ name: 'StopScanDialog' }).exists()).toBe(true)
  })

  it('click [停止扫描] with hits=0 calls scan.cancel(false) directly', async () => {
    const scan = useScanStore()
    ;(scan as any).running = true
    ;(scan as any).progress = { scanned: 12, total: 500, hits: 0, errors: 0 }
    const spy = vi.spyOn(scan, 'cancel')
    const w = mount(SidebarScanPanel)
    await flushPromises()
    const stopBtn = w.findAll('button').find(b => b.text().includes('停止扫描'))!
    await stopBtn.trigger('click')
    expect(spy).toHaveBeenCalledWith(false)
  })
})
