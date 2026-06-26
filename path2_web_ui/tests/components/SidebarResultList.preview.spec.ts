import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'
import { SCAN_FILE, ANALYSIS, PATTERN } from '../fixtures'

const PREVIEW_RESP = {
  analysis: ANALYSIS,
  summary: { events: 6, matches: 1 },
  pattern_spec: PATTERN,
  scan: SCAN_FILE.scan,
}

vi.mock('../../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve({} as any)),
  getPreview: vi.fn(() => Promise.resolve(PREVIEW_RESP)),
}))

describe('SidebarResultList preview UI', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('checkbox disabled when no scanFile', () => {
    const w = mount(SidebarResultList)
    const cb = w.get('input[type="checkbox"]')
    expect((cb.element as HTMLInputElement).disabled).toBe(true)
  })

  it('checkbox enabled when scanFile present', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const w = mount(SidebarResultList)
    const cb = w.get('input[type="checkbox"]')
    expect((cb.element as HTMLInputElement).disabled).toBe(false)
  })

  it('checkbox toggle calls setPreviewEnabled', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const spy = vi.spyOn(v, 'setPreviewEnabled')
    const w = mount(SidebarResultList)
    await w.get('input[type="checkbox"]').setValue(true)
    expect(spy).toHaveBeenCalledWith(true)
  })

  it('refresh button disabled when previewEnabled=false', () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    const w = mount(SidebarResultList)
    const btn = w.get('button.refresh')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled when no preview yet', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewEnabled = true                              // 强设
    const w = mount(SidebarResultList)
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled during loading', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    v.previewLoading = true                              // 强设模拟 loading
    const w = mount(SidebarResultList)
    await flushPromises()
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button disabled when preview.symbol mismatches symbol', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    v.symbol = 'OTHER'                                   // 模拟切走但 preview 未清(异常路径)
    const w = mount(SidebarResultList)
    await flushPromises()
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refresh button enabled when all four conditions met', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    const w = mount(SidebarResultList)
    expect((w.get('button.refresh').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('refresh click calls runPreview', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    await v.setPreviewEnabled(true); await flushPromises()
    const spy = vi.spyOn(v, 'runPreview')
    const w = mount(SidebarResultList)
    await w.get('button.refresh').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })

  it('loading status visible during loading', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewLoading = true
    const w = mount(SidebarResultList)
    expect(w.text()).toContain('计算中…')
  })

  it('error bar visible and closable', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE); v.selectSymbol('AAPL')
    v.previewError = '500: boom'
    const spy = vi.spyOn(v, 'clearPreview')
    const w = mount(SidebarResultList)
    expect(w.text()).toContain('500: boom')
    await w.get('.error a').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })
})
