import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import KlineChart from '../../src/components/KlineChart.vue'
import { useViewStore } from '../../src/stores/view'
import { SCAN_FILE } from '../fixtures'

// jsdom 无 ResizeObserver 实现(KlineChart.vue onMounted 用它观测 main/sub chart 容器 resize)——
// 挂载真实组件(非 stub,ChartArea.spec.ts 一律 stub KlineChart 正是为了绕开这层)必须补 polyfill。
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

vi.mock('../../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getOhlc: vi.fn(() => Promise.resolve({ bars: [] })),
}))

// jsdom 无 canvas 2D context 实现,echarts 真实 setOption 会在 zrender 画布层抛异常
// (Layer.initContext 拿到的 ctx 是 null)。本测试只关心 contextmenu DOM 交互 + 剪贴板,
// 不关心真实渲染像素(那是 e2e/Playwright 的职责,见 e2e/*.spec.ts),故 mock 整个
// echarts.init 返回值,跳过真实 canvas 绘制管线。
function makeFakeChart() {
  const zr = { on: vi.fn(), off: vi.fn() }
  return {
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    getZr: () => zr,
    getOption: () => ({}),
    dispatchAction: vi.fn(),
    convertToPixel: () => [0, 0],
    getWidth: () => 800,
  }
}
vi.mock('echarts', () => ({
  init: vi.fn(() => makeFakeChart()),
}))

describe('KlineChart 右键 driver 复制菜单(Task 23 · V1 D0)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(() => Promise.resolve()) },
      configurable: true,
    })
  })

  function mountWithScan() {
    const view = useViewStore()
    view.loadScanFile(SCAN_FILE)
    view.selectSymbol('AAPL')
    const w = mount(KlineChart)
    return { w, view }
  }

  it('主图右键弹菜单 · 复制 driver 脚本', async () => {
    const { w } = mountWithScan()

    await w.find('.main-chart').trigger('contextmenu')
    expect(w.find('.driver-menu').exists()).toBe(true)

    const copyBtn = w.find('.copy-driver-btn')
    expect(copyBtn.exists()).toBe(true)
    await copyBtn.trigger('click')

    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1)
    const script = (navigator.clipboard.writeText as any).mock.calls[0][0] as string
    // symbol/pattern_id 承 Task 18/21 pattern 从 view store 取(非 props),真实 API 承 Task 22
    // (build_pattern + attach_and_collect + engine.analyze + detach,非 brief 原始伪代码的
    // 不存在的 scan_one_symbol)。
    expect(script).toContain("set_current_symbol('AAPL')")
    expect(script).toContain('from path2_apps.bottom_burst.dag_spec import build_pattern')
    expect(script).toContain('from path2_apps.bottom_burst.params import Params')
    expect(script).toContain('from path2_web.gate_collector import attach_and_collect, detach')
    expect(script).toContain('from path2.dag.engine import analyze')
    expect(script).toContain('breakpoint()')

    // 复制后菜单自动关闭
    expect(w.find('.driver-menu').exists()).toBe(false)
  })

  it('click outside 主图之外 → 菜单自动关闭', async () => {
    const { w } = mountWithScan()

    await w.find('.main-chart').trigger('contextmenu')
    expect(w.find('.driver-menu').exists()).toBe(true)

    document.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await w.vm.$nextTick()

    expect(w.find('.driver-menu').exists()).toBe(false)
  })

  it('ESC → 菜单关闭', async () => {
    const { w } = mountWithScan()

    await w.find('.main-chart').trigger('contextmenu')
    expect(w.find('.driver-menu').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await w.vm.$nextTick()

    expect(w.find('.driver-menu').exists()).toBe(false)
  })
})
