import { describe, it, expect } from 'vitest'

// 单独测 KlineChart 里 B 快捷键分支的行为;不 mount 整个 KlineChart(它依赖 ECharts 初始化重、
// jsdom 下 canvas/DOMRect 会崩)。改用小型 harness:抽出 onKeyDown 的判定逻辑做纯函数测试。
import { isBrushToggleKey } from '../src/components/klineBrushKey'

describe('KlineChart · brush toggle key = Shift+B', () => {
  it('Shift+B → true', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(true)
  })
  it('单字符 b → false', () => {
    expect(isBrushToggleKey({ key: 'b', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('单字符 B → false(无 shift 修饰,虽然 CapsLock 可能导致大写)', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Ctrl+Shift+B → false(有其他修饰)', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: true, ctrlKey: true, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Shift+A → false(键不对)', () => {
    expect(isBrushToggleKey({ key: 'A', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
})
