/**
 * 全局快捷键的焦点守卫:找图清单的 PageUp / PageDown、左右栏的 Shift+L / Shift+R 共用。
 *
 * 焦点在任何输入框(单行、多行)、下拉框、可编辑区里时不接(在 note 里打大写 L、R 是在写字);
 * 自绘的下拉(PatternPicker:顶栏 pattern、样本页的 pattern 一格)菜单开着时也算在下拉框里。
 */
const EDITABLE = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]'

export function focusBlocksKeys(): boolean {
  const ae = document.activeElement as HTMLElement | null
  if (ae && ae.closest(EDITABLE)) return true
  return document.querySelector('[aria-expanded="true"]') !== null
}
