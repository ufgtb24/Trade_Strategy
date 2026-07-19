/**
 * Task 4 · DetailSidebar debug 卡片 · 中文 spinner · cancel tooltip
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DetailSidebar from '../src/components/DetailSidebar.vue'
import { useViewStore } from '../src/stores/view'

beforeEach(() => setActivePinia(createPinia()))

function seedDebugState(store: ReturnType<typeof useViewStore>) {
  ;(store as any).activeDetailCard = 'debug'
  ;(store as any).debugPending = true
  ;(store as any).debugTarget = {
    eventId: 'tb_1', bar: 218, className: 'tb', anchor: 'entry',
  }
}

describe('DetailSidebar · debug 卡片', () => {
  it('activeDetailCard=debug + debugPending → 显示 debug 卡片', () => {
    const store = useViewStore()
    seedDebugState(store)
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.detail-debug-card').exists()).toBe(true)
  })

  it('debug 卡片 spinner 文案含中文关键词', () => {
    const store = useViewStore()
    seedDebugState(store)
    const wrapper = mount(DetailSidebar)
    const html = wrapper.html()
    expect(html).toMatch(/等待|IDE|断点|PyCharm/)
  })

  it('cancel 按钮 tooltip 含中文提示', () => {
    const store = useViewStore()
    seedDebugState(store)
    const wrapper = mount(DetailSidebar)
    const btn = wrapper.find('.debug-cancel-btn')
    expect(btn.exists()).toBe(true)
    const tooltip = btn.attributes('title') ?? ''
    expect(tooltip).toMatch(/取消|放弃|F9|F8|unblock/)
  })

  it('cancel 按钮点击调 view.cancelDebug', async () => {
    const store = useViewStore()
    seedDebugState(store)
    const spy = vi.spyOn(store, 'cancelDebug')
    const wrapper = mount(DetailSidebar)
    await wrapper.find('.debug-cancel-btn').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })

  it('debug 卡片显示当前 anchor + bar', () => {
    const store = useViewStore()
    seedDebugState(store)
    const wrapper = mount(DetailSidebar)
    const text = wrapper.text()
    expect(text).toContain('tb')       // className
    expect(text).toContain('entry')     // anchor
    expect(text).toContain('218')       // bar
  })

  it('activeDetailCard ≠ debug 时不显示 debug 卡片', () => {
    const store = useViewStore()
    ;(store as any).activeDetailCard = 'time'
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.detail-debug-card').exists()).toBe(false)
  })

  it('debugError 非空 + debugPending=false → 显示失败文案 · 不显示 spinner / done', () => {
    const store = useViewStore()
    seedDebugState(store)
    ;(store as any).debugPending = false
    ;(store as any).debugError = 'fetch failed: 500'
    const wrapper = mount(DetailSidebar)
    const html = wrapper.html()
    expect(html).toContain('断点释放失败')
    expect(html).toContain('fetch failed: 500')
    expect(wrapper.find('.debug-spinner').exists()).toBe(false)
    expect(wrapper.find('.debug-done').exists()).toBe(false)
  })

  it('debugPending=true 时即使 debugError 非空也不显示错误分支(v-else-if 优先 pending)', () => {
    const store = useViewStore()
    seedDebugState(store)
    ;(store as any).debugError = 'stale error from previous attempt'
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.debug-spinner').exists()).toBe(true)
    expect(wrapper.find('.debug-error').exists()).toBe(false)
  })
})
