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
    expect(obj).toEqual({ topology: true, sidebar: false, slider: false })
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
