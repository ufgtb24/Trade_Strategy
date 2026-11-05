import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StopScanDialog from '../../src/components/StopScanDialog.vue'

describe('StopScanDialog', () => {
  it('renders hitStocks in prompt', () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 7 } })
    expect(w.text()).toContain('7')
    expect(w.text()).toContain('当前已经命中')
  })

  it('emits save on save button', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 } })
    await w.get('[data-testid="btn-save"]').trigger('click')
    expect(w.emitted('save')).toHaveLength(1)
  })

  it('emits discard on discard button', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 } })
    await w.get('[data-testid="btn-discard"]').trigger('click')
    expect(w.emitted('discard')).toHaveLength(1)
  })

  it('emits continue on continue button', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 } })
    await w.get('[data-testid="btn-continue"]').trigger('click')
    expect(w.emitted('continue')).toHaveLength(1)
  })

  it('Esc keydown does not emit anything (ignored)', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 }, attachTo: document.body })
    await w.find('.card').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('save')).toBeUndefined()
    expect(w.emitted('discard')).toBeUndefined()
    expect(w.emitted('continue')).toBeUndefined()
    w.unmount()
  })

  it('clicking backdrop does not emit anything (ignored)', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 } })
    await w.get('.backdrop').trigger('click')              // self trigger,实现里不应 emit
    expect(w.emitted('save')).toBeUndefined()
    expect(w.emitted('discard')).toBeUndefined()
    expect(w.emitted('continue')).toBeUndefined()
  })

  it('hitStocks prop updates reactively', async () => {
    const w = mount(StopScanDialog, { props: { hitStocks: 3 } })
    expect(w.text()).toContain('3')
    await w.setProps({ hitStocks: 9 })
    expect(w.text()).toContain('9')
  })
})
