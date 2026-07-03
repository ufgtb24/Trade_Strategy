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
    expect(obj).toEqual({ topology: true, sidebar: false, slider: false, subHeightOffset: null })
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
