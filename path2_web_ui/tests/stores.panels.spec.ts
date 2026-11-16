import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'
import { usePanelsStore } from '../src/stores/panels'

const KEY = 'path2_web_ui.panels.v1'

describe('panels store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults all three to false when localStorage is empty', () => {
    const p = usePanelsStore()
    expect(p.showTopology).toBe(false)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(false)
  })

  it('toggle(key) flips that ref and persists to localStorage', async () => {
    const p = usePanelsStore()
    p.toggle('topology')
    await nextTick()
    expect(p.showTopology).toBe(true)
    const raw = localStorage.getItem(KEY)
    expect(raw).not.toBeNull()
    const obj = JSON.parse(raw!)
    expect(obj).toEqual({ topology: true, sidebar: false, slider: false, subHeightOffset: null,
                          leftCollapsed: false, annCollapsed: false, leftWidth: null, annWidth: null, detailWidth: null })
  })

  it('restores all three bools from localStorage on init', () => {
    localStorage.setItem(KEY, JSON.stringify({ topology: true, sidebar: false, slider: true }))
    const p = usePanelsStore()
    expect(p.showTopology).toBe(true)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(true)
  })

  it('falls back to all false on corrupt JSON in localStorage', () => {
    localStorage.setItem(KEY, '{not-json')
    const p = usePanelsStore()
    expect(p.showTopology).toBe(false)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(false)
  })

  it('toggle does not throw when localStorage.setItem throws (quota/private-mode)', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded')
    })
    const p = usePanelsStore()
    expect(() => p.toggle('sidebar')).not.toThrow()
    await nextTick()
    expect(p.showSidebar).toBe(true)
    expect(spy).toHaveBeenCalled()
  })
})

describe('panels store — subHeightOffset(spec 2026-07-03-subchart-boundary-model §1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('initial value is null when localStorage empty', () => {
    const p = usePanelsStore()
    expect(p.subHeightOffset).toBeNull()
  })

  it('setSubHeightOffset(-120) writes -120', () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(-120)
    expect(p.subHeightOffset).toBe(-120)
  })

  it('setSubHeightOffset(null) writes null (回 fit)', () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(-300)
    p.setSubHeightOffset(null)
    expect(p.subHeightOffset).toBeNull()
  })

  it('setSubHeightOffset(NaN) treated as null', () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(NaN)
    expect(p.subHeightOffset).toBeNull()
  })

  it('setSubHeightOffset(5) clamped to 0(offset 恒 ≤ 0)', () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(5)
    expect(p.subHeightOffset).toBe(0)
  })

  it('setSubHeightOffset persists to localStorage', async () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(-250)
    await nextTick()
    const obj = JSON.parse(localStorage.getItem(KEY)!)
    expect(obj.subHeightOffset).toBe(-250)
  })

  it('setSubHeightOffset(null) persists null', async () => {
    const p = usePanelsStore()
    p.setSubHeightOffset(-250)
    await nextTick()
    p.setSubHeightOffset(null)
    await nextTick()
    const obj = JSON.parse(localStorage.getItem(KEY)!)
    expect(obj.subHeightOffset).toBeNull()
  })

  it('loads subHeightOffset from localStorage on init', () => {
    localStorage.setItem(KEY, JSON.stringify({
      topology: false, sidebar: false, slider: false, subHeightOffset: -180,
    }))
    const p = usePanelsStore()
    expect(p.subHeightOffset).toBe(-180)
  })

  it('falls back to null when localStorage json missing subHeightOffset', () => {
    localStorage.setItem(KEY, JSON.stringify({
      topology: true, sidebar: false, slider: true,
    }))
    const p = usePanelsStore()
    expect(p.subHeightOffset).toBeNull()
  })

  it('ignores legacy subHeightOverride field(旧绝对高度语义 → 回 fit,spec §1 迁移)', () => {
    localStorage.setItem(KEY, JSON.stringify({
      topology: false, sidebar: false, slider: false, subHeightOverride: 180,
    }))
    const p = usePanelsStore()
    expect(p.subHeightOffset).toBeNull()
  })

  it('ignores obsolete mainSubRatio field in localStorage', () => {
    localStorage.setItem(KEY, JSON.stringify({
      topology: false, sidebar: false, slider: false, mainSubRatio: 0.42,
    }))
    const p = usePanelsStore()
    expect(p.subHeightOffset).toBeNull()
  })
})

describe('panels store — 左右栏的收起与宽度(各记一份,刷新后记得)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('没存过时:都开着、三份宽度都是没拖过(null)', () => {
    const p = usePanelsStore()
    expect([p.leftCollapsed, p.annCollapsed]).toEqual([false, false])
    expect([p.leftWidth, p.annWidth, p.detailWidth]).toEqual([null, null, null])
  })

  it('改了就存;新建的 store(刷新)读回同样的值,三份宽度互不影响', async () => {
    const p = usePanelsStore()
    p.leftCollapsed = true
    p.leftWidth = 150
    p.annWidth = 400
    await nextTick()
    setActivePinia(createPinia())
    const q = usePanelsStore()
    expect([q.leftCollapsed, q.annCollapsed]).toEqual([true, false])
    expect([q.leftWidth, q.annWidth, q.detailWidth]).toEqual([150, 400, null])
  })

  it('存下的宽度是坏值(非正数、非数字)时当没拖过', () => {
    localStorage.setItem(KEY, JSON.stringify({ leftWidth: -3, annWidth: 'wide', detailWidth: 0, leftCollapsed: 1 }))
    const p = usePanelsStore()
    expect([p.leftWidth, p.annWidth, p.detailWidth]).toEqual([null, null, null])
    expect(p.leftCollapsed).toBe(true)
  })

  it('旧的存法(只有三个开关)读进来:收起都是 false,宽度都是 null,三个开关照旧', () => {
    localStorage.setItem(KEY, JSON.stringify({ topology: true, sidebar: true, slider: false, subHeightOffset: -20 }))
    const p = usePanelsStore()
    expect([p.showTopology, p.showSidebar, p.subHeightOffset]).toEqual([true, true, -20])
    expect([p.leftCollapsed, p.annCollapsed, p.leftWidth]).toEqual([false, false, null])
  })
})
