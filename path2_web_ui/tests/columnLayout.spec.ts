// 左右栏拖宽的几何(src/components/columnLayout.ts):左栏夹在 [最窄, 内容全宽],到了全宽记成全开;
// 右栏夹在 [最窄, 半屏]。拖到最窄就停,不会变成收起(收起只靠箭头和快捷键)。
import { describe, it, expect } from 'vitest'
import { LEFT_MIN, ANN_MIN, leftDragged, rightDragged, rightStyle } from '../src/components/columnLayout'

describe('leftDragged', () => {
  it('在最窄与内容全宽之间:取整后照记', () => {
    expect(leftDragged(228.4, 348)).toBe(228)
    expect(leftDragged(LEFT_MIN + 1, 348)).toBe(LEFT_MIN + 1)
  })
  it('拖过最窄:停在最窄(不是 0、不是收起)', () => {
    expect(leftDragged(10, 348)).toBe(LEFT_MIN)
    expect(leftDragged(-200, 348)).toBe(LEFT_MIN)
  })
  it('拖到或拖过内容全宽:记成全开 null', () => {
    expect(leftDragged(348, 348)).toBeNull()
    expect(leftDragged(347.6, 348)).toBeNull()
    expect(leftDragged(900, 348)).toBeNull()
  })
})

describe('rightDragged', () => {
  it('在最窄与半屏之间照记;拖过最窄停在最窄;拖过半屏停在半屏', () => {
    expect(rightDragged(400.6, ANN_MIN, 2000)).toBe(401)
    expect(rightDragged(100, ANN_MIN, 2000)).toBe(ANN_MIN)
    expect(rightDragged(1500, ANN_MIN, 2000)).toBe(1000)
  })
  it('窗口窄到半屏不足最窄时取最窄', () => {
    expect(rightDragged(600, ANN_MIN, 300)).toBe(ANN_MIN)
  })
})

describe('rightStyle', () => {
  it('没拖过用默认宽度;拖过用拖出的;都带半屏上限与最窄下限', () => {
    expect(rightStyle(null, 320, 260)).toEqual({ width: '320px', maxWidth: '50vw', minWidth: '260px' })
    expect(rightStyle(410, 320, 260)).toEqual({ width: '410px', maxWidth: '50vw', minWidth: '260px' })
  })
})
