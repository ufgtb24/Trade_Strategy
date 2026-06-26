/**
 * 全局 Ctrl 键状态 + 最近鼠标 y 坐标的单例。
 *
 * - isPressed (订阅模式): Ctrl 按下/释放，订阅者收到通知；
 *   window blur / document visibilitychange(hidden) 时强制复位（防"按住切窗"卡死）。
 * - mouseY (拉模式): chart 实例 zr.on('mousemove') 中 setMouseY，
 *   tooltip formatter 现场 mouseY() 读取；不走 reactive。
 *
 * init() 幂等;首次 subscribe 时挂全局监听。
 */

let isPressed = false
let mouseY = 0
const subs = new Set<(p: boolean) => void>()
let initialized = false

function notify(): void {
  subs.forEach(fn => fn(isPressed))
}

function init(): void {
  if (initialized) return
  initialized = true
  document.addEventListener('keydown', e => {
    if (e.key === 'Control' && !isPressed) {
      isPressed = true
      notify()
    }
  })
  document.addEventListener('keyup', e => {
    if (e.key === 'Control' && isPressed) {
      isPressed = false
      notify()
    }
  })
  window.addEventListener('blur', () => {
    if (isPressed) {
      isPressed = false
      notify()
    }
  })
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && isPressed) {
      isPressed = false
      notify()
    }
  })
}

export const ctrlState = {
  isPressed: () => isPressed,
  mouseY: () => mouseY,
  setMouseY: (y: number) => { mouseY = y },
  subscribe: (fn: (p: boolean) => void) => {
    init()
    subs.add(fn)
    return () => { subs.delete(fn) }
  },
}
