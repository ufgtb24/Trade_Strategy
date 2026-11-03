// 顶栏 symbol:回车打开(落在 annotate);列表里没有 → not_found,不动当前的图
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TopBar from '../../src/components/TopBar.vue'
import { useViewStore } from '../../src/stores/view'

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT'])),
}))

async function mountIt() {
  const w = mount(TopBar)
  await flushPromises()
  return { w, view: useViewStore(), input: w.get('[data-testid="symbol-input"]') }
}

describe('TopBar · symbol', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('字段名 symbol;股票列表进输入提示', async () => {
    const { w } = await mountIt()
    expect(w.text()).toContain('symbol')
    expect(w.findAll('datalist option').map(o => o.attributes('value'))).toEqual(['AAPL', 'MSFT'])
  })

  it('输入代码回车 → 打开它、落在 annotate', async () => {
    const { w, view, input } = await mountIt()
    view.mode = 'app'
    await input.setValue(' msft ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(view.symbol).toBe('MSFT')
    expect(view.mode).toBe('annotate')
    expect((input.element as HTMLInputElement).value).toBe('MSFT')
    expect(w.find('[data-testid="symbol-status"]').exists()).toBe(false)
  })

  it('列表里没有 → not_found,当前的图不动;再改输入提示消失', async () => {
    const { w, view, input } = await mountIt()
    view.openSymbol('AAPL')
    await flushPromises()
    await input.setValue('NEW26')
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.get('[data-testid="symbol-status"]').text()).toBe('not_found')
    expect(view.symbol).toBe('AAPL')
    await input.setValue('MSF')
    expect(w.find('[data-testid="symbol-status"]').exists()).toBe(false)
  })

  it('输入框显示当前打开的股票(从扫描列表换股时跟着变)', async () => {
    const { view, input } = await mountIt()
    view.selectSymbol('AAPL')
    await flushPromises()
    expect((input.element as HTMLInputElement).value).toBe('AAPL')
  })
})
