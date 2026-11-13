// 按键走动的两组键(从 KlineChart 的 onKeyDown 抽出,判定与显示栏上的键名都只在这一处,换键只改这里):
// - 跨天:← / →,当前日竖线会动;
// - 同一天:↑ / ↓,竖线不动。
// 两组键正好是键盘上的两个方向;左侧列表切股票用 PageUp / PageDown。
// 带修饰键(Shift / Ctrl / Meta / Alt)的不接(留给浏览器、系统与别的快捷键),输入法组字中不接。

export type WalkKey = { kind: 'pos' | 'stack'; dir: -1 | 1 }

const KEYS: Record<string, WalkKey> = {
  ArrowLeft: { kind: 'pos', dir: -1 }, ArrowRight: { kind: 'pos', dir: 1 },
  ArrowUp: { kind: 'stack', dir: -1 }, ArrowDown: { kind: 'stack', dir: 1 },
}

/** 一次按键 → 怎么走;不是这两组键时为 null。 */
export function walkKeyOf(e: Pick<KeyboardEvent, 'key' | 'shiftKey' | 'ctrlKey' | 'metaKey' | 'altKey' | 'isComposing'>): WalkKey | null {
  if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return null
  return KEYS[e.key] ?? null
}

/** 显示栏上的键名(小键帽里的字) */
export const WALK_KEY_LABEL: Record<WalkKey['kind'], string> = { pos: '←/→', stack: '↑/↓' }

/**
 * compare 下对选中的那一个打开反馈面板的键:不带修饰键的 Enter(面板开着时 Enter 归面板,是保存,
 * 见 ./feedbackPanel.ts 的 panelKeyAction)。输入法组字中不接(Enter 是上屏);按住不放的自动重复不接
 * (否则第一下开面板、重复的下一下落到面板上就是保存)。
 */
export function isFeedbackOpenKey(e: Pick<KeyboardEvent, 'key' | 'shiftKey' | 'ctrlKey' | 'metaKey' | 'altKey' | 'isComposing' | 'keyCode' | 'repeat'>): boolean {
  if (e.repeat || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || e.keyCode === 229) return false
  return e.key === 'Enter'
}

/** 显示栏 feedback 按钮的样子:on 能打开、off 不能作答(灰)、open 面板开着;不给(app 模式)就没有这个按钮 */
export type WalkFeedbackState = 'on' | 'off' | 'open'
