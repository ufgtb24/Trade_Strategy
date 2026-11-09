// 反馈作答面板与 feedback 工具的纯函数:面板开着时按键归不归面板(含输入法组字)、面板翻边、拖选竖带的左右。
import { describe, it, expect } from 'vitest'
import { isComposingKey, panelKeyAction, placePanel, rangeBandPx, PANEL_GAP } from '../src/components/feedbackPanel'

describe('panelKeyAction', () => {
  it('Enter 保存、Esc 关面板', () => {
    expect(panelKeyAction({ key: 'Enter' })).toBe('save')
    expect(panelKeyAction({ key: 'Escape' })).toBe('close')
  })

  it('输入法组字中一律不截:isComposing,或 keyCode 229(Enter 是上屏、Esc 是取消组字)', () => {
    expect(panelKeyAction({ key: 'Enter', isComposing: true })).toBeNull()
    expect(panelKeyAction({ key: 'Escape', isComposing: true })).toBeNull()
    expect(panelKeyAction({ key: 'Enter', keyCode: 229 })).toBeNull()
    expect(panelKeyAction({ key: 'Process', keyCode: 229 })).toBeNull()
    expect(panelKeyAction({ key: 'Escape', keyCode: 229 })).toBeNull()
    expect(isComposingKey({ isComposing: false, keyCode: 13 })).toBe(false)
    expect(isComposingKey({ keyCode: 229 })).toBe(true)
  })

  it('←/→ 与别的键不截(照旧在族里走)', () => {
    for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'Delete', 'a', 'Tab', ' ']) {
      expect(panelKeyAction({ key })).toBeNull()
    }
  })

  it('带 Ctrl / Meta / Alt 的不截;焦点在面板外的输入框里不截', () => {
    expect(panelKeyAction({ key: 'Enter', ctrlKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Enter', metaKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Escape', altKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Enter' }, true)).toBeNull()
    expect(panelKeyAction({ key: 'Escape' }, true)).toBeNull()
  })
})

describe('placePanel', () => {
  const VP = { w: 1000, h: 800 }
  it('放得下:点击处右下', () => {
    expect(placePanel({ x: 100, y: 200 }, { w: 300, h: 200 }, VP)).toEqual({ x: 100 + PANEL_GAP, y: 200 + PANEL_GAP })
  })
  it('右边放不下翻到左边,下边放不下翻到上边', () => {
    expect(placePanel({ x: 900, y: 700 }, { w: 300, h: 200 }, VP)).toEqual({ x: 900 - PANEL_GAP - 300, y: 700 - PANEL_GAP - 200 })
    expect(placePanel({ x: 900, y: 100 }, { w: 300, h: 200 }, VP)).toEqual({ x: 900 - PANEL_GAP - 300, y: 100 + PANEL_GAP })
  })
  it('翻过去仍放不下时贴住视口边', () => {
    expect(placePanel({ x: 50, y: 50 }, { w: 2000, h: 2000 }, VP)).toEqual({ x: 0, y: 0 })
  })
})

describe('rangeBandPx', () => {
  // 第 i 根 K 线中心在 100 + 10·i(一根宽 10)
  const toPx = (i: number) => 100 + 10 * i
  it('整根 K 线覆盖首尾两根', () => {
    expect(rangeBandPx(2, 5, toPx, 56, 900)).toEqual({ left: 115, width: 40 })
    expect(rangeBandPx(3, 3, toPx, 56, 900)).toEqual({ left: 125, width: 10 })
  })
  it('裁到图区内;整段在图区外为 null', () => {
    expect(rangeBandPx(0, 2, toPx, 100, 900)).toEqual({ left: 100, width: 25 })
    expect(rangeBandPx(0, 2, toPx, 200, 900)).toBeNull()
  })
})
