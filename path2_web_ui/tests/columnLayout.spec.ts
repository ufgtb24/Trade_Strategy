// 左右栏拖宽的几何(src/components/columnLayout.ts):左栏夹在 [最窄, 内容全宽],到了全宽记成全开;
// 右栏夹在 [最窄, 半屏]。拖到最窄就停,不会变成收起(收起只靠箭头和快捷键)。
import { describe, it, expect } from 'vitest'
import { LEFT_MIN, ANN_SIZE, leftDragged, rightDragged, rightStyle } from '../src/components/columnLayout'
const ANN_MIN = ANN_SIZE.min

describe('leftDragged', () => {
  it('在最窄与内容全宽之间:取整后照记', () => {
    expect(leftDragged(228.4, 348, null)).toBe(228)
    expect(leftDragged(LEFT_MIN + 1, 348, 300)).toBe(LEFT_MIN + 1)
  })
  it('拖过最窄:停在最窄(不是 0、不是收起)', () => {
    expect(leftDragged(10, 348, null)).toBe(LEFT_MIN)
    expect(leftDragged(-200, 348, 200)).toBe(LEFT_MIN)
  })
  it('拖到或拖过内容全宽:记成全开 null', () => {
    expect(leftDragged(348, 348, null)).toBeNull()
    expect(leftDragged(347.6, 348, 290)).toBeNull()
    expect(leftDragged(900, 348, 100)).toBeNull()
  })
  it('先前记下的宽度不小于当前内容全宽(内容窄的页,栏边已在最外面):往外拖不改它', () => {
    expect(leftDragged(260, 220, 290)).toBe(290)
    expect(leftDragged(220, 220, 220)).toBe(220)
  })
})

describe('rightDragged', () => {
  it('在最窄与半屏之间照记;拖过最窄停在最窄;拖过半屏停在半屏', () => {
    expect(rightDragged(400.6, ANN_SIZE, 2000)).toBe(401)
    expect(rightDragged(100, ANN_SIZE, 2000)).toBe(ANN_MIN)
    expect(rightDragged(1500, ANN_SIZE, 2000)).toBe(1000)
  })
  it('窗口窄到半屏不足最窄时取最窄', () => {
    expect(rightDragged(600, ANN_SIZE, 300)).toBe(ANN_MIN)
  })
})

describe('rightStyle', () => {
  it('没拖过用默认宽度;拖过用拖出的;都带半屏上限与最窄下限', () => {
    expect(rightStyle(null, { dflt: 320, min: 260 })).toEqual({ width: '320px', maxWidth: '50vw', minWidth: '260px' })
    expect(rightStyle(410, { dflt: 320, min: 260 })).toEqual({ width: '410px', maxWidth: '50vw', minWidth: '260px' })
  })
})
