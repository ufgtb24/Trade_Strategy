import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'

// 声明 open 为 prop,确保 stub 能被 .props('open') 读到 drawerOpen 的真值。
const DrawerStub = {
  name: 'WorkingCopyDrawer',
  template: '<div></div>',
  props: { open: Boolean },
}

function mountIt() {
  return mount(ChartArea, {
    global: {
      stubs: {
        KlineChart: true,
        DetailSidebar: true,
        TopologyControl: true,
        WorkingCopyDrawer: DrawerStub,
      },
    },
  })
}

describe('ChartArea — Shift+P toggles params drawer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('Shift+P flips drawer open prop false → true', async () => {
    const w = mountIt()
    const drawer = w.findComponent({ name: 'WorkingCopyDrawer' })
    expect(drawer.props('open')).toBe(false)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', shiftKey: true }))
    await flushPromises()
    expect(drawer.props('open')).toBe(true)
    w.unmount()
  })

  it('Shift+P twice closes drawer again', async () => {
    const w = mountIt()
    const drawer = w.findComponent({ name: 'WorkingCopyDrawer' })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', shiftKey: true }))
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', shiftKey: true }))
    await flushPromises()
    expect(drawer.props('open')).toBe(false)
    w.unmount()
  })

  it('plain p (no shift) does not open drawer', async () => {
    const w = mountIt()
    const drawer = w.findComponent({ name: 'WorkingCopyDrawer' })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', shiftKey: false }))
    await flushPromises()
    expect(drawer.props('open')).toBe(false)
    w.unmount()
  })

  it('Shift+P ignored when focus is in an input (防误触)', async () => {
    const w = mountIt()
    const drawer = w.findComponent({ name: 'WorkingCopyDrawer' })
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', shiftKey: true }))
    await flushPromises()
    expect(drawer.props('open')).toBe(false)
    input.remove()
    w.unmount()
  })

  it('Shift+B does not open drawer (不是参数键)', async () => {
    const w = mountIt()
    const drawer = w.findComponent({ name: 'WorkingCopyDrawer' })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'B', shiftKey: true }))
    await flushPromises()
    expect(drawer.props('open')).toBe(false)
    w.unmount()
  })
})
