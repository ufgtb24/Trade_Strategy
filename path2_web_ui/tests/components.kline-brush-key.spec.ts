import { describe, it, expect } from 'vitest'

// 单独测 KlineChart 里 brush toggle 快捷键分支的行为;不 mount 整个 KlineChart(它依赖 ECharts 初始化重、
// jsdom 下 canvas/DOMRect 会崩)。改用小型 harness:抽出 onKeyDown 的判定逻辑做纯函数测试。
// 注:Shift+,(物理 Shift+逗号键)在美式键盘下 KeyboardEvent.key 为 '<'(Shift 把逗号变成小于号),
// 故判定以 '<' 为准;面向用户的文案写 "Shift+,"。
import { isBrushToggleKey } from '../src/components/klineBrushKey'

describe('KlineChart · brush toggle key = Shift+,', () => {
  it("Shift+, → true(美式键盘 key 为 '<')", () => {
    expect(isBrushToggleKey({ key: '<', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(true)
  })
  it('单字符 ,(无 shift) → false', () => {
    expect(isBrushToggleKey({ key: ',', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Shift+B → false(旧键位,现不再是 brush)', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Ctrl+Shift+, → false(有其他修饰)', () => {
    expect(isBrushToggleKey({ key: '<', shiftKey: true, ctrlKey: true, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Shift+. → false(键不对,> 不是 brush)', () => {
    expect(isBrushToggleKey({ key: '>', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
})
