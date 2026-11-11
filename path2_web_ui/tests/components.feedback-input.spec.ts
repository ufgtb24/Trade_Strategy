// 反馈作答面板与 feedback 工具的纯函数:面板开着时按键归不归面板(含输入法组字)、面板翻边、拖选竖带的左右。
import { describe, it, expect } from 'vitest'
import {
  NOTE_MAX_H, PANEL_GAP, isComposingKey, markAnchor, noteHeight, panelKeyAction, placePanel, rangeBandPx, selectedBandPx,
} from '../src/components/feedbackPanel'

describe('panelKeyAction', () => {
  it('Enter 保存、Esc 关面板', () => {
    expect(panelKeyAction({ key: 'Enter' })).toBe('save')
    expect(panelKeyAction({ key: 'Escape' })).toBe('close')
  })
  it('Shift+Enter 不截(note 里是换行);Shift+Esc 照关', () => {
    expect(panelKeyAction({ key: 'Enter', shiftKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Escape', shiftKey: true })).toBe('close')
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

describe('selectedBandPx', () => {
  const toPx = (i: number) => 100 + 10 * i
  it('左右同拖选的竖带;范围都在图区里时两侧都不算被裁', () => {
    expect(selectedBandPx(2, 5, toPx, 56, 900)).toEqual({ left: 115, width: 40, cutLeft: false, cutRight: false })
    expect(selectedBandPx(3, 3, toPx, 56, 900)).toEqual({ left: 125, width: 10, cutLeft: false, cutRight: false })
  })
  it('伸出图区的那一侧标成被裁(那一侧不画边线);整段在图区外为 null', () => {
    expect(selectedBandPx(0, 2, toPx, 100, 900)).toEqual({ left: 100, width: 25, cutLeft: true, cutRight: false })
    expect(selectedBandPx(2, 5, toPx, 56, 140)).toEqual({ left: 115, width: 25, cutLeft: false, cutRight: true })
    expect(selectedBandPx(0, 9, toPx, 120, 140)).toEqual({ left: 120, width: 20, cutLeft: true, cutRight: true })
    expect(selectedBandPx(0, 2, toPx, 200, 900)).toBeNull()
    expect(selectedBandPx(0, 2, () => NaN, 56, 900)).toBeNull()        // 图还没有 x 轴:换不出像素
  })
})

describe('markAnchor', () => {
  const clip = { left: 56, top: 400, right: 900, bottom: 700 }
  it('记号露在可见区里:左下角,连同记号的顶(翻到上边时用)', () => {
    expect(markAnchor({ left: 200, top: 500, right: 260, bottom: 514 }, clip)).toEqual({ x: 200, y: 514, yUp: 500 })
  })
  it('面板按这个锚点放:放得下在记号下方,放不下翻到记号上方,都不压住记号', () => {
    const a = markAnchor({ left: 200, top: 500, right: 260, bottom: 514 }, clip)
    expect(placePanel(a, { w: 300, h: 100 }, { w: 1000, h: 800 })).toEqual({ x: 208, y: 522 })
    expect(placePanel(a, { w: 300, h: 100 }, { w: 1000, h: 600 })).toEqual({ x: 208, y: 500 - PANEL_GAP - 100 })
    // 没给 yUp(点击处):翻到上边按点击处算
    expect(placePanel({ x: 200, y: 514 }, { w: 300, h: 100 }, { w: 1000, h: 600 })).toEqual({ x: 208, y: 514 - PANEL_GAP - 100 })
  })
  it('左端在图区外:贴住图区左边;整条在右边之外:贴住右边;上下滚出可见区:贴住上下边', () => {
    expect(markAnchor({ left: 10, top: 500, right: 260, bottom: 514 }, clip)).toEqual({ x: 56, y: 514, yUp: 500 })
    expect(markAnchor({ left: 950, top: 500, right: 990, bottom: 514 }, clip)).toEqual({ x: 900, y: 514, yUp: 500 })
    expect(markAnchor({ left: 200, top: 300, right: 260, bottom: 314 }, clip)).toEqual({ x: 200, y: 400, yUp: 400 })
    expect(markAnchor({ left: 200, top: 800, right: 260, bottom: 814 }, clip)).toEqual({ x: 200, y: 700, yUp: 700 })
  })
})

describe('noteHeight', () => {
  it('内容高加边框,到上限为止', () => {
    expect(noteHeight(19, 2)).toBe(21)
    expect(noteHeight(57, 2)).toBe(59)
    expect(noteHeight(1000, 2)).toBe(NOTE_MAX_H)
    expect(noteHeight(1000, 2, 80)).toBe(80)
  })
})
