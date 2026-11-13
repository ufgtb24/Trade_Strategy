// 按键走动的两组键:判定与显示栏键名同一处(src/components/walkKey.ts);compare 下对选中的那一个打开反馈面板的 Enter。
import { describe, it, expect } from 'vitest'
import { isFeedbackOpenKey, walkKeyOf, WALK_KEY_LABEL } from '../src/components/walkKey'

const key = (k: string, o: Partial<KeyboardEvent> = {}) =>
  ({ key: k, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, isComposing: false, ...o }) as KeyboardEvent

describe('walkKeyOf', () => {
  it('← / → 跨天', () => {
    expect(walkKeyOf(key('ArrowLeft'))).toEqual({ kind: 'pos', dir: -1 })
    expect(walkKeyOf(key('ArrowRight'))).toEqual({ kind: 'pos', dir: 1 })
  })
  it('↑ / ↓ 留在同一天:↑ 往前、↓ 往后', () => {
    expect(walkKeyOf(key('ArrowUp'))).toEqual({ kind: 'stack', dir: -1 })
    expect(walkKeyOf(key('ArrowDown'))).toEqual({ kind: 'stack', dir: 1 })
  })
  it('带任何修饰键(Shift / Ctrl / Meta / Alt)都不接,输入法组字中不接', () => {
    for (const k of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']) {
      expect(walkKeyOf(key(k, { shiftKey: true }))).toBeNull()
      expect(walkKeyOf(key(k, { ctrlKey: true }))).toBeNull()
      expect(walkKeyOf(key(k, { metaKey: true }))).toBeNull()
      expect(walkKeyOf(key(k, { altKey: true }))).toBeNull()
      expect(walkKeyOf(key(k, { isComposing: true }))).toBeNull()
    }
  })
  it('别的键不接(切股票的 PageUp / PageDown 归左侧列表)', () => {
    expect(walkKeyOf(key('PageUp'))).toBeNull()
    expect(walkKeyOf(key('PageDown'))).toBeNull()
    expect(walkKeyOf(key('Escape'))).toBeNull()
  })
  it('显示栏的键名', () => {
    expect(WALK_KEY_LABEL).toEqual({ pos: '←/→', stack: '↑/↓' })
  })
})

describe('isFeedbackOpenKey', () => {
  it('不带修饰键的 Enter', () => {
    expect(isFeedbackOpenKey(key('Enter'))).toBe(true)
  })
  it('带 Shift / Ctrl / Meta / Alt 的不算', () => {
    for (const m of ['shiftKey', 'ctrlKey', 'metaKey', 'altKey'] as const) {
      expect(isFeedbackOpenKey(key('Enter', { [m]: true }))).toBe(false)
    }
  })
  it('按住不放的自动重复(repeat)不算:按住 Enter 只在第一下打开', () => {
    expect(isFeedbackOpenKey(key('Enter', { repeat: true }))).toBe(false)
    expect(isFeedbackOpenKey(key('Enter', { repeat: false }))).toBe(true)
  })
  it('输入法组字中不算(Enter 是上屏):isComposing,或 keyCode 229', () => {
    expect(isFeedbackOpenKey(key('Enter', { isComposing: true }))).toBe(false)
    expect(isFeedbackOpenKey(key('Enter', { keyCode: 229 }))).toBe(false)
    expect(isFeedbackOpenKey(key('Enter', { keyCode: 13 }))).toBe(true)
  })
  it('别的键不算', () => {
    for (const k of ['Escape', ' ', 'ArrowLeft', 'f']) expect(isFeedbackOpenKey(key(k))).toBe(false)
  })
})
