// 反馈作答面板与 feedback 工具的纯函数:面板开着时按键归不归面板(含输入法组字)、面板默认落点与拖动时留在视口里、
// 拖选竖带的左右。
import { describe, it, expect } from 'vitest'
import {
  NOTE_MAX_H, PANEL_BAR_GAP, PANEL_GAP, clampToViewport, isComposingKey, noteHeight, panelKeyAction, placePanel,
  rangeBandPx, selectedBandPx, type PanelAnchor,
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

  it('按住 Enter 的自动重复:截下不做事(ignore),不保存;Shift+Enter 的重复照旧不截;Esc 的重复照关', () => {
    expect(panelKeyAction({ key: 'Enter', repeat: true })).toBe('ignore')
    expect(panelKeyAction({ key: 'Enter', repeat: false })).toBe('save')
    expect(panelKeyAction({ key: 'Enter', repeat: true, shiftKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Escape', repeat: true })).toBe('close')
    expect(panelKeyAction({ key: 'Enter', repeat: true, isComposing: true })).toBeNull()
    expect(panelKeyAction({ key: 'Enter', repeat: true, ctrlKey: true })).toBeNull()
    expect(panelKeyAction({ key: 'Enter', repeat: true }, true)).toBeNull()      // 焦点在面板外的输入框里
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
  // 图表区左右 200..1200,显示栏上沿 600;面板 300×200
  const SIZE = { w: 300, h: 200 }
  const a = (band: PanelAnchor['band'], extra: Partial<PanelAnchor> = {}): PanelAnchor =>
    ({ band, bottom: 600, left: 200, right: 1200, ...extra })
  const Y = 600 - PANEL_BAR_GAP - 200

  it('横向:靠在竖带右边,不压竖带;纵向:底边贴住显示栏上沿(留一点空)', () => {
    const p = placePanel(a({ left: 400, right: 420 }), SIZE)
    expect(p).toEqual({ x: 420 + PANEL_GAP, y: Y })
    expect(p.y + SIZE.h).toBe(600 - PANEL_BAR_GAP)
  })
  it('右边刚好放得下仍放右边;差一点就翻到竖带左边', () => {
    expect(placePanel(a({ left: 880, right: 892 }), SIZE)).toEqual({ x: 892 + PANEL_GAP, y: Y })      // 900 + 300 = 1200
    expect(placePanel(a({ left: 880, right: 893 }), SIZE)).toEqual({ x: 880 - PANEL_GAP - 300, y: Y })
  })
  it('左边也放不下(竖带太宽):贴住图表区右边,这时压住竖带的一部分', () => {
    expect(placePanel(a({ left: 300, right: 1000 }), SIZE)).toEqual({ x: 1200 - 300, y: Y })
    // 左边刚好放得下:翻到左边
    expect(placePanel(a({ left: 508, right: 1000 }), SIZE)).toEqual({ x: 200, y: Y })
  })
  it('竖带不在图窗里(null):放在左右范围的正中', () => {
    expect(placePanel(a(null), SIZE)).toEqual({ x: (200 + 1200 - 300) / 2, y: Y })
  })
  it('图表区比面板还窄:贴住左边界,不越出左边', () => {
    expect(placePanel(a(null, { left: 200, right: 400 }), SIZE)).toEqual({ x: 200, y: Y })
    expect(placePanel(a({ left: 250, right: 260 }, { left: 200, right: 400 }), SIZE)).toEqual({ x: 200, y: Y })
  })
  it('上边放不下(主图太矮):贴住视口上沿', () => {
    expect(placePanel(a(null, { bottom: 150 }), SIZE).y).toBe(0)
  })
  it('gap 可另给', () => {
    expect(placePanel(a({ left: 400, right: 420 }), SIZE, 20).x).toBe(440)
    expect(placePanel(a({ left: 880, right: 900 }), SIZE, 20).x).toBe(880 - 20 - 300)
  })
})

describe('clampToViewport', () => {
  const VP = { w: 1000, h: 800 }
  const SIZE = { w: 300, h: 200 }
  it('整块在视口里:原样', () => {
    expect(clampToViewport({ x: 100, y: 50 }, SIZE, VP)).toEqual({ x: 100, y: 50 })
    expect(clampToViewport({ x: 700, y: 600 }, SIZE, VP)).toEqual({ x: 700, y: 600 })
  })
  it('越出哪边就贴住哪边', () => {
    expect(clampToViewport({ x: -40, y: -10 }, SIZE, VP)).toEqual({ x: 0, y: 0 })
    expect(clampToViewport({ x: 900, y: 750 }, SIZE, VP)).toEqual({ x: 700, y: 600 })
  })
  it('面板比视口还大:贴住左上', () => {
    expect(clampToViewport({ x: 300, y: 300 }, { w: 2000, h: 2000 }, VP)).toEqual({ x: 0, y: 0 })
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

describe('noteHeight', () => {
  it('内容高加边框,到上限为止', () => {
    expect(noteHeight(19, 2)).toBe(21)
    expect(noteHeight(57, 2)).toBe(59)
    expect(noteHeight(1000, 2)).toBe(NOTE_MAX_H)
    expect(noteHeight(1000, 2, 80)).toBe(80)
  })
})
