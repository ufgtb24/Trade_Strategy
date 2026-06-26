import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarPatternPanel from '../../src/components/SidebarPatternPanel.vue'
import { usePatternsStore } from '../../src/stores/patterns'

const patternsFixture = [
  { pattern_id: 'bo_only', display_name: 'bo', topology: { nodes: [], edges: [] }, event_styles: {} },
  { pattern_id: 'bbb',     display_name: 'BBB pattern', topology: { nodes: [], edges: [] }, event_styles: {} },
]

describe('SidebarPatternPanel — checkbox multi-select', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders one checkbox per pattern', () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    const checks = w.findAll('input[type="checkbox"]')
    expect(checks.length).toBeGreaterThanOrEqual(2)
  })

  it('click checkbox toggles selectedIds', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    const firstCheck = w.find('input[type="checkbox"][data-pid="bo_only"]')
    await firstCheck.setValue(true)
    expect(ps.selectedIds.has('bo_only')).toBe(true)
    await firstCheck.setValue(false)
    expect(ps.selectedIds.has('bo_only')).toBe(false)
  })

  it('Select All button selects all', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    const w = mount(SidebarPatternPanel)
    await w.find('[data-action="select-all"]').trigger('click')
    expect(ps.selectedIds.size).toBe(2)
  })

  it('Clear button clears selection', async () => {
    const ps = usePatternsStore()
    ps.list = patternsFixture as any
    ps.loaded = true
    ps.selectAll()
    const w = mount(SidebarPatternPanel)
    await w.find('[data-action="select-none"]').trigger('click')
    expect(ps.selectedIds.size).toBe(0)
  })
})
