// KlineChart 里 brush toggle 快捷键判定(从 onKeyDown 抽出以便单测)。
// 语义:严格 Shift+,(物理 Shift+逗号键;美式键盘下 KeyboardEvent.key 为 '<',
//      因 Shift 把逗号变成小于号。不接受裸 ,、不接受与 Ctrl/Meta/Alt 组合)。
export function isBrushToggleKey(e: KeyboardEvent): boolean {
  return e.key === '<' && e.shiftKey === true
      && !e.ctrlKey && !e.metaKey && !e.altKey
}
