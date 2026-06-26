import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ctrlState } from '../src/render/ctrlState'

function emitKey(type: 'keydown' | 'keyup', key: string) {
  document.dispatchEvent(new KeyboardEvent(type, { key }))
}

describe('ctrlState', () => {
  beforeEach(() => {
    // 复位状态（如果模块有泄漏）
    if (ctrlState.isPressed()) {
      emitKey('keyup', 'Control')
    }
    ctrlState.setMouseY(0)
  })

  it('keydown(Control) sets isPressed=true and notifies subscribers', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    expect(ctrlState.isPressed()).toBe(true)
    expect(cb).toHaveBeenCalledWith(true)
    unsub()
  })

  it('keyup(Control) resets isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    emitKey('keyup', 'Control')
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    unsub()
  })

  it('repeated keydown does not double-notify', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    emitKey('keydown', 'Control')
    emitKey('keydown', 'Control')
    expect(cb).toHaveBeenCalledTimes(1)
    unsub()
  })

  it('window blur forces isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    window.dispatchEvent(new Event('blur'))
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    unsub()
  })

  it('visibilitychange(hidden) forces isPressed=false', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    emitKey('keydown', 'Control')
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(ctrlState.isPressed()).toBe(false)
    expect(cb).toHaveBeenLastCalledWith(false)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    unsub()
  })

  it('mouseY pull-mode: setMouseY then mouseY returns same value', () => {
    ctrlState.setMouseY(123.45)
    expect(ctrlState.mouseY()).toBe(123.45)
  })

  it('unsubscribe stops further notifications', () => {
    const cb = vi.fn()
    const unsub = ctrlState.subscribe(cb)
    unsub()
    emitKey('keydown', 'Control')
    expect(cb).not.toHaveBeenCalled()
  })
})
