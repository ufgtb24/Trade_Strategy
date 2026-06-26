import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'
import { SCAN_FILE } from '../fixtures'

describe('SidebarResultList', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('lists hit symbols with summary badges; click selects', async () => {
    const v = useViewStore()
    v.loadScanFile(SCAN_FILE)
    const w = mount(SidebarResultList)
    expect(w.text()).toContain('AAPL')
    expect(w.text()).toContain('bo')   // summary 徽章
    await w.get('[data-symbol="AAPL"]').trigger('click')
    expect(v.symbol).toBe('AAPL')
  })
})
